from nicegui import ui

def shared_layout(page_name:str):
    """모든 페이지에서 공통으로 사용하는 헤더 및 레이아웃"""
    ui.query('body').classes('bg-slate-50')
    
    with ui.header().classes('bg-blue-700 items-center justify-between shadow-md'):
        with ui.row().classes('items-center gap-4'):
            ui.icon('payments', color='white').classes('text-2xl')
            ui.label(f'💰 HMS {page_name}').classes('text-h6 font-bold text-white')
        
        with ui.row().classes('gap-2'):
            ui.button('홈', on_click=lambda: ui.navigate.to('/')).props('flat color=white')
            ui.button('가계부', on_click=lambda: ui.navigate.to('/budget')).props('flat color=white')
            # ui.button('내역조회', on_click=lambda: ui.navigate.to('/list')).props('flat color=white')
            ui.button('재고 관리', on_click=lambda: ui.navigate.to('/inventory')).props('flat color=white')
            ui.button('요리', on_click=lambda: ui.navigate.to('/cooking')).props('flat color=white')
            
            ui.button(icon='refresh', on_click=ui.navigate.reload).props('flat color=white')
