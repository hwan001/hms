from nicegui import ui
from datetime import datetime

from domains.cooking.service import RecipeService
from domains.cooking.schemas import RecipeCreate, RecipeIngredientCreate, RecipeUpdate
from domains.inventory.service import InventoryService
from domains.inventory.schemas import HistoryCreate
from database import db_session
from core.engine import engine
from ui.common.table import scrollable_table


def _fmt_won(val: float | None) -> str:
    if val is None:
        return '-'
    return f"₩{val:,.0f}"


def _price_per_gram(item) -> float | None:
    if item.price and item.start_weight:
        return item.price / item.start_weight
    return None


def _remaining_value(item) -> float | None:
    ppg = _price_per_gram(item)
    if ppg is not None and item.current_weight is not None:
        return ppg * item.current_weight
    return None


def _ingredient_cost(ing) -> float | None:
    """재료 1개의 비용 = 단가(g) × 사용량"""
    item = getattr(ing, 'item', None)
    if item and item.price and item.start_weight and ing.amount_used:
        return (item.price / item.start_weight) * ing.amount_used
    return None


def _recipe_total_cost(recipe) -> float | None:
    costs = [_ingredient_cost(ing) for ing in recipe.ingredients]
    valid = [c for c in costs if c is not None]
    return sum(valid) if valid else None


async def render_cooking():
    with ui.column().classes('w-full max-w-5xl mx-auto p-4'):
        ui.label('요리').classes('text-2xl font-bold mb-4')

        # ══════════════════════════════════════════════════════════════
        # 재료관리 탭 공용 다이얼로그: 소모품 사용 기록
        # ══════════════════════════════════════════════════════════════
        ing_history_state = {'item_id': None, 'item_name': '', 'current_weight': 0}
        ing_refresh_cb: list = []  # refresh_ingredients 참조 보관

        with ui.dialog() as ing_usage_dialog, ui.card().classes('w-[420px]'):
            ui.label('소모품 사용 기록').classes('text-lg font-bold mb-2')
            ing_dlg_item_label    = ui.label('').classes('text-sm text-slate-500 mb-1')
            ing_dlg_current_label = ui.label('').classes('text-sm text-blue-600 font-medium mb-3')
            ing_dlg_weight = ui.number(label='사용 후 측정 무게(g)', value=None).props('outlined dense').classes('w-full')
            ing_dlg_note   = ui.input(label='메모', value='사용').props('outlined dense').classes('w-full mt-2')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('취소', on_click=ing_usage_dialog.close).props('flat')

                async def on_ing_record():
                    if ing_dlg_weight.value is None:
                        ui.notify('측정 무게를 입력해주세요.', color='warning')
                        return
                    try:
                        with db_session() as db:
                            result = await engine.execute(
                                'inventory', 'add_usage_history', db,
                                item_id=ing_history_state['item_id'],
                                history_data=HistoryCreate(
                                    measured_weight=ing_dlg_weight.value,
                                    note=ing_dlg_note.value or '사용'
                                )
                            )
                        if result:
                            used = ing_history_state['current_weight'] - ing_dlg_weight.value
                            ui.notify(
                                f"기록 완료! ({ing_history_state['item_name']}: {used:.0f}g 사용)",
                                color='positive'
                            )
                            ing_usage_dialog.close()
                            for cb in ing_refresh_cb:
                                await cb()
                        else:
                            ui.notify('품목을 찾을 수 없습니다.', color='red')
                    except Exception as e:
                        ui.notify(f'기록 실패: {e}', color='red')

                ui.button('기록', icon='check', on_click=on_ing_record) \
                    .props('elevated').classes('bg-green-600 text-white')

        def open_ing_usage_dialog(item_id, item_name, current_weight):
            ing_history_state.update({
                'item_id': item_id,
                'item_name': item_name,
                'current_weight': current_weight or 0,
            })
            ing_dlg_item_label.set_text(f'품목: {item_name}')
            ing_dlg_current_label.set_text(
                f'현재 잔량: {current_weight:.0f}g' if current_weight else '잔량 정보 없음'
            )
            ing_dlg_weight.value = None
            ing_dlg_note.value = '사용'
            ing_usage_dialog.open()

        # ══════════════════════════════════════════════════════════════

        with ui.card().classes('w-full shadow-sm'):
            with ui.tabs().classes('w-full') as main_tabs:
                recipe_tab     = ui.tab('레시피',   icon='menu_book')
                ingredient_tab = ui.tab('재료관리', icon='set_meal')

            with ui.tab_panels(main_tabs, value=recipe_tab).classes('w-full bg-transparent'):
                with ui.tab_panel(recipe_tab):

                    # ─── 상세/수정 다이얼로그 ─────────────────────────
                    detail_state = {'recipe_id': None}

                    with ui.dialog() as detail_dialog:
                        with ui.card().classes('w-[620px] max-h-[90vh] overflow-y-auto p-0'):
                            detail_content = ui.column().classes('w-full')

                    def open_detail_dialog(recipe):
                        detail_state['recipe_id'] = recipe.id
                        rating_val = {'value': recipe.rating or 0.0}

                        detail_content.clear()
                        with detail_content:
                            # ── 헤더 ──
                            with ui.row().classes('w-full items-center gap-2 px-5 py-4 border-b bg-slate-50'):
                                ui.label(recipe.name).classes('text-lg font-bold flex-1')
                                ui.button(icon='close', on_click=detail_dialog.close).props('flat dense round size=sm')

                            with ui.column().classes('w-full p-5 gap-4'):
                                # ── 별점 ──
                                ui.label('맛 평가').classes('text-xs font-bold text-slate-500 uppercase tracking-wide')
                                star_row = ui.row().classes('gap-0 items-center')

                                def render_stars(rv):
                                    star_row.clear()
                                    with star_row:
                                        for s in range(1, 6):
                                            filled = rv is not None and s <= rv
                                            ui.button(
                                                icon='star' if filled else 'star_border',
                                                on_click=lambda _, sv=s: set_rating(sv)
                                            ).props(f'flat dense round color={"amber" if filled else "grey-4"}')
                                        txt = f'  {rv:.1f} / 5.0' if rv else '  평가 없음'
                                        ui.label(txt).classes('text-sm text-slate-400 ml-1')

                                def set_rating(val):
                                    if rating_val['value'] == val:
                                        rating_val['value'] = 0.0
                                    else:
                                        rating_val['value'] = float(val)
                                    render_stars(rating_val['value'] or None)

                                render_stars(recipe.rating if recipe.rating and recipe.rating > 0 else None)

                                # ── 수정 폼 ──
                                ui.separator()
                                ui.label('기본 정보').classes('text-xs font-bold text-slate-500 uppercase tracking-wide')
                                dlg_name     = ui.input(label='요리 이름').props('outlined dense').classes('w-full')
                                with ui.row().classes('w-full gap-3'):
                                    dlg_servings = ui.number(label='인분', min=0.5, step=0.5).props('outlined dense').classes('flex-grow')
                                    dlg_note     = ui.input(label='메모').props('outlined dense').classes('flex-grow')
                                dlg_name.value     = recipe.name
                                dlg_servings.value = recipe.servings or 1
                                dlg_note.value     = recipe.note or ''

                                # ── 재료 ──
                                ui.separator()
                                ui.label('재료').classes('text-xs font-bold text-slate-500 uppercase tracking-wide mb-1')
                                total_cost = 0.0
                                has_cost   = False
                                with ui.row().classes('flex-wrap gap-2'):
                                    for ing in recipe.ingredients:
                                        cost = _ingredient_cost(ing)
                                        label = f"{ing.item_name}  {ing.amount_used:.0f}{ing.unit}"
                                        if cost:
                                            label += f"  ({_fmt_won(cost)})"
                                            total_cost += cost
                                            has_cost = True
                                        ui.chip(label).props('outline color=green')
                                    if not recipe.ingredients:
                                        ui.label('재료 없음').classes('text-slate-400 text-sm italic')
                                if has_cost:
                                    with ui.row().classes('w-full justify-end items-center gap-2'):
                                        ui.label('총 재료비').classes('text-sm text-slate-500')
                                        ui.label(_fmt_won(total_cost)).classes('font-bold text-emerald-600')

                                # ── 조리 단계 ──
                                steps = sorted(recipe.steps, key=lambda s: s.step_no) if recipe.steps else []
                                if steps:
                                    ui.separator()
                                    ui.label('조리 단계').classes('text-xs font-bold text-slate-500 uppercase tracking-wide mb-1')
                                    for step in steps:
                                        with ui.card().classes('w-full p-3 shadow-none border border-slate-200'):
                                            with ui.row().classes('items-center gap-2 mb-1'):
                                                ui.badge(f'Step {step.step_no}').props('color=indigo')
                                                if step.title:
                                                    ui.label(step.title).classes('font-semibold text-sm')
                                            if step.ingredients_note:
                                                ui.label(f'재료: {step.ingredients_note}').classes('text-xs text-slate-500 mb-1')
                                            if step.description:
                                                ui.label(step.description).classes('text-sm text-slate-700 whitespace-pre-wrap')

                                # ── 결과물 ──
                                if recipe.output_name:
                                    ui.separator()
                                    ui.label('결과물').classes('text-xs font-bold text-slate-500 uppercase tracking-wide mb-1')
                                    parts = [recipe.output_name]
                                    if recipe.output_amount is not None:
                                        parts.append(f"{recipe.output_amount:.0f}{recipe.output_unit or ''}")
                                    ui.chip(' / '.join(parts)).props('outline color=orange')

                                # ── 액션 버튼 ──
                                ui.separator()
                                with ui.row().classes('w-full justify-between items-center'):
                                    async def on_dialog_delete():
                                        with db_session() as db:
                                            await engine.execute(
                                                'cooking', 'delete_recipe', db,
                                                recipe_id=detail_state['recipe_id']
                                            )
                                        ui.notify('레시피 삭제됨', color='positive')
                                        detail_dialog.close()
                                        await refresh_recipes()

                                    ui.button('삭제', icon='delete', on_click=on_dialog_delete) \
                                        .props('flat color=red')

                                    async def on_dialog_save():
                                        upd = RecipeUpdate(
                                            name=dlg_name.value or None,
                                            servings=dlg_servings.value,
                                            rating=rating_val['value'] or None,
                                            note=dlg_note.value or None,
                                        )
                                        with db_session() as db:
                                            await engine.execute(
                                                'cooking', 'update_recipe', db,
                                                recipe_id=detail_state['recipe_id'], update_data=upd
                                            )
                                        ui.notify('저장되었습니다!', color='positive')
                                        detail_dialog.close()
                                        await refresh_recipes()

                                    ui.button('저장', icon='save', on_click=on_dialog_save) \
                                        .props('elevated').classes('bg-blue-600 text-white')

                        detail_dialog.open()

                    # ─── 레시피 추가 다이얼로그 ──────────────────────
                    with ui.dialog() as add_recipe_dialog:
                        with ui.card().classes('w-[700px] max-h-[90vh] overflow-y-auto p-0'):
                            add_recipe_content = ui.column().classes('w-full')

                    def open_add_recipe_dialog():
                        add_recipe_content.clear()
                        dlg_cart: list[dict] = []
                        dlg_steps: list[dict] = []
                        dlg_inventory_items: list = []

                        with add_recipe_content:
                            # ── 헤더 ──
                            with ui.row().classes('w-full items-center gap-2 px-4 py-3 border-b bg-slate-50'):
                                ui.label('레시피 추가').classes('text-base font-bold flex-1')
                                ui.button(icon='close', on_click=add_recipe_dialog.close).props('flat dense round size=sm')

                            with ui.column().classes('w-full p-4'):
                                # ── 재료 추가 ──
                                ui.label('재료 추가').classes('text-base font-bold mb-3')

                                with ui.row().classes('w-full items-end gap-3 flex-wrap'):
                                    dlg_item_select = ui.select(options=[], label='재고 품목 선택') \
                                        .props('outlined dense').classes('flex-grow min-w-48')
                                    dlg_amount_input = ui.number(label='사용량', value=None, min=0) \
                                        .props('outlined dense').classes('w-28')
                                    dlg_unit_select = ui.select(
                                        options=['g', 'ml', '개', '줌', '큰술', '작은술', '적당량'],
                                        value='g', label='단위'
                                    ).props('outlined dense').classes('w-24')

                                    async def dlg_load_inventory():
                                        with db_session() as db:
                                            items = await InventoryService.get_items(db, domain='요리', category='소모품')
                                        dlg_inventory_items.clear()
                                        dlg_inventory_items.extend(items)
                                        dlg_item_select.options = {
                                            item.id: f"{item.name}"
                                                     + (f" — 잔량 {item.current_weight:.0f}g" if item.current_weight is not None else "")
                                            for item in items
                                        }
                                        dlg_item_select.update()

                                    ui.button(icon='refresh', on_click=dlg_load_inventory) \
                                        .props('flat dense round').tooltip('재고 새로고침')

                                    async def dlg_add_to_cart():
                                        if dlg_amount_input.value is None or dlg_amount_input.value <= 0:
                                            ui.notify('사용량을 입력해주세요.', color='warning')
                                            return
                                        selected_id = dlg_item_select.value
                                        selected_name = None
                                        remaining = None
                                        if selected_id:
                                            matched = next((i for i in dlg_inventory_items if i.id == selected_id), None)
                                            if matched:
                                                selected_name = matched.name
                                                remaining = matched.current_weight
                                        else:
                                            selected_name = dlg_item_select.value if isinstance(dlg_item_select.value, str) else None
                                        if not selected_name:
                                            ui.notify('품목을 선택하거나 이름을 입력해주세요.', color='warning')
                                            return
                                        amount = float(dlg_amount_input.value)
                                        if remaining is not None and amount > remaining:
                                            ui.notify(f'잔량({remaining:.0f}g)보다 많습니다.', color='warning')
                                        dlg_cart.append({'item_id': selected_id, 'item_name': selected_name,
                                                         'amount': amount, 'unit': dlg_unit_select.value})
                                        dlg_amount_input.value = None
                                        dlg_refresh_cart()

                                    ui.button('재료 추가', icon='add', on_click=dlg_add_to_cart) \
                                        .props('elevated').classes('bg-green-600 text-white')

                                ui.separator().classes('my-4')
                                ui.label('담은 재료').classes('text-base font-bold mb-2')
                                dlg_cart_container = ui.column().classes('w-full')

                                def dlg_refresh_cart():
                                    dlg_cart_container.clear()
                                    with dlg_cart_container:
                                        if not dlg_cart:
                                            ui.label('재료를 추가해주세요.').classes('text-slate-400 italic')
                                            return
                                        for idx, ing in enumerate(dlg_cart):
                                            with ui.card().classes('w-full p-2 mb-1 shadow-none border'):
                                                with ui.row().classes('w-full items-center gap-3'):
                                                    ui.label(f"• {ing['item_name']}").classes('flex-grow font-medium')
                                                    ui.label(f"{ing['amount']:.0f} {ing['unit']}").classes('text-slate-600 w-24 text-right')
                                                    ui.button(icon='close',
                                                        on_click=lambda _, i=idx: (dlg_cart.pop(i), dlg_refresh_cart())
                                                    ).props('flat dense round color=red')

                                dlg_refresh_cart()

                                # ── 조리 단계 ──
                                ui.separator().classes('my-4')
                                with ui.row().classes('w-full items-center gap-2 mb-2'):
                                    ui.label('조리 단계').classes('text-base font-bold')
                                    ui.label('(선택)').classes('text-xs text-slate-400')

                                dlg_steps_container = ui.column().classes('w-full gap-2')

                                def dlg_rebuild_steps():
                                    dlg_steps_container.clear()
                                    with dlg_steps_container:
                                        if not dlg_steps:
                                            ui.label('단계를 추가해주세요.').classes('text-slate-400 italic text-sm')
                                            return
                                        for idx, step in enumerate(dlg_steps):
                                            with ui.card().classes('w-full p-3 shadow-none border border-slate-200'):
                                                with ui.row().classes('w-full items-center gap-2 mb-2'):
                                                    ui.badge(f'Step {idx + 1}').props('color=indigo')
                                                    ui.space()
                                                    ui.button(icon='delete_outline',
                                                        on_click=lambda _, i=idx: (dlg_steps.pop(i), dlg_rebuild_steps())
                                                    ).props('flat dense round color=red')
                                                ui.input(label='단계 제목 (선택)', value=step.get('title', '')) \
                                                    .props('outlined dense').classes('w-full mb-2').bind_value(step, 'title')
                                                ui.input(label='이 단계 재료 메모', value=step.get('ingredients_note', '')) \
                                                    .props('outlined dense').classes('w-full mb-2').bind_value(step, 'ingredients_note')
                                                ui.textarea(label='조리 방법 설명', value=step.get('description', '')) \
                                                    .props('outlined dense').classes('w-full').bind_value(step, 'description')

                                dlg_rebuild_steps()

                                def dlg_add_step():
                                    dlg_steps.append({'step_no': len(dlg_steps) + 1, 'title': '', 'ingredients_note': '', 'description': ''})
                                    dlg_rebuild_steps()

                                ui.button('+ 단계 추가', icon='add', on_click=dlg_add_step) \
                                    .props('flat').classes('text-indigo-600 mt-1')

                                # ── 결과물 ──
                                ui.separator().classes('my-4')
                                with ui.row().classes('w-full items-center gap-2 mb-3'):
                                    ui.label('결과물').classes('text-base font-bold')
                                    ui.label('(선택)').classes('text-xs text-slate-400')

                                with ui.row().classes('w-full items-end gap-3 flex-wrap'):
                                    dlg_output_name   = ui.input(label='결과물 이름').props('outlined dense').classes('flex-grow')
                                    dlg_output_amount = ui.number(label='수량/무게', value=None, min=0).props('outlined dense').classes('w-28')
                                    dlg_output_unit   = ui.select(
                                        options=['인분', 'g', 'ml', '개', '봉지'], value='인분', label='단위'
                                    ).props('outlined dense').classes('w-24')

                                dlg_output_to_inv = ui.checkbox('재고에 추가하기').classes('mt-2 text-sm font-medium text-indigo-700')

                                # ── 저장 ──
                                ui.separator().classes('my-4')
                                ui.label('요리 완료').classes('text-base font-bold mb-2')

                                with ui.row().classes('w-full items-end gap-3 flex-wrap'):
                                    dlg_recipe_name = ui.input(label='요리 이름').props('outlined dense').classes('flex-grow')
                                    dlg_servings    = ui.number(label='인분', value=1, min=0.5, step=0.5).props('outlined dense').classes('w-24')
                                    dlg_note_input  = ui.input(label='메모').props('outlined dense').classes('flex-grow')

                                async def dlg_on_save():
                                    if not dlg_recipe_name.value:
                                        ui.notify('요리 이름을 입력해주세요.', color='warning')
                                        return
                                    if not dlg_cart:
                                        ui.notify('재료를 하나 이상 추가해주세요.', color='warning')
                                        return
                                    ingredients = [
                                        RecipeIngredientCreate(
                                            item_id=ing['item_id'], item_name=ing['item_name'],
                                            amount_used=ing['amount'], unit=ing['unit'],
                                        ) for ing in dlg_cart
                                    ]
                                    from domains.cooking.schemas import RecipeStepCreate
                                    step_data = [
                                        RecipeStepCreate(
                                            step_no=s['step_no'],
                                            title=s.get('title') or None,
                                            description=s.get('description') or None,
                                            ingredients_note=s.get('ingredients_note') or None,
                                        ) for s in dlg_steps
                                    ]
                                    try:
                                        with db_session() as db:
                                            await engine.execute(
                                                'cooking', 'create_recipe', db,
                                                recipe_data=RecipeCreate(
                                                    name=dlg_recipe_name.value,
                                                    servings=dlg_servings.value or 1,
                                                    note=dlg_note_input.value or None,
                                                    ingredients=ingredients,
                                                    steps=step_data,
                                                    output_name=dlg_output_name.value or None,
                                                    output_amount=dlg_output_amount.value or None,
                                                    output_unit=dlg_output_unit.value or None,
                                                    output_to_inventory=dlg_output_to_inv.value,
                                                )
                                            )
                                        ui.notify(f'"{dlg_recipe_name.value}" 레시피 저장 완료!', color='positive')
                                        add_recipe_dialog.close()
                                        await refresh_recipes()
                                    except Exception as ex:
                                        ui.notify(f'저장 실패: {ex}', color='red')

                                ui.button('레시피 저장 🍳', on_click=dlg_on_save) \
                                    .props('elevated').classes('bg-orange-500 text-white mt-2 w-full')

                        ui.timer(0.1, dlg_load_inventory, once=True)
                        add_recipe_dialog.open()

                    # ─── 레시피 목록 ──────────────────────────────────
                    async def handle_export():
                        try:
                            with db_session() as db:
                                csv_bytes = await engine.export_csv('cooking', db)
                            ui.download(csv_bytes, f"recipes.csv")
                        except Exception as e:
                            ui.notify(f"Export 실패: {e}", color='negative')

                    async def handle_upload(e):
                        try:
                            content = await e.file.read()
                            with db_session() as db:
                                result = await engine.execute('cooking', 'restore_csv', db, content=content)
                            ui.notify(result['message'], color='positive')
                            await refresh_recipes()
                        except Exception as ex:
                            ui.notify(f"Import 실패: {ex}", color='negative')

                    with ui.row().classes('w-full items-center gap-3 pt-2 pb-4'):
                        rf_search = ui.input(placeholder='요리 이름 검색...').props('outlined dense').classes('flex-grow')
                        rf_search.on('keydown.enter', lambda: refresh_recipes())
                        ui.button('조회', icon='search', on_click=lambda: refresh_recipes()) \
                            .props('elevated').classes('bg-blue-600 text-white')
                        ui.space()
                        hidden_upload_rec = ui.upload(auto_upload=True, on_upload=handle_upload).props('accept=".csv"').style('display: none')
                        ui.button('CSV Import', icon='upload', on_click=lambda: hidden_upload_rec.run_method('pickFiles')) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')
                        ui.button('CSV Export', icon='download', on_click=handle_export) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')
                        ui.button('레시피 추가', icon='add', on_click=open_add_recipe_dialog) \
                            .props('elevated').classes('bg-orange-500 text-white shrink-0')

                    recipe_container = ui.column().classes('w-full')

                    async def refresh_recipes():
                        search = rf_search.value.strip() if rf_search.value else None
                        try:
                            with db_session() as db:
                                recipes = await RecipeService.get_recipes(db, search=search)
                        except Exception as e:
                            ui.notify(f'조회 실패: {e}', color='red')
                            return

                        recipe_container.clear()
                        with recipe_container:
                            if not recipes:
                                ui.label('저장된 레시피가 없습니다.').classes('text-slate-400 italic py-8 text-center w-full')
                                return

                            ui.label(f'총 {len(recipes)}개 레시피').classes('text-sm text-slate-500 mb-3')

                            for recipe in recipes:
                                _r = recipe
                                with ui.card().classes(
                                    'w-full mb-2 shadow-sm cursor-pointer hover:shadow-md transition-shadow'
                                ).on('click', lambda _, r=_r: open_detail_dialog(r)):
                                    with ui.row().classes('w-full items-center gap-3'):
                                        ui.label(recipe.created_at.strftime('%Y-%m-%d')) \
                                            .classes('text-xs text-slate-400 w-20 shrink-0')
                                        with ui.row().classes('items-center gap-2 flex-grow'):
                                            ui.label(recipe.name).classes('font-bold text-base')
                                            if recipe.servings:
                                                ui.badge(f'{recipe.servings}인분').props('color=orange')
                                        # 별점 표시
                                        if recipe.rating:
                                            full = int(recipe.rating)
                                            half = recipe.rating % 1 >= 0.5
                                            stars = '★' * full + ('½' if half else '')
                                            ui.label(stars).classes('text-amber-400 shrink-0')
                                        ui.icon('chevron_right').classes('text-slate-300 shrink-0')

                                    if recipe.note:
                                        ui.label(recipe.note).classes('text-sm text-slate-500 mt-1')
                                    if recipe.ingredients:
                                        with ui.row().classes('flex-wrap gap-1 mt-2 items-center'):
                                            for ing in recipe.ingredients:
                                                ui.chip(
                                                    f"{ing.item_name} {ing.amount_used:.0f}{ing.unit}"
                                                ).props('outline color=green dense')
                                    total_cost = _recipe_total_cost(recipe)
                                    if total_cost is not None:
                                        with ui.row().classes('items-center gap-1 mt-1'):
                                            ui.icon('payments').classes('text-emerald-500 text-sm')
                                            ui.label(f'총 재료비 {_fmt_won(total_cost)}') \
                                                .classes('text-sm font-medium text-emerald-600')

                    ui.timer(0.3, refresh_recipes, once=True)

                # ─── 탭 2: 재료관리 ───────────────────────────────────
                with ui.tab_panel(ingredient_tab):

                    with ui.row().classes('w-full items-center gap-3 pt-2 pb-3'):
                        ui.label('요리 소모품').classes('text-base font-bold flex-1')
                        ui.button(icon='refresh', on_click=lambda: refresh_ingredients()) \
                            .props('flat dense round').tooltip('새로고침')

                    ing_container = ui.column().classes('w-full')

                    async def refresh_ingredients():
                        try:
                            with db_session() as db:
                                items = await InventoryService.get_items(db, domain='요리', category='소모품')
                        except Exception as e:
                            ui.notify(f'조회 실패: {e}', color='red')
                            return

                        ing_container.clear()
                        with ing_container:
                            if not items:
                                ui.label('요리 분야 소모품이 없습니다.') \
                                    .classes('text-slate-400 italic py-8 text-center w-full')
                                return

                            # ── 요약 카드 ──────────────────────────────
                            consumables = [i for i in items if i.current_weight is not None]
                            total_rem   = sum(_remaining_value(i) or 0 for i in consumables)

                            with ui.row().classes('w-full gap-4 flex-wrap mb-4'):
                                with ui.card().classes('p-4 shadow-sm min-w-40'):
                                    ui.label('소모품').classes('text-xs font-bold text-slate-500 mb-1')
                                    ui.label(f'{len(items)}개').classes('text-xl font-bold text-indigo-600')
                                with ui.card().classes('p-4 shadow-sm min-w-40'):
                                    ui.label('총 잔여가치').classes('text-xs font-bold text-slate-500 mb-1')
                                    ui.label(_fmt_won(total_rem)).classes('text-xl font-bold text-emerald-600')

                            # ── 잔량 현황 ──────────────────────────────
                            ui.label('잔량 현황').classes('text-base font-bold mb-2')
                            with ui.element('div').style('max-height: 700px; overflow-y: auto;').classes('w-full'):
                                for item in items:
                                    start   = item.start_weight or 0
                                    current = item.current_weight or 0
                                    pct     = (current / start * 100) if start > 0 else 0
                                    color   = 'green' if pct > 50 else ('orange' if pct > 20 else 'red')
                                    rv      = _remaining_value(item)
                                    with ui.card().classes('w-full p-3 mb-2 shadow-none border'):
                                        with ui.row().classes('w-full items-center gap-3'):
                                            ui.label(item.name).classes('font-medium w-36 shrink-0')
                                            ui.linear_progress(value=pct / 100, show_value=False) \
                                                .props(f'color={color}').classes('flex-1')
                                            ui.label(f'{current:.0f}g / {start:.0f}g ({pct:.0f}%)') \
                                                .classes('text-sm text-slate-500 w-44 text-right shrink-0')
                                            if rv is not None:
                                                ui.label(f'잔여가치 {_fmt_won(rv)}') \
                                                    .classes('text-sm font-medium text-emerald-600 w-32 text-right shrink-0')
                                            ui.button(
                                                icon='scale',
                                                on_click=lambda _, iid=item.id, n=item.name, w=item.current_weight:
                                                    open_ing_usage_dialog(iid, n, w)
                                            ).props('flat dense round color=green').tooltip('사용 기록')

                    # refresh 콜백 등록 (다이얼로그에서 사용)
                    ing_refresh_cb.clear()
                    ing_refresh_cb.append(refresh_ingredients)

                    ui.timer(0.3, refresh_ingredients, once=True)
