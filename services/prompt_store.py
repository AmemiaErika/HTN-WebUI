from __future__ import annotations

import json
from typing import Dict

from config import settings

PROMPT_SETTINGS_JSON = settings.DATA_DIR / "prompt_settings.json"

_JSON_REQUIREMENT = """
输出要求：
1. 每个条目只输出 id、name、description、position、bbox 五个字段。
2. id 从 1 开始递增。
3. name 使用简洁中文名称。
4. description 必须简洁准确，包含颜色、形状、材质感、显著特征，用于后续模型定位并生成三视图。
5. position 描述其在画面中的大致位置。
6. bbox 使用归一化坐标 [x1, y1, x2, y2]，数值范围 0 到 1，左上角为 [0,0]，右下角为 [1,1]。
7. 不要输出 category、importance、occlusion_level、suggested_use 或其他字段。
8. 返回严格 JSON，不要 Markdown，不要解释。

返回格式：
{
  "objects": [
    {
      "id": 1,
      "name": "",
      "description": "",
      "position": "",
      "bbox": [0.0, 0.0, 0.0, 0.0]
    }
  ]
}
""".strip()

DEFAULT_PROMPTS: Dict[str, str] = {
    "object_list_overall": f"""
请分析这张图片，列出可以作为完整概念设计素材的主要物品。

拆解原则：
1. 默认只识别完整物品、大型独立道具或完整角色。
2. 不要把完整物品内部的按钮、旋钮、屏幕、螺丝、贴纸、纹理、小标签、小开关拆成单独条目。
3. 只有当多个物件在画面中本身就是独立摆放时，才分别列出。
4. 线缆、阴影、反光、背景、纯光效不要列出，除非它们是明确的可设计实体道具。
5. 如果一个物品由多个可见部件组成，也先作为“一个完整物品”输出。

{_JSON_REQUIREMENT}
""".strip(),
    "object_list_parts": f"""
请针对用户选中的完整物品，拆分其中可以独立作为概念设计素材的主要部件。

选中物品信息：
- 名称：{{{{parent_name}}}}
- 外观描述：{{{{parent_description}}}}
- 位置：{{{{parent_position}}}}
- bbox：{{{{parent_bbox}}}}

拆解原则：
1. 只在选中物品范围内拆分，不要分析其他物品。
2. 只拆大型结构或主要功能部件，例如主体外壳、提手、屏幕面板、底座、包装外壳、大型装饰件。
3. 不要拆到按钮、螺丝、纹理、贴纸、小标签、小孔、小开关等细节。
4. 如果某些部件太小或不适合独立作为概念设计素材，请合并到更大的部件中。

{_JSON_REQUIREMENT}
""".strip(),
    "object_list_details": f"""
请针对用户选中的物品或部件，拆分其中的小型视觉元素。

选中对象信息：
- 名称：{{{{parent_name}}}}
- 外观描述：{{{{parent_description}}}}
- 位置：{{{{parent_position}}}}
- bbox：{{{{parent_bbox}}}}

拆解原则：
1. 只在选中对象范围内拆分，不要分析其他物品。
2. 可以拆出按钮、旋钮、屏幕、贴纸、标签、接口、开关、小装饰件、图案等细节元素。
3. 同类且距离很近的小元素可以合并为一个“按钮组 / 标签组 / 装饰组”。
4. 不要输出纯纹理、反光、阴影、背景噪声。

{_JSON_REQUIREMENT}
""".strip(),
    # Backward-compatible key. Older custom settings can still exist, but the UI now uses the three mode-specific prompts above.
    "object_list": f"""
请分析这张图片，列出可以作为完整概念设计素材的主要物品。

拆解原则：
1. 默认只识别完整物品、大型独立道具或完整角色。
2. 不要把完整物品内部的按钮、旋钮、屏幕、螺丝、贴纸、纹理、小标签、小开关拆成单独条目。
3. 只有当多个物件在画面中本身就是独立摆放时，才分别列出。

{_JSON_REQUIREMENT}
""".strip(),
    "three_view": """
请基于输入参考图中的【{{object_name}}】生成概念设计三视图。

【最高优先级：用户补充要求】
{{extra_prompt}}

执行规则：
- 如果用户补充要求不为空，必须优先满足该要求。
- 如果用户补充要求与下方通用要求存在冲突，以用户补充要求为准。
- 输出前请再次检查是否落实了用户补充要求。

定位与拆解依据：
- 物件名称：{{object_name}}
- 外观描述与原图定位信息：{{object_description}}

画幅要求：
{{aspect_ratio}}

请先根据“物件名称 + 外观描述 + 位置 / bbox 定位信息”在原图中准确找到该对象，再进行补全和三视图生成。

生成要求：
1. 只保留该对象，只输出主体内容。
2. 如果对象是完整物品，生成完整物品三视图；如果对象是部件或细节元素，只生成该部件 / 元素的三视图。
3. 输出一张完整的三视图设计稿，包含 front view、side view、back view。
4. 保持原图画风不变，保持原图中的颜色、形状、材质感、比例和关键细节。
5. 统一使用纯白色背景。
6. 对被遮挡或不可见部分进行合理概念补全，但不要改变核心设计。
7. 保持画面干净简洁，只保留主体内容。
8. 不要添加标签、序号、说明文字、视图标题或任何其他文字元素。
9. 不要添加除主体之外的背景装饰、道具、阴影文字板或无关元素。

最终提醒：用户补充要求是本次生成的最高优先级，请务必落实：{{extra_prompt}}
""".strip(),
    "overview_three_view": """
请基于输入参考图和当前拆解 list，生成一张“整体拆件三视图设计图”。

【最高优先级：用户补充要求】
{{extra_prompt}}

执行规则：
- 如果用户补充要求不为空，必须优先满足该要求。
- 如果用户补充要求与下方通用要求存在冲突，以用户补充要求为准。
- 输出前请再次检查是否落实了用户补充要求。

当前拆解对象列表：
{{objects_text}}

排版要求：
- 排版方式：{{layout}}
- 画幅大小：{{aspect_ratio}}

拆分程度：
{{split_degree}}

生成要求：
1. 固定使用当前 list 中的全部对象，不要省略 list 内对象。
2. 如果拆分程度为“仅拆分主体物”，只为 list 中的主体对象生成三视图，不要继续拆出按钮、螺丝、小标签等细节。
3. 如果拆分程度为“拆分到最细，精确到每个零件”，请在当前 list 对象基础上，把每个主体中可见的按钮、旋钮、屏幕、提手、接口、装饰片等零件也拆出并生成对应三视图。
4. 每个对象或零件包含 front view、side view、back view。
5. 所有对象放在同一张大图里，采用整洁清晰的设计图排版。
6. 保持原图画风不变，保持原图中的颜色、材质、造型和设计语言。
7. 统一使用纯白色背景。
8. 被遮挡或不可见部分可以合理概念补全。
9. 不要加入参考图之外的新物件。
10. 只保留主体内容，不要加入背景装饰。
11. 不要添加标签、序号、名称、说明文字、子编号或任何其他文字元素。
12. 不要做成场景渲染图，避免画面过度拥挤，优先保证主体清晰。

最终提醒：用户补充要求是本次生成的最高优先级，请务必落实：{{extra_prompt}}
""".strip(),
    "compose": """
请根据输入的素材图片，生成一张新的概念设计组合图。

【最高优先级：用户构图要求】
{{composition_prompt}}

执行规则：
- 必须优先满足用户构图要求。
- 如果用户构图要求与下方通用要求存在冲突，以用户构图要求为准。
- 输出前请再次检查主要物件、位置关系和氛围要求是否落实。

环境要求：
- 时间：{{time}}
- 光照：{{lighting}}
- 天气：{{weather}}
- 风格：{{style}}
- 视角：{{camera}}

生成要求：
1. 保持输入素材的主要设计特征。
2. 保持原图画风不变，统一画面风格、材质、透视和光照。
3. 如果主体物体为浅色，使用深灰色背景；如果主体物体为深色，使用白色背景。
4. 尽量不要丢失主要物件。
5. 输出完整产品概念渲染图。

最终提醒：用户构图要求是本次生成的最高优先级，请务必落实：{{composition_prompt}}
""".strip(),
    "sketch_refine": """
请将输入草图细化为完整概念设计图。

【最高优先级：用户要求】
{{refine_prompt}}

执行规则：
- 必须优先满足用户要求。
- 如果用户要求与下方通用要求存在冲突，以用户要求为准。
- 输出前请再次检查是否落实了用户要求。

生成要求：
1. 尽量保留草图的主要轮廓和构图。
2. 根据提示词补充材质、色彩、细节和设计语言。
3. 保持原图画风不变。
4. 如果物体为浅色，使用深灰色背景；如果物体为深色，使用白色背景。
5. 输出干净、完整、适合概念提案的设计图。

最终提醒：用户要求是本次生成的最高优先级，请务必落实：{{refine_prompt}}
""".strip(),
    "image_edit": """
请基于输入的一张或多张参考图执行图片编辑与再生成。

【最高优先级：用户补充说明】
{{extra_prompt}}

执行规则：
- 用户补充说明是最高优先级；如果与下方预设冲突，以用户补充说明为准。
- 主编辑图是需要被编辑的核心图片；风格参考、背景参考、元素参考、光影参考、替换物件参考只用于辅助。
- 不要把参考图用途混淆，不要随意把风格参考图中的主体当成必须加入的物体。
- 输出前请再次检查是否落实了用户补充说明和所选编辑目标。

参考图说明：
{{references_text}}

编辑目标：
{{edit_goals}}

细化增强设置：
{{detail_options}}

风格变换设置：
{{style_options}}

光影 / 环境设置：
{{lighting_options}}

背景替换设置：
{{background_options}}

元素融合设置：
{{fusion_options}}

局部替换设置：
{{replace_options}}

画幅要求：
{{aspect_ratio}}

通用生成要求：
1. 尽量保持主编辑图的主体内容、比例和构图逻辑。
2. 如果选择“细化细节”，在不改变原图画风和构图的前提下提升完成度、边缘清晰度和局部细节。
3. 如果选择“改变画风”，按照风格设置或风格参考图重绘视觉语言，但保留主体识别度。
4. 如果选择“改变光影环境”，主要调整光照、时间、天气和氛围，不要随意改变主体设计。
5. 如果选择“改变背景”，保留主编辑图主体，按背景设置或背景参考图替换背景。
6. 如果选择“融合多个参考图”，保留主编辑图基础，把元素参考图中的设计元素自然融合进去。
7. 如果选择“替换局部物件”，只替换“局部替换设置”里指定的局部对象；替换对象来自“替换物件参考”图片，主编辑图中的其他物体、构图、比例关系、画风和光影尽量保持不变。
8. 如果局部替换设置中包含拆解 list 的对象名称、外观描述、位置描述或 bbox 定位，请把这些信息作为被替换对象的最高优先级定位依据，不要替换其他相似物件。
9. 局部替换时不要扩大修改范围，不要重绘整张图，不要改变周围物件。
10. 保持原图画风不变（除非用户明确要求改变画风），并保持画面干净、完整、适合概念设计展示。
11. 统一使用纯白色背景；如果用户明确要求特定背景或背景替换，则在满足该要求时仍保持整体画面简洁。
12. 画面里不要添加标签、序号、说明文字或任何其他文字元素。
13. 只保留主体内容，不要加入无关装饰、无关物件或多余设计元素。

最终提醒：用户补充说明是本次生成的最高优先级，请务必落实：{{extra_prompt}}
""".strip(),

}

# 当前版本仍保留 object_list / compose / sketch_refine 的旧函数兜底，
# 但设置页只展示仍在 UI 中直接使用的提示词。
LEGACY_PROMPT_KEYS = {"object_list", "compose", "sketch_refine"}
ACTIVE_PROMPT_KEYS = [key for key in DEFAULT_PROMPTS.keys() if key not in LEGACY_PROMPT_KEYS]


PROMPT_LABELS = {
    "object_list_overall": "图片拆解：整体物品识别",
    "object_list_parts": "图片拆解：主要部件拆解",
    "object_list_details": "图片拆解：细节元素拆解",
    "three_view": "图片拆解：单对象三视图生成",
    "overview_three_view": "图片拆解：整体拆件三视图总览",
    "image_edit": "图片编辑：预设驱动编辑",
}

PROMPT_VARIABLES = {
    "object_list_overall": [],
    "object_list_parts": ["{{parent_name}}", "{{parent_description}}", "{{parent_position}}", "{{parent_bbox}}"],
    "object_list_details": ["{{parent_name}}", "{{parent_description}}", "{{parent_position}}", "{{parent_bbox}}"],
    "three_view": ["{{object_name}}", "{{object_description}}", "{{extra_prompt}}", "{{aspect_ratio}}"],
    "overview_three_view": ["{{objects_text}}", "{{extra_prompt}}", "{{layout}}", "{{aspect_ratio}}", "{{split_degree}}"],
    "image_edit": ["{{references_text}}", "{{edit_goals}}", "{{detail_options}}", "{{style_options}}", "{{lighting_options}}", "{{background_options}}", "{{fusion_options}}", "{{replace_options}}", "{{extra_prompt}}", "{{aspect_ratio}}"],
}

def _ensure_file() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not PROMPT_SETTINGS_JSON.exists():
        save_prompt_templates(DEFAULT_PROMPTS)


def _active_default_prompts() -> Dict[str, str]:
    return {key: DEFAULT_PROMPTS[key] for key in ACTIVE_PROMPT_KEYS}


def load_prompt_templates() -> Dict[str, str]:
    _ensure_file()
    try:
        data = json.loads(PROMPT_SETTINGS_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = {}
    prompts = _active_default_prompts()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in prompts and isinstance(value, str) and value.strip():
                prompts[key] = value
    return prompts


def save_prompt_templates(prompts: Dict[str, str]) -> None:
    cleaned = {}
    for key in ACTIVE_PROMPT_KEYS:
        cleaned[key] = str(prompts.get(key, DEFAULT_PROMPTS[key]))
    PROMPT_SETTINGS_JSON.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")


def get_prompt_template(key: str) -> str:
    prompts = load_prompt_templates()
    if key in prompts:
        return prompts[key]
    return DEFAULT_PROMPTS.get(key, "")


def save_prompt_template(key: str, value: str) -> None:
    prompts = load_prompt_templates()
    if key not in ACTIVE_PROMPT_KEYS:
        raise ValueError(f"未知或已停用的提示词类型：{key}")
    prompts[key] = value
    save_prompt_templates(prompts)


def reset_prompt_template(key: str) -> None:
    prompts = load_prompt_templates()
    if key not in ACTIVE_PROMPT_KEYS:
        raise ValueError(f"未知或已停用的提示词类型：{key}")
    prompts[key] = DEFAULT_PROMPTS[key]
    save_prompt_templates(prompts)


def reset_all_prompt_templates() -> None:
    save_prompt_templates(_active_default_prompts())


def render_template(template: str, variables: Dict[str, object]) -> str:
    text = template
    for key, value in variables.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text.strip()
