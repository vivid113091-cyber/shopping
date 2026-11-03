"""쇼핑 리스트 데이터 계층: JSON 저장/로드 및 CRUD 함수.

모든 CRUD 함수는 입력 리스트를 변경하지 않고 새 리스트를 반환한다.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from uuid import uuid4

DATA_FILE = Path(__file__).resolve().parent / "shopping_list.json"
MAX_NAME_LENGTH = 50
MAX_QUANTITY = 999


def _new_id() -> str:
    return uuid4().hex[:8]


def _clean_item(raw, seen_ids: set[str]) -> dict | None:
    """파일에서 읽은 아이템 하나를 검증·보정한다. 살릴 수 없으면 None.

    - name: 문자열이 아니거나 비어 있으면 버림, 50자 초과는 자름
    - id: 없거나 중복이면 새로 발급 (중복 id는 위젯 key 충돌로 앱을 멈추게 함)
    - quantity: 정수로 변환 후 1~999로 보정, 변환 불가면 1
    - checked: 정확히 true일 때만 구매 완료
    """
    if not isinstance(raw, dict):
        return None
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    item_id = raw.get("id")
    if not isinstance(item_id, str) or not item_id or item_id in seen_ids:
        item_id = _new_id()
    seen_ids.add(item_id)
    created_at = raw.get("created_at")
    return {
        "id": item_id,
        "name": name.strip()[:MAX_NAME_LENGTH],
        "quantity": _normalize_quantity(raw.get("quantity")),
        "checked": raw.get("checked") is True,
        "created_at": created_at if isinstance(created_at, str) else "",
    }


def load_items(path: Path = DATA_FILE) -> list[dict]:
    """JSON 파일에서 아이템 목록을 불러온다.

    파일이 없거나 손상되었으면 빈 리스트, 일부 아이템만 잘못되었으면 해당 아이템만 보정/제외한다.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return []

    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return []
    seen: set[str] = set()
    cleaned = [item for item in (_clean_item(raw, seen) for raw in data["items"]) if item is not None]
    if cleaned != data["items"]:
        # 보정 결과(특히 새로 발급한 id)를 저장해 두지 않으면 실행할 때마다 id가 바뀌어
        # 위젯 key와 콜백 대상이 어긋난다.
        try:
            save_items(cleaned, path)
        except OSError:
            pass
    return cleaned


def save_items(items: list[dict], path: Path = DATA_FILE) -> None:
    """아이템 목록을 JSON 파일로 원자적으로 저장한다 (임시 파일 → os.replace)."""
    path = Path(path)
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, prefix=".shopping_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"items": items}, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def validate_name(name: str) -> str | None:
    """이름 검증. 오류가 있으면 메시지를, 정상이면 None을 반환한다."""
    stripped = (name or "").strip()
    if not stripped:
        return "아이템 이름을 입력해 주세요."
    if len(stripped) > MAX_NAME_LENGTH:
        return f"아이템 이름은 {MAX_NAME_LENGTH}자 이하로 입력해 주세요."
    return None


def _normalize_quantity(quantity) -> int:
    if isinstance(quantity, bool):
        return 1
    try:
        return min(MAX_QUANTITY, max(1, int(quantity)))
    except (TypeError, ValueError, OverflowError):
        return 1


def find_item(items: list[dict], item_id: str) -> dict | None:
    return next((item for item in items if item["id"] == item_id), None)


def add_item(items: list[dict], name: str, quantity: int = 1) -> list[dict]:
    new_item = {
        "id": _new_id(),
        "name": name.strip(),
        "quantity": _normalize_quantity(quantity),
        "checked": False,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    return [*items, new_item]


def update_item(items: list[dict], item_id: str, name: str, quantity: int) -> list[dict]:
    return [
        {**item, "name": name.strip(), "quantity": _normalize_quantity(quantity)}
        if item["id"] == item_id
        else item
        for item in items
    ]


def delete_item(items: list[dict], item_id: str) -> list[dict]:
    return [item for item in items if item["id"] != item_id]


def toggle_item(items: list[dict], item_id: str) -> list[dict]:
    return [
        {**item, "checked": not item.get("checked", False)} if item["id"] == item_id else item
        for item in items
    ]


def set_checked(items: list[dict], item_id: str, checked: bool) -> list[dict]:
    """체크 상태를 지정한 값으로 설정한다.

    다른 탭에서 이미 바뀐 상태를 다시 뒤집지 않도록, UI에서는 toggle 대신 이 함수를 쓴다.
    """
    return [{**item, "checked": bool(checked)} if item["id"] == item_id else item for item in items]


def clear_checked(items: list[dict]) -> list[dict]:
    return [item for item in items if not item.get("checked", False)]
