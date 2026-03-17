"""
HMSEngine — 데이터 수정(write) 작업의 전역 추상화 레이어.

도메인별 핸들러를 Registry 방식으로 관리하며,
모든 write 요청은 engine.execute() 단일 진입점을 통해 처리됩니다.

Usage:
    from core.engine import engine

    # inventory 도메인 write
    await engine.execute("inventory", "create_item", db, item_data=item_schema)
    await engine.execute("inventory", "update_item", db, item_id="...", update_data=update_schema)
    await engine.execute("inventory", "delete_item", db, item_id="...")

    # spending 도메인 write
    await engine.execute("spending", "update_spending", db, record_id=1, update_data={...})
    await engine.execute("spending", "delete_spending", db, record_id=1)
    await engine.execute("spending", "import_csv", db, content=b"...")

    # blueprint 실행 (복합 작업)
    await engine.execute_blueprint(db, {
        "inputs":  [{"domain": "inventory", "id": "water_01", "amount": 100}],
        "outputs": [{"domain": "inventory", "id": "ice_01",   "amount": 10}],
    })
"""
from core.handlers.inventory import InventoryHandler
from core.handlers.spending import SpendingHandler
from core.handlers.cooking import CookingHandler
from core.handlers.finance import FinanceHandler


class HMSEngine:
    """
    여러 도메인에 대한 write 작업 추상화 엔진.
    도메인 핸들러를 registry에 등록해 단일 진입점(execute)으로 디스패치합니다.
    - service를 직접 호출하지 않고 엔진에 요청을보내 input/ output을 중앙처리
    - csv import/export 요청 처리
    - 추후 모든 요청에 대한 로깅
    """

    def __init__(self):
        self._registry: dict = {}
        # 기본 핸들러 등록
        self.register("inventory", InventoryHandler())
        self.register("spending", SpendingHandler())
        self.register("cooking", CookingHandler())
        self.register("finance", FinanceHandler())

    def register(self, domain: str, handler) -> None:
        """도메인 핸들러를 등록합니다. 동일 domain 재등록 시 덮어씁니다."""
        self._registry[domain] = handler

    async def execute(self, domain: str, action: str, db, **kwargs):
        """
        단일 진입점 — 지정된 도메인의 write 작업을 실행합니다.

        Args:
            domain: 도메인 이름 (예: "inventory", "spending")
            action: 수행할 작업 이름 (예: "create_item", "delete_spending")
            db:     SQLAlchemy Session
            **kwargs: 각 핸들러의 handle() 메서드에 전달될 인자들
        """
        handler = self._registry.get(domain)
        if handler is None:
            raise ValueError(
                f"[HMSEngine] Unknown domain: '{domain}'. "
                f"Registered domains: {list(self._registry.keys())}"
            )
        
        try:
            result = await handler.handle(action, db, **kwargs)
            # engine을 경유하는 모든 작업 종류 후 트랜잭션 커밋
            db.commit()
            return result
        except Exception as e:
            db.rollback()
            # HTTPException은 그대로 재전파 (FastAPI가 상태코드를 유지하도록)
            from fastapi import HTTPException
            if isinstance(e, HTTPException):
                raise
            raise RuntimeError(f"엔진 릴레이 중 오류 발생: {str(e)}") from e

    async def execute_blueprint(self, db, blueprint: dict):
        """
        복합 작업(blueprint) 실행.
        여러 도메인에 걸친 inputs/outputs 처리를 순차적으로 위임합니다.
        
        blueprint 부분 전체가 하나의 execute_blueprint 트랜잭션 안에서 수행되어야 하므로
        위의 execute 내부 커밋과 별개로 관리하거나, 중첩 트랜잭션을 염두에 두어야 합니다.
        """
        try:
            for inp in blueprint.get("inputs", []):
                # execute 직접 호출 시 매번 commit 되므로, 
                # blueprint의 원자성을 보장하려면 execute가 commit을 유보하도록 플래그처리를 하거나 
                # 내부적으로 handler.handle을 직접 호출해야 합니다.
                handler = self._registry.get(inp["domain"])
                if handler:
                    await handler.handle("decrease_weight", db, item_id=inp["id"], amount=inp["amount"])

            for outp in blueprint.get("outputs", []):
                handler = self._registry.get(outp["domain"])
                if handler:
                    await handler.handle("upsert_stock", db, item_id=outp["id"], amount=outp["amount"])

            db.commit()
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"블루프린트 실행 중 오류 발생: {str(e)}") from e
            
    async def import_csv(self, domain: str, db, content: bytes, **kwargs):
        """
        [Helper] CSV Import 중앙 라우팅 추가 경로. (트랜잭션 관리 동일 적용)
        """
        return await self.execute(domain, "import_csv", db, content=content, **kwargs)

    async def export_csv(self, domain: str, db, action: str = "export_csv", **kwargs):
        """
        [Helper] CSV Export 중앙 라우팅 경로.
        action 기본값은 "export_csv". 히스토리 등 별도 액션은 action 인자로 지정.
        """
        return await self.execute(domain, action, db, **kwargs)

    async def export_all(self, db) -> bytes:
        """
        모든 도메인 CSV를 단일 ZIP으로 묶어 반환.
        포함 파일: spending.csv, inventory.csv, inventory_history.csv, cooking.csv,
                   finance_portfolios.csv, finance_holdings.csv, finance_simulations.csv
        """
        import io
        import zipfile

        file_map = [
            ("spending",  "export_csv",             "spending.csv"),
            ("inventory", "export_csv",             "inventory.csv"),
            ("inventory", "export_history_csv",     "inventory_history.csv"),
            ("cooking",   "export_csv",             "cooking.csv"),
            ("finance",   "export_portfolios_csv",  "finance_portfolios.csv"),
            ("finance",   "export_holdings_csv",    "finance_holdings.csv"),
            ("finance",   "export_simulations_csv", "finance_simulations.csv"),
        ]

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for domain, action, filename in file_map:
                handler = self._registry.get(domain)
                if handler is None:
                    continue
                csv_bytes = await handler.handle(action, db)
                zf.writestr(filename, csv_bytes)
        return buf.getvalue()

    async def import_all(self, content: bytes) -> dict:
        """
        ZIP 파일을 받아 파일명에 따라 각 도메인 restore를 순차 실행.
        각 도메인마다 독립 세션을 사용해 세션 상태 오염을 방지한다.
        지원 파일명: spending.csv, inventory.csv, inventory_history.csv, cooking.csv
        """
        import io
        import zipfile
        from database import db_session

        # 처리 순서 고정 (inventory → history FK, finance portfolios → holdings/simulations FK)
        ORDER = [
            "spending.csv",
            "inventory.csv",
            "inventory_history.csv",
            "cooking.csv",
            "finance_portfolios.csv",
            "finance_holdings.csv",
            "finance_simulations.csv",
        ]
        domain_action_map = {
            "spending.csv":           ("spending", "restore_csv"),
            "inventory.csv":          ("inventory", "restore_csv"),
            "inventory_history.csv":  ("inventory", "restore_history_csv"),
            "cooking.csv":            ("cooking",  "restore_csv"),
            "finance_portfolios.csv": ("finance",  "restore_portfolios_csv"),
            "finance_holdings.csv":   ("finance",  "restore_holdings_csv"),
            "finance_simulations.csv":("finance",  "restore_simulations_csv"),
        }

        results = {}
        try:
            with zipfile.ZipFile(io.BytesIO(content), "r") as zf:
                # ZIP 내 파일명 → zip 경로 매핑
                zip_lookup = {}
                for zip_path in zf.namelist():
                    basename = zip_path.split("/")[-1]
                    if basename in domain_action_map:
                        zip_lookup[basename] = zip_path

                for basename in ORDER:
                    if basename not in zip_lookup:
                        continue
                    domain, action = domain_action_map[basename]
                    handler = self._registry.get(domain)
                    if handler is None:
                        continue
                    file_content = zf.read(zip_lookup[basename])
                    # 도메인별 독립 세션: 세션 간 identity map 오염 없음
                    with db_session() as fresh_db:
                        result = await handler.handle(action, fresh_db, content=file_content)
                        fresh_db.commit()
                    results[basename] = result

            return {"status": "success", "results": results}
        except Exception as e:
            raise RuntimeError(f"전체 Import 오류: {str(e)}") from e


    async def clear_all(self) -> dict:
        """
        모든 도메인 데이터 초기화.
        Base에 등록된 모든 테이블을 DROP 후 재생성합니다.
        """
        from database import engine as sqla_engine, Base
        import domains.inventory.models  # noqa
        import domains.cooking.models    # noqa
        import domains.spending.models   # noqa
        import domains.finance.models    # noqa

        with sqla_engine.begin() as conn:
            Base.metadata.drop_all(bind=conn)
            Base.metadata.create_all(bind=conn)
        return {"status": "success", "message": "전체 데이터 초기화 완료"}


# 전역 싱글톤 — import 후 바로 사용 가능
engine = HMSEngine()