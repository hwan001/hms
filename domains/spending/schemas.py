from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Dict, Any

class SpendingBase(BaseModel):
    date: str
    type: Optional[str] = None
    content: Optional[str] = None
    income: float = 0.0
    outcome: float = 0.0
    balance: float = 0.0
    category: Optional[str] = None
    memo: Optional[str] = None

class SpendingCreate(SpendingBase):
    pass

class SpendingRead(SpendingBase):
    id: int
    # Pydantic v2의 표준 설정 방식입니다.
    model_config = ConfigDict(from_attributes=True)

class SpendingStats(BaseModel):
    current_balance: float
    monthly_trend: List[Dict[str, Any]]
    category_distribution: List[Dict[str, Any]]

class SpendingSummary(BaseModel):
    total_withdrawal: float
    total_deposit: float
    net_amount: float

class PaginationInfo(BaseModel):
    total_count: int
    page: int
    size: int
    total_pages: int

class SpendingUpdate(BaseModel):
    구분: Optional[str] = Field(None, json_schema_extra={"example": "식비"})
    메모: Optional[str] = Field(None, json_schema_extra={"example": "자동입력"})
    출금: Optional[float] = Field(None, json_schema_extra={"example": 5500.0})
    입금: Optional[float] = Field(None, json_schema_extra={"example": 0.0})
    일시: Optional[str] = Field(None, json_schema_extra={"example": "2026-02-19 12:00:00"})

class SpendingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    status: str
    count: int
    summary: SpendingSummary
    pagination: PaginationInfo
    filters: Dict[str, Optional[str]]
    data: List[Dict[str, Any]]

class UploadResponse(BaseModel):
    status: str
    message: str
    first_row_preview: Optional[Dict[str, Any]] = None

SpendingResponse.model_rebuild()