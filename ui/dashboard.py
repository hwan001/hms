from nicegui import ui
import pandas as pd
import traceback  # 에러 상세 추적을 위해 추가

from domains.spending.service import SpendingService
from database import engine, TABLE_NAME
from ui.common.config import ui_refs

async def render_dashboard():
    # 1. 기초 데이터 로드
    try:
        stats = await SpendingService.get_stats(engine, TABLE_NAME)
        balance = int(stats.get('current_balance', 0))
        available_categories = [c['name'] for c in stats.get('category_distribution', [])]
    except Exception as e:
        ui.notify(f"데이터 로드 실패: {e}", color='red')
        return

    with ui.column().classes('w-full max-w-5xl mx-auto p-4 gap-6'):
        ui.label('📊 대시보드').classes('text-2xl font-bold mb-2')
        
        # KPI 섹션 (기존과 동일)
        with ui.row().classes('w-full justify-between gap-4'):
            latest_month = stats['monthly_trend'][-1] if stats['monthly_trend'] else {'month': '-', 'amount': 0}
            with ui.card().classes('flex-1 shadow-sm'):
                ui.label(f"이번 달 지출 ({latest_month['month']})").classes('text-slate-500 text-sm')
                ui.label(f"{int(latest_month['amount']):,} 원").classes('text-2xl font-bold text-blue-600')
            with ui.card().classes('flex-1 shadow-sm'):
                ui.label("소비 카테고리 수").classes('text-slate-500 text-sm')
                ui.label(f"{len(stats['category_distribution'])} 개").classes('text-2xl font-bold text-indigo-600')

        # --- 소비 시뮬레이션 섹션 ---
        ui.label('🎯 소비 생존 예측 시뮬레이션').classes('text-xl font-bold mt-4')
        
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
                        
                        # Service 호출
                        res = await SpendingService.get_combined_burn_rate_analysis(
                            engine, TABLE_NAME, selected_items, total_budget
                        )
                       
                        loading.delete()

                        if res['status'] == 'success':
                            with ui.card().classes('w-full p-6 bg-white border-2 border-indigo-100 shadow-md'):
                                with ui.row().classes('w-full justify-between items-center'):
                                    ui.label('🎯 생존 시뮬레이션 결과').classes('text-xl font-bold text-indigo-900')
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
                    # ✅ 상세 에러를 로그에 찍고 사용자에게 알림
                    print(f"Update Error Traceback: {traceback.format_exc()}")
                    ui.notify(f"실행 중 오류 발생: {str(e)}", color='red')

            # 초기 안내 문구
            with result_container:
                ui.label('카테고리를 선택하고 버튼을 누르세요.').classes('text-slate-400 italic')