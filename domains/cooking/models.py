import uuid
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Recipe(Base):
    """완료된 요리 레시피"""
    __tablename__ = "recipe"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    servings = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)          # 별점 (0.5 단위, 1~5)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    ingredients = relationship("RecipeIngredient", back_populates="recipe",
                               cascade="all, delete-orphan")


class RecipeIngredient(Base):
    """레시피에 사용된 재료 (재고 품목과 연결)"""
    __tablename__ = "recipe_ingredient"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recipe_id = Column(String, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False)
    # 품목이 삭제돼도 레시피는 보존
    item_id = Column(String, ForeignKey("inventory.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String, nullable=False)     # 품목명 보존
    amount_used = Column(Float, nullable=False)    # 사용량 (g)
    unit = Column(String, nullable=True, default="g")

    recipe = relationship("Recipe", back_populates="ingredients")
    item = relationship("Inventory")
