from sqlalchemy import Column, Integer, String, Float, Text
# database.py에서 정의한 Base를 임포트하여 통합 관리합니다.
from database import Base 

class SpendingHistory(Base):
    __tablename__ = "spending_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(String, nullable=False)      # 일시
    type = Column(String, nullable=True)       # 종류
    content = Column(String, nullable=True)    # 보낸 사람/받는 사람 (내용)
    income = Column(Float, default=0.0)        # 입금액
    outcome = Column(Float, default=0.0)       # 출금액
    balance = Column(Float, default=0.0)       # 현재잔액
    category = Column(String, nullable=True)   # 구분 (카테고리)
    memo = Column(Text, nullable=True)         # 메모