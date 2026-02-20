from nicegui import ui
import traceback  # 에러 상세 추적을 위해 추가

from domains.spending.service import SpendingService
from database import db_session
from ui.pages.list import render_list

async def render_simulator():
    try:
        with db_session() as db:
            stats = await SpendingService.get_stats(db)
            balance = int(stats.get('current_balance', 0))
            available_categories = [c['name'] for c in stats.get('category_distribution', [])]
    except Exception as e:
        ui.notify(f"데이터 로드 실패: {e}", color='red')
        return

    ui.label('소비 생존 예측 시뮬레이션').classes('text-xl font-bold mt-4')
    
    with ui.card().classes('w-full bg-slate-50 p-6 shadow-none border border-slate-200'):
        with ui.row().classes('w-full items-center gap-4 mb-4'):
            # 멀티 셀렉트
            category_select = ui.select(
                options=available_categories, 
                label='카테고리 다중 선택',
                multiple=True  
            ).props('outlined dense use-chips').classes('flex-grow bg-white')
            
            ui.label('기준 예산:').classes('font-medium ml-4')
            budget_input = ui.number(value=balance, format='%.0f').props('outlined dense').classes('w-44 bg-white')

            # ✅ 버튼 클릭 시 실행될 함수를 여기서 정의하거나 람다로 연결
            async def handle_click():
                ui.notify('분석을 시작합니다...', color='info') # 동작 확인용
                await update_multi_analysis()

            ui.button('통합 분석', icon='analytics', on_click=handle_click) \
                .props('elevated').classes('bg-indigo-600 text-white px-6')
        
        ui.separator().classes('my-4')
        result_container = ui.column().classes('w-full')

        # 2. 통합 분석 실행 함수
        async def update_multi_analysis():
            try:
                selected_items = category_select.value
                total_budget = budget_input.value
                
                if not selected_items:
                    ui.notify('분석할 카테고리를 먼저 선택해주세요!', color='warning')
                    return

                result_container.clear()
                with result_container:
                    loading = ui.spinner(size='lg')
                    
                    with db_session() as db:
                        res = await SpendingService.get_combined_burn_rate_analysis(
                            db, selected_items, total_budget
                        )
                    
                    loading.delete()

                    if res['status'] == 'success':
                        with ui.card().classes('w-full p-6 bg-white border-2 border-indigo-100 shadow-md'):
                            with ui.row().classes('w-full justify-between items-center'):
                                ui.label('생존 시뮬레이션 결과').classes('text-xl font-bold text-indigo-900')
                                ui.label(f"분석 대상: {', '.join(selected_items)}").classes('text-sm text-slate-400')
                            
                            ui.separator().classes('my-4')
                            
                            with ui.row().classes('w-full gap-8'):
                                with ui.column().classes('flex-1'):
                                    ui.label('소비 페이스 (기준)').classes('text-xs text-slate-400 font-bold mb-2')
                                    ui.label(f"일평균 {int(res['combined_avg_daily']):,}원 지출 중").classes('text-lg font-medium')
                                    ui.label(f"설정 예산: {int(res['total_budget']):,}원").classes('text-slate-500')
                                
                                with ui.column().classes('flex-1 items-center bg-green-50 p-4 rounded-xl'):
                                    ui.label('예상 버틸 수 있는 기간').classes('text-sm text-green-600 mb-1')
                                    
                                    days_val = res['days_left']
                                    display_text = f"{days_val}일" if isinstance(days_val, int) else days_val
                                    ui.label(display_text).classes('text-4xl font-black text-green-600')

                            ui.label("이 예산은 현재 소비 습관 유지 시 위 기간 동안 사용 가능합니다.").classes('text-xs mt-6 text-slate-400')
                    else:
                        reason = res.get('reason', '알 수 없는 오류')
                        ui.notify(f"분석 실패: {reason}", color='red', duration=5)

            except Exception as e:
                print(f"Update Error Traceback: {traceback.format_exc()}")
                ui.notify(f"실행 중 오류 발생: {str(e)}", color='red')

        with result_container:
            ui.label('카테고리를 선택하고 버튼을 누르세요.').classes('text-slate-400 italic')

async def render_budget():
    with ui.column().classes('w-full max-w-6xl mx-auto p-4 gap-6'):
        ui.label('대시보드').classes('text-2xl font-bold mb-2')
        with ui.card().classes('w-full shadow-sm'):
            with ui.tabs().classes('w-full') as tabs:
                stat_tab = ui.tab('상세 통계', icon='pie_chart')
                list_tab = ui.tab('거래 내역 조회', icon='list')
                simulator_tab = ui.tab('생존 시뮬레이터', icon='monitor')
            
            # 2. 탭 패널 (컨텐츠 영역)
            with ui.tab_panels(tabs, value=list_tab).classes('w-full bg-transparent'):
                with ui.tab_panel(list_tab):
                    ui.label('거래 내역 리스트').classes('text-lg font-bold mb-2')
                    await render_list()

                with ui.tab_panel(stat_tab):
                    ui.label('카테고리별 상세 분석').classes('text-lg font-bold mb-2')
                    with ui.row().classes('w-full gap-4'):
                        with ui.card().classes('flex-1 p-4'):
                            ui.label('이번 주 지출 흐름').classes('text-sm text-slate-500')

                with ui.tab_panel(simulator_tab):
                    ui.label('생존 시뮬레이터').classes('text-lg font-bold mb-2')
                    with ui.row().classes('w-full gap-4'):
                        with ui.card().classes('flex-1 p-4'):
                            await render_simulator()
