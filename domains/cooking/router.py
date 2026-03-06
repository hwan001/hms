from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from core.engine import engine
from . import schemas, service

router = APIRouter(prefix="/cooking", tags=["Cooking"])

@router.get("/", response_model=List[schemas.RecipeRead], summary="레시피 목록 조회")
async def get_recipes(
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    return await service.RecipeService.get_recipes(db, search=search)

@router.post("/", response_model=schemas.RecipeRead, summary="레시피 등록")
async def create_recipe(recipe: schemas.RecipeCreate, db: Session = Depends(get_db)):
    return await engine.execute("cooking", "create_recipe", db, recipe_data=recipe)

@router.patch("/{recipe_id}", response_model=schemas.RecipeRead, summary="레시피 수정")
async def update_recipe(recipe_id: str, data: schemas.RecipeUpdate, db: Session = Depends(get_db)):
    result = await engine.execute("cooking", "update_recipe", db, recipe_id=recipe_id, update_data=data)
    if not result:
        raise HTTPException(status_code=404, detail="레시피를 찾을 수 없습니다.")
    return result

@router.delete("/{recipe_id}", summary="레시피 삭제")
async def delete_recipe(recipe_id: str, db: Session = Depends(get_db)):
    result = await engine.execute("cooking", "delete_recipe", db, recipe_id=recipe_id)
    if not result:
        raise HTTPException(status_code=404, detail="레시피를 찾을 수 없습니다.")
    return {"status": "success", "message": f"레시피 삭제 완료"}
