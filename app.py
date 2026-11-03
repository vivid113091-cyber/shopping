"""쇼핑 리스트 Streamlit 앱."""

import html

import streamlit as st

from storage import (
    MAX_NAME_LENGTH,
    MAX_QUANTITY,
    add_item,
    clear_checked,
    delete_item,
    find_item,
    load_items,
    save_items,
    set_checked,
    update_item,
    validate_name,
)

st.set_page_config(page_title="쇼핑 리스트", page_icon="🛒")

FILTER_OPTIONS = ["전체", "미구매", "구매 완료"]
MISSING_ITEM_MSG = "이미 삭제된 아이템입니다. 다른 탭에서 변경되었을 수 있어요."


# ---------------------------------------------------------------------------
# 상태 및 공통 헬퍼
# ---------------------------------------------------------------------------
def init_state() -> None:
    # 데이터의 기준은 항상 파일이다. 세션에 목록을 캐시해 두면 다른 탭/세션의 변경을
    # 이전 목록으로 덮어써 데이터가 사라지므로, 매 실행마다 파일에서 다시 읽는다.
    # 주의: "items"는 session_state의 dict 메서드(.items())와 이름이 겹치므로 사용하지 않는다.
    st.session_state.shopping_items = load_items()
    if "editing_id" not in st.session_state:
        st.session_state.editing_id = None
    if "flash" not in st.session_state:
        st.session_state.flash = []


def fresh_items() -> list[dict]:
    """콜백에서 사용할 최신 목록 (화면을 그린 뒤 다른 탭에서 바뀌었을 수 있음)."""
    return load_items()


def commit(items: list[dict]) -> None:
    """변경된 목록을 세션에 반영하고 즉시 파일에 저장한다."""
    st.session_state.shopping_items = items
    save_items(items)


def flash(kind: str, message: str, area: str = "add") -> None:
    """콜백에서 생성한 메시지를 다음 렌더링 때 표시하기 위해 보관한다.

    area: 메시지를 표시할 위치 ("add" = 추가 폼 아래, "edit" = 편집 중인 행 아래)
    """
    st.session_state.flash.append((kind, message, area))


def name_html(name: str, checked: bool) -> str:
    """아이템 이름을 HTML 블록으로 만든다.

    줄 맨 앞이 <div>인 HTML 블록 안은 마크다운으로 파싱되지 않으므로
    (굵게/링크 자동 변환/LaTeX/이모지 단축코드 모두 무시) html.escape만으로 안전하다.
    """
    text = html.escape(name)
    if checked:
        return f"<div class='item-name done'><s>{text}</s></div>"
    return f"<div class='item-name'>{text}</div>"


def _normalize(name: str) -> str:
    return "".join(name.split()).casefold()


# ---------------------------------------------------------------------------
# 콜백
# ---------------------------------------------------------------------------
def on_add() -> None:
    name = st.session_state.get("new_name", "")
    quantity = st.session_state.get("new_qty", 1)
    error = validate_name(name)
    if error:
        flash("warning", error)
        return
    items = fresh_items()
    if any(_normalize(i["name"]) == _normalize(name) for i in items):
        flash("info", "이미 목록에 있는 아이템입니다. 그래도 추가했어요.")
    commit(add_item(items, name, quantity))
    flash("toast", f"'{name.strip()}' 추가됨")


def on_toggle(item_id: str) -> None:
    # 뒤집기(toggle) 대신 체크박스의 현재 값을 그대로 저장해, 화면이 오래된 경우에도
    # 사용자가 본 대로 반영되게 한다.
    items = fresh_items()
    if find_item(items, item_id) is None:
        flash("warning", MISSING_ITEM_MSG)
        return
    commit(set_checked(items, item_id, st.session_state.get(f"chk_{item_id}", False)))


def on_start_edit(item_id: str) -> None:
    st.session_state.editing_id = item_id


def on_save_edit(item_id: str) -> None:
    name = st.session_state.get(f"name_{item_id}", "")
    quantity = st.session_state.get(f"qty_{item_id}", 1)
    error = validate_name(name)
    if error:
        flash("warning", error, area="edit")
        return  # 편집 모드 유지
    items = fresh_items()
    if find_item(items, item_id) is None:
        st.session_state.editing_id = None
        flash("warning", MISSING_ITEM_MSG)
        return
    commit(update_item(items, item_id, name, quantity))
    st.session_state.editing_id = None
    flash("toast", "수정되었습니다")


def on_cancel_edit() -> None:
    st.session_state.editing_id = None


def on_delete(item_id: str) -> None:
    items = fresh_items()
    target = find_item(items, item_id)
    if target is not None:
        commit(delete_item(items, item_id))
    if st.session_state.editing_id == item_id:
        st.session_state.editing_id = None
    if target:
        flash("toast", f"'{target['name']}' 삭제됨")


def on_clear_checked() -> None:
    items = fresh_items()
    remaining = clear_checked(items)
    removed = len(items) - len(remaining)
    if st.session_state.editing_id not in {i["id"] for i in remaining}:
        st.session_state.editing_id = None
    commit(remaining)
    flash("toast", f"구매 완료 항목 {removed}개 삭제됨")


@st.dialog("전체 삭제")
def confirm_clear_all() -> None:
    st.write(f"쇼핑 리스트의 아이템 {len(st.session_state.shopping_items)}개를 모두 삭제할까요?")
    st.write("이 작업은 되돌릴 수 없습니다.")
    col_ok, col_cancel = st.columns(2)
    if col_ok.button("삭제", type="primary", width="stretch"):
        commit([])
        st.session_state.editing_id = None
        flash("toast", "모든 아이템이 삭제되었습니다")
        st.rerun()
    if col_cancel.button("취소", width="stretch"):
        st.rerun()


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------
# 아이템 카드는 key 접두사로 CSS를 구분한다:
#   row_{id} = 미구매 카드, done_{id} = 구매 완료 카드, editrow_{id} = 편집 중 카드
STYLE = """
<style>
/* 헤더 */
.app-subtitle { color: #5F6F60; margin: -0.75rem 0 1rem; }
.summary { display: flex; gap: .5rem; margin-bottom: .75rem; }
.summary .stat {
    flex: 1; background: #fff; border: 1px solid #DCE5DB; border-radius: .75rem;
    padding: .6rem .5rem; text-align: center;
}
.summary .num { display: block; font-size: 1.5rem; font-weight: 700; line-height: 1.2; }
.summary .lbl { font-size: .8rem; color: #5F6F60; }
.summary .stat.left .num { color: #E65100; }
.summary .stat.done .num { color: #2E7D32; }

/* 아이템 이름 / 수량 배지 */
.item-name { overflow-wrap: anywhere; word-break: break-word; line-height: 1.45; }
.item-name.done { color: #9AA59B; }
.qty-badge {
    display: inline-block; min-width: 2.2rem; padding: .1rem .5rem; border-radius: 999px;
    background: #EAF2E9; color: #2E7D32; font-size: .85rem; font-weight: 600; text-align: center;
}
.done-badge { background: #EEF0EE; color: #9AA59B; }

/* 카드 행: 모바일(<640px)에서도 열이 세로로 쌓이지 않고 한 줄 유지 */
[class*="st-key-row_"] [data-testid="stHorizontalBlock"],
[class*="st-key-done_"] [data-testid="stHorizontalBlock"],
[class*="st-key-editrow_"] [data-testid="stHorizontalBlock"],
.st-key-addbox [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; gap: .4rem !important;
}
[class*="st-key-row_"] [data-testid="stColumn"],
[class*="st-key-done_"] [data-testid="stColumn"],
[class*="st-key-editrow_"] [data-testid="stColumn"],
.st-key-addbox [data-testid="stColumn"] {
    min-width: 0 !important; width: auto !important; flex: 0 0 auto !important;
}
/* 이름(또는 이름 입력) 열만 남는 폭을 모두 차지 */
[class*="st-key-row_"] [data-testid="stColumn"]:nth-child(2),
[class*="st-key-done_"] [data-testid="stColumn"]:nth-child(2),
[class*="st-key-editrow_"] [data-testid="stColumn"]:first-child,
.st-key-addbox [data-testid="stColumn"]:first-child {
    flex: 1 1 auto !important;
}
.st-key-addbox [data-testid="stColumn"]:nth-child(2),
[class*="st-key-editrow_"] [data-testid="stColumn"]:nth-child(2) { width: 7.5rem !important; }

/* 편집 카드의 저장/취소 버튼 행은 같은 폭으로 */
[class*="st-key-editrow_"] [class*="st-key-editbtns_"] [data-testid="stColumn"]:nth-child(n) {
    flex: 1 1 0 !important; width: auto !important;
}

/* 카드 스타일 */
[class*="st-key-row_"] { background: #fff; }
[class*="st-key-done_"] { background: #FAFBFA; }
[class*="st-key-editrow_"] {
    background: #F1F8F0; border-color: #2E7D32 !important; box-shadow: 0 0 0 1px #2E7D32;
}
[class*="st-key-row_"] button, [class*="st-key-done_"] button { padding: 0 .35rem; min-height: 2rem; }
/* 마크다운 기본 음수 하단 여백(-1rem) 때문에 이름이 아래로 처지는 문제 보정 */
[class*="st-key-row_"] [data-testid="stMarkdownContainer"],
[class*="st-key-done_"] [data-testid="stMarkdownContainer"] { margin-bottom: 0 !important; }

/* 모바일: 수량 입력 폭을 줄여 이름 입력 공간 확보 */
@media (max-width: 640px) {
    .st-key-addbox [data-testid="stColumn"]:nth-child(2),
    [class*="st-key-editrow_"] [data-testid="stColumn"]:nth-child(2) { width: 5.5rem !important; }
    .summary .num { font-size: 1.25rem; }
}
</style>
"""


def render_flash(area: str) -> None:
    """해당 위치(area)의 메시지를 표시하고 큐에서 제거한다. 토스트는 위치와 무관하게 표시한다."""
    remaining = []
    for kind, message, msg_area in st.session_state.flash:
        if kind == "toast":
            st.toast(message, icon="✅")
        elif msg_area != area:
            remaining.append((kind, message, msg_area))
        elif kind == "warning":
            st.warning(message, icon="⚠️")
        else:
            st.info(message, icon="ℹ️")
    st.session_state.flash = remaining


def render_header() -> None:
    st.title("🛒 쇼핑 리스트")
    st.html("<p class='app-subtitle'>오늘 살 것들을 정리해 보세요</p>")
    items = st.session_state.shopping_items
    total = len(items)
    done = sum(1 for i in items if i.get("checked"))
    ratio = done / total if total else 0.0
    st.html(
        "<div class='summary'>"
        f"<div class='stat'><span class='num'>{total}</span><span class='lbl'>전체</span></div>"
        f"<div class='stat left'><span class='num'>{total - done}</span>"
        "<span class='lbl'>남은 항목</span></div>"
        f"<div class='stat done'><span class='num'>{done}</span><span class='lbl'>완료</span></div>"
        "</div>"
    )
    st.progress(ratio, text=f"{done} / {total} 구매 완료")
    if total and done == total:
        st.success("🎉 장보기 완료! 모든 아이템을 구매했어요.")


def render_add_form() -> None:
    with st.container(key="addbox"):
        with st.form("add_form", clear_on_submit=True):
            col_name, col_qty, col_btn = st.columns([5, 2, 1.3], vertical_alignment="bottom")
            col_name.text_input(
                "아이템 이름",
                key="new_name",
                max_chars=MAX_NAME_LENGTH,
                placeholder="예: 우유, 계란, 사과",
            )
            col_qty.number_input(
                "수량", key="new_qty", min_value=1, max_value=MAX_QUANTITY, value=1, step=1
            )
            col_btn.form_submit_button("추가", type="primary", on_click=on_add, width="stretch")
    render_flash("add")


def render_filter() -> str:
    return st.radio(
        "필터", FILTER_OPTIONS, key="filter", horizontal=True, label_visibility="collapsed"
    )


def _render_view_row(item: dict) -> None:
    item_id = item["id"]
    checked = item.get("checked", False)
    with st.container(border=True, key=f"{'done' if checked else 'row'}_{item_id}"):
        col_chk, col_name, col_qty, col_edit, col_del = st.columns(
            [0.5, 6, 1.1, 0.6, 0.6], vertical_alignment="center", gap="small"
        )
        # 위젯 상태를 매번 데이터 값으로 맞춘다 (value= 대신). 다른 탭에서 바뀐 체크 상태가
        # 이전 위젯 상태에 가려지지 않게 하기 위함.
        st.session_state[f"chk_{item_id}"] = checked
        col_chk.checkbox(
            "구매 완료",
            key=f"chk_{item_id}",
            on_change=on_toggle,
            args=(item_id,),
            label_visibility="collapsed",
        )
        col_name.markdown(name_html(item["name"], checked), unsafe_allow_html=True)
        badge_class = "qty-badge done-badge" if checked else "qty-badge"
        # <div>로 시작해야 <p>로 감싸지지 않아 세로 정렬이 맞는다.
        col_qty.markdown(
            f"<div><span class='{badge_class}'>x{int(item['quantity'])}</span></div>",
            unsafe_allow_html=True,
        )
        col_edit.button(
            "✏️",
            key=f"edit_{item_id}",
            type="tertiary",
            help="수정",
            on_click=on_start_edit,
            args=(item_id,),
        )
        col_del.button(
            "🗑️",
            key=f"del_{item_id}",
            type="tertiary",
            help="삭제",
            on_click=on_delete,
            args=(item_id,),
        )


def _render_edit_row(item: dict) -> None:
    item_id = item["id"]
    with st.container(border=True, key=f"editrow_{item_id}"):
        col_name, col_qty = st.columns([5, 2], vertical_alignment="bottom")
        col_name.text_input(
            "이름 수정",
            value=item["name"],
            key=f"name_{item_id}",
            max_chars=MAX_NAME_LENGTH,
        )
        col_qty.number_input(
            "수량 수정",
            value=item["quantity"],
            min_value=1,
            max_value=MAX_QUANTITY,
            step=1,
            key=f"qty_{item_id}",
        )
        with st.container(key=f"editbtns_{item_id}"):
            col_save, col_cancel = st.columns(2)
        col_save.button(
            "저장",
            key=f"save_{item_id}",
            type="primary",
            width="stretch",
            on_click=on_save_edit,
            args=(item_id,),
        )
        col_cancel.button("취소", key=f"cancel_{item_id}", width="stretch", on_click=on_cancel_edit)
        render_flash("edit")


def render_item_list(filter_option: str) -> None:
    items = st.session_state.shopping_items
    if not items:
        st.info("쇼핑 리스트가 비어 있습니다. 위에서 살 물건을 추가해 보세요.", icon="🧺")
        return

    if filter_option == "미구매":
        visible = [i for i in items if not i.get("checked")]
    elif filter_option == "구매 완료":
        visible = [i for i in items if i.get("checked")]
    else:
        visible = items

    if not visible:
        st.info("해당하는 아이템이 없습니다", icon="🔍")
        return

    # 미구매 항목을 위로, 구매 완료 항목을 아래로 (같은 그룹 안에서는 추가 순서 유지)
    for item in sorted(visible, key=lambda i: bool(i.get("checked"))):
        if item["id"] == st.session_state.editing_id:
            _render_edit_row(item)
        else:
            _render_view_row(item)
    # 편집 행이 화면에 없으면(필터로 숨겨짐 등) 남은 편집 메시지를 버린다.
    st.session_state.flash = [f for f in st.session_state.flash if f[2] != "edit"]


def render_bulk_actions() -> None:
    items = st.session_state.shopping_items
    has_checked = any(i.get("checked") for i in items)
    st.divider()
    col_clear, col_all = st.columns(2)
    col_clear.button(
        "🧹 구매 완료 항목 삭제",
        on_click=on_clear_checked,
        disabled=not has_checked,
        width="stretch",
    )
    if col_all.button("전체 삭제", type="secondary", disabled=not items, width="stretch"):
        confirm_clear_all()


def main() -> None:
    init_state()
    # st.html(<style>만)은 이벤트 컨테이너로 보내져 본문에 적용되지 않으므로 markdown으로 주입한다.
    st.markdown(STYLE, unsafe_allow_html=True)
    render_header()
    render_add_form()
    filter_option = render_filter()
    render_item_list(filter_option)
    render_bulk_actions()


main()
