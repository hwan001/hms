import uuid
from sqlalchemy import Column, String, Float, DateTime, Date, ForeignKey, Integer, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Portfolio(Base):
    """투자 포트폴리오 (여러 종목 묶음)"""
    __tablename__ = "portfolios"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    holdings = relationship(
        "PortfolioHolding",
        back_populates="portfolio",
        cascade="all, delete-orphan",
    )
    simulations = relationship(
        "SimulationSession",
        back_populates="portfolio",
        passive_deletes=True,
    )


class PortfolioHolding(Base):
    """포트폴리오 내 개별 종목"""
    __tablename__ = "portfolio_holdings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(
        String, ForeignKey("portfolios.id", ondelete="CASCADE"), nullable=False
    )
    ticker = Column(String, nullable=False)       # 종목 코드 (예: 005930.KS, AAPL)
    name = Column(String, nullable=False)          # 종목명
    quantity = Column(Float, nullable=False, default=0.0)   # 보유 수량
    avg_price = Column(Float, nullable=False, default=0.0)  # 평균 매입가
    currency = Column(String, default="KRW")       # KRW / USD
    target_ratio = Column(Float, nullable=True, default=0.0)  # 목표 비율 (%)
    memo = Column(Text, nullable=True)

    portfolio = relationship("Portfolio", back_populates="holdings")


class SimulationSession(Base):
    """DCA(정기 매수) 시뮬레이션 세션"""
    __tablename__ = "simulation_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    portfolio_id = Column(
        String, ForeignKey("portfolios.id", ondelete="SET NULL"), nullable=True
    )
    name = Column(String, nullable=False)
    monthly_amount = Column(Float, nullable=False, default=500_000.0)  # 정기 매수 금액
    buy_day = Column(Integer, nullable=False, default=1)                # 매수일 (1~28)
    start_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    portfolio = relationship("Portfolio", back_populates="simulations")
