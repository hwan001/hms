from nicegui import ui


def scrollable_table(
    columns: list,
    rows: list,
    row_key: str = 'id',
    max_height: str = '800px',
) -> ui.table:
    """헤더 고정 + 세로 스크롤 테이블 공통 컴포넌트.

    - 외부 div에 max-height + overflow-y:auto 적용 → 스크롤 컨테이너
    - thead th position:sticky → 헤더 고정 (layout.py CSS)
    - virtual-scroll 미사용: $parent.$emit 기반 커스텀 슬롯 이벤트 정상 작동

    Usage:
        tbl = scrollable_table(columns, rows)
        tbl.props('dense flat bordered')
        tbl.add_slot(...)
        tbl.on(...)
    """
    with ui.element('div').style(f'max-height: {max_height}; overflow-y: auto;').classes('w-full'):
        tbl = ui.table(columns=columns, rows=rows, row_key=row_key, pagination={'rowsPerPage': 0})
        tbl.classes('w-full hms-scroll-table')
    return tbl
