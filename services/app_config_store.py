from __future__ import annotations

import json
from typing import Dict, Any

from config import settings

APP_CONFIG_JSON = settings.DATA_DIR / "app_config.json"

CONFIG_KEYS = [
    "DEFAULT_LIST_ANALYZER",
    "DEFAULT_IMAGE_GENERATOR",
    "GEMINI_API_KEY",
    "GEMINI_VISION_MODEL",
    "GEMINI_IMAGE_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_VISION_MODEL",
    "OPENAI_IMAGE_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
]


def _current_defaults() -> Dict[str, str]:
    return {key: str(getattr(settings, key, "") or "") for key in CONFIG_KEYS}


def load_app_config() -> Dict[str, str]:
    config = _current_defaults()
    if APP_CONFIG_JSON.exists():
        try:
            data = json.loads(APP_CONFIG_JSON.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key in CONFIG_KEYS:
                    if key in data and data[key] is not None:
                        config[key] = str(data[key])
        except json.JSONDecodeError:
            pass
    return config


def save_app_config(config: Dict[str, Any]) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = {key: str(config.get(key, "") or "") for key in CONFIG_KEYS}
    APP_CONFIG_JSON.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_app_config(config: Dict[str, Any]) -> None:
    for key in CONFIG_KEYS:
        if key in config:
            setattr(settings, key, str(config.get(key, "") or ""))
