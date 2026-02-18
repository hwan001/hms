from nicegui import ui
from database import init_db_from_schema

from ui.dashboard import render_dashboard
from ui.list import render_list
from ui.layout import shared_layout


def base_page_config():
    """모든 페이지에서 공통으로 호출할 레이아웃 및 스타일"""
    shared_layout()

@ui.page('/')
async def index_page():
    base_page_config()
    await render_dashboard()

@ui.page('/list')
async def list_page():
    base_page_config()
    await render_list()

if __name__ in {"__main__", "__mp_main__"}:
    init_db_from_schema() 
    
    ui.run(
        title='HAS Spending Tracker',
        port=8080,
        reload=True,
        dark=False,
        # storage_secret='your_secret_key' # 만약 ui.storage를 쓸 계획이라면 추가
    )