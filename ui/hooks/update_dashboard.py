
from ui.common.config import ui_refs
from domains.spending.service import SpendingService
from database import engine, TABLE_NAME


async def update_dashboard():
    # ui_refs에서 안전하게 값 추출
    raw_start = ui_refs['start_date'].value
    raw_end = ui_refs['end_date'].value
    s_date = raw_start.replace('-', '.') if raw_start else None
    e_date = raw_end.replace('-', '.') if raw_end else None
    
    # search_column 객체 참조
    target_col = ui_refs['search_column'].value 
    search_val = ui_refs['search_input'].value.strip() if ui_refs['search_input'].value else None

    try:
        # 서비스 호출 (TABLE_NAME 포함)
        res = await SpendingService.get_spending_list(
            engine,
            TABLE_NAME,
            start_date=s_date, 
            end_date=e_date, 
            # search=search_val if target_col == 'content' else None, # 선택한 컬럼에 따라 처리
            limit=10000 
        )
        data = res['data']
        
        # 선택된 컬럼에 따른 클라이언트 필터링
        if search_val:
            s_lower = search_val.lower()
            data = [r for r in data if s_lower in str(r.get(target_col, '')).lower()]
            
        # --- 테이블 갱신 ---
        ui_refs['table'].rows = data

        # --- 그래프 갱신 로직 (추가) ---
        if data:
            # 1. 월별 지출 차트
            monthly_sums = {}
            for r in data:
                raw_date = str(r.get('date', ''))
                if raw_date:
                    month_key = raw_date[:7].replace('.', '-')
                    monthly_sums[month_key] = monthly_sums.get(month_key, 0) + float(r.get('outcome', 0) or 0)
            
            sorted_months = sorted(monthly_sums.keys())
            ui_refs['trend_chart'].options['xAxis']['data'] = sorted_months
            ui_refs['trend_chart'].options['series'][0]['data'] = [int(monthly_sums[m]) for m in sorted_months]
            ui_refs['trend_chart'].update()

            # 2. 잔액 흐름 차트
            balance_flow = sorted(data, key=lambda x: x.get('date', ''))
            ui_refs['balance_chart'].options['xAxis']['data'] = [d.get('date', '')[:10] for d in balance_flow]
            ui_refs['balance_chart'].options['series'][0]['data'] = [float(d.get('balance', 0)) for d in balance_flow]
            ui_refs['balance_chart'].update()

        # --- 합계 라벨 갱신 ---
        total_in = sum(float(r.get('income', 0) or 0) for r in data)
        total_out = sum(float(r.get('outcome', 0) or 0) for r in data)
        ui_refs['in_label'].set_text(f"총 입금: {int(total_in):,}원")
        ui_refs['out_label'].set_text(f"총 출금: {int(total_out):,}원")
        ui_refs['count_label'].set_text(f"조회 결과: {len(data)}건")

    except Exception as e:
        print(f"Update Error: {e}")
        ui.notify(f"데이터 로드 실패: {str(e)}", color='red')
