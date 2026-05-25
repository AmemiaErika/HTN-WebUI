from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List

from config import settings

CUSTOM_PROVIDERS_JSON = settings.DATA_DIR / "custom_providers.json"
PROVIDER_TYPES = ["vision", "image", "both"]
REQUEST_FORMATS = ["openai_compatible"]


def _ensure_file() -> None:
    CUSTOM_PROVIDERS_JSON.parent.mkdir(parents=True, exist_ok=True)
    if not CUSTOM_PROVIDERS_JSON.exists():
        CUSTOM_PROVIDERS_JSON.write_text(json.dumps({"providers": []}, ensure_ascii=False, indent=2), encoding="utf-8")


def _clean_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    provider_id = str(provider.get("id") or provider.get("provider_id") or "").strip() or f"custom_{uuid.uuid4().hex[:10]}"
    name = str(provider.get("name") or "自定义接口").strip() or "自定义接口"
    base_url = str(provider.get("base_url") or "").strip()
    api_key = str(provider.get("api_key") or "").strip()
    model = str(provider.get("model") or "").strip()
    provider_type = str(provider.get("provider_type") or provider.get("type") or "both").strip().lower()
    if provider_type not in PROVIDER_TYPES:
        provider_type = "both"
    request_format = str(provider.get("request_format") or "openai_compatible").strip().lower()
    if request_format not in REQUEST_FORMATS:
        request_format = "openai_compatible"
    enabled = bool(provider.get("enabled", True))
    return {
        "id": provider_id,
        "name": name,
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "model": model,
        "provider_type": provider_type,
        "request_format": request_format,
        "enabled": enabled,
    }


def load_custom_providers() -> List[Dict[str, Any]]:
    _ensure_file()
    try:
        data = json.loads(CUSTOM_PROVIDERS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {"providers": []}
    providers = data.get("providers", []) if isinstance(data, dict) else []
    if not isinstance(providers, list):
        providers = []
    cleaned = [_clean_provider(p) for p in providers if isinstance(p, dict)]
    # Save back after cleaning so old configs stay normalized.
    save_custom_providers(cleaned)
    return cleaned


def save_custom_providers(providers: List[Dict[str, Any]]) -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    cleaned = [_clean_provider(p) for p in providers if isinstance(p, dict)]
    CUSTOM_PROVIDERS_JSON.write_text(json.dumps({"providers": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_custom_provider(provider: Dict[str, Any]) -> Dict[str, Any]:
    new_provider = _clean_provider(provider)
    providers = load_custom_providers()
    found = False
    updated = []
    for item in providers:
        if item.get("id") == new_provider.get("id"):
            updated.append(new_provider)
            found = True
        else:
            updated.append(item)
    if not found:
        updated.append(new_provider)
    save_custom_providers(updated)
    return new_provider


def delete_custom_provider(provider_id: str) -> None:
    provider_id = str(provider_id or "").strip()
    providers = [p for p in load_custom_providers() if p.get("id") != provider_id]
    save_custom_providers(providers)


def get_custom_provider(provider_id: str) -> Dict[str, Any] | None:
    provider_id = str(provider_id or "").replace("custom:", "", 1).strip()
    for provider in load_custom_providers():
        if provider.get("id") == provider_id:
            return provider
    return None


def custom_provider_label(provider: Dict[str, Any]) -> str:
    name = provider.get("name", "自定义接口")
    model = provider.get("model", "")
    provider_id = provider.get("id", "")
    return f"custom: {name} / {model} [{provider_id}]" if model else f"custom: {name} [{provider_id}]"


def custom_provider_option(provider: Dict[str, Any]) -> str:
    return f"custom:{provider.get('id', '')}"


def is_custom_option(option: str) -> bool:
    return str(option or "").startswith("custom:")


def custom_options_for(provider_type: str) -> List[str]:
    provider_type = str(provider_type or "").strip().lower()
    options = []
    for provider in load_custom_providers():
        if not provider.get("enabled", True):
            continue
        ptype = provider.get("provider_type", "both")
        if ptype == "both" or ptype == provider_type:
            options.append(custom_provider_option(provider))
    return options


def option_label(option: str) -> str:
    option = str(option or "")
    if not is_custom_option(option):
        return option
    provider = get_custom_provider(option)
    if not provider:
        return option
    return custom_provider_label(provider)
