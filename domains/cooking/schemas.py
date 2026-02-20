from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime


class RecipeIngredientCreate(BaseModel):
    item_id: Optional[str] = None
    item_name: str
    amount_used: float
    unit: str = "g"


class RecipeCreate(BaseModel):
    name: str
    servings: Optional[int] = None
    note: Optional[str] = None
    ingredients: List[RecipeIngredientCreate] = []


class RecipeIngredientRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    item_id: Optional[str] = None
    item_name: str
    amount_used: float
    unit: Optional[str] = "g"


class RecipeUpdate(BaseModel):
    name: Optional[str] = None
    servings: Optional[float] = None
    rating: Optional[float] = None   # 0.5 ~ 5.0
    note: Optional[str] = None


class RecipeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    servings: Optional[float] = None
    rating: Optional[float] = None
    note: Optional[str] = None
    created_at: datetime
    ingredients: List[RecipeIngredientRead] = []
