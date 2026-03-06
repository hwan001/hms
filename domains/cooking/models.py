import uuid
from sqlalchemy import Column, String, Float, DateTime, Text, ForeignKey, Integer, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Recipe(Base):
    """완료된 요리 레시피"""
    __tablename__ = "recipe"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    servings = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # 결과물 정보
    output_name = Column(String, nullable=True)           # 결과물 이름
    output_amount = Column(Float, nullable=True)          # 수량/무게
    output_unit = Column(String, nullable=True)           # 단위 (인분, g 등)
    output_to_inventory = Column(Boolean, default=False)  # 재고 등록 여부

    ingredients = relationship("RecipeIngredient", back_populates="recipe",
                               cascade="all, delete-orphan")
    steps = relationship("RecipeStep", back_populates="recipe",
                         cascade="all, delete-orphan",
                         order_by="RecipeStep.step_no")


class RecipeIngredient(Base):
    """레시피에 사용된 재료 (재고 품목과 연결)"""
    __tablename__ = "recipe_ingredient"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recipe_id = Column(String, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False)
    item_id = Column(String, ForeignKey("inventory.id", ondelete="SET NULL"), nullable=True)
    item_name = Column(String, nullable=False)
    amount_used = Column(Float, nullable=False)
    unit = Column(String, nullable=True, default="g")

    recipe = relationship("Recipe", back_populates="ingredients")
    item = relationship("Inventory")


class RecipeStep(Base):
    """레시피 단계별 조리 방법"""
    __tablename__ = "recipe_step"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    recipe_id = Column(String, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False)
    step_no = Column(Integer, nullable=False)             # 순서 (1부터 시작)
    title = Column(String, nullable=True)                 # 단계 제목 (선택)
    description = Column(Text, nullable=True)             # 조리 설명
    ingredients_note = Column(Text, nullable=True)        # 이 단계에서 쓰는 재료 메모

    recipe = relationship("Recipe", back_populates="steps")
