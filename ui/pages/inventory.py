from nicegui import ui
from datetime import datetime

from domains.inventory.service import InventoryService
from domains.inventory.schemas import InventoryCreate, InventoryUpdate, HistoryCreate
from database import db_session
from core.engine import engine

EVENT_COLORS = {'등록': 'indigo', '사용': 'green', '수정': 'orange', '삭제': 'red', '완료': 'teal'}


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


async def render_inventory():
    with ui.column().classes('w-full max-w-5xl mx-auto p-4'):
        ui.label('재고 관리').classes('text-2xl font-bold mb-4')

        refresh_callbacks = {}

        # ══════════════════════════════════════════════════════════════
        # 다이얼로그: 사용 기록
        # ══════════════════════════════════════════════════════════════
        history_state = {'item_id': None, 'item_name': '', 'current_weight': 0}

        with ui.dialog() as usage_dialog, ui.card().classes('w-[420px]'):
            ui.label('소모품 사용 기록').classes('text-lg font-bold mb-2')
            dlg_item_label    = ui.label('').classes('text-sm text-slate-500 mb-1')
            dlg_current_label = ui.label('').classes('text-sm text-blue-600 font-medium mb-3')
            dlg_weight = ui.number(label='사용 후 측정 무게(g)', value=None).props('outlined dense').classes('w-full')
            dlg_note   = ui.input(label='메모', value='사용').props('outlined dense').classes('w-full mt-2')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('취소', on_click=usage_dialog.close).props('flat')

                async def on_record():
                    if dlg_weight.value is None:
                        ui.notify('측정 무게를 입력해주세요.', color='warning')
                        return
                    try:
                        with db_session() as db:
                            result = await engine.execute(
                                'inventory', 'add_usage_history', db,
                                item_id=history_state['item_id'],
                                history_data=HistoryCreate(measured_weight=dlg_weight.value, note=dlg_note.value or '사용')
                            )
                        if result:
                            used = history_state['current_weight'] - dlg_weight.value
                            ui.notify(f"기록 완료! ({history_state['item_name']}: {used:.0f}g 사용)", color='positive')
                            usage_dialog.close()
                            for cb in refresh_callbacks.values():
                                await cb()
                        else:
                            ui.notify('품목을 찾을 수 없습니다.', color='red')
                    except Exception as e:
                        ui.notify(f'기록 실패: {e}', color='red')

                ui.button('기록', icon='check', on_click=on_record).props('elevated').classes('bg-green-600 text-white')

        def open_usage_dialog(item_id, item_name, current_weight):
            history_state.update({'item_id': item_id, 'item_name': item_name, 'current_weight': current_weight or 0})
            dlg_item_label.set_text(f'품목: {item_name}')
            dlg_current_label.set_text(f'현재 잔량: {current_weight:.0f}g' if current_weight else '잔량 정보 없음')
            dlg_weight.value = None
            dlg_note.value = '사용'
            usage_dialog.open()

        # ══════════════════════════════════════════════════════════════
        # 다이얼로그: 수정
        # ══════════════════════════════════════════════════════════════
        edit_state = {'item_id': None}

        with ui.dialog() as edit_dialog, ui.card().classes('w-[440px]'):
            ui.label('품목 수정').classes('text-lg font-bold mb-4')
            edit_name    = ui.input(label='품목명').props('outlined dense').classes('w-full')
            edit_qty     = ui.number(label='수량', value=None, min=1, step=1).props('outlined dense').classes('w-full mt-2')
            edit_weight  = ui.number(label='현재 잔량(g)', value=None).props('outlined dense').classes('w-full mt-2')
            edit_price   = ui.number(label='구매 가격(원)', value=None).props('outlined dense').classes('w-full mt-2')
            edit_memo    = ui.textarea(label='메모').props('outlined dense').classes('w-full mt-2')

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('취소', on_click=edit_dialog.close).props('flat')

                async def on_edit_save():
                    try:
                        update_data = InventoryUpdate(
                            name=edit_name.value or None,
                            quantity=int(edit_qty.value) if edit_qty.value else None,
                            current_weight=edit_weight.value,
                            price=edit_price.value,
                            memo=edit_memo.value or None,
                        )
                        with db_session() as db:
                            result = await engine.execute(
                                'inventory', 'update_item', db,
                                item_id=edit_state['item_id'], update_data=update_data
                            )
                        if result:
                            ui.notify('수정되었습니다!', color='positive')
                            edit_dialog.close()
                            for cb in refresh_callbacks.values():
                                await cb()
                        else:
                            ui.notify('품목을 찾을 수 없습니다.', color='red')
                    except Exception as e:
                        ui.notify(f'수정 실패: {e}', color='red')

                ui.button('저장', icon='save', on_click=on_edit_save).props('elevated').classes('bg-orange-500 text-white')

        def open_edit_dialog(item):
            edit_state['item_id'] = item['id']
            edit_name.value   = item['_name_raw']
            edit_qty.value    = item['_qty_raw']
            edit_weight.value = item['_weight_raw']
            edit_price.value  = item['_price_raw']
            edit_memo.value   = item['_memo_raw']
            edit_dialog.open()

        # ══════════════════════════════════════════════════════════════
        # 다이얼로그: 삭제 확인
        # ══════════════════════════════════════════════════════════════
        delete_state = {'item_id': None, 'item_name': ''}

        with ui.dialog() as delete_dialog, ui.card().classes('w-80'):
            ui.label('품목 삭제').classes('text-lg font-bold text-red-600 mb-2')
            del_label = ui.label('').classes('text-sm text-slate-600 mb-4')
            ui.label('이 작업은 되돌릴 수 없습니다. 사용 이력은 보존됩니다.').classes('text-xs text-slate-400 mb-4')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('취소', on_click=delete_dialog.close).props('flat')

                async def on_delete_confirm():
                    try:
                        with db_session() as db:
                            ok = await engine.execute(
                                'inventory', 'delete_item', db,
                                item_id=delete_state['item_id']
                            )
                        if ok:
                            ui.notify(f"'{delete_state['item_name']}' 삭제 완료", color='positive')
                            delete_dialog.close()
                            for cb in refresh_callbacks.values():
                                await cb()
                        else:
                            ui.notify('품목을 찾을 수 없습니다.', color='red')
                    except Exception as e:
                        ui.notify(f'삭제 실패: {e}', color='red')

                ui.button('삭제', icon='delete', on_click=on_delete_confirm).props('elevated').classes('bg-red-600 text-white')

        def open_delete_dialog(item_id, item_name):
            delete_state.update({'item_id': item_id, 'item_name': item_name})
            del_label.set_text(f'"{item_name}" 을(를) 삭제하시겠습니까?')
            delete_dialog.open()


        # ══════════════════════════════════════════════════════════════
        # 다이얼로그: 완료 확인
        # ══════════════════════════════════════════════════════════════
        finish_state = {'item_id': None, 'item_name': '', 'remaining': 0.0}

        with ui.dialog() as finish_dialog, ui.card().classes('w-80'):
            ui.label('품목 완료 처리').classes('text-lg font-bold text-emerald-700 mb-2')
            finish_label = ui.label('').classes('text-sm text-slate-600 mb-2')
            ui.label('남은 잔량을 전부 사용 처리하고 품목을 종료합니다.').classes('text-xs text-slate-400 mb-4')
            with ui.row().classes('w-full justify-end gap-2'):
                ui.button('취소', on_click=finish_dialog.close).props('flat')

                async def on_finish_confirm():
                    try:
                        with db_session() as db:
                            ok = await engine.execute(
                                'inventory', 'finish_item', db,
                                item_id=finish_state['item_id']
                            )
                        if ok:
                            ui.notify(f"'{finish_state['item_name']}' 완료 처리됨", color='positive')
                            finish_dialog.close()
                            for cb in refresh_callbacks.values():
                                await cb()
                        else:
                            ui.notify('품목을 찾을 수 없습니다.', color='red')
                    except Exception as e:
                        ui.notify(f'완료 처리 실패: {e}', color='red')

                ui.button('완료', icon='check_circle', on_click=on_finish_confirm) \
                    .props('elevated').classes('bg-emerald-600 text-white')

        def open_finish_dialog(item_id, item_name, remaining):
            finish_state.update({'item_id': item_id, 'item_name': item_name, 'remaining': remaining})
            finish_label.set_text(f'품목: {item_name}  |  현재 잔량: {remaining:.0f}g')
            finish_dialog.open()

        # ══════════════════════════════════════════════════════════════
        # 다이얼로그: 품목 등록
        # ══════════════════════════════════════════════════════════════
        with ui.dialog() as add_dialog, ui.card().classes('w-96'):
            ui.label('새 품목 등록').classes('text-lg font-bold mb-4')
            add_domain    = ui.select(['탈것','위생','요리','전자장비','공구','기타'], label='분야', value='기타').props('outlined dense').classes('w-full')
            add_category  = ui.select(['도구','소모품','전자장비','기타'], label='분류', value='도구').props('outlined dense').classes('w-full')
            add_name      = ui.input(label='품목명').props('outlined dense').classes('w-full')
            add_qty       = ui.number(label='수량', value=1, min=1, step=1).props('outlined dense').classes('w-full')
            add_unit_wt   = ui.number(label='개별 무게(g)', value=None).props('outlined dense').classes('w-full')
            add_total_lbl = ui.label('전체 무게: -').classes('text-xs text-slate-500 mt-1')
            add_price     = ui.number(label='구매 가격(원)', value=None).props('outlined dense').classes('w-full')
            add_memo      = ui.textarea(label='메모').props('outlined dense').classes('w-full')

            def _update_total_label():
                qty = int(add_qty.value) if add_qty.value else 1
                uw  = add_unit_wt.value
                if uw:
                    add_total_lbl.set_text(f'전체 무게: {qty * uw:.0f}g ({qty} × {uw:.0f}g)')
                else:
                    add_total_lbl.set_text('전체 무게: -')

            add_qty.on('update:model-value',    lambda _: _update_total_label())
            add_unit_wt.on('update:model-value', lambda _: _update_total_label())

            with ui.row().classes('w-full justify-end gap-2 mt-4'):
                ui.button('취소', on_click=add_dialog.close).props('flat')

                async def on_add():
                    if not add_name.value:
                        ui.notify('품목명을 입력해주세요.', color='warning')
                        return
                    qty = int(add_qty.value) if add_qty.value else 1
                    uw  = add_unit_wt.value
                    total_weight = (qty * uw) if uw else None
                    try:
                        with db_session() as db:
                            await engine.execute(
                                'inventory', 'create_item', db,
                                item_data=InventoryCreate(
                                    domain=add_domain.value, category=add_category.value,
                                    name=add_name.value,
                                    quantity=qty,
                                    start_weight=total_weight,
                                    price=add_price.value,
                                    memo=add_memo.value
                                )
                            )
                        ui.notify('품목이 등록되었습니다!', color='positive')
                        add_dialog.close()
                        for cb in refresh_callbacks.values():
                            await cb()
                    except Exception as e:
                        ui.notify(f'등록 실패: {e}', color='red')

                ui.button('등록', on_click=on_add).props('elevated').classes('bg-blue-600 text-white')

        # ══════════════════════════════════════════════════════════════
        # 최상위 탭
        # ══════════════════════════════════════════════════════════════
        with ui.card().classes('w-full shadow-sm'):
            with ui.tabs().classes('w-full') as main_tabs:
                stock_tab   = ui.tab('재고 현황', icon='inventory')
                history_tab = ui.tab('히스토리',  icon='history')

            with ui.tab_panels(main_tabs, value=stock_tab).classes('w-full bg-transparent'):

                # ─── 탭 1: 재고 현황 ──────────────────────────────────
                with ui.tab_panel(stock_tab):

                    async def handle_export():
                        try:
                            with db_session() as db:
                                csv_bytes = await engine.export_csv('inventory', db)
                            ui.download(csv_bytes, f"inventory.csv")
                        except Exception as e:
                            ui.notify(f"Export 실패: {e}", color='negative')
                            
                    async def handle_upload(e):
                        try:
                            content = await e.file.read()
                            with db_session() as db:
                                result = await engine.execute('inventory', 'restore_csv', db, content=content)
                            ui.notify(result['message'], color='positive')
                            await refresh_stock()
                        except Exception as ex:
                            ui.notify(f"Import 실패: {ex}", color='negative')

                    with ui.row().classes('w-full items-center gap-3 pt-2 pb-4'):
                        sf_domain   = ui.select(['전체','탈것','위생','요리','전자장비','공구','기타'], value='전체', label='분야').props('outlined dense').classes('w-36')
                        sf_category = ui.select(['전체','도구','소모품','전자장비','기타'], value='전체', label='분류').props('outlined dense').classes('w-36')
                        ui.button('조회', icon='search', on_click=lambda: refresh_stock()).props('elevated').classes('bg-blue-600 text-white')
                        ui.space()
                        hidden_upload_inv = ui.upload(auto_upload=True, on_upload=handle_upload).props('accept=".csv"').style('display: none')
                        ui.button('CSV Import', icon='upload', on_click=lambda: hidden_upload_inv.run_method('pickFiles')) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')
                        ui.button('CSV Export', icon='download', on_click=handle_export) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')
                        ui.button('품목 등록', icon='add', on_click=add_dialog.open).props('elevated').classes('bg-indigo-600 text-white')

                    stock_container = ui.column().classes('w-full')

                    async def refresh_stock():
                        domain   = sf_domain.value   if sf_domain.value   != '전체' else None
                        category = sf_category.value if sf_category.value != '전체' else None
                        try:
                            with db_session() as db:
                                items = await InventoryService.get_items(db, domain=domain, category=category)
                        except Exception as e:
                            ui.notify(f'조회 실패: {e}', color='red')
                            return

                        stock_container.clear()
                        with stock_container:
                            if not items:
                                ui.label('등록된 품목이 없습니다.').classes('text-slate-400 italic py-8 text-center w-full')
                                return

                            # ── 품목 테이블 ──────────────────────────
                            ui.label('품목 리스트').classes('text-base font-bold mb-2')
                            columns = [
                                {'name': 'item_no',      'label': '품목번호', 'field': 'item_no',      'align': 'center'},
                                {'name': 'domain',       'label': '분야',     'field': 'domain',       'align': 'center'},
                                {'name': 'category',     'label': '분류',     'field': 'category',     'align': 'center'},
                                {'name': 'name',         'label': '품목명',   'field': 'name',         'align': 'left'},
                                {'name': 'quantity',     'label': '수량',     'field': 'quantity',     'align': 'right'},
                                {'name': 'unit_weight',  'label': '개별무게(g)','field': 'unit_weight','align': 'right'},
                                {'name': 'start_weight', 'label': '전체무게(g)','field': 'start_weight','align': 'right'},
                                {'name': 'current_weight','label': '잔량(g)', 'field': 'current_weight','align': 'right'},
                                {'name': 'price',        'label': '구매가',   'field': 'price',        'align': 'right'},
                                {'name': 'rem_value',    'label': '잔여가치', 'field': 'rem_value',    'align': 'right'},
                                {'name': 'memo',         'label': '메모',     'field': 'memo',         'align': 'left'},
                                {'name': 'actions',      'label': '작업',     'field': 'actions',      'align': 'center'},
                            ]
                            rows = []
                            for item in items:
                                ppg = _price_per_gram(item)
                                rv  = _remaining_value(item)
                                qty = item.quantity or 1
                                uw  = (item.start_weight / qty) if item.start_weight else None
                                rows.append({
                                    'id':             item.id,
                                    'item_no':        item.item_no or '-',
                                    'domain':         item.domain,
                                    'category':       item.category,
                                    'name':           item.name,
                                    'quantity':       qty,
                                    'unit_weight':    f"{uw:.0f}" if uw is not None else '-',
                                    'start_weight':   f"{item.start_weight:.0f}" if item.start_weight is not None else '-',
                                    'current_weight': f"{item.current_weight:.0f}" if item.current_weight is not None else '-',
                                    'price':          _fmt_won(item.price),
                                    'rem_value':      _fmt_won(rv),
                                    'memo':           item.memo or '-',
                                    'is_consumable':  item.category == '소모품',
                                    '_name_raw':   item.name,
                                    '_qty_raw':    item.quantity,
                                    '_weight_raw': item.current_weight,
                                    '_price_raw':  item.price,
                                    '_memo_raw':   item.memo or '',
                                })

                            tbl = ui.table(columns=columns, rows=rows, row_key='id') \
                                .classes('w-full').props('dense flat bordered')
                            tbl.add_slot('body-cell-actions', '''
                                <q-td :props="props">
                                    <q-btn icon="edit" size="sm" dense flat color="orange"
                                        @click="$parent.$emit('edit', props.row)" />
                                    <q-btn v-if="props.row.is_consumable"
                                        icon="scale" size="sm" dense flat color="green"
                                        @click="$parent.$emit('use', props.row)" />
                                    <q-btn v-if="props.row.is_consumable"
                                        icon="check_circle" size="sm" dense flat color="teal"
                                        @click="$parent.$emit('finish', props.row)"
                                        title="완료 처리" />
                                    <q-btn icon="delete" size="sm" dense flat color="red"
                                        @click="$parent.$emit('del', props.row)" />
                                </q-td>
                            ''')
                            tbl.on('edit', lambda e: open_edit_dialog(e.args))
                            tbl.on('use',  lambda e: open_usage_dialog(
                                e.args['id'], e.args['name'],
                                float(e.args['current_weight']) if e.args['current_weight'] != '-' else 0
                            ))
                            tbl.on('del',  lambda e: open_delete_dialog(e.args['id'], e.args['name']))
                            tbl.on('finish', lambda e: open_finish_dialog(
                                e.args['id'], e.args['name'],
                                float(e.args['current_weight']) if e.args['current_weight'] != '-' else 0.0
                            ))

                            # ── 소모품 잔량 + 가치 프로그레스 ─────────
                            consumables = [i for i in items if i.category == '소모품' and i.current_weight is not None]
                            if consumables:
                                ui.separator().classes('my-4')
                                ui.label('소모품 잔량 현황').classes('text-base font-bold mb-2')
                                for item in consumables:
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
                                            ui.button(icon='scale',
                                                on_click=lambda _, iid=item.id, n=item.name, w=item.current_weight:
                                                    open_usage_dialog(iid, n, w)
                                            ).props('flat dense round color=green').tooltip('사용 기록')

                            # ── 통계 ──────────────────────────────────
                            ui.separator().classes('my-4')
                            ui.label('통계').classes('text-base font-bold mb-2')
                            domain_cnt, category_cnt = {}, {}
                            total_price = sum(i.price or 0 for i in items)
                            total_rem   = sum(_remaining_value(i) or 0 for i in items)
                            for item in items:
                                domain_cnt[item.domain]     = domain_cnt.get(item.domain, 0) + 1
                                category_cnt[item.category] = category_cnt.get(item.category, 0) + 1

                            with ui.row().classes('w-full gap-4 flex-wrap'):
                                with ui.card().classes('flex-1 p-4 shadow-sm min-w-48'):
                                    ui.label('분야별').classes('text-sm font-bold text-slate-500 mb-2')
                                    for d, cnt in domain_cnt.items():
                                        with ui.row().classes('justify-between'):
                                            ui.label(d); ui.badge(str(cnt)).props('color=blue')
                                with ui.card().classes('flex-1 p-4 shadow-sm min-w-48'):
                                    ui.label('분류별').classes('text-sm font-bold text-slate-500 mb-2')
                                    for c, cnt in category_cnt.items():
                                        with ui.row().classes('justify-between'):
                                            ui.label(c); ui.badge(str(cnt)).props('color=indigo')
                                with ui.card().classes('flex-1 p-4 shadow-sm min-w-48'):
                                    ui.label('가치 요약').classes('text-sm font-bold text-slate-500 mb-2')
                                    with ui.row().classes('justify-between'):
                                        ui.label('총 구매가')
                                        ui.label(_fmt_won(total_price)).classes('font-medium text-blue-600')
                                    with ui.row().classes('justify-between'):
                                        ui.label('총 잔여가치')
                                        ui.label(_fmt_won(total_rem)).classes('font-medium text-emerald-600')

                    refresh_callbacks['stock'] = refresh_stock

                # ─── 탭 2: 히스토리 ───────────────────────────────────
                with ui.tab_panel(history_tab):
                    hist_container = ui.column().classes('w-full')

                    item_options_state = {'by_no': {}}  # item_no → item_id

                    async def _load_item_options():
                        try:
                            with db_session() as db:
                                all_inv = await InventoryService.get_items_all(db)
                            item_options_state['by_no'] = {
                                it.item_no: it.id
                                for it in all_inv if it.item_no
                            }
                        except Exception:
                            pass

                    with ui.row().classes('w-full items-center gap-3 flex-wrap pt-2 pb-4'):
                        hf_start  = ui.input('시작일').props('type=date outlined dense').classes('w-36')
                        hf_end    = ui.input('종료일').props('type=date outlined dense').classes('w-36')
                        hf_item_no = ui.input(placeholder='품목번호 (INV-XXXX)').props('outlined dense').classes('w-44')
                        hf_search = ui.input(placeholder='메모 검색...').props('outlined dense').classes('flex-grow')
                        hf_search.on('keydown.enter', lambda: refresh_history())
                        with ui.row().classes('items-center gap-1'):
                            ui.label('구분:').classes('text-sm text-slate-500')
                            chk_reg  = ui.checkbox('등록', value=True)
                            chk_use  = ui.checkbox('사용', value=True)
                            chk_upd  = ui.checkbox('수정', value=True)
                            chk_done = ui.checkbox('완료', value=True)
                            chk_del  = ui.checkbox('삭제', value=True)
                        ui.button('조회', icon='search', on_click=lambda: refresh_history()) \
                            .props('elevated').classes('bg-blue-600 text-white')
                        ui.space()
                        hidden_upload_hist = ui.upload(auto_upload=True, on_upload=lambda e: handle_upload_history(e)).props('accept=".csv"').style('display: none')
                        ui.button('CSV Import', icon='upload', on_click=lambda: hidden_upload_hist.run_method('pickFiles')) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')
                        ui.button('CSV Export', icon='download', on_click=lambda: handle_export_history()) \
                            .props('elevated').classes('bg-indigo-600 text-white shrink-0')

                    ui.timer(0.1, _load_item_options, once=True)

                    async def handle_export_history():
                        try:
                            item_id_filter = None
                            item_no_val = hf_item_no.value.strip().upper() if hf_item_no.value else None
                            if item_no_val:
                                by_no = item_options_state.get('by_no', {})
                                item_id_filter = by_no.get(item_no_val)
                                if not item_id_filter:
                                    for no, uid in by_no.items():
                                        if no.startswith(item_no_val):
                                            item_id_filter = uid
                                            break
                            with db_session() as db:
                                csv_bytes = await engine.execute('inventory', 'export_history_csv', db, item_id=item_id_filter)
                            ui.download(csv_bytes, f"inventory_history.csv")
                        except Exception as e:
                            ui.notify(f"Export 실패: {e}", color='negative')

                    async def handle_upload_history(e):
                        try:
                            content = await e.file.read()
                            with db_session() as db:
                                result = await engine.execute('inventory', 'restore_history_csv', db, content=content)
                            ui.notify(result.get('message', 'Import 성공'), color='positive')
                            await refresh_history()
                        except Exception as ex:
                            ui.notify(f"Import 실패: {ex}", color='negative')

                    async def refresh_history():
                        raw_start = hf_start.value
                        raw_end   = hf_end.value
                        start_dt  = datetime.strptime(raw_start, '%Y-%m-%d') if raw_start else None
                        end_dt    = datetime.strptime(raw_end, '%Y-%m-%d').replace(hour=23, minute=59, second=59) if raw_end else None
                        search    = hf_search.value.strip() if hf_search.value else None
                        selected_types = [t for t, chk in [('등록', chk_reg), ('사용', chk_use), ('수정', chk_upd), ('완료', chk_done), ('삭제', chk_del)] if chk.value]
                        # 품목번호로 item_id 조회 (exact or prefix match)
                        item_no_val = hf_item_no.value.strip().upper() if hf_item_no.value else None
                        item_id_filter = None
                        if item_no_val:
                            by_no = item_options_state['by_no']
                            # 완전 일치 우선, 없으면 prefix
                            item_id_filter = by_no.get(item_no_val)
                            if not item_id_filter:
                                for no, uid in by_no.items():
                                    if no.startswith(item_no_val):
                                        item_id_filter = uid
                                        break

                        try:
                            with db_session() as db:
                                histories = await InventoryService.get_history(
                                    db,
                                    item_id=item_id_filter,
                                    start_date=start_dt, end_date=end_dt,
                                    search=search,
                                    event_types=selected_types if selected_types else None,
                                )
                        except Exception as e:
                            ui.notify(f'조회 실패: {e}', color='red')
                            return

                        h_columns = [
                            {'name': 'item_no',      'label': '품목번호',    'field': 'item_no',      'align': 'center'},
                            {'name': 'action_date',  'label': '일시',        'field': 'action_date',  'align': 'center', 'sortable': True},
                            {'name': 'event_type',   'label': '구분',        'field': 'event_type',   'align': 'center'},
                            {'name': 'item_name',    'label': '품목명',      'field': 'item_name',    'align': 'left'},
                            {'name': 'item_domain',  'label': '분야',        'field': 'item_domain',  'align': 'center'},
                            {'name': 'weight',       'label': '기록(g)',     'field': 'weight',       'align': 'right'},
                            {'name': 'usage_amount', 'label': '사용량(g)',   'field': 'usage_amount', 'align': 'right'},
                            {'name': 'usage_value',  'label': '사용 가치',   'field': 'usage_value',  'align': 'right'},
                            {'name': 'note',         'label': '메모',        'field': 'note',         'align': 'left'},
                        ]

                        # 가격 정보 맵 (item_id → price_per_gram)
                        ppg_map: dict[str, float] = {}
                        try:
                            with db_session() as db:
                                all_items = await InventoryService.get_items_all(db)
                            for it in all_items:
                                ppg = _price_per_gram(it)
                                if ppg:
                                    ppg_map[it.id] = ppg
                        except Exception:
                            pass

                        h_rows = []
                        for h in histories:
                            iname = (h.item.name if h.item else None) or h.item_name or '-'
                            # 사용 가치 계산
                            usage_val = None
                            if h.usage_amount and h.item_id and h.item_id in ppg_map:
                                usage_val = ppg_map[h.item_id] * h.usage_amount

                            if search:
                                if search.lower() not in (h.note or '').lower() and search.lower() not in iname.lower():
                                    continue

                            h_rows.append({
                                'id':           h.id,
                                'item_no':      (h.item.item_no if h.item else None) or '-',
                                'action_date':  h.action_date.strftime('%Y-%m-%d %H:%M') if h.action_date else '-',
                                'event_type':   h.event_type,
                                'item_name':    iname,
                                'item_domain':  (h.item.domain if h.item else '-'),
                                'weight':       f"{h.measured_weight:.0f}" if h.measured_weight is not None else '-',
                                'usage_amount': f"{h.usage_amount:.0f}" if h.usage_amount else '-',
                                'usage_value':  _fmt_won(usage_val),
                                'note':         h.note or '-',
                                '_color':       EVENT_COLORS.get(h.event_type, 'grey'),
                            })

                        hist_container.clear()
                        with hist_container:
                            if not h_rows:
                                ui.label('이력이 없습니다.').classes('text-slate-400 italic py-8 text-center w-full')
                                return

                            ui.label(f'총 {len(h_rows)}건').classes('text-sm text-slate-500 mb-2')
                            tbl = ui.table(columns=h_columns, rows=h_rows, row_key='id') \
                                .classes('w-full').props('dense flat bordered')
                            tbl.add_slot('body-cell-item_no', '''
                                <q-td :props="props">
                                    <q-chip dense clickable size="sm" color="blue-grey-2"
                                        text-color="blue-grey-9" icon="tag"
                                        :label="props.value"
                                        @click="$parent.$emit('filter_no', props.value)"
                                        title="클릭: 이 품목번호만 필터링" />
                                </q-td>
                            ''')
                            tbl.add_slot('body-cell-event_type', '''
                                <q-td :props="props">
                                    <q-badge :color="props.row._color" :label="props.value" />
                                </q-td>
                            ''')
                            async def _on_filter_no(e):
                                no = e.args if isinstance(e.args, str) else str(e.args)
                                if no and no != '-':
                                    hf_item_no.value = no
                                    await refresh_history()
                            tbl.on('filter_no', _on_filter_no)

                    ui.timer(0.3, refresh_history, once=True)
                    refresh_callbacks['history'] = refresh_history

        await refresh_stock()
