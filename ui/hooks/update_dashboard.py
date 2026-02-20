
from ui.common.config import ui_refs
from domains.spending.service import SpendingService
from database import db_session

async def update_dashboard():
    # ui_refs에서 안전하게 값 추출
    raw_start = ui_refs['start_date'].value
    raw_end = ui_refs['end_date'].value
    s_date = raw_start.replace('-', '.') if raw_start else None
    e_date = raw_end.replace('-', '.') if raw_end else None
    
    # search_column 객체 참조
    target_col = ui_refs['search_column'].value 
    search_val = ui_refs['search_input'].value.strip() if ui_refs['search_input'].value else None

    # limit은 서비스에서 기본값(20)이 있지만, 필요하다면 override. 
    # 기존 코드에서는 limit=10000 으로 되어 있었으나, 
    # service.py의 get_spending_list signature는 (db, category, start_date, end_date, page, size, search) 임.
    # size=10000 으로 매핑해야 함.

    try:
        with db_session() as db:
            # 서비스 호출
            res = await SpendingService.get_spending_list(
                db,
                category=None, # 여기서 카테고리 필터링은 클라이언트단에서 하던가, 아니면 select box 값을 넘겨야 함. 
                               # 기존 코드에는 category 인자가 없었음.
                start_date=s_date, 
                end_date=e_date, 
                size=10000,
                search=search_val if target_col in ['content', 'memo'] else None # search 인자는 content/memo 검색용
            )
        data = res['data']
        
        # 선택된 컬럼에 따른 클라이언트 필터링 (서비스에서 search 로 커버 안되는 부분)
        # 서비스의 search는 content, memo 에 대한 like 검색임.
        # 기존 코드는 target_col이 무엇이든 search_val이 있으면 필터링을 시도했음.
        
        if search_val:
             # 서비스 search가 이미 적용되었을 수 있지만, 
             # target_col이 category나 type인 경우 등 정밀 필터링을 위해 유지하거나 보완
            s_lower = search_val.lower()
            data = [r for r in data if s_lower in str(r.get(target_col, '')).lower()]
            
        # --- 테이블 갱신 ---
        ui_refs['table'].rows = data

        # --- KPI 카드 갱신 ---
        if data:
            total_income = sum(float(r.get('income', 0) or 0) for r in data)
            total_outcome = sum(float(r.get('outcome', 0) or 0) for r in data)
            unique_categories = {r.get('category') for r in data if r.get('category')}

            ui_refs['kpi_month_title'].set_text('지출 합계')
            net = total_income - total_outcome
            net_text = f'{int(net):,} 원 (입금 : {int(total_income):,}원, 출금 : {int(total_outcome):,}원)'
            net_color = 'color: #dc2626' if net > 0 else 'color: #2563eb'  # red-600 / blue-600
            ui_refs['kpi_month_amount'].set_text(net_text)
            ui_refs['kpi_month_amount'].style(net_color)
            ui_refs['kpi_category_count'].set_text(f'{len(unique_categories)} 개')
        else:
            ui_refs['kpi_month_title'].set_text('지출 합계')
            ui_refs['kpi_month_amount'].set_text('0 원')
            ui_refs['kpi_category_count'].set_text('0 개')

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
            if int(total_income - total_outcome) > 0:
                ui_refs['trend_chart'].options['series'][0]['itemStyle']['color'] = 'red'
            else:
                ui_refs['trend_chart'].options['series'][0]['itemStyle']['color'] = 'blue'
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
