import uuid
from sqlalchemy import Column, String, Float, Integer, DateTime, JSON, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base

class Inventory(Base):
    __tablename__ = "inventory"

    id      = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    item_no = Column(String, nullable=True, unique=True)  # 품목번호 e.g. INV-0001
    domain = Column(String, nullable=False)
    category = Column(String, nullable=False)
    name = Column(String, nullable=False)

    # 소모품 특화
    start_weight = Column(Float, nullable=True)
    current_weight = Column(Float, nullable=True)
    quantity = Column(Integer, nullable=True)   # 구매 수량
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    ended_at = Column(DateTime(timezone=True), nullable=True)

    image_url = Column(String, nullable=True)   # 이미지 URL
    extra_info = Column(JSON, nullable=True)
    memo = Column(Text, nullable=True)
    price = Column(Float, nullable=True)   # 구매 가격 (원)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 삭제 시 history의 item_id를 NULL로 설정 (이력은 보존)
    history = relationship("InventoryHistory", back_populates="item",
                           cascade="save-update, merge",
                           passive_deletes=True)

class InventoryHistory(Base):
    __tablename__ = "inventory_history"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # nullable=True + ondelete="SET NULL" → 품목 삭제 후에도 이력 보존
    item_id = Column(String, ForeignKey("inventory.id", ondelete="SET NULL"), nullable=True)
    event_type = Column(String, nullable=False, default="사용")  # 등록/사용/수정/삭제
    item_no = Column(String, nullable=True)     # 품목번호 보존용 (품목 삭제 후에도 유지)
    item_name = Column(String, nullable=True)   # 삭제된 품목명 보존용
    action_date = Column(DateTime(timezone=True), server_default=func.now())
    measured_weight = Column(Float, nullable=True)
    usage_amount = Column(Float, nullable=True)
    note = Column(Text, nullable=False)

    item = relationship("Inventory", back_populates="history")