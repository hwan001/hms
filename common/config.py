
DATABASE_URL = "sqlite:///./spending_data.db"
TABLE_NAME = "spending_history"

# common
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


# spending
CSV_MAPPING = {
    '일시': 'date',
    '종류': 'type',
    '보낸 사람/받는 사람': 'content',
    '입금': 'income',
    '출금': 'outcome',
    '잔액': 'balance',
    '구분': 'category',
    '메모': 'memo',
    '거래점': 'branch',
    '일시 (날짜 포맷)': 'date_formatted'
}

# 숫자형으로 관리할 영문 컬럼 목록 (DB 생성 및 데이터 변환 시 참조)
NUMERIC_COLUMNS = ['income', 'outcome', 'balance']