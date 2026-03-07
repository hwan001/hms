from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime, date


# ── Portfolio ───────────────────────────────────────────────

class PortfolioCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class PortfolioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: Optional[str] = None
    created_at: datetime


# ── Portfolio Holdings ──────────────────────────────────────

class HoldingCreate(BaseModel):
    portfolio_id: str
    ticker: str
    name: str
    quantity: float = 0.0
    avg_price: float = 0.0
    currency: str = "KRW"
    target_ratio: Optional[float] = 0.0
    memo: Optional[str] = None


class HoldingUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[float] = None
    avg_price: Optional[float] = None
    currency: Optional[str] = None
    target_ratio: Optional[float] = None
    memo: Optional[str] = None


class HoldingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    portfolio_id: str
    ticker: str
    name: str
    quantity: float
    avg_price: float
    currency: str
    target_ratio: Optional[float] = None
    memo: Optional[str] = None


# ── Simulation ──────────────────────────────────────────────

class SimulationCreate(BaseModel):
    portfolio_id: str
    name: str
    monthly_amount: float = 500_000.0
    buy_day: int = 1
    start_date: date


class SimulationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    portfolio_id: Optional[str] = None
    name: str
    monthly_amount: float
    buy_day: int
    start_date: date
    created_at: datetime
