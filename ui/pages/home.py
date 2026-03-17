from datetime import datetime

from nicegui import ui

from core.engine import engine
from database import db_session
from domains.spending.service import SpendingService
from domains.inventory.service import InventoryService
from domains.cooking.service import RecipeService


async def render_home():
    with ui.column().classes('w-full max-w-5xl mx-auto p-6 gap-6'):

        # ── Hero ──────────────────────────────────────────────────────
        with ui.card().classes('w-full p-8 shadow-md').style(
            'background: linear-gradient(135deg, #1d4ed8 0%, #1e40af 60%, #1e3a8a 100%);'
        ):
            ui.label('HMS').classes('text-5xl font-black text-white')
            ui.label('Home Management System').classes('text-base text-blue-300 mt-1')
            ui.label('가계부 · 재고 · 요리를 한곳에서 관리하세요').classes('text-sm text-blue-200 mt-2')

        # ── 바로가기 ──────────────────────────────────────────────────
        ui.label('바로가기').classes('text-xl font-bold')
        with ui.element('div').style('overflow-x: auto; padding-bottom: 4px;').classes('w-full'):
            with ui.row().classes('gap-4 flex-nowrap'):
                _nav_card('payments',       '가계부',    '/budget',    'green',  '지출 내역 · 통계 · 시뮬레이션')
                _nav_card('inventory',      '재고 관리', '/inventory', 'indigo', '품목 관리 · 소모품 잔량 추적')
                _nav_card('restaurant',     '요리',      '/cooking',   'orange', '레시피 등록 및 관리')
                _nav_card('account_balance','금융',      '/finance',   'blue',   '금융 계좌 · 자산 관리')

        # ── 현황 요약 ─────────────────────────────────────────────────
        ui.label('현황 요약').classes('text-xl font-bold')
        with ui.row().classes('w-full gap-4 flex-wrap'):
            await _spending_summary()
            await _inventory_summary()
            await _cooking_summary()

        # ── 데이터 관리 ───────────────────────────────────────────────
        with ui.expansion('데이터 관리', icon='storage') \
                .classes('w-full text-xl font-bold border rounded-lg shadow-sm'):
            await _data_management_panel()

        # ── 위험 구역 ─────────────────────────────────────────────────
        with ui.expansion('위험 구역', icon='warning') \
                .classes('w-full text-xl font-bold border border-red-200 rounded-lg shadow-sm text-red-600'):
            await _danger_zone_panel()


# ── 헬퍼 ──────────────────────────────────────────────────────────────

def _nav_card(icon: str, label: str, path: str, color: str, desc: str):
    """클릭 가능한 바로가기 카드"""
    bg_map = {
        'green':  ('bg-green-50',  'border-green-200',  'text-green-700'),
        'indigo': ('bg-indigo-50', 'border-indigo-200', 'text-indigo-700'),
        'orange': ('bg-orange-50', 'border-orange-200', 'text-orange-700'),
        'blue':   ('bg-blue-50',   'border-blue-200',   'text-blue-700'),
    }
    bg, border, icon_color = bg_map[color]

    with ui.card().classes(f'shrink-0 w-52 p-5 border {bg} {border} cursor-pointer hover:shadow-lg transition-shadow') \
            .on('click', lambda _p=path: ui.navigate.to(_p)):
        with ui.row().classes('items-center gap-3 mb-2'):
            ui.icon(icon).classes(f'text-3xl {icon_color}')
            ui.label(label).classes('text-lg font-bold')
        ui.label(desc).classes('text-sm text-slate-500')
        ui.icon('arrow_forward').classes(f'text-sm {icon_color} mt-2')


async def _spending_summary():
    """가계부 요약 카드"""
    with ui.card().classes('flex-1 min-w-52 p-5 shadow-sm border'):
        with ui.row().classes('items-center gap-2 mb-3'):
            ui.icon('payments').classes('text-xl text-green-600')
            ui.label('가계부').classes('font-bold text-base')
        try:
            with db_session() as db:
                stats = await SpendingService.get_stats(db)
            balance = int(stats.get('current_balance', 0))
            latest  = stats.get('latest_date', '-')
            monthly = stats.get('monthly_trend', [])
            this_month_out = int(monthly[-1]['amount']) if monthly else 0

            _stat_row('이번 달 지출', f'₩{this_month_out:,}', 'text-red-500')
            _stat_row('현재 잔액',   f'₩{balance:,}',         'text-blue-600')
            _stat_row('최근 데이터', latest,                   'text-slate-400')
        except Exception:
            ui.label('데이터 없음').classes('text-slate-400 text-sm italic')


async def _inventory_summary():
    """재고 요약 카드"""
    with ui.card().classes('flex-1 min-w-52 p-5 shadow-sm border'):
        with ui.row().classes('items-center gap-2 mb-3'):
            ui.icon('inventory').classes('text-xl text-indigo-600')
            ui.label('재고 관리').classes('font-bold text-base')
        try:
            with db_session() as db:
                items = await InventoryService.get_items(db)
            total = len(items)
            consumables = [i for i in items if i.category == '소모품' and i.current_weight is not None]
            low = [
                i for i in consumables
                if i.start_weight and (i.current_weight / i.start_weight) < 0.2
            ]

            _stat_row('등록 품목',     f'{total}개',     'text-indigo-600')
            _stat_row('소모품',        f'{len(consumables)}개', 'text-slate-600')
            _stat_row('잔량 부족 (<20%)', f'{len(low)}개', 'text-red-500' if low else 'text-slate-400')
        except Exception:
            ui.label('데이터 없음').classes('text-slate-400 text-sm italic')


async def _cooking_summary():
    """요리 요약 카드"""
    with ui.card().classes('flex-1 min-w-52 p-5 shadow-sm border'):
        with ui.row().classes('items-center gap-2 mb-3'):
            ui.icon('restaurant').classes('text-xl text-orange-600')
            ui.label('요리').classes('font-bold text-base')
        try:
            with db_session() as db:
                recipes = await RecipeService.get_recipes(db)
            total = len(recipes)
            _stat_row('등록 레시피', f'{total}개', 'text-orange-600')
            if recipes:
                latest = recipes[-1].name if hasattr(recipes[-1], 'name') else '-'
                _stat_row('최근 레시피', latest, 'text-slate-500')
        except Exception:
            ui.label('데이터 없음').classes('text-slate-400 text-sm italic')


def _stat_row(label: str, value: str, value_class: str):
    with ui.row().classes('w-full justify-between items-center py-1'):
        ui.label(label).classes('text-sm text-slate-500')
        ui.label(value).classes(f'text-sm font-semibold {value_class}')


async def _data_management_panel():
    """전체/도메인별 CSV import·export 중앙 관리 패널"""

    # ── 전체 일괄 처리 ─────────────────────────────────────────────
    with ui.card().classes('w-full p-5 shadow-sm border'):
        with ui.row().classes('items-center gap-2 mb-1'):
            ui.icon('archive').classes('text-xl text-slate-600')
            ui.label('전체 일괄 처리').classes('font-bold text-base')
        ui.label('모든 도메인 데이터를 ZIP 하나로 export하거나 ZIP에서 일괄 import합니다.') \
            .classes('text-xs text-slate-400 mb-4')

        async def handle_export_all():
            try:
                with db_session() as db:
                    zip_bytes = await engine.export_all(db)
                filename = f"hms_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
                ui.download(zip_bytes, filename)
                ui.notify(f'전체 Export 완료: {filename}', color='positive')
            except Exception as e:
                ui.notify(f'Export 실패: {e}', color='negative')

        async def handle_import_all(e):
            try:
                content = await e.file.read()
                result = await engine.import_all(content)
                imported = list(result.get('results', {}).keys())
                ui.notify(f'Import 완료: {", ".join(imported)}', color='positive')
            except Exception as ex:
                ui.notify(f'Import 실패: {ex}', color='negative')

        hidden_upload_all = ui.upload(
            auto_upload=True, on_upload=handle_import_all
        ).props('accept=".zip"').style('display: none')

        with ui.row().classes('gap-3'):
            ui.button('전체 Export (ZIP)', icon='download', on_click=handle_export_all) \
                .props('elevated').classes('bg-slate-700 text-white')
            ui.button('전체 Import (ZIP)', icon='upload',
                      on_click=lambda: hidden_upload_all.run_method('pickFiles')) \
                .props('elevated').classes('bg-slate-600 text-white')

    # ── 도메인별 개별 처리 ─────────────────────────────────────────
    with ui.card().classes('w-full p-5 shadow-sm border'):
        with ui.row().classes('items-center gap-2 mb-4'):
            ui.icon('table_chart').classes('text-xl text-slate-600')
            ui.label('도메인별 CSV').classes('font-bold text-base')


        domain_configs = [
            {
                'label':   '가계부',
                'icon':    'payments',
                'color':   'green',
                'exports': [('spending', 'export_csv', 'spending.csv')],
                'imports': [('spending', 'restore_csv', 'spending.csv', '.csv')],
            },
            {
                'label':   '재고 관리',
                'icon':    'inventory',
                'color':   'indigo',
                'exports': [
                    ('inventory', 'export_csv',         'inventory.csv'),
                    ('inventory', 'export_history_csv', 'inventory_history.csv'),
                ],
                'imports': [
                    ('inventory', 'restore_csv',         'inventory.csv',         '.csv'),
                    ('inventory', 'restore_history_csv', 'inventory_history.csv', '.csv'),
                ],
            },
            {
                'label':   '요리',
                'icon':    'restaurant',
                'color':   'orange',
                'exports': [('cooking', 'export_csv', 'cooking.csv')],
                'imports': [('cooking', 'restore_csv', 'cooking.csv', '.csv')],
            },
            {
                'label':   '금융',
                'icon':    'account_balance',
                'color':   'blue',
                'exports': [
                    ('finance', 'export_portfolios_csv',  'portfolios.csv'),
                    ('finance', 'export_holdings_csv',    'holdings.csv'),
                    ('finance', 'export_simulations_csv', 'simulations.csv'),
                ],
                'imports': [
                    ('finance', 'restore_portfolios_csv',  'portfolios.csv',  '.csv'),
                    ('finance', 'restore_holdings_csv',    'holdings.csv',    '.csv'),
                    ('finance', 'restore_simulations_csv', 'simulations.csv', '.csv'),
                ],
            },
        ]

        color_map = {
            'green':  'bg-green-600',
            'indigo': 'bg-indigo-600',
            'orange': 'bg-orange-500',
            'blue':   'bg-blue-600',
        }

        for cfg in domain_configs:
            with ui.card().classes('w-full mb-3 p-4 shadow-none border border-slate-100'):
                with ui.row().classes('w-full items-center gap-2 mb-3'):
                    ui.icon(cfg['icon']).classes(f'text-lg text-{cfg["color"]}-600')
                    ui.label(cfg['label']).classes('font-semibold')

                btn_color = color_map[cfg['color']]

                with ui.row().classes('gap-2 flex-wrap'):
                    # Export 버튼들
                    for domain, action, filename in cfg['exports']:
                        async def _export(d=domain, a=action, f=filename):
                            try:
                                with db_session() as db:
                                    csv_bytes = await engine.execute(d, a, db)
                                ui.download(csv_bytes, f)
                                ui.notify(f'{f} Export 완료', color='positive')
                            except Exception as ex:
                                ui.notify(f'Export 실패: {ex}', color='negative')

                        ui.button(f'Export {filename}', icon='download', on_click=_export) \
                            .props('elevated').classes(f'{btn_color} text-white')

                    # Import 버튼들
                    for domain, action, filename, accept in cfg['imports']:
                        async def _import_upload(e, d=domain, a=action, f=filename):
                            try:
                                content = await e.file.read()
                                with db_session() as db:
                                    result = await engine.execute(d, a, db, content=content)
                                msg = result.get('message', f'{f} Import 완료')
                                ui.notify(msg, color='positive')
                            except Exception as ex:
                                ui.notify(f'Import 실패: {ex}', color='negative')

                        hidden = ui.upload(
                            auto_upload=True,
                            on_upload=lambda e, d=domain, a=action, f=filename: _import_upload(e, d, a, f)
                        ).props(f'accept="{accept}"').style('display: none')

                        ui.button(f'Import {filename}', icon='upload',
                                  on_click=lambda _, h=hidden: h.run_method('pickFiles')) \
                            .props('outlined').classes(f'text-{cfg["color"]}-700')


async def _danger_zone_panel():
    """모든 데이터 초기화 패널"""
    with ui.card().classes('w-full p-5 shadow-sm border border-red-200 bg-red-50'):
        ui.label('모든 도메인(가계부·재고·요리·금융)의 데이터를 완전히 삭제합니다. 이 작업은 되돌릴 수 없습니다.') \
            .classes('text-xs text-red-400 mb-4')

        async def _do_clear():
            try:
                await engine.clear_all()
                ui.notify('전체 데이터가 초기화되었습니다.', color='positive')
            except Exception as ex:
                ui.notify(f'초기화 실패: {ex}', color='negative')

        async def _confirm_clear():
            with ui.dialog() as dlg, ui.card().classes('p-6 gap-4'):
                ui.label('정말로 모든 데이터를 삭제하시겠습니까?').classes('font-bold text-red-700')
                ui.label('가계부, 재고, 요리, 금융 데이터가 모두 사라집니다.').classes('text-sm text-slate-500')
                with ui.row().classes('gap-3 mt-2'):
                    ui.button('취소', on_click=dlg.close).props('outlined')
                    async def _confirmed():
                        dlg.close()
                        await _do_clear()
                    ui.button('전체 삭제', icon='delete_forever', on_click=_confirmed) \
                        .classes('bg-red-600 text-white')
            dlg.open()

        ui.button('전체 데이터 초기화', icon='delete_forever', on_click=_confirm_clear) \
            .props('elevated').classes('bg-red-600 text-white')
