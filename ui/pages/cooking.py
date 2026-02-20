from nicegui import ui
from datetime import datetime

from domains.cooking.service import RecipeService
from domains.cooking.schemas import RecipeCreate, RecipeIngredientCreate, RecipeUpdate
from domains.inventory.service import InventoryService
from database import db_session


def _fmt_won(val: float | None) -> str:
    if val is None:
        return '-'
    return f"₩{val:,.0f}"


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

        cart: list[dict] = []

        with ui.card().classes('w-full shadow-sm'):
            with ui.tabs().classes('w-full') as main_tabs:
                cook_tab   = ui.tab('요리하기', icon='cooking')
                recipe_tab = ui.tab('레시피',   icon='menu_book')

            with ui.tab_panels(main_tabs, value=cook_tab).classes('w-full bg-transparent'):

                # ══════════════════════════╗
                #  탭 1: 요리하기            ║
                # ══════════════════════════╝
                with ui.tab_panel(cook_tab):
                    ui.label('재료 추가').classes('text-base font-bold mt-2 mb-3')

                    inventory_items = []

                    with ui.row().classes('w-full items-end gap-3 flex-wrap'):
                        item_select = ui.select(
                            options=[], label='재고 품목 선택'
                        ).props('outlined dense').classes('flex-grow min-w-48')

                        amount_input = ui.number(label='사용량', value=None, min=0) \
                            .props('outlined dense').classes('w-28')

                        unit_select = ui.select(
                            options=['g', 'ml', '개', '줌', '큰술', '작은술', '적당량'],
                            value='g', label='단위'
                        ).props('outlined dense').classes('w-24')

                        async def load_inventory():
                            with db_session() as db:
                                items = await InventoryService.get_items(
                                    db, domain='요리', category='소모품'
                                )
                            inventory_items.clear()
                            inventory_items.extend(items)
                            item_select.options = {
                                item.id: f"{item.name}"
                                         + (f" — 잔량 {item.current_weight:.0f}g" if item.current_weight is not None else "")
                                for item in items
                            }
                            item_select.update()

                        ui.button(icon='refresh', on_click=load_inventory) \
                            .props('flat dense round').tooltip('재고 새로고침')

                        async def add_to_cart():
                            if amount_input.value is None or amount_input.value <= 0:
                                ui.notify('사용량을 입력해주세요.', color='warning')
                                return
                            selected_id = item_select.value
                            selected_name = None
                            remaining = None

                            if selected_id:
                                matched = next((i for i in inventory_items if i.id == selected_id), None)
                                if matched:
                                    selected_name = matched.name
                                    remaining = matched.current_weight
                            else:
                                selected_name = item_select.value if isinstance(item_select.value, str) else None

                            if not selected_name:
                                ui.notify('품목을 선택하거나 이름을 입력해주세요.', color='warning')
                                return

                            amount = float(amount_input.value)
                            if remaining is not None and amount > remaining:
                                ui.notify(f'잔량({remaining:.0f}g)보다 많습니다. 재고가 0 이하로 설정될 수 있습니다.', color='warning')

                            cart.append({'item_id': selected_id, 'item_name': selected_name,
                                         'amount': amount, 'unit': unit_select.value})
                            amount_input.value = None
                            refresh_cart()

                        ui.button('재료 추가', icon='add', on_click=add_to_cart) \
                            .props('elevated').classes('bg-green-600 text-white')

                    ui.separator().classes('my-4')
                    ui.label('담은 재료').classes('text-base font-bold mb-2')
                    cart_container = ui.column().classes('w-full')

                    def refresh_cart():
                        cart_container.clear()
                        with cart_container:
                            if not cart:
                                ui.label('재료를 추가해주세요.').classes('text-slate-400 italic')
                                return
                            for idx, ing in enumerate(cart):
                                with ui.card().classes('w-full p-2 mb-1 shadow-none border'):
                                    with ui.row().classes('w-full items-center gap-3'):
                                        ui.label(f"• {ing['item_name']}").classes('flex-grow font-medium')
                                        ui.label(f"{ing['amount']:.0f} {ing['unit']}").classes('text-slate-600 w-24 text-right')
                                        ui.button(icon='close',
                                            on_click=lambda _, i=idx: (cart.pop(i), refresh_cart())
                                        ).props('flat dense round color=red')

                    refresh_cart()

                    ui.separator().classes('my-4')
                    ui.label('요리 완료').classes('text-base font-bold mb-2')

                    with ui.row().classes('w-full items-end gap-3 flex-wrap'):
                        recipe_name_input = ui.input(label='요리 이름').props('outlined dense').classes('flex-grow')
                        servings_input    = ui.number(label='인분', value=1, min=0.5, step=0.5).props('outlined dense').classes('w-24')
                        recipe_note_input = ui.input(label='메모').props('outlined dense').classes('flex-grow')

                    async def on_complete_cooking():
                        if not recipe_name_input.value:
                            ui.notify('요리 이름을 입력해주세요.', color='warning')
                            return
                        if not cart:
                            ui.notify('재료를 하나 이상 추가해주세요.', color='warning')
                            return
                        ingredients = [
                            RecipeIngredientCreate(
                                item_id=ing['item_id'], item_name=ing['item_name'],
                                amount_used=ing['amount'], unit=ing['unit'],
                            ) for ing in cart
                        ]
                        try:
                            with db_session() as db:
                                recipe = await RecipeService.create_recipe(db, RecipeCreate(
                                    name=recipe_name_input.value,
                                    servings=servings_input.value or 1,
                                    note=recipe_note_input.value or None,
                                    ingredients=ingredients,
                                ))
                            ui.notify(f'"{recipe.name}" 요리 완료! 레시피에 저장되었습니다.', color='positive')
                            cart.clear()
                            recipe_name_input.value = ''
                            recipe_note_input.value = ''
                            servings_input.value = 1
                            refresh_cart()
                            await load_inventory()
                            await refresh_recipes()
                        except Exception as e:
                            ui.notify(f'저장 실패: {e}', color='red')

                    ui.button('요리 완료 🍳', on_click=on_complete_cooking) \
                        .props('elevated').classes('bg-orange-500 text-white mt-2 w-full')

                    await load_inventory()

                # ══════════════════════════╗
                #  탭 2: 레시피             ║
                # ══════════════════════════╝
                with ui.tab_panel(recipe_tab):

                    # ─── 상세/수정 다이얼로그 ─────────────────────────
                    detail_state   = {'recipe_id': None}
                    dlg_rating_val = {'value': 0.0}

                    with ui.dialog() as detail_dialog, ui.card().classes('w-[520px] max-h-[90vh] overflow-y-auto p-5'):
                        with ui.row().classes('w-full items-center justify-between mb-3'):
                            dlg_title = ui.label('').classes('text-lg font-bold')
                            ui.button(icon='close', on_click=detail_dialog.close).props('flat dense round')

                        # 별점
                        ui.label('맛 평가').classes('text-xs font-bold text-slate-500 uppercase tracking-wide mb-1')
                        star_row = ui.row().classes('gap-0 mb-4 items-center')

                        def render_stars(rating_val):
                            star_row.clear()
                            with star_row:
                                for s in range(1, 6):
                                    filled = rating_val is not None and s <= rating_val
                                    ui.button(
                                        icon='star' if filled else 'star_border',
                                        on_click=lambda _, sv=s: set_rating(sv)
                                    ).props(f'flat dense round color={"amber" if filled else "grey-4"}')
                                rating_text = f'  {rating_val:.1f} / 5.0' if rating_val else '  평가 없음'
                                ui.label(rating_text).classes('text-sm text-slate-400 ml-1')

                        def set_rating(val):
                            if dlg_rating_val['value'] == val:
                                dlg_rating_val['value'] = 0.0
                            else:
                                dlg_rating_val['value'] = float(val)
                            render_stars(dlg_rating_val['value'] or None)

                        render_stars(None)

                        # 수정 폼
                        dlg_name     = ui.input(label='요리 이름').props('outlined dense').classes('w-full mb-2')
                        dlg_servings = ui.number(label='인분', min=0.5, step=0.5).props('outlined dense').classes('w-full mb-2')
                        dlg_note     = ui.textarea(label='메모').props('outlined dense').classes('w-full mb-3')

                        # 재료 (읽기 전용)
                        ui.label('재료').classes('text-xs font-bold text-slate-500 uppercase tracking-wide mb-1')
                        dlg_ing_row = ui.row().classes('flex-wrap gap-2 mb-4')

                        ui.separator().classes('mb-3')
                        with ui.row().classes('w-full justify-between items-center'):
                            async def on_dialog_delete():
                                with db_session() as db:
                                    await RecipeService.delete_recipe(db, detail_state['recipe_id'])
                                ui.notify('레시피 삭제됨', color='positive')
                                detail_dialog.close()
                                await refresh_recipes()

                            ui.button('삭제', icon='delete', on_click=on_dialog_delete) \
                                .props('flat color=red')

                            async def on_dialog_save():
                                upd = RecipeUpdate(
                                    name=dlg_name.value or None,
                                    servings=dlg_servings.value,
                                    rating=dlg_rating_val['value'] or None,
                                    note=dlg_note.value or None,
                                )
                                with db_session() as db:
                                    await RecipeService.update_recipe(db, detail_state['recipe_id'], upd)
                                ui.notify('저장되었습니다!', color='positive')
                                detail_dialog.close()
                                await refresh_recipes()

                            ui.button('저장', icon='save', on_click=on_dialog_save) \
                                .props('elevated').classes('bg-blue-600 text-white')

                    def open_detail_dialog(recipe):
                        detail_state['recipe_id'] = recipe.id
                        dlg_title.set_text(recipe.name)
                        dlg_name.value     = recipe.name
                        dlg_servings.value = recipe.servings or 1
                        dlg_note.value     = recipe.note or ''
                        rating = recipe.rating or 0.0
                        dlg_rating_val['value'] = rating
                        render_stars(rating if rating > 0 else None)
                        dlg_ing_row.clear()
                        total_cost = 0.0
                        has_cost   = False
                        with dlg_ing_row:
                            for ing in recipe.ingredients:
                                cost = _ingredient_cost(ing)
                                label = f"{ing.item_name} {ing.amount_used:.0f}{ing.unit}"
                                if cost:
                                    label += f" ({_fmt_won(cost)})"
                                    total_cost += cost
                                    has_cost = True
                                ui.chip(label).props('outline color=green')
                            if not recipe.ingredients:
                                ui.label('재료 없음').classes('text-slate-400 text-sm italic')
                            if has_cost:
                                ui.separator().classes('w-full mt-2')
                                with ui.row().classes('w-full justify-end items-center gap-2 mt-1'):
                                    ui.label('총 재료비').classes('text-sm text-slate-500')
                                    ui.label(_fmt_won(total_cost)).classes('font-bold text-emerald-600')
                        detail_dialog.open()

                    # ─── 레시피 목록 ──────────────────────────────────
                    with ui.row().classes('w-full items-center gap-3 pt-2 pb-4'):
                        rf_search = ui.input(placeholder='요리 이름 검색...').props('outlined dense').classes('flex-grow')
                        rf_search.on('keydown.enter', lambda: refresh_recipes())
                        ui.button('조회', icon='search', on_click=lambda: refresh_recipes()) \
                            .props('elevated').classes('bg-blue-600 text-white')

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
