"""
Spending domain write handler.
SpendingService의 write 메서드를 action 문자열로 매핑합니다.
"""
from domains.spending.service import SpendingService


class SpendingHandler:
    """
    Supported actions (write-only):
        update_spending, delete_spending, import_csv
    """

    async def handle(self, action: str, db, **kwargs):
        match action:
            case "update_spending":
                return await SpendingService.update_spending(
                    db, kwargs["record_id"], kwargs["update_data"]
                )

            case "delete_spending":
                return await SpendingService.delete_spending(db, kwargs["record_id"])

            case "import_csv":
                return SpendingService.import_csv_from_bytes(
                    kwargs["content"], db
                )

            case "export_csv":
                return SpendingService.export_to_csv_bytes(db)

            case "restore_csv":
                return SpendingService.restore_from_csv_bytes(kwargs["content"], db)

            case _:
                raise ValueError(
                    f"[SpendingHandler] Unknown action: '{action}'. "
                    f"Valid actions: update_spending, delete_spending, import_csv, export_csv"
                )
