from pydantic import BaseModel, ConfigDict
from typing import Optional, Dict, Any
from datetime import datetime


class InventoryBase(BaseModel):
    domain: str
    category: str
    name: str
    quantity: Optional[int] = None         # 구매 수량
    start_weight: Optional[float] = None
    price: Optional[float] = None          # 구매 가격 (원)
    extra_info: Optional[Dict[str, Any]] = None
    memo: Optional[str] = None


class InventoryCreate(InventoryBase):
    pass


class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    quantity: Optional[int] = None
    current_weight: Optional[float] = None
    price: Optional[float] = None
    extra_info: Optional[Dict[str, Any]] = None
    memo: Optional[str] = None
    ended_at: Optional[datetime] = None


class HistoryCreate(BaseModel):
    measured_weight: Optional[float] = None
    note: str


class InventoryRead(InventoryBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    current_weight: Optional[float] = None
    started_at: datetime
    ended_at: Optional[datetime] = None
    created_at: datetime

    @property
    def price_per_gram(self) -> Optional[float]:
        if self.price and self.start_weight:
            return self.price / self.start_weight
        return None

    @property
    def remaining_value(self) -> Optional[float]:
        if self.price and self.start_weight and self.current_weight is not None:
            return (self.price / self.start_weight) * self.current_weight
        return None


class HistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    action_date: datetime
    measured_weight: Optional[float] = None
    usage_amount: Optional[float] = None
    note: str