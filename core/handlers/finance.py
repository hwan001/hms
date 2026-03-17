"""
Finance domain write handler.
"""
from domains.finance.service import FinanceService


class FinanceHandler:
    """
    Supported actions:
        create_portfolio, update_portfolio, delete_portfolio,
        add_holding, update_holding, delete_holding,
        create_simulation, delete_simulation
    """

    async def handle(self, action: str, db, **kwargs):
        match action:
            case "create_portfolio":
                return await FinanceService.create_portfolio(db, kwargs["data"])

            case "update_portfolio":
                return await FinanceService.update_portfolio(
                    db, kwargs["portfolio_id"], kwargs["data"]
                )

            case "delete_portfolio":
                return await FinanceService.delete_portfolio(db, kwargs["portfolio_id"])

            case "add_holding":
                return await FinanceService.add_holding(db, kwargs["data"])

            case "update_holding":
                return await FinanceService.update_holding(
                    db, kwargs["holding_id"], kwargs["data"]
                )

            case "delete_holding":
                return await FinanceService.delete_holding(db, kwargs["holding_id"])

            case "create_simulation":
                return await FinanceService.create_simulation(db, kwargs["data"])

            case "delete_simulation":
                return await FinanceService.delete_simulation(db, kwargs["session_id"])

            case "export_portfolios_csv":
                return FinanceService.export_portfolios_to_csv_bytes(db)

            case "export_holdings_csv":
                return FinanceService.export_holdings_to_csv_bytes(db)

            case "export_simulations_csv":
                return FinanceService.export_simulations_to_csv_bytes(db)

            case "restore_portfolios_csv":
                return FinanceService.restore_portfolios_from_csv_bytes(kwargs["content"], db)

            case "restore_holdings_csv":
                return FinanceService.restore_holdings_from_csv_bytes(kwargs["content"], db)

            case "restore_simulations_csv":
                return FinanceService.restore_simulations_from_csv_bytes(kwargs["content"], db)

            case _:
                raise ValueError(
                    f"[FinanceHandler] Unknown action: '{action}'"
                )
