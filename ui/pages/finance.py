import re
from calendar import monthrange
from nicegui import ui
from datetime import date

from domains.finance.service import FinanceService
from domains.finance.schemas import (
    PortfolioCreate, PortfolioUpdate,
    HoldingCreate, HoldingUpdate,
    SimulationCreate,
)
from database import db_session
from core.engine import engine

_TICKER_RE = re.compile(r'^[A-Z0-9\.\-]{1,15}$')


# ── 포맷 헬퍼 ────────────────────────────────────────────────

def _fmt(val, currency="KRW"):
    if val is None:
        return "-"
    if currency == "USD":
        return f"${val:,.2f}"
    return f"₩{val:,.0f}"


def _pct_cls(v):
    if v is None:
        return "text-slate-400"
    return "text-red-500" if v < 0 else "text-emerald-600"


def _pct(v):
    if v is None:
        return "-"
    return f"{'+'if v>=0 else ''}{v:.2f}%"


# ════════════════════════════════════════════════════════════
async def render_finance():
    with ui.column().classes("w-full max-w-6xl mx-auto p-4"):
        ui.label("금융").classes("text-2xl font-bold mb-4")

        with ui.card().classes("w-full shadow-sm"):
            with ui.tabs().classes("w-full") as main_tabs:
                portfolio_tab  = ui.tab("포트폴리오", icon="pie_chart")
                simulation_tab = ui.tab("거래 시뮬레이션", icon="show_chart")

            with ui.tab_panels(main_tabs, value=portfolio_tab).classes("w-full bg-transparent"):
                with ui.tab_panel(portfolio_tab):
                    await _portfolio_panel()
                with ui.tab_panel(simulation_tab):
                    await _simulation_panel()


# ════════════════════════════════════════════════════════════
# PORTFOLIO PANEL
# ════════════════════════════════════════════════════════════
async def _portfolio_panel():

    # ── 포트폴리오 추가 다이얼로그 ──────────────────────────
    with ui.dialog() as add_pf_dlg:
        with ui.card().classes("w-96 p-5"):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("포트폴리오 추가").classes("font-bold")
                ui.button(icon="close", on_click=add_pf_dlg.close).props("flat dense round")
            apf_name = ui.input(label="포트폴리오 이름").props("outlined dense").classes("w-full mb-2")
            apf_desc = ui.textarea(label="설명 (선택)").props("outlined dense").classes("w-full mb-3")

            async def on_add_portfolio():
                if not apf_name.value:
                    ui.notify("이름을 입력해주세요.", color="warning")
                    return
                with db_session() as db:
                    await engine.execute("finance", "create_portfolio", db,
                                         data=PortfolioCreate(name=apf_name.value.strip(),
                                                              description=apf_desc.value or None))
                ui.notify("포트폴리오 생성!", color="positive")
                apf_name.value = ""
                apf_desc.value = ""
                add_pf_dlg.close()
                await refresh_portfolios()

            ui.button("생성", icon="add", on_click=on_add_portfolio) \
                .props("elevated").classes("bg-blue-600 text-white w-full")

    # ── 포트폴리오 상세 다이얼로그 ──────────────────────────
    with ui.dialog() as pf_detail_dlg:
        with ui.card().classes("w-[820px] max-h-[92vh] overflow-y-auto p-0"):
            pf_detail_content = ui.column().classes("w-full")

    # ── 종목 수정 서브 다이얼로그 ───────────────────────────
    edit_h_state: dict = {"id": None}
    with ui.dialog() as edit_h_dlg:
        with ui.card().classes("w-[440px] p-5"):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                edit_h_title = ui.label("종목 수정").classes("font-bold")
                ui.button(icon="close", on_click=edit_h_dlg.close).props("flat dense round")
            eh_name    = ui.input(label="종목명").props("outlined dense").classes("w-full mb-2")
            with ui.row().classes("w-full gap-2 mb-2"):
                eh_qty   = ui.number(label="보유 수량", min=0).props("outlined dense").classes("flex-grow")
                eh_price = ui.number(label="평균 매입가", min=0).props("outlined dense").classes("flex-grow")
            with ui.row().classes("w-full gap-2 mb-2"):
                eh_ratio = ui.number(label="목표 비율 (%)", min=0, max=100, step=5).props("outlined dense").classes("flex-grow")
                eh_cur   = ui.select(options=["KRW", "USD"], label="통화").props("outlined dense").classes("w-24")
            eh_memo = ui.input(label="메모 (선택)").props("outlined dense").classes("w-full mb-3")

            async def on_save_holding():
                with db_session() as db:
                    await engine.execute("finance", "update_holding", db,
                                         holding_id=edit_h_state["id"],
                                         data=HoldingUpdate(
                                             name=eh_name.value or None,
                                             quantity=eh_qty.value,
                                             avg_price=eh_price.value,
                                             target_ratio=eh_ratio.value,
                                             currency=eh_cur.value,
                                             memo=eh_memo.value or None,
                                         ))
                ui.notify("저장 완료!", color="positive")
                edit_h_dlg.close()
                await reopen_portfolio_detail()
                await refresh_portfolios()

            ui.button("저장", icon="save", on_click=on_save_holding) \
                .props("elevated").classes("bg-blue-600 text-white w-full")

    open_pf_state: dict = {"id": None}

    async def reopen_portfolio_detail():
        if open_pf_state["id"]:
            await open_portfolio_detail(open_pf_state["id"])

    def open_holding_edit(h):
        edit_h_state["id"] = h.id
        edit_h_title.set_text(f"{h.ticker} 수정")
        eh_name.value  = h.name
        eh_qty.value   = h.quantity
        eh_price.value = h.avg_price
        eh_ratio.value = h.target_ratio or 0
        eh_cur.value   = h.currency
        eh_memo.value  = h.memo or ""
        edit_h_dlg.open()

    async def open_portfolio_detail(portfolio_id: str):
        open_pf_state["id"] = portfolio_id
        with db_session() as db:
            pf = await FinanceService.get_portfolio(db, portfolio_id)
        if not pf:
            return

        total_ratio = sum((h.target_ratio or 0) for h in pf.holdings)
        ratio_full  = total_ratio >= 99.5

        pf_detail_content.clear()
        with pf_detail_content:
            # ── 헤더 ──
            with ui.row().classes("w-full items-center gap-3 px-5 py-4 border-b bg-slate-50"):
                with ui.column().classes("flex-grow gap-0"):
                    ui.label(pf.name).classes("text-lg font-bold")
                    if pf.description:
                        ui.label(pf.description).classes("text-sm text-slate-500")
                ui.button(icon="close", on_click=pf_detail_dlg.close).props("flat dense round size=sm")

            with ui.column().classes("w-full p-5 gap-4"):
                # ── 비율 합계 경고 ──
                if pf.holdings:
                    ratio_color = "text-emerald-600" if abs(total_ratio - 100) < 0.5 else "text-amber-600"
                    ui.label(
                        f"비율 합계: {total_ratio:.1f}%  "
                        f"({'✓ 정상' if abs(total_ratio - 100) < 0.5 else '⚠ 100%로 맞춰주세요'})"
                    ).classes(f"text-sm font-medium {ratio_color}")

                # ── 투자 요약 ──
                total_invest = sum(h.avg_price * h.quantity for h in pf.holdings)
                if total_invest > 0:
                    ui.label(f"총 투자금액 (평균가 기준): {_fmt(total_invest)}").classes("text-sm text-slate-600")

                # ── 보유 종목 ──
                ui.separator()
                ui.label("보유 종목").classes("text-sm font-bold text-slate-600 mb-1")

                # 종목 추가 인라인 폼
                add_h_row = ui.row().classes("w-full items-end gap-2 mb-2")

                if ratio_full:
                    add_btn_label = "비율 100% 도달 - 종목 추가 불가"
                    add_btn_icon  = "block"
                else:
                    add_btn_label = "+ 종목 추가"
                    add_btn_icon  = "add"

                add_btn = ui.button(
                    add_btn_label, icon=add_btn_icon,
                    on_click=lambda: add_h_row.set_visibility(True)
                ).props("flat dense color=blue").classes("mb-2")
                add_btn.set_enabled(not ratio_full)

                with add_h_row:
                    nh_ticker = ui.input(label="종목코드 (예: AAPL)").props("outlined dense").classes("w-36")
                    nh_name   = ui.input(label="종목명").props("outlined dense").classes("flex-grow")
                    nh_qty    = ui.number(label="수량", min=0, value=0).props("outlined dense").classes("w-20")
                    nh_price  = ui.number(label="평균가", min=0, value=0).props("outlined dense").classes("w-28")
                    nh_ratio  = ui.number(
                        label="비율%", min=0, max=100 - total_ratio, value=0
                    ).props("outlined dense").classes("w-20")
                    nh_cur    = ui.select(options=["KRW", "USD"], value="USD", label="통화").props("outlined dense").classes("w-20")

                    async def on_add_holding():
                        ticker_raw = (nh_ticker.value or "").strip().upper()
                        name_raw   = (nh_name.value or "").strip()

                        if not ticker_raw or not name_raw:
                            ui.notify("종목코드와 이름을 입력하세요.", color="warning")
                            return
                        if not _TICKER_RE.match(ticker_raw):
                            ui.notify(
                                "종목코드 형식이 올바르지 않습니다. (영문/숫자/./-  최대 15자, 예: AAPL, 005930.KS)",
                                color="warning",
                            )
                            return

                        new_ratio = nh_ratio.value or 0
                        if total_ratio + new_ratio > 100.05:
                            ui.notify(
                                f"비율 합계가 100%를 초과합니다. (현재 {total_ratio:.1f}% + {new_ratio:.1f}%)",
                                color="warning",
                            )
                            return

                        with db_session() as db:
                            await engine.execute(
                                "finance", "add_holding", db,
                                data=HoldingCreate(
                                    portfolio_id=portfolio_id,
                                    ticker=ticker_raw,
                                    name=name_raw,
                                    quantity=nh_qty.value or 0,
                                    avg_price=nh_price.value or 0,
                                    target_ratio=new_ratio,
                                    currency=nh_cur.value,
                                ),
                            )
                        ui.notify("종목 추가!", color="positive")
                        add_h_row.set_visibility(False)
                        await open_portfolio_detail(portfolio_id)
                        await refresh_portfolios()

                    ui.button("추가", icon="check", on_click=on_add_holding) \
                        .props("elevated color=blue dense")

                add_h_row.set_visibility(False)

                # ── 종목 목록 ──
                if not pf.holdings:
                    ui.label("종목을 추가해주세요.").classes("text-slate-400 italic text-sm")
                else:
                    sorted_holdings = sorted(pf.holdings, key=lambda h: -(h.target_ratio or 0))
                    for h in sorted_holdings:
                        invest = h.avg_price * h.quantity
                        _h = h
                        with ui.card().classes("w-full p-3 shadow-none border"):
                            with ui.row().classes("w-full items-center gap-3"):
                                ratio_v = h.target_ratio or 0
                                ui.label(f"{ratio_v:.0f}%").classes(
                                    "text-sm font-bold w-10 text-center text-indigo-600"
                                )
                                with ui.element("div").classes("w-16 h-2 bg-slate-200 rounded overflow-hidden shrink-0"):
                                    ui.element("div").classes("h-full bg-indigo-400 rounded") \
                                        .style(f"width:{min(ratio_v, 100):.0f}%")
                                with ui.column().classes("flex-grow gap-0"):
                                    with ui.row().classes("items-center gap-2"):
                                        ui.label(h.name).classes("font-semibold text-sm")
                                        ui.chip(h.ticker).props("outline color=indigo dense size=sm")
                                    ui.label(
                                        f"{h.quantity:,.4f}주  @  {_fmt(h.avg_price, h.currency)}"
                                        f"  |  투자금액 {_fmt(invest, h.currency)}"
                                    ).classes("text-xs text-slate-500")
                                ui.button(
                                    icon="edit",
                                    on_click=lambda _, hh=_h: open_holding_edit(hh),
                                ).props("flat dense round color=blue")

                                async def on_del_h(hh=_h):
                                    with db_session() as db:
                                        await engine.execute("finance", "delete_holding", db, holding_id=hh.id)
                                    ui.notify(f"{hh.name} 삭제", color="positive")
                                    await open_portfolio_detail(portfolio_id)
                                    await refresh_portfolios()

                                ui.button(icon="delete", on_click=on_del_h).props("flat dense round color=red")

        pf_detail_dlg.open()

    # ── 포트폴리오 목록 컨테이너 ─────────────────────────────
    with ui.row().classes("w-full items-center gap-3 pt-2 pb-4"):
        ui.label("포트폴리오").classes("text-base font-bold flex-1")
        ui.button("포트폴리오 추가", icon="add", on_click=add_pf_dlg.open) \
            .props("elevated").classes("bg-blue-600 text-white shrink-0")

    pf_container = ui.column().classes("w-full")

    COLORS = ["#6366f1", "#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"]

    async def refresh_portfolios():
        with db_session() as db:
            portfolios = await FinanceService.get_portfolios(db)

        pf_container.clear()
        with pf_container:
            if not portfolios:
                ui.label("포트폴리오를 추가해주세요.").classes("text-slate-400 italic py-8 text-center w-full")
                return

            with ui.element("div").classes("w-full border rounded-lg overflow-hidden"):
                for i, pf in enumerate(portfolios):
                    _pf = pf
                    with db_session() as db:
                        full_pf = await FinanceService.get_portfolio(db, pf.id)

                    total_ratio  = sum((h.target_ratio or 0) for h in full_pf.holdings)
                    total_invest = sum(h.avg_price * h.quantity for h in full_pf.holdings)
                    ratio_ok     = abs(total_ratio - 100) < 0.5 if full_pf.holdings else False
                    border_cls   = "border-t border-slate-100" if i > 0 else ""

                    with ui.row().classes(
                        f"w-full items-center gap-3 px-4 py-3 hover:bg-slate-50 {border_cls}"
                    ):
                        # 클릭 영역 (삭제 버튼 제외)
                        with ui.row().classes("flex-grow items-center gap-4 min-w-0 cursor-pointer") \
                                .on("click", lambda _, pp=_pf: open_portfolio_detail(pp.id)):

                            with ui.column().classes("gap-0 min-w-[140px]"):
                                ui.label(_pf.name).classes("font-bold text-sm")
                                if _pf.description:
                                    ui.label(_pf.description).classes("text-xs text-slate-400 truncate max-w-[180px]")

                            ui.label(f"종목 {len(full_pf.holdings)}개").classes("text-xs text-slate-400 shrink-0")

                            badge_color = "green" if ratio_ok else "amber"
                            ui.badge(f"비율 {total_ratio:.0f}%").props(f"color={badge_color}").classes("shrink-0")

                            if total_invest > 0:
                                ui.label(_fmt(total_invest)).classes("text-sm font-medium text-slate-700 shrink-0")

                            if full_pf.holdings:
                                sorted_h = sorted(full_pf.holdings, key=lambda h: -(h.target_ratio or 0))
                                with ui.row().classes("h-2 gap-0 rounded overflow-hidden shrink-0").style("width:80px"):
                                    for j, h in enumerate(sorted_h):
                                        r = h.target_ratio or 0
                                        if r > 0:
                                            ui.element("div").style(
                                                f"width:{r:.0f}%;background:{COLORS[j % len(COLORS)]};height:8px"
                                            )

                        async def on_del_pf(pp=_pf):
                            with db_session() as db:
                                await engine.execute("finance", "delete_portfolio", db, portfolio_id=pp.id)
                            ui.notify(f'"{pp.name}" 삭제', color="positive")
                            await refresh_portfolios()

                        ui.button(icon="delete", on_click=on_del_pf) \
                            .props("flat dense round color=red size=sm")

    ui.timer(0.3, refresh_portfolios, once=True)


# ════════════════════════════════════════════════════════════
# SIMULATION PANEL
# ════════════════════════════════════════════════════════════
async def _simulation_panel():

    sim_results: dict = {}

    # ── 시뮬레이션 추가 다이얼로그 ──────────────────────────
    with ui.dialog() as new_sim_dlg:
        with ui.card().classes("w-[480px] p-5"):
            with ui.row().classes("w-full items-center justify-between mb-4"):
                ui.label("시뮬레이션 추가").classes("font-bold")
                ui.button(icon="close", on_click=new_sim_dlg.close).props("flat dense round")

            ns_name   = ui.input(label="시뮬레이션 이름").props("outlined dense").classes("w-full mb-2")
            ns_pf     = ui.select(options={}, label="포트폴리오 선택").props("outlined dense").classes("w-full mb-2")
            with ui.row().classes("w-full gap-3 mb-2"):
                ns_amount = ui.number(label="월 매수 금액", value=500_000, min=1).props("outlined dense").classes("flex-grow")
                ns_day    = ui.number(label="매수일 (1~28)", value=1, min=1, max=28).props("outlined dense").classes("w-28")
            ns_start = ui.input(
                label="시작 날짜", value=str(date.today())
            ).props("type=date outlined dense").classes("w-full mb-1")
            ui.label("※ 오늘 또는 미래 날짜도 설정 가능 — 첫 매수일은 익월 지정일부터 시작됩니다.").classes("text-xs text-slate-400 mb-3")

            async def load_portfolios_for_select():
                with db_session() as db:
                    pfs = await FinanceService.get_portfolios(db)
                ns_pf.options = {p.id: p.name for p in pfs}
                ns_pf.update()

            async def on_create_sim():
                if not ns_name.value or not ns_pf.value:
                    ui.notify("이름과 포트폴리오를 선택해주세요.", color="warning")
                    return
                if not ns_start.value:
                    ui.notify("시작 날짜를 입력해주세요.", color="warning")
                    return
                start_dt = date.fromisoformat(ns_start.value)

                data = SimulationCreate(
                    portfolio_id=ns_pf.value,
                    name=ns_name.value.strip(),
                    monthly_amount=ns_amount.value or 500_000,
                    buy_day=int(ns_day.value or 1),
                    start_date=start_dt,
                )
                with db_session() as db:
                    await engine.execute("finance", "create_simulation", db, data=data)
                ui.notify("시뮬레이션 생성!", color="positive")
                ns_name.value = ""
                new_sim_dlg.close()
                await refresh_simulations()

            ui.button("생성", icon="add", on_click=on_create_sim) \
                .props("elevated").classes("bg-indigo-600 text-white w-full")

    # ── 시뮬레이션 상세 다이얼로그 ──────────────────────────
    with ui.dialog() as sim_detail_dlg:
        with ui.card().classes("w-[820px] max-h-[92vh] overflow-y-auto p-0"):
            sim_detail_content = ui.column().classes("w-full")

    def open_sim_detail(session_id: str):
        result = sim_results.get(session_id)
        if not result or "error" in result:
            ui.notify("먼저 시뮬레이션을 실행해주세요.", color="warning")
            return

        sim_detail_content.clear()
        with sim_detail_content:
            with ui.row().classes("w-full items-center gap-3 px-5 py-4 border-b bg-slate-50"):
                with ui.column().classes("flex-grow gap-0"):
                    ui.label(result.get("_name", "")).classes("text-lg font-bold")
                    ui.label(
                        f"포트폴리오: {result['portfolio_name']}  |  "
                        f"{result['start_date']} ~ {result['end_date']}  |  "
                        f"매수 {result['buy_count']}회"
                    ).classes("text-sm text-slate-500")
                ui.button(icon="close", on_click=sim_detail_dlg.close).props("flat dense round size=sm")

            with ui.column().classes("w-full p-5 gap-4"):
                kpi_items = [
                    ("총 투자금액",   _fmt(result["total_invested"]),      "text-slate-700"),
                    ("현재 평가금액", _fmt(result["total_current_value"]),  "text-blue-600 font-bold"),
                    ("총 손익",       _fmt(result["total_pnl"]),            _pct_cls(result["total_pnl"])),
                    ("총 수익률",     _pct(result["total_pct"]),            _pct_cls(result["total_pct"])),
                ]
                with ui.row().classes("w-full gap-3"):
                    for label, val, cls in kpi_items:
                        with ui.card().classes("flex-1 p-3 shadow-none border"):
                            ui.label(label).classes("text-xs text-slate-400 mb-1")
                            ui.label(val).classes(f"text-base font-bold {cls}")

                ui.separator()
                ui.label("종목별 내역").classes("text-sm font-bold text-slate-600 mb-2")

                columns = [
                    {"name": "ticker",        "label": "종목코드", "field": "ticker",        "align": "left"},
                    {"name": "name",          "label": "종목명",   "field": "name",          "align": "left"},
                    {"name": "target_ratio",  "label": "비율",     "field": "target_ratio",  "align": "center"},
                    {"name": "shares",        "label": "매수량",   "field": "shares",        "align": "right"},
                    {"name": "avg_cost",      "label": "평균단가", "field": "avg_cost",      "align": "right"},
                    {"name": "current_price", "label": "현재가",   "field": "current_price", "align": "right"},
                    {"name": "total_cost",    "label": "투자금액", "field": "total_cost",    "align": "right"},
                    {"name": "current_value", "label": "평가금액", "field": "current_value", "align": "right"},
                    {"name": "pnl_pct",       "label": "수익률",   "field": "pnl_pct",       "align": "right"},
                ]
                rows = []
                for s in result["per_stock"]:
                    cur = s["currency"]
                    rows.append({
                        "ticker":        s["ticker"],
                        "name":          s["name"],
                        "target_ratio":  f"{s['target_ratio']:.0f}%",
                        "shares":        f"{s['shares']:,.4f}",
                        "avg_cost":      _fmt(s["avg_cost"], cur),
                        "current_price": _fmt(s["current_price"], cur) if s["current_price"] else "-",
                        "total_cost":    _fmt(s["total_cost"], cur),
                        "current_value": _fmt(s["current_value"], cur),
                        "pnl_pct":       _pct(s["pnl_pct"]),
                        "_pnl_pct_raw":  s["pnl_pct"],
                    })

                tbl = ui.table(columns=columns, rows=rows, row_key="ticker") \
                    .classes("w-full").props("dense flat bordered")
                tbl.add_slot("body-cell-pnl_pct", """
                    <q-td :props="props">
                        <span :class="props.row._pnl_pct_raw >= 0 ? 'text-green-600 font-bold' : 'text-red-500 font-bold'">
                            {{ props.value }}
                        </span>
                    </q-td>
                """)

                timeline = result.get("timeline", [])
                if len(timeline) >= 2:
                    ui.separator().classes("mt-2")
                    ui.label("포트폴리오 가치 추이").classes("text-sm font-bold text-slate-600 mb-2 mt-2")
                    dates = [t["date"] for t in timeline]
                    vals  = [t["value"] for t in timeline]
                    invs  = [t["invested"] for t in timeline]
                    ui.echart({
                        "tooltip": {"trigger": "axis"},
                        "legend": {"data": ["평가금액", "누적 투자금액"]},
                        "xAxis": {"type": "category", "data": dates},
                        "yAxis": {"type": "value"},
                        "series": [
                            {
                                "name": "평가금액",
                                "type": "line",
                                "data": vals,
                                "smooth": True,
                                "itemStyle": {"color": "#6366f1"},
                                "areaStyle": {"opacity": 0.15},
                            },
                            {
                                "name": "누적 투자금액",
                                "type": "line",
                                "data": invs,
                                "smooth": False,
                                "lineStyle": {"type": "dashed"},
                                "itemStyle": {"color": "#94a3b8"},
                            },
                        ],
                    }).classes("w-full h-64 mt-2")

        sim_detail_dlg.open()

    # ── 시뮬레이션 목록 컨테이너 ─────────────────────────────
    async def open_new_sim_dlg():
        await load_portfolios_for_select()
        ns_name.value  = ""
        ns_start.value = str(date.today())
        new_sim_dlg.open()

    with ui.row().classes("w-full items-center gap-3 pt-2 pb-4"):
        ui.label("거래 시뮬레이션").classes("text-base font-bold flex-1")
        ui.button("시뮬레이션 추가", icon="add", on_click=open_new_sim_dlg) \
            .props("elevated").classes("bg-indigo-600 text-white shrink-0")

    sim_container = ui.column().classes("w-full")

    async def refresh_simulations():
        with db_session() as db:
            sessions = await FinanceService.get_simulations(db)

        sim_container.clear()
        with sim_container:
            if not sessions:
                ui.label("시뮬레이션을 추가해주세요.").classes("text-slate-400 italic py-8 text-center w-full")
                return

            with ui.row().classes("w-full flex-wrap gap-3"):
                for s in sessions:
                    _s = s
                    result  = sim_results.get(s.id)
                    pf_name = s.portfolio.name if s.portfolio else "포트폴리오 없음"
                    today   = date.today()
                    months  = (today.year - s.start_date.year) * 12 + (today.month - s.start_date.month) + 1

                    with ui.card().classes("w-80 shadow-sm"):
                        with ui.column().classes("p-4 gap-2"):
                            with ui.row().classes("w-full items-start justify-between"):
                                with ui.column().classes("gap-0"):
                                    ui.label(_s.name).classes("font-bold text-base")
                                    ui.label(pf_name).classes("text-xs text-indigo-600")

                                async def on_del_sim(ss=_s):
                                    with db_session() as db:
                                        await engine.execute("finance", "delete_simulation", db, session_id=ss.id)
                                    sim_results.pop(ss.id, None)
                                    ui.notify(f'"{ss.name}" 삭제', color="positive")
                                    await refresh_simulations()

                                ui.button(icon="delete", on_click=on_del_sim).props("flat dense round color=red size=sm")

                            ui.separator()

                            ui.label(
                                f"{s.start_date} ~ {today}  ({months}개월)"
                            ).classes("text-xs text-slate-500")
                            ui.label(
                                f"매월 {s.buy_day}일  /  {_fmt(s.monthly_amount)} 매수"
                            ).classes("text-xs text-slate-500")

                            if result and "error" not in result:
                                if result["buy_count"] == 0:
                                    next_buy = result.get("next_buy_date", "-")
                                    ui.label("아직 매수 이력 없음").classes("text-xs text-slate-400 italic")
                                    ui.label(f"다음 매수 예정일: {next_buy}").classes("text-xs text-indigo-500")
                                else:
                                    with ui.row().classes("w-full items-center gap-2 mt-1"):
                                        ui.label(_fmt(result["total_invested"])).classes("text-xs text-slate-500")
                                        ui.icon("arrow_forward").classes("text-xs text-slate-300")
                                        ui.label(_fmt(result["total_current_value"])).classes("text-sm font-bold text-blue-600")
                                    ui.label(_pct(result["total_pct"])).classes(
                                        f"text-xl font-bold {_pct_cls(result['total_pct'])}"
                                    )
                            elif result and "error" in result:
                                ui.label(f"오류: {result['error']}").classes("text-xs text-red-500")
                            else:
                                ui.label("실행 전").classes("text-xs text-slate-300 italic")

                            with ui.row().classes("w-full gap-2 mt-1"):
                                async def on_run(ss=_s):
                                    ui.notify(f'"{ss.name}" 시뮬레이션 실행 중...', color="info")
                                    with db_session() as db:
                                        r = await FinanceService.run_simulation(db, ss.id)
                                    r["_name"] = ss.name
                                    sim_results[ss.id] = r
                                    if "error" in r:
                                        ui.notify(f"실패: {r['error']}", color="negative")
                                    else:
                                        ui.notify("완료!", color="positive")
                                    await refresh_simulations()

                                ui.button("실행", icon="play_arrow", on_click=on_run) \
                                    .props("elevated dense").classes("bg-teal-600 text-white flex-1")

                                res = sim_results.get(_s.id)
                                detail_enabled = bool(res and "error" not in res)
                                ui.button(
                                    "상세", icon="bar_chart",
                                    on_click=lambda _, ss=_s: open_sim_detail(ss.id),
                                ).props("outlined dense").classes("flex-1") \
                                 .set_enabled(detail_enabled)

    ui.timer(0.3, refresh_simulations, once=True)
