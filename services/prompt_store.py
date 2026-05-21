from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from config import settings

PROMPT_SETTINGS_JSON = settings.DATA_DIR / "prompt_settings.json"

DEFAULT_PROMPTS: Dict[str, str] = {
    "object_list": """
请分析这张图片，列出所有可以独立作为概念设计素材的物件。

要求：
1. 只识别实体物件，不要识别背景、阴影、反光、空气、纯光效。
2. 合并同类重复的小装饰，除非它们设计明显不同。
3. 每个物件只需要包含 name 和 description 两个字段。
4. name：简洁中文名称，方便用户识别。
5. description：简洁且准确的外观描述，必须包含颜色、形状、材质感、位置特征、可见细节，用于后续模型在原图中定位并拆解该物件。
6. 不要输出 category、importance、occlusion_level、suggested_use 或其他字段。
7. 返回严格 JSON，不要 Markdown，不要解释。

返回格式：
{
  "objects": [
    {
      "name": "",
      "description": ""
    }
  ]
}
""".strip(),
    "three_view": """
请基于输入参考图中的【{{object_name}}】生成概念设计三视图。

定位与拆解依据：
- 物件名称：{{object_name}}
- 外观描述：{{object_description}}

请先根据“物件名称 + 外观描述”在原图中准确定位该物件，再进行拆解、补全和三视图生成。

生成要求：
1. 只保留该物件，不要背景，不要其他物件。
2. 输出一张完整的三视图设计稿，包含 front view、side view、back view。
3. 保持外观描述中的颜色、形状、材质感、比例和关键细节。
4. 保持原图中的设计语言、配色、材质、比例和角色特征。
5. 对被遮挡或不可见部分进行合理概念补全，但不要改变核心设计。
6. 使用干净白底，产品设计稿排版。
7. 不要添加无关文字，只保留极简视图标签即可。
""".strip(),
    "compose": """
请根据输入的素材图片，生成一张新的概念设计组合图。

构图要求：
{{composition_prompt}}

环境要求：
- 时间：{{time}}
- 光照：{{lighting}}
- 天气：{{weather}}
- 风格：{{style}}
- 视角：{{camera}}

生成要求：
1. 保持输入素材的主要设计特征。
2. 统一画面风格、材质、透视和光照。
3. 尽量不要丢失主要物件。
4. 输出完整产品概念渲染图。
""".strip(),
    "sketch_refine": """
请将输入草图细化为完整概念设计图。

用户要求：
{{refine_prompt}}

生成要求：
1. 尽量保留草图的主要轮廓和构图。
2. 根据提示词补充材质、色彩、细节和设计语言。
3. 输出干净、完整、适合概念提案的设计图。
""".strip(),
}

PROMPT_LABELS = {
    "object_list": "流 A：拆解 list / 物件识别",
    "three_view": "流 A：三视图生成",
    "compose": "流 B：组合生成 / 环境调整",
    "sketch_refine": "流 C：草图细化",
}

PROMPT_VARIABLES = {
    "object_list": [],
    "three_view": ["{{object_name}}", "{{object_description}}"],
    "compose": ["{{composition_prompt}}", "{{time}}", "{{lighting}}", "{{weather}}", "{{style}}", "{{camera}}"],
    "sketch_refine": ["{{refine_prompt}}"],
}


def _ensure_file() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_SETTINGS_JSON.exists():
        save_prompt_templates(DEFAULT_PROMPTS)


def load_prompt_templates() -> Dict[str, str]:
    _ensure_file()
    try:
        data = json.loads(PROMPT_SETTINGS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    prompts = dict(DEFAULT_PROMPTS)
    if isinstance(data, dict):
        for key, value in data.items():
            if key in prompts and isinstance(value, str) and value.strip():
                prompts[key] = value
    return prompts


def save_prompt_templates(prompts: Dict[str, str]) -> None:
    cleaned = {}
    for key in DEFAULT_PROMPTS:
        cleaned[key] = str(prompts.get(key, DEFAULT_PROMPTS[key]))
    PROMPT_SETTINGS_JSON.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def get_prompt_template(key: str) -> str:
    return load_prompt_templates().get(key, DEFAULT_PROMPTS.get(key, ""))


def save_prompt_template(key: str, value: str) -> None:
    prompts = load_prompt_templates()
    if key not in DEFAULT_PROMPTS:
        raise ValueError(f"未知提示词类型：{key}")
    prompts[key] = value
    save_prompt_templates(prompts)


def reset_prompt_template(key: str) -> None:
    prompts = load_prompt_templates()
    if key not in DEFAULT_PROMPTS:
        raise ValueError(f"未知提示词类型：{key}")
    prompts[key] = DEFAULT_PROMPTS[key]
    save_prompt_templates(prompts)


def reset_all_prompt_templates() -> None:
    save_prompt_templates(DEFAULT_PROMPTS)


def render_template(template: str, variables: Dict[str, object]) -> str:
    text = template
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text.strip()
