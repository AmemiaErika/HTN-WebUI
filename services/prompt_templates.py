from services.prompt_store import get_prompt_template, render_template


def object_list_prompt(mode: str = "整体物品", parent_object: dict | None = None) -> str:
    """Build the prompt used by visual analyzers.

    mode:
    - 整体物品: identify complete standalone objects only.
    - 主要部件: split the selected parent object into large reusable parts.
    - 细节元素: split the selected parent object into small visual details.
    """
    parent_object = parent_object or {}
    variables = {
        "parent_name": parent_object.get("name", ""),
        "parent_description": parent_object.get("description", ""),
        "parent_position": parent_object.get("position", ""),
        "parent_bbox": parent_object.get("bbox", ""),
    }
    if mode == "主要部件":
        key = "object_list_parts"
    elif mode == "细节元素":
        key = "object_list_details"
    else:
        key = "object_list_overall"
    return render_template(get_prompt_template(key), variables)


def three_view_prompt(object_name: str, object_description: str, extra_prompt: str = "", aspect_ratio: str = "自动") -> str:
    return render_template(
        get_prompt_template("three_view"),
        {
            "object_name": object_name,
            "object_description": object_description,
            "extra_prompt": extra_prompt or "无",
            "aspect_ratio": aspect_ratio or "自动",
        },
    )




def overview_three_view_prompt(
    objects: list[dict],
    extra_prompt: str = "",
    layout: str = "设计板排版",
    aspect_ratio: str = "自动",
    split_degree: str = "仅拆分主体物",
) -> str:
    lines = []
    for i, obj in enumerate(objects, start=1):
        obj_id = obj.get("id", i)
        name = obj.get("name", "未命名对象")
        desc = obj.get("description", "")
        position = obj.get("position", "")
        bbox = obj.get("bbox", "")
        level = obj.get("level", "")
        line = f"{obj_id}. {name}"
        details = []
        if level:
            details.append(f"层级：{level}")
        if desc:
            details.append(f"外观：{desc}")
        if position:
            details.append(f"位置：{position}")
        if bbox:
            details.append(f"bbox：{bbox}")
        if details:
            line += "；" + "；".join(details)
        lines.append(line)
    objects_text = "\n".join(lines)
    return render_template(
        get_prompt_template("overview_three_view"),
        {
            "objects_text": objects_text,
            "extra_prompt": extra_prompt,
            "layout": layout,
            "aspect_ratio": aspect_ratio or "自动",
            "split_degree": split_degree or "仅拆分主体物",
        },
    )


def compose_prompt(composition_prompt: str, env_options: dict) -> str:
    return render_template(
        get_prompt_template("compose"),
        {
            "composition_prompt": composition_prompt,
            "time": env_options.get("time", "白天"),
            "lighting": env_options.get("lighting", "柔光"),
            "weather": env_options.get("weather", "晴天"),
            "style": env_options.get("style", "潮玩概念设计"),
            "camera": env_options.get("camera", "产品摄影视角"),
        },
    )


def sketch_refine_prompt(refine_prompt: str) -> str:
    return render_template(
        get_prompt_template("sketch_refine"),
        {
            "refine_prompt": refine_prompt,
        },
    )


def image_edit_prompt(
    references_text: str,
    edit_goals: str,
    detail_options: str = "",
    style_options: str = "",
    lighting_options: str = "",
    background_options: str = "",
    fusion_options: str = "",
    replace_options: str = "",
    extra_prompt: str = "",
    aspect_ratio: str = "自动",
) -> str:
    return render_template(
        get_prompt_template("image_edit"),
        {
            "references_text": references_text,
            "edit_goals": edit_goals,
            "detail_options": detail_options or "无",
            "style_options": style_options or "无",
            "lighting_options": lighting_options or "无",
            "background_options": background_options or "无",
            "fusion_options": fusion_options or "无",
            "replace_options": replace_options or "无",
            "extra_prompt": extra_prompt or "无",
            "aspect_ratio": aspect_ratio or "自动",
        },
    )
