import pytest
from sqlalchemy import create_engine
from main import app
from database import engine as real_engine

# 테스트용 메모리 DB 엔진
test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

@pytest.fixture
def db_engine():
    # 테스트 시작 전 테이블 생성
    from database import TABLE_NAME, SCHEMA_PATH
    import pandas as pd
    df_schema = pd.read_csv(SCHEMA_PATH, encoding='utf-8-sig')
    df_schema.head(0).to_sql(TABLE_NAME, con=test_engine, if_exists='replace', index=False)
    yield test_engine
    # 테스트 종료 후 정리 (메모리라 자동 소멸되지만 명시적 처리)
    test_engine.dispose()