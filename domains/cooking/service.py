from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc
from .models import Recipe, RecipeIngredient
from .schemas import RecipeCreate, RecipeUpdate
from domains.inventory.models import Inventory, InventoryHistory


class RecipeService:

    @staticmethod
    async def create_recipe(db: Session, recipe_data: RecipeCreate) -> Recipe:
        """요리 완료: 레시피 저장 + 재고 차감 + 사용 이력"""
        recipe = Recipe(
            name=recipe_data.name,
            servings=recipe_data.servings,
            note=recipe_data.note,
        )
        db.add(recipe)
        db.flush()

        for ing in recipe_data.ingredients:
            db.add(RecipeIngredient(
                recipe_id=recipe.id,
                item_id=ing.item_id,
                item_name=ing.item_name,
                amount_used=ing.amount_used,
                unit=ing.unit,
            ))
            if ing.item_id:
                item = db.query(Inventory).filter(Inventory.id == ing.item_id).first()
                if item and item.current_weight is not None:
                    new_weight = max(0.0, item.current_weight - ing.amount_used)
                    old_weight = item.current_weight
                    item.current_weight = new_weight
                    db.add(InventoryHistory(
                        item_id=ing.item_id,
                        event_type="사용",
                        item_name=item.name,
                        measured_weight=new_weight,
                        usage_amount=old_weight - new_weight,
                        note=f"요리: {recipe_data.name}",
                    ))

        db.commit()
        db.refresh(recipe)
        return recipe

    @staticmethod
    async def get_recipes(db: Session, search: str = None, limit: int = 50) -> list:
        """레시피 목록 조회 (재료의 item도 함께 로드해 가격 계산 가능)"""
        query = db.query(Recipe).options(
            joinedload(Recipe.ingredients).joinedload(RecipeIngredient.item)
        )
        if search:
            query = query.filter(Recipe.name.ilike(f"%{search}%"))
        return query.order_by(desc(Recipe.created_at)).limit(limit).all()

    @staticmethod
    async def update_recipe(db: Session, recipe_id: str, update_data: RecipeUpdate) -> Recipe | None:
        """레시피 별점·메모·이름 수정"""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            return None
        data = update_data.model_dump(exclude_none=True)
        # rating=0 같이 falsy지만 유효한 값 처리
        if 'rating' in update_data.model_dump() and update_data.rating is not None:
            recipe.rating = update_data.rating
        for field, val in data.items():
            setattr(recipe, field, val)
        db.commit()
        db.refresh(recipe)
        return recipe

    @staticmethod
    async def delete_recipe(db: Session, recipe_id: str) -> bool:
        """레시피 삭제"""
        recipe = db.query(Recipe).filter(Recipe.id == recipe_id).first()
        if not recipe:
            return False
        db.delete(recipe)
        db.commit()
        return True
