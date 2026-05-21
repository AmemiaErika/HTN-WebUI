from __future__ import annotations

import json
from typing import List, Dict, Any

from config import settings

CATEGORIES_JSON = settings.DATA_DIR / "categories.json"
DEFAULT_CATEGORIES = ["未分类"]


def _ensure_file() -> None:
    CATEGORIES_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not CATEGORIES_JSON.exists():
        CATEGORIES_JSON.write_text(json.dumps(DEFAULT_CATEGORIES, ensure_ascii=False, indent=2), encoding="utf-8")


def list_categories() -> List[str]:
    _ensure_file()
    try:
        data = json.loads(CATEGORIES_JSON.read_text(encoding="utf-8"))
        if isinstance(data, list):
            cleaned = [str(x).strip() for x in data if str(x).strip()]
            return sorted(set(cleaned), key=lambda x: x.lower()) or DEFAULT_CATEGORIES
    except json.JSONDecodeError:
        pass
    return DEFAULT_CATEGORIES


def save_categories(categories: List[str]) -> List[str]:
    cleaned = sorted({str(c).strip() for c in categories if str(c).strip()}, key=lambda x: x.lower())
    _ensure_file()
    CATEGORIES_JSON.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
    return cleaned


def create_category(name: str) -> List[str]:
    name = str(name).strip()
    cats = list_categories()
    if name and name not in cats:
        cats.append(name)
        cats = save_categories(cats)
    return cats


def delete_category(name: str) -> List[str]:
    """Delete a category name from the saved category list.

    Note: if existing assets still use this category, get_all_categories() will
    show it again. Move those assets before calling this when you want it gone
    from the sidebar.
    """
    name = str(name).strip()
    cats = [c for c in list_categories() if c != name]
    if not cats:
        cats = ["未分类"]
    return save_categories(cats)


def get_all_categories(assets: List[Dict[str, Any]] | None = None) -> List[str]:
    cats = set(list_categories())
    for asset in assets or []:
        cat = str(asset.get("category", "未分类") or "未分类").strip()
        if cat:
            cats.add(cat)
    return sorted(cats, key=lambda x: x.lower()) or ["未分类"]
