
from nicegui import ui
from database import init_db

from ui.pages.home import render_home
from ui.pages.budget import render_budget
from ui.pages.list import render_list
from ui.pages.inventory import render_inventory
from ui.pages.cooking import render_cooking
from ui.pages.finance import render_finance

from ui.layout import shared_layout


def base_page_config(page_name: str):
    """모든 페이지에서 공통으로 호출할 레이아웃 및 스타일"""
    shared_layout(page_name)
    
@ui.page('/')
async def index_page():
    base_page_config("home")
    await render_home()

@ui.page('/budget')
async def budget_page():
    base_page_config("budget")
    await render_budget()

# 재고 관리
@ui.page('/inventory')
async def inventory_page():
    base_page_config("inventory")
    await render_inventory()

# 요리
@ui.page('/cooking')
async def cooking_page():
    base_page_config("cooking")
    await render_cooking()

# 금융
@ui.page('/finance')
async def finance_page():
    base_page_config("finance")
    await render_finance()

# @ui.page('/list')
# async def list_page():
#     base_page_config("list")
#     await render_list()

if __name__ in {"__main__", "__mp_main__"}:
    init_db() 
    
    ui.run(
        title='HMS',
        port=8080,
        reload=True,
        dark=False,
        # storage_secret='your_secret_key' # 만약 ui.storage를 쓸 계획이라면 추가
    )