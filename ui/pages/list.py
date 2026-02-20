from nicegui import ui
from ui.hooks.update_dashboard import update_dashboard
from ui.common.config import ui_refs

from domains.spending.service import SpendingService
from database import db_session

async def render_list():    
    with ui.column().classes('w-full max-w-5xl mx-auto p-4'):
        ui.label('차트').classes('text-2xl font-bold mb-4')
        # KPI 섹션
        with ui.row().classes('w-full justify-between gap-4'):
            with ui.card().classes('flex-1 shadow-sm'):
                ui_refs['kpi_month_title'] = ui.label('지출 합계').classes('text-slate-500 text-sm')
                ui_refs['kpi_month_amount'] = ui.label('0 원').classes('text-2lg font-bold text-blue-600')
            with ui.card().classes('flex-1 shadow-sm'):
                ui.label('카테고리 수').classes('text-slate-500 text-sm')
                ui_refs['kpi_category_count'] = ui.label('0 개').classes('text-2lg font-bold text-black-600')
        # 2. 차트 섹션
        with ui.row().classes('w-full gap-4'):
            # 월별 지출 추이 (Bar Chart)
            with ui.card().classes('flex-1 h-80'):
                ui.label('월별 지출 추이').classes('font-bold')
                ui_refs['trend_chart'] = ui.echart({
                    'xAxis': {'type': 'category', 'data': []},
                    'yAxis': {'type': 'value'},
                    'series': [{'data': [], 'type': 'bar', 'itemStyle': {'color': '#5865f2'}}],
                    'tooltip': {'trigger': 'axis'}
                }).classes('h-64')

            # 통장 잔액 변화 흐름 (Line Chart)
            with ui.card().classes('flex-1 h-80'):
                ui.label('통장 잔액 변화 흐름').classes('font-bold')
                ui_refs['balance_chart'] = ui.echart({
                    'tooltip': {'trigger': 'axis'},
                    'xAxis': {'type': 'category', 'data': []},
                    'yAxis': {'type': 'value', 'min': 0, 'splitLine': {'show': True}, 'scale': True},
                    'series': [{
                        'data': [],
                        'type': 'line',
                        'smooth': True,
                        'areaStyle': {'opacity': 0.1},
                        'itemStyle': {'color': '#10b981'}
                    }]
                }).classes('h-64')

        ui.label('상세 거래 내역').classes('text-2xl font-bold mb-4')

        # 3. 상세 검색 섹션
        with ui.card().classes('w-full mb-4 p-4'):
            with ui.row().classes('w-full items-center gap-4 flex-wrap'):
                ui.label('상세 검색').classes('font-bold text-indigo-600')
                
                # 기간 필터
                ui_refs['start_date'] = ui.input('시작일').props('type=date outlined dense').classes('w-36')
                ui_refs['end_date'] = ui.input('종료일').props('type=date outlined dense').classes('w-36')
                
                # 검색 대상 컬럼 선택
                search_options = {
                    'category': '카테고리',
                    'content': '내용(거래처)',
                    'type': '거래종류',
                    'memo': '메모'
                }
                ui_refs['search_column'] = ui.select(
                    options=search_options, 
                    value='category', 
                    label='검색 대상'
                ).props('outlined dense').classes('w-40')

                ui_refs['search_input'] = ui.input(placeholder='검색어 입력...').props('outlined dense').classes('flex-grow')
                ui_refs['search_input'].on('keydown.enter', lambda: update_dashboard())

                ui.button('조회', icon='search', on_click=lambda: update_dashboard()) \
                    .props('elevated').classes('bg-blue-600 text-white px-6')

        # 4. 상세 내역 테이블
        with ui.column().classes('w-full gap-0'):
            columns = [
                {'name': 'date', 'label': '일시', 'field': 'date', 'align': 'center', 'sortable': True},
                {'name': 'type', 'label': '종류', 'field': 'type', 'align': 'left'},
                {'name': 'content', 'label': '내용', 'field': 'content', 'align': 'left'},
                {'name': 'income', 'label': '입금액', 'field': 'income', 'align': 'right', 'sortable': True},
                {'name': 'outcome', 'label': '출금액', 'field': 'outcome', 'align': 'right', 'sortable': True},
                {'name': 'balance', 'label': '현재잔액', 'field': 'balance', 'align': 'right', 'sortable': True},
                {'name': 'category', 'label': '카테고리', 'field': 'category', 'align': 'right'},
            ]
            ui_refs['table'] = ui.table(columns=columns, rows=[], row_key='id').classes('w-full shadow-none').props('dense flat bordered')
            ui_refs['table'].pagination.rows_per_page = 10

            with ui.row().classes('w-full bg-blue-50 p-3 justify-end gap-8 border border-t-0'):
                ui_refs['in_label'] = ui.label('총 입금: 0원').classes('font-bold text-blue-600')
                ui_refs['out_label'] = ui.label('총 출금: 0원').classes('font-bold text-red-600')
                ui_refs['count_label'] = ui.label('조회 결과: 0건').classes('text-slate-500 text-sm')

        # ── CSV Import / Export ──────────────────────────────
        async def handle_upload(e):
            try:
                content = await e.file.read()
                with db_session() as db:
                    result = SpendingService.import_csv_from_bytes(content, db)
                ui.notify(result['message'], color='positive')
                ui.timer(0.1, update_dashboard, once=True)
            except Exception as ex:
                ui.notify(f"Import 실패: {ex}", color='negative')
        
        async def handle_export():
            try:
                with db_session() as db:
                    csv_bytes = SpendingService.export_to_csv_bytes(db)
                ui.download(csv_bytes, filename='spending_export.csv', media_type='text/csv')
                ui.notify('Export 완료!', color='positive')
            except Exception as ex:
                ui.notify(f"Export 실패: {ex}", color='negative')

        with ui.element('div').classes('flex items-center gap-2 ml-auto'):
            # QUploader를 숨기고 버튼에서 pickFiles 메서드로 파일 선택창 열기
            hidden_upload = ui.upload(
                auto_upload=True,
                on_upload=handle_upload,
            ).props('accept=".csv"').style('display: none')

            ui.button('CSV Import', icon='upload',
                      on_click=lambda: hidden_upload.run_method('pickFiles')) \
                .props('flat dense color="green"').classes('shrink-0')

            ui.button('CSV Export', icon='download', on_click=handle_export) \
                .props('flat dense color="indigo"').classes('shrink-0')
 
        ui.timer(0.2, update_dashboard, once=True)