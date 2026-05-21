from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.settings import ASSETS_JSON


def _read_assets() -> List[Dict[str, Any]]:
    if not ASSETS_JSON.exists():
        ASSETS_JSON.write_text("[]", encoding="utf-8")
    try:
        data = json.loads(ASSETS_JSON.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_assets(assets: List[Dict[str, Any]]) -> None:
    ASSETS_JSON.write_text(json.dumps(assets, ensure_ascii=False, indent=2), encoding="utf-8")


def list_assets() -> List[Dict[str, Any]]:
    return _read_assets()


def add_asset(asset: Dict[str, Any]) -> Dict[str, Any]:
    assets = _read_assets()
    now = datetime.now().isoformat(timespec="seconds")
    asset = {
        "asset_id": asset.get("asset_id") or f"asset_{uuid.uuid4().hex[:12]}",
        "name": asset.get("name", "未命名素材"),
        "category": asset.get("category", "prop"),
        "description": asset.get("description", ""),
        "source_image_path": asset.get("source_image_path", ""),
        "three_view_path": asset.get("three_view_path", ""),
        "prompt": asset.get("prompt", ""),
        "provider": asset.get("provider", ""),
        "created_at": asset.get("created_at") or now,
        "updated_at": now,
    }
    assets.append(asset)
    _write_assets(assets)
    return asset


def delete_asset(asset_id: str) -> bool:
    assets = _read_assets()
    new_assets = [a for a in assets if a.get("asset_id") != asset_id]
    _write_assets(new_assets)
    return len(new_assets) != len(assets)


def update_asset(asset_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    assets = _read_assets()
    updated = None
    for a in assets:
        if a.get("asset_id") == asset_id:
            a.update(patch)
            a["updated_at"] = datetime.now().isoformat(timespec="seconds")
            updated = a
            break
    _write_assets(assets)
    return updated
