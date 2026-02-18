import io
# import re
# import math
import pandas as pd
# import numpy as np
# from typing import Optional, List, Dict, Any
from sqlalchemy import text, bindparam
from fastapi import HTTPException
from common.config import CSV_MAPPING, NUMERIC_COLUMNS


class SpendingService:
    @staticmethod
    def to_clean_float(val):
        """금액 문자열 정제 함수"""
        if pd.isna(val) or str(val).strip() == '':
            return 0.0
        try:
            # 콤마 제거 및 공백 정리
            return float(str(val).replace(',', '').strip())
        except ValueError:
            return 0.0

    @staticmethod
    async def process_csv_upload(file, engine, table_name):
        """중앙 설정을 참조한 CSV 업로드 로직"""
        try:
            content = await file.read()
            # BOM(utf-8-sig) 대응 및 모든 데이터를 일단 문자열로 로드
            df = pd.read_csv(io.StringIO(content.decode("utf-8-sig")), dtype=str)
            
            # 1. 헤더 공백 정리 및 영문 매핑
            df.columns = [c.strip() for c in df.columns]
            df = df.rename(columns=CSV_MAPPING)
            
            # 2. 유효한 영문 컬럼만 추출
            valid_cols = [c for c in CSV_MAPPING.values() if c in df.columns]
            df = df[valid_cols]

            # 3. 숫자형 컬럼 변환
            for col in NUMERIC_COLUMNS:
                if col in df.columns:
                    df[col] = df[col].apply(SpendingService.to_clean_float)

            with engine.connect() as conn:
                # 4. 중복 체크를 위한 기존 데이터 로드 (영문 컬럼 사용)
                existing_query = text(f"SELECT date, content, outcome, income FROM {table_name}")
                existing_rows = conn.execute(existing_query).fetchall()
                
                existing_set = set()
                for r in existing_rows:
                    # 중복 판별용 튜플 생성 (날짜, 내용, 지출, 수입)
                    existing_set.add((str(r[0]), str(r[1]), int(r[2] or 0), int(r[3] or 0)))

                new_records = []
                duplicate_count = 0
                
                for _, row in df.iterrows():
                    # 현재 행의 중복 체크용 키
                    current_key = (
                        str(row.get('date', '')),
                        str(row.get('content', '')),
                        int(row.get('outcome', 0)),
                        int(row.get('income', 0))
                    )
                    
                    if current_key not in existing_set:
                        # 메모 필드 결측치 처리
                        row_dict = row.to_dict()
                        if 'memo' in row_dict and pd.isna(row_dict['memo']):
                            row_dict['memo'] = ""
                        
                        new_records.append(row_dict)
                        existing_set.add(current_key)
                    else:
                        duplicate_count += 1

                msg = ""
                if new_records:
                    new_df = pd.DataFrame(new_records)
                    new_df.to_sql(table_name, con=engine, if_exists='append', index=False)
                    msg = f"업로드 완료! (신규: {len(new_records)}건, 중복 제외: {duplicate_count}건)"
                else:
                    msg = f"새로운 내역이 없습니다. (중복 제외: {duplicate_count}건)"
                
                conn.commit()
            return {"status": "success", "message": msg}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"CSV 처리 오류: {str(e)}")

    @staticmethod
    async def get_spending_list(engine, table_name, start_date=None, end_date=None, category=None, search=None, limit=50, offset=0):
        """영문 컬럼명 기반 통합 검색 및 필터링"""
        try:
            base_where = " WHERE 1=1"
            params = {"limit": limit, "offset": offset}

            if category and category != '전체':
                base_where += " AND category = :category"
                params["category"] = category
            if start_date:
                base_where += " AND date >= :start_date"
                params["start_date"] = start_date
            if end_date:
                base_where += " AND date <= :end_date"
                params["end_date"] = f"{end_date} 23:59:59"
            if search:
                # 거래처(content)와 메모(memo) 동시 검색
                base_where += " AND (content LIKE :search OR memo LIKE :search)"
                params["search"] = f"%{search}%"

            with engine.connect() as conn:
                # 데이터 쿼리
                data_query = text(f"SELECT * FROM {table_name}{base_where} ORDER BY date DESC LIMIT :limit OFFSET :offset")
                rows = conn.execute(data_query, params).fetchall()
                data = [dict(row._mapping) for row in rows]

                # 요약 통계 쿼리 (REAL 타입이라 바로 SUM 가능)
                sum_query = text(f"SELECT SUM(outcome), SUM(income), COUNT(*) FROM {table_name}{base_where}")
                sum_res = conn.execute(sum_query, params).fetchone()

            return {
                "status": "success",
                "count": sum_res[2] or 0,
                "summary": {
                    "total_withdrawal": float(sum_res[0] or 0.0),
                    "total_deposit": float(sum_res[1] or 0.0)
                },
                "data": data
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"조회 처리 오류: {str(e)}")

    @staticmethod
    async def get_stats(engine, table_name):
        """영문 컬럼 기반 통계 분석"""
        try:
            with engine.connect() as conn:
                # 1. 월별 지출 추이
                monthly_query = text(f"""
                    SELECT strftime('%Y-%m', replace(date, '.', '-')) as month, SUM(outcome)
                    FROM {table_name} WHERE outcome > 0
                    GROUP BY month ORDER BY month DESC LIMIT 6
                """)
                monthly_res = conn.execute(monthly_query).fetchall()
                
                # 2. 카테고리별 비중
                category_query = text(f"""
                    SELECT category, SUM(outcome) as val FROM {table_name}
                    WHERE outcome > 0 GROUP BY category ORDER BY val DESC LIMIT 10
                """)
                category_res = conn.execute(category_query).fetchall()

                # 3. 현재 잔액 (가장 최근 데이터의 balance)
                balance_query = text(f"SELECT balance FROM {table_name} ORDER BY date DESC, id DESC LIMIT 1")
                current_balance = conn.execute(balance_query).scalar() or 0.0

            return {
                "status": "success",
                "current_balance": current_balance,
                "monthly_trend": [{"month": r[0], "amount": r[1] or 0} for r in reversed(monthly_res)],
                "category_distribution": [{"name": r[0] or "미분류", "value": r[1] or 0} for r in category_res]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"통계 분석 오류: {str(e)}")

    @staticmethod
    async def delete_spending(engine, table_name, record_id: int):
        # rowid 대신 id 컬럼 사용
        query = text(f"DELETE FROM {table_name} WHERE id = :record_id")
        with engine.connect() as conn:
            result = conn.execute(query, {"record_id": record_id})
            conn.commit()
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="삭제할 항목을 찾을 수 없습니다.")
        return {"status": "success", "message": f"ID {record_id} 항목 삭제 완료"}

    @staticmethod
    async def update_spending(engine, table_name, record_id: int, update_data: dict):
        if not update_data:
            raise HTTPException(status_code=400, detail="수정할 데이터가 없습니다.")
            
        # 업데이트 쿼리 동적 생성
        set_clause = ", ".join([f'"{key}" = :{key}' for key in update_data.keys()])
        query = text(f"UPDATE {table_name} SET {set_clause} WHERE id = :record_id")
        
        # 파라미터 구성
        params = {**update_data, "record_id": record_id}
        
        with engine.connect() as conn:
            result = conn.execute(query, params)
            conn.commit()
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="수정할 항목을 찾을 수 없습니다.")
        return {"status": "success", "message": f"ID {record_id} 항목 수정 완료"}
    

    @staticmethod
    async def get_history(engine, table_name, start_date=None, end_date=None, category=None, search=None):
        query = f"SELECT * FROM {table_name} WHERE 1=1"
        params = {}
        
        if start_date:
            query += " AND 일시 >= :start_date"
            params['start_date'] = start_date
        if end_date:
            query += " AND 일시 <= :end_date"
            params['end_date'] = end_date + " 23:59:59"
        if category and category != '전체':
            query += " AND 구분 = :category"
            params['category'] = category
        if search:
            query += " AND \"보낸 사람/받는 사람\" LIKE :search"
            params['search'] = f"%{search}%"
            
        query += " ORDER BY 일시 DESC"
        
        with engine.connect() as conn:
            result = conn.execute(text(query), params).fetchall()
            # 결과를 딕셔너리 리스트로 변환하여 반환
            return [dict(row._mapping) for row in result]
    
    @staticmethod
    async def get_combined_burn_rate_analysis(engine, table_name, categories: list, total_budget: float):
        try:
            if not categories:
                return {"status": "no_data", "reason": "선택된 카테고리가 없습니다."}

            # 1. SQL 쿼리 (기존 파라미터 바인딩 방식 유지)
            placeholders = ", ".join([f":cat{i}" for i in range(len(categories))])
            params = {f"cat{i}": cat for i, cat in enumerate(categories)}

            query_str = f"""
                SELECT date, outcome 
                FROM {table_name} 
                WHERE category IN ({placeholders}) AND outcome > 0
            """
            
            query = text(query_str)
            
            with engine.connect() as conn:
                result = conn.execute(query, params)
                rows = result.fetchall()
            
            if not rows:
                return {"status": "no_data", "reason": "해당 카테고리의 지출 내역이 없습니다."}

            # 2. 데이터 가공
            parsed_data = []
            for r in rows:
                try:
                    d_str = r[0].replace('.', '-')
                    parsed_data.append({'date': pd.to_datetime(d_str), 'outcome': float(r[1])})
                except: continue

            df = pd.DataFrame(parsed_data)
            
            # [핵심 수정] 일평균 금액 계산
            # 데이터가 있는 첫 날부터 마지막 날까지의 실제 기간 동안의 평균을 구합니다.
            start_date = df['date'].min()
            end_date = df['date'].max()
            # 데이터가 단 하루치만 있을 경우를 대비해 최소 1일 보장
            actual_days = max(1, (end_date - start_date).days + 1)
            
            # 해당 카테고리들의 총 지출액을 실제 경과 기간으로 나누어 일평균 도출
            category_total_spent = df['outcome'].sum()
            combined_avg_daily = category_total_spent / actual_days

            # 3. [시뮬레이션 계산] 
            # 사용자가 입력한 예산을 현재의 일평균 지출로 나눕니다.
            # (과거에 이미 쓴 돈을 차감하지 않고, 새로 부여된 예산으로 시뮬레이션)
            if combined_avg_daily > 0:
                days_left = int(total_budget / combined_avg_daily)
                is_over = False # 시뮬레이션이므로 예산 입력 즉시 초과될 일은 없음
            else:
                days_left = "∞"
                is_over = False

            return {
                "status": "success",
                "combined_avg_daily": round(combined_avg_daily, 0),
                "total_budget": total_budget,
                "days_left": days_left,
                "is_over_budget": is_over,
                "progress": 0 # 시뮬레이션 모드이므로 게이지는 0부터 시작하거나 다른 용도로 활용
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}