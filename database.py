import pandas as pd
from sqlalchemy import create_engine, inspect, text
from common.config import DATABASE_URL, TABLE_NAME, CSV_MAPPING, NUMERIC_COLUMNS

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

def init_db_from_schema():
    inspector = inspect(engine)
    if TABLE_NAME not in inspector.get_table_names():
        try:
            df_schema = pd.read_csv(SCHEMA_PATH, encoding='utf-8-sig', nrows=0)
            raw_columns = [c.strip() for c in df_schema.columns if c.strip()]

            cols_def = []
            for col in raw_columns:
                eng_name = CSV_MAPPING.get(col, col) 
                
                # 타입 결정
                col_type = "REAL" if eng_name in NUMERIC_COLUMNS else "TEXT"
                cols_def.append(f'"{eng_name}" {col_type}')

            cols_sql = ", ".join(cols_def)
            create_table_sql = f'CREATE TABLE {TABLE_NAME} (id INTEGER PRIMARY KEY AUTOINCREMENT, {cols_sql})'
            
            with engine.connect() as conn:
                conn.execute(text(create_table_sql))
                conn.commit()
            print(f" '{TABLE_NAME}' 테이블이 중앙 설정(config) 기반 영문 컬럼으로 생성되었습니다.")
        except Exception as e:
            print(f" 스키마 생성 오류: {e}")