import json
import re
from typing import Any, Dict


def extract_json(text: str) -> Dict[str, Any]:
    """从模型返回文本中尽量提取 JSON。"""
    if not text:
        return {"objects": []}
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            return {"objects": []}
        data = json.loads(match.group(0))
    if isinstance(data, list):
        data = {"objects": data}
    if "objects" not in data or not isinstance(data["objects"], list):
        data["objects"] = []
    return data
