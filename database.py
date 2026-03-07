from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from common.config import DATABASE_URL

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    # 모든 도메인 모델 import → Base에 등록
    import domains.inventory.models  # noqa
    import domains.cooking.models    # noqa
    import domains.finance.models    # noqa
    Base.metadata.create_all(bind=engine)
    # 기존 DB에 새 컬럼이 없을 경우 자동 추가 + 기존 이력 item_no 백필
    from sqlalchemy import text
    with engine.connect() as conn:
        for tbl_col in [
            ("inventory",         "image_url VARCHAR"),
            ("inventory_history", "item_no VARCHAR"),
        ]:
            try:
                conn.execute(text(f"ALTER TABLE {tbl_col[0]} ADD COLUMN {tbl_col[1]}"))
                conn.commit()
            except Exception:
                pass  # 이미 존재하면 무시
        # item_no가 NULL인 이력에 대해 inventory 테이블에서 item_no 백필
        try:
            conn.execute(text("""
                UPDATE inventory_history
                SET item_no = (SELECT item_no FROM inventory WHERE inventory.id = inventory_history.item_id)
                WHERE item_no IS NULL AND item_id IS NOT NULL
            """))
            conn.commit()
        except Exception:
            pass
        # Finance 스키마 마이그레이션:
        # simulation_sessions 가 구버전(portfolio_id 컬럼 없음)이면 finance 테이블 전체 재생성
        try:
            cols = [r[1] for r in conn.execute(text("PRAGMA table_info(simulation_sessions)")).fetchall()]
            if cols and "portfolio_id" not in cols:
                # 구버전 테이블 제거 → create_all 이 이미 실행됐으므로 DROP 후 재생성
                for t in ("simulation_trades", "simulation_sessions", "stock_holdings"):
                    conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
                conn.commit()
                # 신버전 테이블 생성
                import domains.finance.models  # noqa
                Base.metadata.create_all(bind=engine)
        except Exception:
            pass

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@contextmanager
def db_session():
    """UI에서 사용할 동기 컨텍스트 매니저"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
