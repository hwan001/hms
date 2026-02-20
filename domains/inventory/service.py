from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from .models import Inventory, InventoryHistory
from .schemas import InventoryCreate, InventoryUpdate, HistoryCreate

class InventoryService:

    @staticmethod
    async def create_item(db: Session, item_data: InventoryCreate):
        """새로운 재고 품목 생성 + 등록 이력"""
        # 품목번호 자동 생성 (INV-YYYY-MM-XXXXXXXX)
        from datetime import datetime as _dt
        now = _dt.now()
        prefix = f"INV-{now.year}-{now.month:02d}-"
        # 전체 번호 중 max sequence 추출 (연/월 무관하게 글로벌 시퀀스 유지)
        last = db.query(Inventory.item_no).filter(
            Inventory.item_no.like('INV-%')
        ).order_by(Inventory.item_no.desc()).first()
        if last and last[0]:
            try:
                seq = int(last[0].split('-')[-1]) + 1
            except (IndexError, ValueError):
                seq = 1
        else:
            seq = 1

        db_item = Inventory(**item_data.model_dump())
        db_item.item_no = f"{prefix}{seq:08d}"
        if db_item.category == "소모품" and db_item.start_weight is not None:
            db_item.current_weight = db_item.start_weight
        db.add(db_item)
        db.flush()  # id 확보

        note_val = f"최초 등록 ({db_item.start_weight:.0f}g)" if db_item.start_weight else "최초 등록"
        db.add(InventoryHistory(
            item_id=db_item.id,
            event_type="등록",
            item_name=db_item.name,
            measured_weight=db_item.start_weight,
            usage_amount=0.0,
            note=note_val,
        ))
        db.commit()
        db.refresh(db_item)
        return db_item

    @staticmethod
    async def get_items(db: Session, domain: str = None, category: str = None):
        """품목 리스트 조회 (완료 처리된 품목 제외)"""
        query = db.query(Inventory).filter(Inventory.ended_at.is_(None))
        if domain:
            query = query.filter(Inventory.domain == domain)
        if category:
            query = query.filter(Inventory.category == category)
        return query.order_by(desc(Inventory.created_at)).all()

    @staticmethod
    async def get_items_all(db: Session):
        """완료 품목 포함 전체 품목 조회 (가격 계산용)"""
        return db.query(Inventory).order_by(desc(Inventory.created_at)).all()

    @staticmethod
    async def get_item_detail(db: Session, item_id: str):
        """특정 품목 상세 조회"""
        return db.query(Inventory).filter(Inventory.id == item_id).first()

    @staticmethod
    async def update_item(db: Session, item_id: str, update_data: InventoryUpdate):
        """품목 정보 수정 + 수정 이력"""
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return None

        changes = []
        data = update_data.model_dump(exclude_none=True)
        for field, new_val in data.items():
            old_val = getattr(item, field, None)
            if old_val != new_val:
                label_map = {
                    'name': '이름', 'memo': '메모',
                    'current_weight': '잔량(g)', 'ended_at': '종료일'
                }
                label = label_map.get(field, field)
                changes.append(f"{label}: {old_val} → {new_val}")
            setattr(item, field, new_val)

        note_val = "수정: " + ", ".join(changes) if changes else "수정 (변경 없음)"
        db.add(InventoryHistory(
            item_id=item_id,
            event_type="수정",
            item_name=item.name,
            measured_weight=item.current_weight,
            usage_amount=0.0,
            note=note_val,
        ))
        db.commit()
        db.refresh(item)
        return item

    @staticmethod
    async def delete_item(db: Session, item_id: str):
        """품목 삭제 + 삭제 이력. raw SQL로 삭제해 ORM 관계 추적 우회"""
        from sqlalchemy import text

        # ORM으로 품목 정보만 조회 (관계는 로드하지 않음)
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return False

        item_name = item.name
        item_domain = item.domain
        item_category = item.category
        item_cw = item.current_weight

        # 기존 이력의 item_name 백필 (raw SQL)
        db.execute(
            text("UPDATE inventory_history SET item_name = :name WHERE item_id = :iid AND (item_name IS NULL OR item_name = '')"),
            {"name": item_name, "iid": item_id}
        )

        # 삭제 이력 기록 (삭제 전, item_id 실제 값)
        db.add(InventoryHistory(
            item_id=item_id,
            event_type="삭제",
            item_name=item_name,
            measured_weight=item_cw,
            usage_amount=0.0,
            note=f"품목 삭제 ({item_domain} / {item_category})",
        ))
        db.flush()

        # raw SQL DELETE → ORM 관계 추적 우회 (SET NULL 방지)
        db.execute(text("DELETE FROM inventory WHERE id = :id"), {"id": item_id})
        db.commit()
        return True

    @staticmethod
    async def get_history(
        db: Session,
        item_id: str = None,
        start_date=None,
        end_date=None,
        search: str = None,
        event_types: list = None,
    ):
        """전체 사용 이력 조회 (품목명 join 포함, 필터 지원)"""
        query = db.query(InventoryHistory).options(joinedload(InventoryHistory.item))
        if item_id:
            query = query.filter(InventoryHistory.item_id == item_id)
        if start_date:
            query = query.filter(InventoryHistory.action_date >= start_date)
        if end_date:
            query = query.filter(InventoryHistory.action_date <= end_date)
        if search:
            query = query.filter(InventoryHistory.note.ilike(f"%{search}%"))
        if event_types:
            query = query.filter(InventoryHistory.event_type.in_(event_types))
        return query.order_by(desc(InventoryHistory.action_date)).all()

    @staticmethod
    async def add_usage_history(db: Session, item_id: str, history_data: HistoryCreate):
        """사용 이력 기록 및 소모품 무게 업데이트"""
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return None

        usage = 0.0
        if item.category == "소모품" and history_data.measured_weight is not None:
            prev_weight = item.current_weight if item.current_weight is not None else item.start_weight
            usage = (prev_weight or 0) - history_data.measured_weight
            item.current_weight = history_data.measured_weight

        new_history = InventoryHistory(
            item_id=item_id,
            event_type="사용",
            item_name=item.name,
            measured_weight=history_data.measured_weight,
            usage_amount=usage,
            note=history_data.note,
        )
        db.add(new_history)
        db.commit()
        db.refresh(new_history)
        return new_history
    @staticmethod
    async def finish_item(db: Session, item_id: str):
        """품목 완료 처리: 남은 무게를 전부 사용으로 기록 후 종료"""
        from datetime import datetime, timezone
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return None

        remaining = item.current_weight or 0.0
        item.current_weight = 0.0
        item.ended_at = datetime.now(timezone.utc)

        db.add(InventoryHistory(
            item_id=item_id,
            event_type="완료",
            item_name=item.name,
            measured_weight=0.0,
            usage_amount=remaining,
            note=f"완료 처리 (잔량 {remaining:.0f}g 소진)",
        ))
        db.commit()
        return item
