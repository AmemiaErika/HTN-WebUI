from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import RESULTS_JSON
from services.asset_service import add_asset


def _ensure_file() -> None:
    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not RESULTS_JSON.exists():
        RESULTS_JSON.write_text("[]", encoding="utf-8")


def _read_results() -> List[Dict[str, Any]]:
    _ensure_file()
    try:
        data = json.loads(RESULTS_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_results(results: List[Dict[str, Any]]) -> None:
    _ensure_file()
    RESULTS_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


def list_results() -> List[Dict[str, Any]]:
    return sorted(_read_results(), key=lambda x: x.get("created_at", ""), reverse=True)


def add_result(result: Dict[str, Any]) -> Dict[str, Any]:
    results = _read_results()
    now = datetime.now().isoformat(timespec="seconds")
    item = {
        "result_id": result.get("result_id") or f"result_{uuid.uuid4().hex[:12]}",
        "type": result.get("type", "generation"),
        "name": result.get("name", "未命名结果"),
        "category": result.get("category", "prop"),
        "description": result.get("description", ""),
        "image_path": result.get("image_path", ""),
        "source_image_path": result.get("source_image_path", ""),
        "prompt": result.get("prompt", ""),
        "provider": result.get("provider", ""),
        "meta": result.get("meta", {}),
        "created_at": result.get("created_at") or now,
        "updated_at": now,
        "archived": bool(result.get("archived", False)),
        "asset_id": result.get("asset_id", ""),
    }
    results.append(item)
    _write_results(results)
    return item


def delete_result(result_id: str) -> bool:
    results = _read_results()
    new_results = [r for r in results if r.get("result_id") != result_id]
    _write_results(new_results)
    return len(new_results) != len(results)


def update_result(result_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    results = _read_results()
    updated = None
    for r in results:
        if r.get("result_id") == result_id:
            r.update(patch)
            r["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = r
            break
    _write_results(results)
    return updated


def archive_result_to_asset(result_id: str, patch: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    results = _read_results()
    target = None
    for r in results:
        if r.get("result_id") == result_id:
            target = r
            break
    if not target:
        return None

    data = dict(target)
    if patch:
        data.update(patch)

    asset = add_asset({
        "name": data.get("name", "未命名素材"),
        "category": data.get("category", "prop"),
        "description": data.get("description", ""),
        "source_image_path": data.get("source_image_path", ""),
        "three_view_path": data.get("image_path", ""),
        "prompt": data.get("prompt", ""),
        "provider": data.get("provider", ""),
    })
    update_result(result_id, {"archived": True, "asset_id": asset.get("asset_id", ""), **(patch or {})})
    return asset


def clear_results() -> None:
    _write_results([])
