"""
Inventory domain write handler.
InventoryService의 write 메서드를 action 문자열로 매핑합니다.
"""
from domains.inventory.service import InventoryService


class InventoryHandler:
    """
    Supported actions (write-only):
        create_item, update_item, delete_item,
        add_usage_history, finish_item,
        decrease_weight, upsert_stock, import_csv, import_history_csv
    """

    async def handle(self, action: str, db, **kwargs):
        match action:
            case "create_item":
                return await InventoryService.create_item(db, kwargs["item_data"])

            case "update_item":
                return await InventoryService.update_item(
                    db, kwargs["item_id"], kwargs["update_data"]
                )

            case "delete_item":
                return await InventoryService.delete_item(db, kwargs["item_id"])

            case "add_usage_history":
                return await InventoryService.add_usage_history(
                    db, kwargs["item_id"], kwargs["history_data"]
                )

            case "finish_item":
                return await InventoryService.finish_item(db, kwargs["item_id"])

            case "decrease_weight":
                return await InventoryService.decrease_weight(
                    db, kwargs["item_id"], kwargs["amount"]
                )

            case "upsert_stock":
                return await InventoryService.upsert_stock(
                    db, kwargs["item_id"], kwargs["amount"]
                )

            case "import_csv":
                return InventoryService.import_csv_from_bytes(kwargs["content"], db)

            case "import_history_csv":
                return InventoryService.import_history_from_csv_bytes(kwargs["content"], db)

            case "export_csv":
                return InventoryService.export_to_csv_bytes(db)

            case "export_history_csv":
                return InventoryService.export_history_to_csv_bytes(db, **kwargs)

            case "restore_csv":
                return InventoryService.restore_from_csv_bytes(kwargs["content"], db)

            case "restore_history_csv":
                return InventoryService.restore_history_from_csv_bytes(kwargs["content"], db)

            case _:
                raise ValueError(
                    f"[InventoryHandler] Unknown action: '{action}'. "
                    f"Valid actions: create_item, update_item, delete_item, "
                    f"add_usage_history, finish_item, decrease_weight, upsert_stock, "
                    f"import_csv, import_history_csv, export_csv, export_history_csv"
                )
