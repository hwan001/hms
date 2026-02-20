import io
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import text, func, desc
from fastapi import HTTPException
from common.config import SPENDING_CSV_MAPPING, NUMERIC_COLUMNS
from .models import SpendingHistory

class SpendingService:
    @staticmethod
    def to_clean_float(val):
        """금액 문자열 정제 함수"""
        if pd.isna(val) or str(val).strip() == '':
            return 0.0
        try:
            return float(str(val).replace(',', '').strip())
        except ValueError:
            return 0.0

    @staticmethod
    async def process_csv_upload(file, db: Session):
        """ORM 기반 CSV 업로드 및 중복 방지 로직"""
        try:
            content = await file.read()
            df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")), dtype=str)
            
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=SPENDING_CSV_MAPPING)
            
            model_cols = {c.key for c in SpendingHistory.__table__.columns}
            valid_cols = [c for c in SPENDING_CSV_MAPPING.values() if c in df.columns and c in model_cols]
            df = df[valid_cols]

            for col in NUMERIC_COLUMNS:
                if col in df.columns:
                    df[col] = df[col].apply(SpendingService.to_clean_float)

            # 카테고리 앞뒤 공백 제거
            if 'category' in df.columns:
                df['category'] = df['category'].str.strip()

            # 중복 체크를 위해 기존 데이터 로드 (ORM 방식)
            existing_data = db.query(
                SpendingHistory.date, 
                SpendingHistory.content, 
                SpendingHistory.outcome, 
                SpendingHistory.income
            ).all()
            
            existing_set = {
                (str(r.date), str(r.content), int(r.outcome or 0), int(r.income or 0)) 
                for r in existing_data
            }

            new_records = []
            duplicate_count = 0
            
            for _, row in df.iterrows():
                current_key = (
                    str(row.get('date', '')),
                    str(row.get('content', '')),
                    int(row.get('outcome', 0)),
                    int(row.get('income', 0))
                )
                
                if current_key not in existing_set:
                    row_dict = row.to_dict()
                    # 결측치(NaN) 처리
                    for k, v in row_dict.items():
                        if pd.isna(v): row_dict[k] = None
                    
                    new_records.append(SpendingHistory(**row_dict))
                    existing_set.add(current_key)
                else:
                    duplicate_count += 1

            if new_records:
                db.add_all(new_records)
                db.commit()
                msg = f"업로드 완료! (신규: {len(new_records)}건, 중복 제외: {duplicate_count}건)"
            else:
                msg = f"새로운 내역이 없습니다. (중복 제외: {duplicate_count}건)"
            
            return {"status": "success", "message": msg}

        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def import_csv_from_bytes(content: bytes, db: Session) -> dict:
        """UI 직접 호출용 CSV import (bytes 입력, 동기)"""
        try:
            df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")), dtype=str)
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=SPENDING_CSV_MAPPING)

            model_cols = {c.key for c in SpendingHistory.__table__.columns}
            valid_cols = [c for c in SPENDING_CSV_MAPPING.values() if c in df.columns and c in model_cols]
            df = df[valid_cols]

            for col in NUMERIC_COLUMNS:
                if col in df.columns:
                    df[col] = df[col].apply(SpendingService.to_clean_float)

            if 'category' in df.columns:
                df['category'] = df['category'].str.strip()

            existing_data = db.query(
                SpendingHistory.date,
                SpendingHistory.content,
                SpendingHistory.outcome,
                SpendingHistory.income
            ).all()
            existing_set = {
                (str(r.date), str(r.content), int(r.outcome or 0), int(r.income or 0))
                for r in existing_data
            }

            new_records = []
            duplicate_count = 0
            for _, row in df.iterrows():
                current_key = (
                    str(row.get('date', '')),
                    str(row.get('content', '')),
                    int(row.get('outcome', 0)),
                    int(row.get('income', 0))
                )
                if current_key not in existing_set:
                    row_dict = row.to_dict()
                    for k, v in row_dict.items():
                        if pd.isna(v): row_dict[k] = None
                    new_records.append(SpendingHistory(**row_dict))
                    existing_set.add(current_key)
                else:
                    duplicate_count += 1

            if new_records:
                db.add_all(new_records)
                db.commit()
                return {"status": "success", "message": f"업로드 완료! (신규: {len(new_records)}건, 중복 제외: {duplicate_count}건)"}
            else:
                return {"status": "success", "message": f"새로운 내역이 없습니다. (중복 제외: {duplicate_count}건)"}
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"CSV 처리 오류: {str(e)}")

    @staticmethod
    def export_to_csv_bytes(db: Session) -> bytes:
        """DB 전체 내역을 CSV bytes로 반환 (UI Export용)"""
        rows = db.query(SpendingHistory).order_by(desc(SpendingHistory.date)).all()
        # SPENDING_CSV_MAPPING을 역방향(영문→한글)으로 사용해 헤더 생성
        reverse_map = {v: k for k, v in SPENDING_CSV_MAPPING.items()}
        export_cols = [c for c in reverse_map if hasattr(SpendingHistory, c)]
        data = [
            {reverse_map[col]: getattr(r, col) for col in export_cols}
            for r in rows
        ]
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding='utf-8-sig')
        return buf.getvalue().encode('utf-8-sig')

    @staticmethod
    async def get_spending_list(db: Session, category=None, start_date=None, end_date=None, page=1, size=20, search=None):
        """ORM 기반 필터링 및 페이징 조회"""
        try:
            query = db.query(SpendingHistory)

            if category and category != '전체':
                query = query.filter(SpendingHistory.category == category)
            if start_date:
                query = query.filter(SpendingHistory.date >= start_date)
            if end_date:
                query = query.filter(SpendingHistory.date <= f"{end_date} 23:59:59")
            if search:
                query = query.filter(
                    (SpendingHistory.content.like(f"%{search}%")) | 
                    (SpendingHistory.memo.like(f"%{search}%"))
                )

            total_count = query.count()
            
            # 요약 통계 계산
            summary_res = db.query(
                func.sum(SpendingHistory.outcome).label("total_out"),
                func.sum(SpendingHistory.income).label("total_in")
            ).filter(query.whereclause).first()

            # 페이징 적용
            offset = (page - 1) * size if size > 0 else 0
            if size > 0:
                rows = query.order_by(desc(SpendingHistory.date)).offset(offset).limit(size).all()
            else:
                rows = query.order_by(desc(SpendingHistory.date)).all()
            
            total_pages = (total_count + size - 1) // size if size > 0 else 1

            return {
                "status": "success",
                "count": total_count,
                "summary": {
                    "total_withdrawal": float(summary_res.total_out or 0.0),
                    "total_deposit": float(summary_res.total_in or 0.0),
                    "net_amount": float((summary_res.total_in or 0.0) - (summary_res.total_out or 0.0))
                },
                "pagination": {
                    "total_count": total_count,
                    "page": page,
                    "size": size,
                    "total_pages": total_pages
                },
                "filters": {"category": category, "start_date": start_date, "end_date": end_date},
                "data": [dict(r.__dict__, **{"_sa_instance_state": None}) for r in rows]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"조회 처리 오류: {str(e)}")

    @staticmethod
    async def get_stats(db: Session):
        """ORM 기반 통계 분석"""
        try:
            # 1. 월별 지출 추이
            monthly_trend = db.query(
                func.strftime('%Y-%m', func.replace(SpendingHistory.date, '.', '-')).label('month'),
                func.sum(SpendingHistory.outcome).label('amount')
            ).filter(SpendingHistory.outcome > 0).group_by('month').order_by(desc('month')).limit(6).all()
            
            # 2. 카테고리별 비중
            category_dist = db.query(
                SpendingHistory.category,
                func.sum(SpendingHistory.outcome).label('val')
            ).filter(SpendingHistory.outcome > 0).group_by(SpendingHistory.category).order_by(desc('val')).all()

            # 3. 현재 잔액 (가장 최근 데이터)
            latest = db.query(SpendingHistory).order_by(desc(SpendingHistory.date), desc(SpendingHistory.id)).first()
            current_balance = latest.balance if latest else 0.0

            return {
                "status": "success",
                "current_balance": current_balance,
                "monthly_trend": [{"month": r.month, "amount": r.amount or 0} for r in reversed(monthly_trend)],
                "category_distribution": [{"name": r.category or "미분류", "value": r.val or 0} for r in category_dist]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"통계 분석 오류: {str(e)}")

    @staticmethod
    async def update_spending(db: Session, record_id: int, update_data: dict):
        """ORM 객체 수정을 통한 업데이트"""
        record = db.query(SpendingHistory).filter(SpendingHistory.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
            
        for key, value in update_data.items():
            # Pydantic 필드명(한글)과 DB 필드명(영문) 매핑 대응이 필요할 수 있음
            # 여기서는 전달된 dict 키가 이미 영문 컬럼명이라고 가정합니다.
            if hasattr(record, key):
                setattr(record, key, value)
            
        db.commit()
        return {"status": "success", "message": f"ID {record_id} 항목 수정 완료"}

    @staticmethod
    async def delete_spending(db: Session, record_id: int):
        """ORM 기반 삭제"""
        record = db.query(SpendingHistory).filter(SpendingHistory.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="삭제할 항목을 찾을 수 없습니다.")
        
        db.delete(record)
        db.commit()
        return {"status": "success", "message": f"ID {record_id} 항목 삭제 완료"}

    @staticmethod
    async def get_combined_burn_rate_analysis(db: Session, categories: list, total_budget: float):
        """통합 소비 생존 시뮬레이션 로직"""
        try:
            if not categories:
                return {"status": "no_data", "reason": "선택된 카테고리가 없습니다."}

            rows = db.query(SpendingHistory.date, SpendingHistory.outcome)\
                     .filter(SpendingHistory.category.in_(categories))\
                     .filter(SpendingHistory.outcome > 0).all()
            
            if not rows:
                return {"status": "no_data", "reason": "해당 카테고리의 지출 내역이 없습니다."}

            parsed_data = []
            for r in rows:
                try:
                    d_str = r.date.replace('.', '-')
                    parsed_data.append({'date': pd.to_datetime(d_str), 'outcome': float(r.outcome)})
                except: continue

            df = pd.DataFrame(parsed_data)
            start_date = df['date'].min()
            end_date = df['date'].max()
            actual_days = max(1, (end_date - start_date).days + 1)
            
            category_total_spent = df['outcome'].sum()
            combined_avg_daily = category_total_spent / actual_days

            if combined_avg_daily > 0:
                days_left = int(total_budget / combined_avg_daily)
            else:
                days_left = "∞"

            return {
                "status": "success",
                "combined_avg_daily": round(combined_avg_daily, 0),
                "total_budget": total_budget,
                "days_left": days_left,
                "is_over_budget": False,
                "progress": 0
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}