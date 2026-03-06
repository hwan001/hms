"""
Cooking domain write handler.
RecipeService의 write 메서드를 action 문자열로 매핑합니다.
"""
from domains.cooking.service import RecipeService


class CookingHandler:
    """
    Supported actions (write-only):
        create_recipe, update_recipe, delete_recipe, import_csv
    """

    async def handle(self, action: str, db, **kwargs):
        match action:
            case "create_recipe":
                return await RecipeService.create_recipe(db, kwargs["recipe_data"])

            case "update_recipe":
                return await RecipeService.update_recipe(
                    db, kwargs["recipe_id"], kwargs["update_data"]
                )

            case "delete_recipe":
                return await RecipeService.delete_recipe(db, kwargs["recipe_id"])

            case "import_csv":
                return RecipeService.import_csv_from_bytes(kwargs["content"], db)

            case "export_csv":
                return RecipeService.export_to_csv_bytes(db)

            case "restore_csv":
                return RecipeService.restore_from_csv_bytes(kwargs["content"], db)

            case _:
                raise ValueError(
                    f"[CookingHandler] Unknown action: '{action}'. "
                    f"Valid actions: create_recipe, update_recipe, delete_recipe, import_csv, export_csv"
                )
