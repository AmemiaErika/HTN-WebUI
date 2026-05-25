from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config import settings

LIST_HISTORY_JSON = settings.DATA_DIR / "list_history.json"


def _ensure_file() -> None:
    LIST_HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not LIST_HISTORY_JSON.exists():
        LIST_HISTORY_JSON.write_text("[]", encoding="utf-8")


def _read_histories() -> List[Dict[str, Any]]:
    _ensure_file()
    try:
        data = json.loads(LIST_HISTORY_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_histories(histories: List[Dict[str, Any]]) -> None:
    _ensure_file()
    LIST_HISTORY_JSON.write_text(json.dumps(histories, ensure_ascii=False, indent=2), encoding="utf-8")


def list_histories() -> List[Dict[str, Any]]:
    return sorted(_read_histories(), key=lambda x: x.get("created_at", ""), reverse=True)


def get_history(history_id: str) -> Optional[Dict[str, Any]]:
    for item in _read_histories():
        if item.get("history_id") == history_id:
            return item
    return None


def add_list_history(record: Dict[str, Any]) -> Dict[str, Any]:
    histories = _read_histories()
    now = datetime.now().isoformat(timespec="seconds")
    item = {
        "history_id": record.get("history_id") or f"list_{uuid.uuid4().hex[:12]}",
        "title": record.get("title") or "拆解结果",
        "image_path": record.get("image_path", ""),
        "image_name": record.get("image_name", ""),
        "objects": record.get("objects", []),
        "mode": record.get("mode", "整体物品"),
        "parent_object": record.get("parent_object", {}),
        "provider": record.get("provider", ""),
        "analyzer": record.get("analyzer", ""),
        "raw_results": record.get("raw_results", []),
        "created_at": record.get("created_at") or now,
        "updated_at": now,
    }
    histories.append(item)
    _write_histories(histories)
    return item


def update_list_history(history_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    histories = _read_histories()
    updated = None
    for item in histories:
        if item.get("history_id") == history_id:
            item.update(patch)
            item["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = item
            break
    _write_histories(histories)
    return updated


def delete_list_history(history_id: str) -> bool:
    histories = _read_histories()
    new_histories = [h for h in histories if h.get("history_id") != history_id]
    _write_histories(new_histories)
    return len(new_histories) != len(histories)
