import pandas as pd
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from .models import Inventory, InventoryHistory
from .schemas import InventoryCreate, InventoryUpdate, HistoryCreate

class InventoryService:

    @staticmethod
    async def create_item(db: Session, item_data: InventoryCreate):
        """새로운 재고 품목 생성 + 등록 이력"""
        # 품목번호 자동 생성 (INV-YYYYMMDD-XXXXXXXX)
        from datetime import datetime as _dt
        now = _dt.now()
        prefix = f"INV-{now.strftime('%Y%m%d')}-"
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
        db.flush()
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
        db.flush()
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
        db.flush()
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
        db.flush()
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
        db.flush()
        return item

    @staticmethod
    async def decrease_weight(db: Session, item_id: str, amount: float):
        """소모품 무게 감소 (수동 입력)"""
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return None

        item.current_weight = (item.current_weight or 0) - amount
        db.add(InventoryHistory(
            item_id=item_id,
            event_type="사용",
            item_name=item.name,
            measured_weight=item.current_weight,
            usage_amount=amount,
            note=f"무게 감소: {amount:.0f}g",
        ))
        db.flush()
        return item 

    @staticmethod
    async def upsert_stock(db: Session, item_id: str, amount: float):
        """소모품 무게 추가 (수동 입력)"""
        item = db.query(Inventory).filter(Inventory.id == item_id).first()
        if not item:
            return None

        item.current_weight = (item.current_weight or 0) + amount
        db.add(InventoryHistory(
            item_id=item_id,
            event_type="사용",
            item_name=item.name,
            measured_weight=item.current_weight,
            usage_amount=amount,
            note=f"무게 증가: {amount:.0f}g",
        ))
        db.flush()
        return item

    @staticmethod
    def export_to_csv_bytes(db: Session) -> bytes:
        """재고 전체(활성+완료)를 CSV bytes로 반환"""
        import io
        import pandas as pd
        from sqlalchemy import desc

        rows = db.query(Inventory).order_by(desc(Inventory.created_at)).all()
        data = []
        for r in rows:
            data.append({
                '품목ID':      r.id,
                '품목번호':    r.item_no or '',
                '분야':        r.domain,
                '분류':        r.category,
                '품목명':      r.name,
                '수량':        r.quantity or '',
                '전체무게(g)': r.start_weight or '',
                '잔량(g)':     r.current_weight or '',
                '구매가격(원)': r.price or '',
                '메모':        r.memo or '',
                '등록일':      r.started_at.strftime('%Y-%m-%d') if r.started_at else '',
            })
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    def import_csv_from_bytes(content: bytes, db: Session) -> dict:
        """CSV bytes로 재고 품목 일괄 등록 (품목번호는 자동 생성)"""
        import pandas as pd
        from core.utils import decode_csv_bytes

        COL_MAP = {
            '분야': 'domain', '분류': 'category', '품목명': 'name',
            '수량': 'quantity', '전체무게(g)': 'start_weight',
            '잔량(g)': 'current_weight', '구매가격(원)': 'price', '메모': 'memo',
        }

        try:
            df = decode_csv_bytes(content)
            df = df.rename(columns=COL_MAP)

            required = {'domain', 'category', 'name'}
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"필수 컬럼 누락: {missing}")

            # 숫자 컬럼 변환
            for col in ['quantity', 'start_weight', 'current_weight', 'price']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            from datetime import datetime as _dt
            now = _dt.now()
            prefix = f"INV-{now.strftime('%Y%m%d')}-"
            last = db.query(Inventory.item_no).filter(
                Inventory.item_no.like('INV-%')
            ).order_by(Inventory.item_no.desc()).first()
            seq = 1
            if last and last[0]:
                try:
                    seq = int(last[0].split('-')[-1]) + 1
                except (IndexError, ValueError):
                    seq = 1

            new_count = 0
            for _, row in df.iterrows():
                if not row.get('domain') or not row.get('category') or not row.get('name'):
                    continue
                item = Inventory(
                    domain=str(row['domain']).strip(),
                    category=str(row['category']).strip(),
                    name=str(row['name']).strip(),
                    quantity=int(row['quantity']) if pd.notna(row.get('quantity')) else None,
                    start_weight=float(row['start_weight']) if pd.notna(row.get('start_weight')) else None,
                    current_weight=float(row['current_weight']) if pd.notna(row.get('current_weight')) else None,
                    price=float(row['price']) if pd.notna(row.get('price')) else None,
                    memo=str(row['memo']).strip() if pd.notna(row.get('memo')) else None,
                )
                item.item_no = f"{prefix}{seq:08d}"
                seq += 1
                if item.current_weight is None and item.start_weight is not None and item.category == '소모품':
                    item.current_weight = item.start_weight
                db.add(item)
                db.flush()
                note = f"CSV 일괄 등록 ({item.start_weight:.0f}g)" if item.start_weight else "CSV 일괄 등록"
                db.add(InventoryHistory(
                    item_id=item.id, event_type="등록",
                    item_name=item.name, measured_weight=item.start_weight,
                    usage_amount=0.0, note=note,
                ))
                new_count += 1

            db.flush()
            return {"status": "success", "message": f"CSV 등록 완료! (신규: {new_count}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def export_history_to_csv_bytes(db: Session, item_id: str = None) -> bytes:
        import io
        import pandas as pd
        from sqlalchemy import desc
        
        query = db.query(InventoryHistory).options(
            __import__('sqlalchemy.orm', fromlist=['joinedload']).joinedload(InventoryHistory.item)
        ).order_by(desc(InventoryHistory.action_date))
        
        if item_id:
            query = query.filter(InventoryHistory.item_id == item_id)
            
        rows = query.all()
        data = []
        for r in rows:
            data.append({
                '이력ID': r.id,
                '품목ID': r.item_id or '',
                '품목명': r.item_name or (r.item.name if r.item else ''),
                '발생일시': r.action_date.strftime('%Y-%m-%d %H:%M:%S') if r.action_date else '',
                '이벤트유형': r.event_type,
                '측정무게(g)': r.measured_weight if r.measured_weight is not None else '',
                '사용량(g)': r.usage_amount if r.usage_amount is not None else '',
                '메모': r.note or ''
            })
            
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    def import_history_from_csv_bytes(content: bytes, db: Session) -> dict:
        import pandas as pd
        from sqlalchemy.sql import func
        from datetime import datetime
        from core.utils import decode_csv_bytes
        
        COL_MAP = {
            '이력ID': 'id', '품목ID': 'item_id', '품목명': 'item_name', 
            '발생일시': 'action_date', '이벤트유형': 'event_type', 
            '측정무게(g)': 'measured_weight', '사용량(g)': 'usage_amount', '메모': 'note'
        }
        
        try:
            df = decode_csv_bytes(content)
            df = df.rename(columns=COL_MAP)
            
            required = {'item_id', 'event_type', 'note'}
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"필수 컬럼 누락: {missing}")

            for col in ['measured_weight', 'usage_amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            new_count = 0
            for _, row in df.iterrows():
                item_id = str(row.get('item_id', '')).strip()
                event_type = str(row.get('event_type', '')).strip()
                note = str(row.get('note', '')).strip()

                if not item_id or item_id == 'nan' or not event_type or not note:
                    continue

                measured = float(row['measured_weight']) if pd.notna(row.get('measured_weight')) else None
                usage = float(row['usage_amount']) if pd.notna(row.get('usage_amount')) else None

                action_date = func.now()
                if pd.notna(row.get('action_date')):
                    try:
                        action_date = datetime.strptime(str(row['action_date']), '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass

                history = InventoryHistory(
                    item_id=item_id,
                    event_type=event_type,
                    item_name=str(row.get('item_name', '')).strip() if pd.notna(row.get('item_name')) else None,
                    action_date=action_date,
                    measured_weight=measured,
                    usage_amount=usage,
                    note=note
                )

                # 만약 제공된 id가 있다면 유지 (업데이트가 아니라 무조건 insert 처리이나, PK 충돌 방지 차원)
                row_id = str(row.get('id', '')).strip()
                if row_id and row_id != 'nan':
                    # 이미 존재하는지 확인
                    exists = db.query(InventoryHistory).filter(InventoryHistory.id == row_id).first()
                    if exists:
                        continue # 이미 있는 이력은 skip
                    history.id = row_id
                    
                db.add(history)
                new_count += 1
                
            db.flush()
            return {"status": "success", "message": f"이력 CSV 등록 완료! (신규: {new_count}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def restore_from_csv_bytes(content: bytes, db: Session) -> dict:
        """
        [Restore] 재고 전체 복원.
        기존 이력 → 기존 품목 순으로 삭제 후, 원래 ID 그대로 재삽입.
        품목ID 컬럼이 없으면 일반 import 로 폴백.
        """
        import pandas as pd
        from core.utils import decode_csv_bytes

        COL_MAP = {
            '품목ID': 'id', '품목번호': 'item_no',
            '분야': 'domain', '분류': 'category', '품목명': 'name',
            '수량': 'quantity', '전체무게(g)': 'start_weight',
            '잔량(g)': 'current_weight', '구매가격(원)': 'price', '메모': 'memo',
        }
        try:
            df = decode_csv_bytes(content)
            df = df.rename(columns=COL_MAP)

            required = {'domain', 'category', 'name'}
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"필수 컬럼 누락: {missing}")

            for col in ['quantity', 'start_weight', 'current_weight', 'price']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            import uuid as _uuid
            has_id = 'id' in df.columns
            records = []
            for _, row in df.iterrows():
                if not row.get('domain') or not row.get('name'):
                    continue
                row_id = str(row['id']).strip() if has_id and pd.notna(row.get('id')) else str(_uuid.uuid4())
                records.append({
                    'id': row_id,
                    'item_no': str(row['item_no']).strip() if pd.notna(row.get('item_no')) and str(row['item_no']).strip() else None,
                    'domain': str(row['domain']).strip(),
                    'category': str(row['category']).strip(),
                    'name': str(row['name']).strip(),
                    'quantity': int(row['quantity']) if pd.notna(row.get('quantity')) else None,
                    'start_weight': float(row['start_weight']) if pd.notna(row.get('start_weight')) else None,
                    'current_weight': float(row['current_weight']) if pd.notna(row.get('current_weight')) else None,
                    'price': float(row['price']) if pd.notna(row.get('price')) else None,
                    'memo': str(row['memo']).strip() if pd.notna(row.get('memo')) else None,
                })

            from database import engine as sqla_engine
            with sqla_engine.begin() as conn:
                InventoryHistory.__table__.drop(conn, checkfirst=True)
                Inventory.__table__.drop(conn, checkfirst=True)
                Inventory.__table__.create(conn, checkfirst=True)
                InventoryHistory.__table__.create(conn, checkfirst=True)
                if records:
                    conn.execute(Inventory.__table__.insert(), records)
            return {"status": "success", "message": f"재고 복원 완료! ({len(records)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def restore_history_from_csv_bytes(content: bytes, db: Session) -> dict:
        """
        [Restore] 이력 전체 복원.
        기존 이력 전체 삭제 후 원래 ID·품목ID 그대로 재삽입.
        """
        import pandas as pd
        from sqlalchemy.sql import func as sqlfunc
        from datetime import datetime
        from core.utils import decode_csv_bytes

        COL_MAP = {
            '이력ID': 'id', '품목ID': 'item_id', '품목명': 'item_name',
            '발생일시': 'action_date', '이벤트유형': 'event_type',
            '측정무게(g)': 'measured_weight', '사용량(g)': 'usage_amount', '메모': 'note',
        }
        try:
            df = decode_csv_bytes(content)
            df = df.rename(columns=COL_MAP)

            required = {'item_id', 'event_type', 'note'}
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"필수 컬럼 누락: {missing}")

            for col in ['measured_weight', 'usage_amount']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            import uuid as _uuid
            records = []
            for _, row in df.iterrows():
                item_id = str(row.get('item_id', '')).strip()
                event_type = str(row.get('event_type', '')).strip()
                note = str(row.get('note', '')).strip()
                if not item_id or item_id == 'nan' or not event_type or not note:
                    continue

                action_date = None
                if pd.notna(row.get('action_date')):
                    try:
                        action_date = datetime.strptime(str(row['action_date']), '%Y-%m-%d %H:%M:%S')
                    except Exception:
                        pass

                row_id = str(row.get('id', '')).strip()
                records.append({
                    'id': row_id if row_id and row_id != 'nan' else str(_uuid.uuid4()),
                    'item_id': item_id,
                    'event_type': event_type,
                    'item_name': str(row.get('item_name', '')).strip() if pd.notna(row.get('item_name')) else None,
                    'action_date': action_date,
                    'measured_weight': float(row['measured_weight']) if pd.notna(row.get('measured_weight')) else None,
                    'usage_amount': float(row['usage_amount']) if pd.notna(row.get('usage_amount')) else None,
                    'note': note,
                })

            from database import engine as sqla_engine
            with sqla_engine.begin() as conn:
                InventoryHistory.__table__.drop(conn, checkfirst=True)
                InventoryHistory.__table__.create(conn, checkfirst=True)
                if records:
                    conn.execute(InventoryHistory.__table__.insert(), records)
            return {"status": "success", "message": f"이력 복원 완료! ({len(records)}건)"}
        except Exception as e:
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")