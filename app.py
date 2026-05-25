from __future__ import annotations

from pathlib import Path
import re
import json
import html
import hashlib

from PIL import Image, ImageDraw, ImageFont, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

try:
    from streamlit_sortables import sort_items
except Exception:
    sort_items = None

from config import settings
from services.analyzer_factory import get_list_analyzer
from services.generator_factory import get_image_generator
from services.asset_service import add_asset, list_assets, delete_asset, update_asset
from services.category_service import list_categories, create_category, delete_category, get_all_categories
from services.result_service import list_results, add_result, delete_result, clear_results, archive_result_to_asset
from services.list_history_service import list_histories, add_list_history, update_list_history, delete_list_history
from services.app_config_store import load_app_config, save_app_config, apply_app_config
from services.custom_provider_service import (
    load_custom_providers,
    upsert_custom_provider,
    delete_custom_provider,
    custom_options_for,
    option_label,
    is_custom_option,
    get_custom_provider,
)
from services.providers.custom.openai_compatible import (
    CustomOpenAICompatibleVisionAnalyzer,
    CustomOpenAICompatibleImageGenerator,
)
from services.prompt_templates import object_list_prompt, image_edit_prompt
from services.prompt_store import (
    PROMPT_LABELS,
    PROMPT_VARIABLES,
    DEFAULT_PROMPTS,
    ACTIVE_PROMPT_KEYS,
    load_prompt_templates,
    save_prompt_template,
    reset_prompt_template,
    reset_all_prompt_templates,
    render_template,
)
from utils.file_utils import save_uploaded_file, image_to_data_url

st.set_page_config(page_title="AI 概念设计 WebUI", layout="wide", initial_sidebar_state="expanded")

BASE_ANALYZER_OPTIONS = ["gemini", "openai", "claude", "ensemble", "mock"]
BASE_GENERATOR_OPTIONS = ["gemini", "openai", "mock"]


def get_analyzer_options() -> list[str]:
    return BASE_ANALYZER_OPTIONS + custom_options_for("vision")


def get_generator_options() -> list[str]:
    return BASE_GENERATOR_OPTIONS + custom_options_for("image")
RESULT_TYPE_LABELS = {
    "three_view": "单对象三视图",
    "overview_three_view": "整体拆件三视图",
    "composition": "组合图",
    "sketch_refine": "草图细化",
    "image_edit": "图片编辑",
    "generation": "生成图",
}

ANALYSIS_MODES = ["整体物品", "主要部件", "细节元素"]
MODE_TO_LEVEL = {"整体物品": "object", "主要部件": "part", "细节元素": "detail"}

ASPECT_RATIO_OPTIONS = {
    "自动": "自动，由模型根据内容自行决定",
    "1:1 方图": "1:1 方形画幅",
    "4:3 横向": "4:3 横向画幅",
    "3:4 竖向": "3:4 竖向画幅",
    "16:9 横向": "16:9 横向画幅",
    "9:16 竖向": "9:16 竖向画幅",
    "A4 横向": "A4 横向设计板画幅",
    "A4 竖向": "A4 竖向设计板画幅",
    "21:9 极宽": "21:9 极宽横向画幅",
    "9:21 极长": "9:21 极长竖向画幅",
    "3:1 超宽": "3:1 超宽横向画幅",
    "1:3 超长": "1:3 超长竖向画幅",
}

OVERVIEW_SPLIT_DEGREE_OPTIONS = ["仅拆分主体物", "拆分到最细，精确到每个零件"]

STYLE_PRESETS = {
    "潮玩盲盒": "可爱潮玩盲盒风格，圆润比例，软胶/搪胶质感，干净高饱和配色，适合角色与小物件设计。",
    "3D卡通渲染": "3D卡通渲染风格，圆润体块，柔和高光，清晰材质，类似产品概念展示图。",
    "赛璐璐动画": "赛璐璐动画风格，干净线稿，清晰色块，少量明暗层次，整体轻快明亮。",
    "厚涂概念设计": "厚涂概念设计风格，笔触更丰富，明暗体积更强，适合角色、道具、场景概念图。",
    "水彩插画": "水彩插画风格，柔和边缘，轻盈透明的色彩叠加，纸面手绘质感。",
    "复古海报": "复古海报风格，颗粒感、旧印刷质感、偏复古配色，画面具有装饰性。",
    "产品渲染": "产品渲染风格，干净商业展示图，材质清晰，光影简洁，主体边缘明确。",
    "像素游戏": "像素游戏风格，低分辨率像素块，复古游戏感，轮廓简洁。",
    "黏土定格动画": "黏土定格动画风格，手工黏土质感，柔和不完美的表面，亲和可爱。",
    "极简扁平插画": "极简扁平插画风格，简化形体，低细节，纯色块与清晰轮廓。",
}


def is_checked(value) -> bool:
    """Return True only for an explicit checked value from st.data_editor.

    Empty cells in dynamically added rows can be NaN/NA; treating those as
    bool(value) would incorrectly become True in some cases.
    """
    try:
        if pd.isna(value):
            return False
    except Exception:
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是", "勾选"}
    return bool(value)


def level_label(level: str) -> str:
    return {"object": "整体物品", "part": "主要部件", "detail": "细节元素"}.get(str(level or ""), str(level or ""))


def object_for_prompt(obj: dict | None) -> dict:
    if not obj:
        return {}
    return {
        "id": obj.get("id", ""),
        "name": obj.get("name", ""),
        "description": obj.get("description", ""),
        "position": obj.get("position", ""),
        "bbox": obj.get("bbox", ""),
        "level": obj.get("level", "object"),
    }



def init_state():
    st.session_state.setdefault("source_image_path", "")
    st.session_state.setdefault("detected_objects", [])
    st.session_state.setdefault("last_generation", None)
    st.session_state.setdefault("selected_asset_ids", [])
    st.session_state.setdefault("pending_archive_result_id", "")
    st.session_state.setdefault("object_selected_index", None)
    st.session_state.setdefault("current_list_history_id", "")
    st.session_state.setdefault("analysis_mode", "整体物品")
    st.session_state.setdefault("edit_reference_images", [])


def get_runtime_config():
    config = load_app_config()
    analyzer_options = get_analyzer_options()
    generator_options = get_generator_options()
    analyzer = config.get("DEFAULT_LIST_ANALYZER", settings.DEFAULT_LIST_ANALYZER) or "gemini"
    generator = config.get("DEFAULT_IMAGE_GENERATOR", settings.DEFAULT_IMAGE_GENERATOR) or "gemini"
    if analyzer not in analyzer_options:
        analyzer = "mock" if "mock" in analyzer_options else analyzer_options[0]
    if generator not in generator_options:
        generator = "mock" if "mock" in generator_options else generator_options[0]
    config["DEFAULT_LIST_ANALYZER"] = analyzer
    config["DEFAULT_IMAGE_GENERATOR"] = generator
    apply_app_config(config)
    return config

def show_image_if_exists(path: str, caption: str = ""):
    """Safely display an image without crashing the whole Streamlit page.

    Some preview files may become partially written or corrupted after an interrupted
    generation/rerun. Streamlit raises a PIL OSError when it receives such a file.
    We verify and load the image first; invalid files are reported as warnings.
    """
    if not path:
        return
    p = Path(path)
    if not p.exists():
        st.warning(f"文件不存在：{path}")
        return
    try:
        with Image.open(p) as img:
            img.load()
            safe_img = img.convert("RGB").copy()
        st.image(safe_img, caption=caption, use_container_width=True)
    except Exception as exc:
        st.warning(f"图片预览失败，文件可能不完整或格式异常：{p.name}")
        with st.expander("查看错误详情", expanded=False):
            st.code(str(exc))


def asset_label(asset: dict) -> str:
    name = str(asset.get("name", "未命名") or "未命名").strip()
    category = str(asset.get("category", "未分类") or "未分类").strip()
    asset_id = str(asset.get("asset_id", "") or "").strip()
    # Native Streamlit selectbox supports typing after the dropdown is focused.
    # Keep name/category/id in one option label so typing any of them can定位素材.
    return f"{name} / {category}  [{asset_id}]"


def parse_asset_id(label: str) -> str:
    m = re.search(r"\[([^\[\]]+)\]\s*$", label)
    return m.group(1) if m else ""


def asset_image_path(asset: dict) -> str:
    """Return the display/generation image path stored in an asset record."""
    return str(asset.get("three_view_path") or asset.get("source_image_path") or "")




EDIT_REFERENCE_ROLES = ["主编辑图", "风格参考", "背景参考", "元素参考", "光影参考", "替换物件参考"]
EDIT_GOAL_OPTIONS = ["细化细节", "改变画风", "改变光影环境", "改变背景", "融合多个参考图", "替换局部物件"]


def add_edit_reference_image(path: str, name: str = "", role: str = "元素参考", source: str = "upload") -> None:
    if not path:
        return
    refs = st.session_state.setdefault("edit_reference_images", [])
    for item in refs:
        if item.get("path") == path:
            if role == "主编辑图":
                item["role"] = role
            return
    if role == "主编辑图":
        for item in refs:
            if item.get("role") == "主编辑图":
                item["role"] = "元素参考"
    refs.append({
        "path": path,
        "name": name or Path(path).name,
        "role": role,
        "source": source,
    })


def remove_edit_reference_image(index: int) -> None:
    refs = st.session_state.setdefault("edit_reference_images", [])
    if 0 <= index < len(refs):
        refs.pop(index)


def ensure_one_main_reference() -> None:
    refs = st.session_state.setdefault("edit_reference_images", [])
    if not refs:
        return
    main_indices = [i for i, item in enumerate(refs) if item.get("role") == "主编辑图"]
    if not main_indices:
        refs[0]["role"] = "主编辑图"
    elif len(main_indices) > 1:
        keep = main_indices[0]
        for i in main_indices[1:]:
            refs[i]["role"] = "元素参考"


def reference_summary_text(refs: list[dict]) -> str:
    lines = []
    for i, item in enumerate(refs, start=1):
        lines.append(f"{i}. {item.get('role', '参考图')}：{item.get('name') or Path(item.get('path', '')).name}")
    return "\n".join(lines) if lines else "无"


def build_image_edit_prompt_from_options(
    refs: list[dict],
    edit_goals: list[str],
    detail_strength: str = "中",
    keep_style_for_detail: bool = True,
    keep_composition_for_detail: bool = True,
    cleanup_sketch: bool = True,
    edge_enhance: bool = True,
    style_mode: str = "参考图迁移",
    style_strength: str = "中",
    style_preset: str = "",
    keep_color: bool = True,
    keep_composition_for_style: bool = True,
    time_of_day: str = "白天",
    lighting: str = "柔光",
    weather: str = "晴天",
    background_type: str = "展示台",
    background_complexity: str = "中",
    keep_foreground: bool = True,
    subject_preserve: str = "中",
    merge_strength: str = "中",
    auto_layout: bool = True,
    keep_composition_for_fusion: bool = True,
    replacement_target: str = "",
    replacement_target_source: str = "手动描述",
    replacement_strength: str = "中等",
    keep_style_for_replace: bool = True,
    keep_composition_for_replace: bool = True,
    keep_lighting_for_replace: bool = True,
    keep_surroundings_for_replace: bool = True,
    extra_prompt: str = "",
    aspect_ratio: str = "自动",
) -> str:
    detail_options = f"细化强度：{detail_strength}；保持原画风：{'是' if keep_style_for_detail else '否'}；保持原构图：{'是' if keep_composition_for_detail else '否'}；清理草稿感：{'是' if cleanup_sketch else '否'}；增强边缘清晰度：{'是' if edge_enhance else '否'}"
    style_preset_text = ""
    if style_mode == "预设风格套用" and style_preset:
        style_preset_text = f"；预设风格：{style_preset}；预设说明：{STYLE_PRESETS.get(style_preset, '')}"
    style_options = f"风格方式：{style_mode}；风格强度：{style_strength}{style_preset_text}；保留原配色：{'是' if keep_color else '否'}；保留原构图：{'是' if keep_composition_for_style else '否'}"
    lighting_options = f"时间：{time_of_day}；光照：{lighting}；天气/氛围：{weather}"
    background_options = f"背景类型：{background_type}；背景复杂度：{background_complexity}；保留前景摆放：{'是' if keep_foreground else '否'}"
    fusion_options = f"主体保留强度：{subject_preserve}；元素融合强度：{merge_strength}；自动排布：{'是' if auto_layout else '否'}；保留原构图：{'是' if keep_composition_for_fusion else '否'}"
    replacement_refs = [r for r in refs if r.get("role") == "替换物件参考"]
    if not replacement_refs:
        replacement_refs = [r for r in refs if r.get("role") == "元素参考"]
    replacement_ref_text = ", ".join([r.get("name") or Path(r.get("path", "")).name for r in replacement_refs]) or "未指定"
    replace_options = (
        f"目标定位方式：{replacement_target_source}；"
        f"被替换对象定位信息：{replacement_target or '未填写'}；"
        f"替换物件参考：{replacement_ref_text}；"
        f"替换强度：{replacement_strength}；"
        f"保持原画风：{'是' if keep_style_for_replace else '否'}；"
        f"保持原构图：{'是' if keep_composition_for_replace else '否'}；"
        f"保持整体光影：{'是' if keep_lighting_for_replace else '否'}；"
        f"保持周围物件不变：{'是' if keep_surroundings_for_replace else '否'}"
    )
    return image_edit_prompt(
        references_text=reference_summary_text(refs),
        edit_goals="、".join(edit_goals) if edit_goals else "细化细节",
        detail_options=detail_options if "细化细节" in edit_goals else "未启用",
        style_options=style_options if "改变画风" in edit_goals else "未启用",
        lighting_options=lighting_options if "改变光影环境" in edit_goals else "未启用",
        background_options=background_options if "改变背景" in edit_goals else "未启用",
        fusion_options=fusion_options if "融合多个参考图" in edit_goals else "未启用",
        replace_options=replace_options if "替换局部物件" in edit_goals else "未启用",
        extra_prompt=extra_prompt or "无",
        aspect_ratio=aspect_ratio,
    )

def _normalize_bbox_value(value):
    """Return a normalized [x1, y1, x2, y2] bbox or None.

    The analyzer prompt asks models to return normalized coordinates in 0-1.
    This helper is intentionally tolerant because some models may return strings
    or percentages. Invalid boxes are ignored rather than breaking the workflow.
    """
    if value is None:
        return None
    if isinstance(value, str):
        nums = re.findall(r"-?\d+(?:\.\d+)?", value)
        if len(nums) < 4:
            return None
        value = [float(x) for x in nums[:4]]
    if not isinstance(value, (list, tuple)) or len(value) < 4:
        return None
    try:
        coords = [float(x) for x in value[:4]]
    except Exception:
        return None

    # If a model returns percentages or pixel-like values, try to coerce.
    if max(coords) > 1.5 and max(coords) <= 100:
        coords = [x / 100.0 for x in coords]

    x1, y1, x2, y2 = coords
    # Some models may return [x, y, w, h]. If x2/y2 look like width/height,
    # convert only when it is strongly suggested.
    if x2 <= x1 or y2 <= y1:
        x2 = x1 + abs(x2)
        y2 = y1 + abs(y2)

    x1 = max(0.0, min(1.0, x1))
    y1 = max(0.0, min(1.0, y1))
    x2 = max(0.0, min(1.0, x2))
    y2 = max(0.0, min(1.0, y2))
    if x2 - x1 < 0.01 or y2 - y1 < 0.01:
        return None
    return [round(x1, 4), round(y1, 4), round(x2, 4), round(y2, 4)]


def normalize_detected_object(obj: dict, index: int = 0) -> dict:
    """Keep object list simple, while preserving visual location metadata."""
    if not isinstance(obj, dict):
        return {
            "id": index + 1,
            "name": "未命名物件",
            "description": str(obj),
            "position": "",
            "bbox": None,
            "level": "object",
            "parent_id": "",
            "parent_name": "",
        }

    name = (
        obj.get("name")
        or obj.get("名称")
        or obj.get("物件名称")
        or obj.get("object_name")
        or "未命名物件"
    )
    description = (
        obj.get("description")
        or obj.get("appearance")
        or obj.get("appearance_description")
        or obj.get("外观描述")
        or obj.get("外观")
        or obj.get("描述")
        or ""
    )
    position = (
        obj.get("position")
        or obj.get("位置")
        or obj.get("location")
        or obj.get("画面位置")
        or ""
    )
    obj_id = obj.get("id") or obj.get("编号") or obj.get("index") or index + 1
    try:
        obj_id = int(obj_id)
    except Exception:
        obj_id = index + 1
    bbox = _normalize_bbox_value(obj.get("bbox") or obj.get("box") or obj.get("bounding_box") or obj.get("范围"))
    level = obj.get("level") or obj.get("层级") or obj.get("type") or "object"
    parent_id = obj.get("parent_id") or obj.get("parentId") or obj.get("父级ID") or ""
    parent_name = obj.get("parent_name") or obj.get("parentName") or obj.get("父级名称") or ""
    return {
        "id": obj_id,
        "name": str(name).strip() or "未命名物件",
        "description": str(description).strip(),
        "position": str(position).strip(),
        "bbox": bbox,
        "level": str(level).strip() or "object",
        "parent_id": str(parent_id).strip(),
        "parent_name": str(parent_name).strip(),
    }


def normalize_detected_objects(objects: list[dict]) -> list[dict]:
    normalized = [normalize_detected_object(obj, i) for i, obj in enumerate(objects) if isinstance(obj, dict)]
    # Keep ids stable and sequential in the UI even if a model returns duplicates.
    for i, obj in enumerate(normalized):
        obj["id"] = i + 1
    return normalized


def _image_fingerprint(image_path: str) -> str:
    try:
        p = Path(image_path)
        data = p.read_bytes()[:1024 * 1024]
        stat = p.stat()
        return hashlib.sha256(data + str(stat.st_size).encode()).hexdigest()[:16]
    except Exception:
        return hashlib.sha256(str(image_path).encode()).hexdigest()[:16]


def _bbox_to_pixels(bbox: list[float], width: int, height: int, pad: int = 0):
    x1, y1, x2, y2 = bbox
    left = int(x1 * width) - pad
    top = int(y1 * height) - pad
    right = int(x2 * width) + pad
    bottom = int(y2 * height) + pad
    left = max(0, min(width - 1, left))
    top = max(0, min(height - 1, top))
    right = max(left + 1, min(width, right))
    bottom = max(top + 1, min(height, bottom))
    return left, top, right, bottom


def _draw_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], label: str, fill: tuple[int, int, int]):
    x, y = xy
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    text_bbox = draw.textbbox((x, y), label, font=font)
    pad = 4
    rect = (text_bbox[0] - pad, text_bbox[1] - pad, text_bbox[2] + pad, text_bbox[3] + pad)
    draw.rectangle(rect, fill=fill)
    draw.text((x, y), label, fill="white", font=font)


def build_object_visuals(image_path: str, objects: list[dict], selected_index: int | None = None) -> tuple[str, list[dict]]:
    """Create an annotated source image and bbox thumbnails for the object list.

    To reduce visual noise, all items are shown as numbered points by default;
    only the currently selected item receives a full orange bbox.
    """
    if not image_path or not Path(image_path).exists() or not objects:
        return "", objects

    preview_dir = settings.OUTPUT_DIR / "object_previews"
    crop_dir = preview_dir / "crops"
    preview_dir.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)

    image_key = _image_fingerprint(image_path)
    try:
        with Image.open(image_path) as source_img:
            source_img.load()
            img = source_img.convert("RGB").copy()
    except Exception as exc:
        st.warning(f"源图片读取失败，无法生成定位预览：{exc}")
        return "", objects
    width, height = img.size
    annotated = img.copy()
    draw = ImageDraw.Draw(annotated)

    visual_objects = []
    for i, obj in enumerate(objects):
        obj = dict(obj)
        bbox = _normalize_bbox_value(obj.get("bbox"))
        obj["bbox"] = bbox
        obj_id = int(obj.get("id") or i + 1)
        if bbox:
            left, top, right, bottom = _bbox_to_pixels(bbox, width, height, pad=0)
            is_selected = selected_index == i
            color = (255, 88, 0) if is_selected else (40, 120, 255)

            # Numbered point: use bbox center, less noisy than showing every rectangle.
            cx = int((left + right) / 2)
            cy = int((top + bottom) / 2)
            radius = max(12, int(min(width, height) * (0.015 if not is_selected else 0.02)))
            draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=color, outline="white", width=3)
            try:
                font = ImageFont.load_default()
            except Exception:
                font = None
            label = str(obj_id)
            tb = draw.textbbox((0, 0), label, font=font)
            tx = cx - int((tb[2] - tb[0]) / 2)
            ty = cy - int((tb[3] - tb[1]) / 2)
            draw.text((tx, ty), label, fill="white", font=font)

            # Only selected object gets a bbox.
            if is_selected:
                line_width = 5
                for offset in range(line_width):
                    draw.rectangle((left - offset, top - offset, right + offset, bottom + offset), outline=color)

            crop_pad = max(12, int(max(width, height) * 0.018))
            crop_box = _bbox_to_pixels(bbox, width, height, pad=crop_pad)
            crop = img.crop(crop_box)
            crop.thumbnail((260, 260))
            crop_path = crop_dir / f"{image_key}_{i + 1}.png"
            crop.save(crop_path)
            obj["thumbnail_path"] = str(crop_path)
            try:
                obj["thumbnail_data_url"] = image_to_data_url(str(crop_path))
            except Exception:
                obj["thumbnail_data_url"] = ""
        else:
            obj["thumbnail_path"] = ""
            obj["thumbnail_data_url"] = ""
        visual_objects.append(obj)

    selected_suffix = "none" if selected_index is None else str(selected_index + 1)
    annotated_path = preview_dir / f"{image_key}_selected_{selected_suffix}.png"
    tmp_path = preview_dir / f".{image_key}_selected_{selected_suffix}.tmp.png"
    try:
        annotated.save(tmp_path, format="PNG")
        tmp_path.replace(annotated_path)
    except Exception as exc:
        st.warning(f"定位预览图保存失败：{exc}")
        return "", visual_objects
    return str(annotated_path), visual_objects

def object_location_text(obj: dict) -> str:
    parts = []
    if obj.get("level"):
        parts.append(f"对象层级：{obj.get('level')}")
    if obj.get("parent_name"):
        parts.append(f"父级对象：{obj.get('parent_name')}")
    if obj.get("position"):
        parts.append(f"位置描述：{obj.get('position')}")
    if obj.get("bbox"):
        parts.append(f"原图定位框 bbox：{obj.get('bbox')}")
    return "\n".join(parts)




def build_overview_objects(objects: list[dict], limit: int | None = None) -> list[dict]:
    cleaned = []
    for i, obj in enumerate(normalize_detected_objects(objects or []), start=1):
        if limit is not None and len(cleaned) >= limit:
            break
        cleaned.append({
            "id": obj.get("id", i),
            "name": obj.get("name", "未命名对象"),
            "description": obj.get("description", ""),
            "position": obj.get("position", ""),
            "bbox": obj.get("bbox"),
            "level": obj.get("level", ""),
            "parent_name": obj.get("parent_name", ""),
        })
    return cleaned


def generate_overview_three_view_result(
    *,
    image_path: str,
    objects: list[dict],
    generator_choice: str,
    extra_prompt: str = "",
    layout: str = "设计板排版",
    aspect_ratio: str = "自动",
    split_degree: str = "仅拆分主体物",
    source_context: str = "当前拆解 list",
):
    # 整体拆件三视图固定使用当前 list 的全部对象。
    overview_objects = build_overview_objects(objects, None)
    if not overview_objects:
        raise RuntimeError("当前没有可用于生成整体拆件三视图的 list。")
    generator = get_image_generator(generator_choice)
    result = generator.generate_overview_three_view(
        image_path,
        overview_objects,
        extra_prompt=extra_prompt,
        layout=layout,
        aspect_ratio=aspect_ratio,
        split_degree=split_degree,
    )
    object_names = "、".join([str(o.get("name", "")) for o in overview_objects if o.get("name")])
    saved = add_result({
        "type": "overview_three_view",
        "name": "整体拆件三视图",
        "category": "未分类",
        "description": f"{source_context}；对象数量：{len(overview_objects)}；对象：{object_names}",
        "source_image_path": image_path,
        "image_path": result.get("image_path", ""),
        "prompt": result.get("prompt", ""),
        "provider": result.get("provider", generator_choice),
        "meta": {
            "objects": overview_objects,
            "object_count": len(overview_objects),
            "layout": layout,
            "extra_prompt": extra_prompt,
            "aspect_ratio": aspect_ratio,
            "split_degree": split_degree,
        },
    })
    return saved


def merge_edited_objects(original_objects: list[dict], edited_rows: list[dict]) -> list[dict]:
    merged = []
    for i, row in enumerate(edited_rows):
        original = original_objects[i] if i < len(original_objects) else {}
        base = dict(original)
        base["id"] = i + 1
        base["name"] = str(row.get("name") or row.get("物件名称") or base.get("name") or "未命名物件").strip()
        base["description"] = str(row.get("description") or row.get("外观描述") or base.get("description") or "").strip()
        base["position"] = str(row.get("position") or row.get("位置") or base.get("position") or "").strip()
        base["bbox"] = _normalize_bbox_value(base.get("bbox"))
        merged.append(base)
    return normalize_detected_objects(merged)


def get_categories(assets: list[dict]) -> list[str]:
    return get_all_categories(assets)


def searchable_selectbox(label: str, options: list, key: str, index: int = 0, **kwargs):
    """A thin wrapper around Streamlit selectbox.

    It keeps the UI as a normal dropdown. After opening/focusing the dropdown,
    users can type to filter/locate long option lists. No extra input boxes or
    action buttons are added.
    """
    if not options:
        return None
    safe_index = min(max(index, 0), len(options) - 1)
    return st.selectbox(label, options, index=safe_index, key=key, **kwargs)


def render_asset_card(asset: dict, compact: bool = False, sidebar_mode: bool = False):
    asset_id = asset.get("asset_id", "")
    with st.container(border=True):
        st.markdown(f"**{asset.get('name', '未命名')}**")
        st.caption(f"{asset.get('category', '')} · {asset.get('provider', '')}")
        if asset.get("three_view_path"):
            show_image_if_exists(asset.get("three_view_path", ""), "")

        if sidebar_mode:
            selected = asset_id in st.session_state.get("selected_asset_ids", [])
            label = "从组合移除" if selected else "加入组合"
            if st.button(label, key=f"sidebar_select_{asset_id}", use_container_width=True):
                current = list(st.session_state.get("selected_asset_ids", []))
                if selected:
                    current = [x for x in current if x != asset_id]
                else:
                    current.append(asset_id)
                st.session_state["selected_asset_ids"] = current
                st.rerun()
            if st.button("删除素材", key=f"sidebar_delete_{asset_id}", use_container_width=True):
                delete_asset(asset_id)
                st.rerun()
            return

        if not compact:
            with st.expander("详情"):
                st.write(asset.get("description", ""))
                st.code(asset.get("prompt", "")[:2000])

        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            new_name = st.text_input("重命名", value=asset.get("name", ""), key=f"rename_{asset_id}")
        with c2:
            new_category = st.text_input("分类", value=asset.get("category", "未分类"), key=f"cat_{asset_id}")
        with c3:
            st.write("")
            if st.button("保存", key=f"save_asset_{asset_id}"):
                update_asset(asset_id, {"name": new_name, "category": new_category})
                st.rerun()
        if st.button("删除", key=f"delete_{asset_id}"):
            delete_asset(asset_id)
            st.rerun()


def render_category_drag_manager(assets: list[dict]):
    st.subheader("分类管理")

    categories = get_categories(assets)
    asset_by_id = {a.get("asset_id"): a for a in assets}

    st.markdown("##### 新建分类")
    new_cat_only = st.text_input("新建分类名称", key="create_category_name")
    if st.button("创建分类", use_container_width=True, disabled=not new_cat_only.strip()):
        create_category(new_cat_only.strip())
        st.success(f"已创建分类：{new_cat_only.strip()}")
        st.rerun()

    st.divider()
    st.markdown("##### 删除分类")
    if not categories:
        st.info("暂无可删除分类。")
    else:
        protected_categories = {"未分类"}
        deletable_categories = [c for c in categories if c not in protected_categories]
        if not deletable_categories:
            st.caption("当前只有基础分类，暂无可删除分类。")
        else:
            delete_cat = searchable_selectbox("选择要删除的分类", deletable_categories, key="delete_category_select")
            cat_assets = [a for a in assets if str(a.get("category", "未分类") or "未分类") == delete_cat]
            st.caption(f"该分类下有 {len(cat_assets)} 个素材。")

            target_options = [c for c in categories if c != delete_cat]
            if "未分类" not in target_options:
                target_options.append("未分类")
            move_target = "未分类"
            if cat_assets:
                move_target = searchable_selectbox("删除后将素材移动到", target_options, key="delete_category_move_target")

            confirm_delete = st.checkbox("确认删除该分类", key="delete_category_confirm")
            if st.button("删除分类", use_container_width=True, disabled=not confirm_delete):
                for asset in cat_assets:
                    update_asset(asset.get("asset_id", ""), {"category": move_target})
                delete_category(delete_cat)
                st.success(f"已删除分类：{delete_cat}")
                st.rerun()

    st.divider()
    st.markdown("##### 移动素材到已有分类")
    if not assets:
        st.info("当前没有素材。可以先创建分类，后续入库时选择该分类。")
        return

    if sort_items is not None:
        containers = []
        for cat in categories:
            items = [asset_label(a) for a in assets if str(a.get("category", "未分类") or "未分类") == cat]
            containers.append({"header": cat, "items": items})
        try:
            sorted_containers = sort_items(containers, multi_containers=True, key="asset_category_sort")
            if st.button("应用拖拽分类", use_container_width=True):
                for container in sorted_containers:
                    cat = container.get("header", "未分类")
                    for label in container.get("items", []):
                        aid = parse_asset_id(label)
                        if aid in asset_by_id:
                            update_asset(aid, {"category": cat})
                st.success("分类已更新。")
                st.rerun()
        except Exception as e:
            st.warning(f"拖拽组件暂不可用，已切换为快速移动。原因：{e}")
            render_quick_move_assets(assets, categories)
    else:
        render_quick_move_assets(assets, categories)

def render_quick_move_assets(assets: list[dict], categories: list[str]):
    if not assets:
        st.info("暂无素材可移动。")
        return
    selected_label = searchable_selectbox("素材", [asset_label(a) for a in assets], key="fallback_asset_select")
    target_cat = searchable_selectbox("目标分类", categories, key="fallback_target_cat")
    if st.button("移动素材", use_container_width=True):
        aid = parse_asset_id(selected_label)
        if aid:
            update_asset(aid, {"category": target_cat})
            st.rerun()


def render_sidebar_upload_to_library(assets: list[dict]):
    categories = get_all_categories(assets)
    if "未分类" not in categories:
        categories = ["未分类"] + categories

    def _render_upload_form():
        uploaded_asset = st.file_uploader(
            "选择图片",
            type=["png", "jpg", "jpeg", "webp"],
            key="sidebar_library_upload_file",
        )
        upload_name = st.text_input("素材名称", value="", key="sidebar_library_upload_name")
        upload_category = st.selectbox("入库分类", categories, index=0, key="sidebar_library_upload_category")
        upload_description = st.text_area("描述（可选）", value="", height=80, key="sidebar_library_upload_description")
        if st.button("确认上传入库", use_container_width=True, disabled=uploaded_asset is None, key="sidebar_library_upload_confirm"):
            path = save_uploaded_file(uploaded_asset, settings.ASSET_DIR, "asset_upload")
            name = upload_name.strip() or Path(uploaded_asset.name).stem or "用户上传素材"
            add_asset({
                "name": name,
                "category": upload_category or "未分类",
                "description": upload_description.strip(),
                "source_image_path": path,
                "three_view_path": path,
                "prompt": "用户从侧栏上传入库",
                "provider": "manual_upload",
            })
            st.success("已上传到素材仓库。")
            st.rerun()

    if hasattr(st, "popover"):
        with st.popover("上传图片到仓库", use_container_width=True):
            _render_upload_form()
    else:
        with st.expander("上传图片到仓库", expanded=False):
            _render_upload_form()


def render_source_from_library(assets: list[dict]):
    valid_assets = [a for a in assets if asset_image_path(a)]
    if not valid_assets:
        st.info("仓库暂无可用于拆解的图片。")
        return

    labels = [asset_label(a) for a in valid_assets]
    selected_label = searchable_selectbox("选择仓库图片", labels, key="source_library_asset_select")
    selected_id = parse_asset_id(selected_label)
    selected_asset = next((a for a in valid_assets if a.get("asset_id") == selected_id), None)

    if not selected_asset:
        return

    selected_path = asset_image_path(selected_asset)
    st.caption(f"分类：{selected_asset.get('category', '未分类')}")
    show_image_if_exists(selected_path, selected_asset.get("name", "仓库图片"))

    if st.button("载入仓库图片", use_container_width=True, key="source_library_asset_load"):
        st.session_state["source_image_path"] = selected_path
        st.session_state["detected_objects"] = []
        st.session_state["object_selected_index"] = None
        st.session_state["current_list_history_id"] = ""
        st.success("已从仓库载入图片。")
        st.rerun()


def render_asset_sidebar():
    with st.sidebar:
        st.markdown("### 素材仓库")
        assets = list_assets()
        render_sidebar_upload_to_library(assets)
        st.divider()

        if not assets:
            st.info("暂无素材。可先点击上方“上传图片到仓库”，或在“生成结果”中点击入库。")
            return

        keyword = st.text_input("搜索素材", value="", key="sidebar_asset_search")
        selected_ids = st.session_state.get("selected_asset_ids", [])
        st.caption(f"总计 {len(assets)} 个素材，已加入组合 {len(selected_ids)} 个")
        if selected_ids and st.button("清空组合选择", use_container_width=True):
            st.session_state["selected_asset_ids"] = []
            st.rerun()

        kw = keyword.strip().lower()
        for cat in get_categories(assets):
            cat_assets = [a for a in assets if str(a.get("category", "未分类") or "未分类") == cat]
            if kw:
                cat_assets = [
                    a for a in cat_assets
                    if kw in str(a.get("name", "")).lower()
                    or kw in str(a.get("category", "")).lower()
                    or kw in str(a.get("description", "")).lower()
                ]
            if not cat_assets and kw:
                continue
            with st.expander(f"{cat}（{len(cat_assets)}）", expanded=bool(cat_assets)):
                if not cat_assets:
                    st.caption("该分类暂无素材。")
                for asset in cat_assets:
                    render_asset_card(asset, compact=True, sidebar_mode=True)

def build_result_copy_text(result: dict, name: str, category: str, description: str) -> str:
    type_label = RESULT_TYPE_LABELS.get(result.get("type", "generation"), result.get("type", "generation"))
    return "\n".join([
        f"名称：{name}",
        f"分类：{category}",
        f"类型：{type_label}",
        f"模型：{result.get('provider', '')}",
        f"图片路径：{result.get('image_path', '')}",
        f"生成时间：{result.get('created_at', '')}",
        f"描述：{description}",
        "",
        "生成提示词：",
        result.get("prompt", ""),
    ])


def render_clipboard_copy_button(text: str, key: str, label: str = "复制信息"):
    safe_text = html.escape(text)
    safe_key = re.sub(r"[^a-zA-Z0-9_]", "_", key)
    components.html(
        f"""
        <div style="display:flex; align-items:center; gap:8px; width:100%;">
          <textarea id="{safe_key}_text" style="position:absolute; left:-9999px; top:-9999px;">{safe_text}</textarea>
          <button id="{safe_key}_btn" style="width:100%; padding:0.45rem 0.75rem; border-radius:0.5rem; border:1px solid #d0d0d0; background:#ffffff; cursor:pointer;">
            {html.escape(label)}
          </button>
          <span id="{safe_key}_msg" style="font-size:12px;color:#1f7a1f;white-space:nowrap;"></span>
        </div>
        <script>
          const btn_{safe_key} = document.getElementById("{safe_key}_btn");
          const text_{safe_key} = document.getElementById("{safe_key}_text");
          const msg_{safe_key} = document.getElementById("{safe_key}_msg");
          btn_{safe_key}.onclick = async () => {{
            try {{
              await navigator.clipboard.writeText(text_{safe_key}.value);
              msg_{safe_key}.innerText = "已复制";
            }} catch (err) {{
              text_{safe_key}.style.position = "static";
              text_{safe_key}.style.width = "100%";
              text_{safe_key}.style.height = "120px";
              text_{safe_key}.select();
              document.execCommand("copy");
              msg_{safe_key}.innerText = "已复制 / 可手动复制";
            }}
          }};
        </script>
        """,
        height=42,
    )

def render_result_card(result: dict):
    rid = result.get("result_id", "")
    type_label = RESULT_TYPE_LABELS.get(result.get("type", "generation"), result.get("type", "generation"))
    with st.container(border=True):
        top1, top2 = st.columns([1, 1])
        with top1:
            st.markdown(f"**{result.get('name', '未命名结果')}**")
            st.caption(f"{type_label} · {result.get('provider', '')} · {result.get('created_at', '')}")
            if result.get("archived"):
                st.success(f"已入库：{result.get('asset_id', '')}")
            show_image_if_exists(result.get("image_path", ""), "")
        with top2:
            name = st.text_input("入库名称", value=result.get("name", "未命名结果"), key=f"result_name_{rid}")
            category = st.text_input("建议分类", value=result.get("category", "未分类"), key=f"result_category_{rid}")
            description = st.text_area("描述", value=result.get("description", ""), height=80, key=f"result_desc_{rid}")
            st.markdown("**生成提示词**")
            st.code(result.get("prompt", ""), language="text")

            copy_text = build_result_copy_text(result, name, category, description)
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("入库", type="primary", key=f"archive_{rid}", disabled=result.get("archived", False)):
                    st.session_state["pending_archive_result_id"] = rid
                    st.rerun()
            with c2:
                render_clipboard_copy_button(copy_text, key=f"copy_result_{rid}", label="复制信息")
            with c3:
                if st.button("删除", key=f"delete_result_{rid}"):
                    delete_result(rid)
                    if st.session_state.get("pending_archive_result_id") == rid:
                        st.session_state["pending_archive_result_id"] = ""
                    st.rerun()

            if st.session_state.get("pending_archive_result_id") == rid and not result.get("archived"):
                st.warning("请确认是否将这张生成图入库。")
                available_categories = get_categories(list_assets())
                if category and category not in available_categories:
                    available_categories = [category] + available_categories
                confirm_category = st.selectbox(
                    "确认入库分类",
                    available_categories,
                    index=available_categories.index(category) if category in available_categories else 0,
                    key=f"confirm_category_{rid}",
                )
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("确认入库", type="primary", key=f"confirm_archive_{rid}", use_container_width=True):
                        create_category(confirm_category)
                        asset = archive_result_to_asset(rid, {"name": name, "category": confirm_category, "description": description})
                        if asset:
                            st.session_state["pending_archive_result_id"] = ""
                            st.success(f"已入库：{asset.get('name', '')}")
                            st.rerun()
                        else:
                            st.error("入库失败。")
                with cc2:
                    if st.button("取消", key=f"cancel_archive_{rid}", use_container_width=True):
                        st.session_state["pending_archive_result_id"] = ""
                        st.rerun()


def history_label(item: dict) -> str:
    image_name = item.get("image_name") or Path(item.get("image_path", "")).name or "未命名图片"
    count = len(item.get("objects", []) or [])
    created = item.get("created_at", "")
    provider = item.get("provider") or item.get("analyzer", "")
    mode = item.get("mode") or "整体物品"
    parent = item.get("parent_object") or {}
    parent_name = parent.get("name", "") if isinstance(parent, dict) else ""
    parent_text = f" · 父级：{parent_name}" if parent_name else ""
    return f"{created} · {image_name} · {mode}{parent_text} · {count} 项 · {provider} [{item.get('history_id', '')}]"


def parse_history_id(label: str) -> str:
    m = re.search(r"\[([^\[\]]+)\]\s*$", label)
    return m.group(1) if m else ""


def _safe_file_sha256(path: str) -> str:
    try:
        p = Path(path)
        if not p.exists() or not p.is_file():
            return ""
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return ""


def is_same_image_file(path_a: str, path_b: str) -> bool:
    if not path_a or not path_b:
        return False
    try:
        pa = Path(path_a)
        pb = Path(path_b)
        if pa.exists() and pb.exists() and pa.resolve() == pb.resolve():
            return True
    except Exception:
        pass
    sha_a = _safe_file_sha256(path_a)
    sha_b = _safe_file_sha256(path_b)
    return bool(sha_a and sha_b and sha_a == sha_b)


def histories_for_image(image_path: str) -> list[dict]:
    if not image_path:
        return []
    matched = []
    for history in list_histories():
        if is_same_image_file(image_path, history.get("image_path", "")):
            matched.append(history)
    return matched


def object_replacement_label(obj: dict, index: int) -> str:
    obj_id = obj.get("id", index + 1)
    name = obj.get("name", "未命名对象")
    level = level_label(obj.get("level", "object"))
    position = obj.get("position", "")
    suffix = f" · {position}" if position else ""
    return f"{obj_id}. {name} / {level}{suffix} [{index}]"


def parse_object_index(label: str) -> int | None:
    m = re.search(r"\[([0-9]+)\]\s*$", label or "")
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def replacement_target_text_from_object(obj: dict, history: dict | None = None) -> str:
    history = history or {}
    lines = ["使用拆解 list 精确定位被替换对象。"]
    if history.get("history_id"):
        lines.append(f"拆解记录 ID：{history.get('history_id')}")
    if history.get("mode"):
        lines.append(f"拆解模式：{history.get('mode')}")
    level = obj.get("level", "")
    if level:
        lines.append(f"对象层级：{level_label(level)}")
    lines.append(f"对象编号：{obj.get('id', '')}")
    lines.append(f"对象名称：{obj.get('name', '')}")
    if obj.get("description"):
        lines.append(f"外观描述：{obj.get('description')}")
    if obj.get("position"):
        lines.append(f"位置描述：{obj.get('position')}")
    if obj.get("bbox"):
        lines.append(f"bbox 定位：{obj.get('bbox')}")
    parent = obj.get("parent_name", "")
    if not parent and isinstance(history.get("parent_object"), dict):
        parent = (history.get("parent_object") or {}).get("name", "")
    if parent:
        lines.append(f"父级对象：{parent}")
    lines.append("请只替换上述 list 指定对象，不要替换其他相似物件。")
    return "\n".join(lines)


def render_list_history_page(generator_choice: str):
    st.subheader("拆解历史")
    histories = list_histories()
    if not histories:
        st.info("暂无拆解历史。请先在“图片拆解”中分析图片。")
        return

    keyword = st.text_input("搜索拆解历史", value="", key="list_history_search")
    kw = keyword.strip().lower()
    filtered = histories
    if kw:
        def match_history(item: dict) -> bool:
            haystack = " ".join([
                str(item.get("image_name", "")),
                str(item.get("image_path", "")),
                str(item.get("provider", "")),
                str(item.get("analyzer", "")),
                str(item.get("mode", "")),
                str((item.get("parent_object") or {}).get("name", "")) if isinstance(item.get("parent_object"), dict) else "",
                " ".join(str(o.get("name", "")) + " " + str(o.get("description", "")) + " " + str(o.get("position", "")) for o in item.get("objects", []) or []),
            ]).lower()
            return kw in haystack
        filtered = [item for item in histories if match_history(item)]

    st.caption(f"显示 {len(filtered)} / {len(histories)} 条记录")
    if not filtered:
        st.warning("没有匹配的拆解历史。")
        return

    labels = [history_label(item) for item in filtered]
    selected_label = searchable_selectbox("选择拆解记录", labels, key="list_history_select")
    history_id = parse_history_id(selected_label or "")
    history = next((item for item in filtered if item.get("history_id") == history_id), filtered[0])
    history_id = history.get("history_id", "")

    h1, h2, h3 = st.columns([2, 1, 1])
    with h1:
        
        parent_info = history.get("parent_object") or {}
        parent_text = f" · 父级：{parent_info.get('name', '')}" if isinstance(parent_info, dict) and parent_info.get("name") else ""
        st.caption(f"记录 ID：{history_id} · 模式：{history.get('mode', '整体物品')}{parent_text} · 创建时间：{history.get('created_at', '')} · 更新时间：{history.get('updated_at', '')}")
    with h2:
        if st.button("载入到图片拆解", key=f"load_history_{history_id}", use_container_width=True):
            st.session_state["source_image_path"] = history.get("image_path", "")
            st.session_state["detected_objects"] = normalize_detected_objects(history.get("objects", []) or [])
            st.session_state["object_selected_index"] = 0 if st.session_state["detected_objects"] else None
            st.session_state["current_list_history_id"] = history_id
            # 不在这里直接修改 analysis_mode_radio。
            # Streamlit 不允许在同一轮运行中修改已经实例化过的 widget key。
            # 只更新业务状态，下一轮渲染图片拆解页时会在 radio 创建前同步。
            mode_to_load = history.get("mode", "整体物品")
            if mode_to_load not in ANALYSIS_MODES:
                mode_to_load = "整体物品"
            st.session_state["analysis_mode"] = mode_to_load
            st.success("已载入到图片拆解。")
            st.rerun()
    with h3:
        if st.button("删除该 list", key=f"delete_history_{history_id}", use_container_width=True):
            delete_list_history(history_id)
            if st.session_state.get("current_list_history_id") == history_id:
                st.session_state["current_list_history_id"] = ""
            st.rerun()

    image_path = history.get("image_path", "")
    objects = normalize_detected_objects(history.get("objects", []) or [])
    selected_key = f"history_selected_index_{history_id}"
    if selected_key not in st.session_state:
        st.session_state[selected_key] = 0 if objects else None
    current_selected_index = st.session_state.get(selected_key)
    if current_selected_index is not None and current_selected_index >= len(objects):
        current_selected_index = 0 if objects else None
        st.session_state[selected_key] = current_selected_index

    if not objects:
        st.info("该记录中没有物件 list。")
        return

    annotated_path, visual_objects = build_object_visuals(image_path, objects, current_selected_index)

    preview_col, list_col = st.columns([1, 1.25])
    with preview_col:
        st.markdown("**原图定位预览**")
        if annotated_path:
            show_image_if_exists(annotated_path, "数字点为识别对象，橙框为当前选择")
        else:
            show_image_if_exists(image_path, "原图")

    with list_col:
        st.markdown("**可编辑 list**")
        display_df = pd.DataFrame({
            "选择": [i == current_selected_index for i in range(len(visual_objects))],
            "删除": [False for _ in range(len(visual_objects))],
            "编号": [obj.get("id", i + 1) for i, obj in enumerate(visual_objects)],
            "预览": [obj.get("thumbnail_data_url", "") for obj in visual_objects],
            "层级": [level_label(obj.get("level", "object")) for obj in visual_objects],
            "name": [obj.get("name", "") for obj in visual_objects],
            "description": [obj.get("description", "") for obj in visual_objects],
            "position": [obj.get("position", "") for obj in visual_objects],
        })
        edited = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "选择": st.column_config.CheckboxColumn("选择", help="当前只支持同时勾选 1 个物件", width="small"),
                "删除": st.column_config.CheckboxColumn("删除", help="勾选后从 list 中删除该条目", width="small"),
                "编号": st.column_config.NumberColumn("编号", width="small"),
                "预览": st.column_config.ImageColumn("局部图", width="small", help="根据 bbox 从原图自动裁切"),
                "层级": st.column_config.TextColumn("层级", width="small"),
                "name": st.column_config.TextColumn("物件名称", width="medium"),
                "description": st.column_config.TextColumn("外观描述", width="large"),
                "position": st.column_config.TextColumn("位置", width="small"),
            },
            column_order=["选择", "删除", "编号", "预览", "层级", "name", "description", "position"],
            disabled=["编号", "预览", "层级"],
            key=f"history_objects_editor_{history_id}",
        )

    delete_indices = [i for i, value in enumerate(edited.get("删除", [])) if is_checked(value)]
    selected_indices = [i for i, value in enumerate(edited.get("选择", [])) if is_checked(value) and i not in delete_indices]
    edited_rows = edited.drop(columns=["选择", "删除", "编号", "预览", "层级"], errors="ignore").to_dict("records")
    edited_objects_all = merge_edited_objects(visual_objects, edited_rows)
    if delete_indices:
        delete_names = [str(edited_objects_all[i].get("name", f"条目 {i + 1}")) for i in delete_indices if i < len(edited_objects_all)]
        st.warning("已勾选删除：" + "、".join(delete_names))
        confirm_key = f"confirm_delete_history_items_{history_id}"
        button_key = f"confirm_delete_history_items_button_{history_id}"
        confirm_delete_items = st.checkbox("确认删除以上 list 条目", key=confirm_key)
        if st.button("确认删除选中条目", key=button_key, disabled=not confirm_delete_items, use_container_width=True):
            edited_objects = [obj for i, obj in enumerate(edited_objects_all) if i not in delete_indices]
            update_list_history(history_id, {"objects": edited_objects})
            st.session_state[selected_key] = 0 if edited_objects else None
            st.success(f"已删除 {len(delete_indices)} 个 list 条目。")
            st.rerun()
    edited_objects = edited_objects_all
    for i, obj in enumerate(edited_objects):
        if i < len(visual_objects):
            obj["thumbnail_path"] = visual_objects[i].get("thumbnail_path", "")
            obj["thumbnail_data_url"] = visual_objects[i].get("thumbnail_data_url", "")

    previous_index = st.session_state.get(selected_key)
    if len(selected_indices) > 1:
        new_indices = [i for i in selected_indices if i != previous_index]
        selected_index = new_indices[-1] if new_indices else selected_indices[0]
        st.session_state[selected_key] = selected_index
        st.warning("当前只支持同时生成 1 张图，已自动保留一个勾选项。")
        st.rerun()
    elif len(selected_indices) == 1:
        selected_index = selected_indices[0]
        if selected_index != previous_index:
            st.session_state[selected_key] = selected_index
            st.rerun()
    else:
        selected_index = None
        if previous_index is not None:
            st.session_state[selected_key] = None

    selected_row = edited_objects[selected_index] if selected_index is not None and selected_index < len(edited_objects) else None

    history_single_extra = st.text_input(
        "单件三视图补充要求",
        value="",
        placeholder="例如：保持结构清晰、视图间距更大、不要加装饰文字",
        key=f"history_single_extra_{history_id}",
    )
    history_single_aspect_label = st.selectbox(
        "单件三视图画幅大小",
        list(ASPECT_RATIO_OPTIONS.keys()),
        index=list(ASPECT_RATIO_OPTIONS.keys()).index("4:3 横向"),
        key=f"history_single_aspect_{history_id}",
    )
    history_single_aspect = ASPECT_RATIO_OPTIONS.get(history_single_aspect_label, history_single_aspect_label)

    c1, c2 = st.columns([1, 1])
    with c1:
        if st.button("保存 list 修改", type="primary", key=f"save_history_{history_id}", use_container_width=True):
            update_list_history(history_id, {"objects": edited_objects})
            st.success("已保存 list 修改。")
            st.rerun()
    with c2:
        if st.button("生成三视图", key=f"history_generate_three_view_{history_id}", type="primary", disabled=not selected_row or not image_path, use_container_width=True):
            try:
                generator = get_image_generator(generator_choice)
                name = selected_row.get("name", "未命名物件")
                desc = selected_row.get("description", "")
                loc_text = object_location_text(selected_row)
                prompt_desc = desc if not loc_text else f"{desc}\n{loc_text}"
                with st.spinner(f"正在生成：{name}"):
                    result = generator.generate_three_view(
                        image_path,
                        name,
                        prompt_desc,
                        extra_prompt=history_single_extra,
                        aspect_ratio=history_single_aspect,
                    )
                    saved = add_result({
                        "type": "three_view",
                        "name": name,
                        "category": "未分类",
                        "description": prompt_desc,
                        "source_image_path": image_path,
                        "image_path": result.get("image_path", ""),
                        "prompt": result.get("prompt", ""),
                        "provider": result.get("provider", generator_choice),
                        "meta": {
                            "history_id": history_id,
                            "object_id": selected_row.get("id"),
                            "object_bbox": selected_row.get("bbox"),
                            "object_position": selected_row.get("position"),
                            "extra_prompt": history_single_extra,
                            "aspect_ratio": history_single_aspect,
                        },
                    })
                    update_list_history(history_id, {"objects": edited_objects})
                    st.success(f"已生成：{saved['name']}。请到“生成结果”确认后入库。")
                    show_image_if_exists(saved.get("image_path"), saved["name"])
            except Exception as e:
                st.error(str(e))


    st.divider()
    st.markdown("**整体拆件三视图**")
    hv1, hv2, hv3, hv4 = st.columns([1, 1, 1, 2])
    with hv1:
        history_overview_layout = st.selectbox("排版方式", ["设计板排版", "网格排版", "横向长图"], key=f"history_overview_layout_{history_id}")
    with hv2:
        history_overview_split_degree = st.selectbox("拆分程度", OVERVIEW_SPLIT_DEGREE_OPTIONS, index=0, key=f"history_overview_split_degree_{history_id}")
    with hv3:
        history_overview_aspect_label = st.selectbox(
            "画幅大小",
            list(ASPECT_RATIO_OPTIONS.keys()),
            index=list(ASPECT_RATIO_OPTIONS.keys()).index("16:9 横向"),
            key=f"history_overview_aspect_{history_id}",
        )
    with hv4:
        history_overview_extra = st.text_input("补充要求", value="", placeholder="例如：减少文字、保持原图配色", key=f"history_overview_extra_{history_id}")
    history_overview_aspect = ASPECT_RATIO_OPTIONS.get(history_overview_aspect_label, history_overview_aspect_label)

    if st.button("生成整体拆件三视图", key=f"history_generate_overview_{history_id}", type="primary", disabled=not edited_objects or not image_path, use_container_width=True):
        try:
            update_list_history(history_id, {"objects": edited_objects})
            with st.spinner("正在生成整体拆件三视图..."):
                saved = generate_overview_three_view_result(
                    image_path=image_path,
                    objects=edited_objects,
                    generator_choice=generator_choice,
                    extra_prompt=history_overview_extra,
                    layout=history_overview_layout,
                    aspect_ratio=history_overview_aspect,
                    split_degree=history_overview_split_degree,
                    source_context=f"拆解历史 / {history.get('mode', '当前')} list",
                )
                st.success("已生成整体拆件三视图。请到“生成结果”确认后入库。")
                show_image_if_exists(saved.get("image_path"), saved.get("name", "整体拆件三视图"))
        except Exception as e:
            st.error(str(e))

    st.caption("当前只支持同时生成 1 张三视图；编辑后可先保存，也可以直接生成。")

def render_results_page():
    h1, h2 = st.columns([3, 1])
    with h1:
        st.subheader("生成结果")
    with h2:
        if st.button("清空所有结果", use_container_width=True, disabled=not list_results()):
            clear_results()
            st.session_state["pending_archive_result_id"] = ""
            st.rerun()
    st.caption("所有生成图片会先进入这里，不会自动入库。确认满意后点击“入库”。")
    results = list_results()
    if not results:
        st.info("暂无生成结果。")
        return

    type_options = ["全部"] + list(RESULT_TYPE_LABELS.values())
    type_reverse = {v: k for k, v in RESULT_TYPE_LABELS.items()}
    c1, c2 = st.columns([1, 1])
    with c1:
        type_filter = st.selectbox("结果类型", type_options, key="result_type_filter")
    with c2:
        show_archived = st.checkbox("显示已入库结果", value=True)

    filtered = results
    if type_filter != "全部":
        filtered = [r for r in filtered if r.get("type") == type_reverse.get(type_filter)]
    if not show_archived:
        filtered = [r for r in filtered if not r.get("archived")]

    st.caption(f"显示 {len(filtered)} / {len(results)}")
    for result in filtered:
        render_result_card(result)

def render_model_settings_tab():
    app_config = load_app_config()
    analyzer_options = get_analyzer_options()
    generator_options = get_generator_options()
    default_analyzer = app_config.get("DEFAULT_LIST_ANALYZER", settings.DEFAULT_LIST_ANALYZER)
    if default_analyzer not in analyzer_options:
        default_analyzer = "mock"
    default_generator = app_config.get("DEFAULT_IMAGE_GENERATOR", settings.DEFAULT_IMAGE_GENERATOR)
    if default_generator not in generator_options:
        default_generator = "mock"

    st.subheader("模型与 API 设置")
    c1, c2 = st.columns(2)
    with c1:
        analyzer_choice = st.selectbox(
            "拆解 list 模型",
            analyzer_options,
            index=analyzer_options.index(default_analyzer),
            format_func=option_label,
            key="settings_analyzer_choice",
        )
    with c2:
        generator_choice = st.selectbox(
            "图像生成模型",
            generator_options,
            index=generator_options.index(default_generator),
            format_func=option_label,
            key="settings_generator_choice",
        )

    st.markdown("##### API Key")
    k1, k2, k3 = st.columns(3)
    with k1:
        gemini_key = st.text_input("Gemini / Banana API Key", value=app_config.get("GEMINI_API_KEY", ""), type="password", key="settings_api_key_gemini")
    with k2:
        openai_key = st.text_input("OpenAI API Key", value=app_config.get("OPENAI_API_KEY", ""), type="password", key="settings_api_key_openai")
    with k3:
        anthropic_key = st.text_input("Claude / Anthropic API Key", value=app_config.get("ANTHROPIC_API_KEY", ""), type="password", key="settings_api_key_anthropic")

    with st.expander("高级：模型名称"):
        m1, m2 = st.columns(2)
        with m1:
            gemini_vision_model = st.text_input("Gemini 视觉理解模型", value=app_config.get("GEMINI_VISION_MODEL", settings.GEMINI_VISION_MODEL), key="settings_model_gemini_vision")
            openai_vision_model = st.text_input("OpenAI 视觉理解模型", value=app_config.get("OPENAI_VISION_MODEL", settings.OPENAI_VISION_MODEL), key="settings_model_openai_vision")
            anthropic_model = st.text_input("Claude 视觉理解模型", value=app_config.get("ANTHROPIC_MODEL", settings.ANTHROPIC_MODEL), key="settings_model_anthropic")
        with m2:
            gemini_image_model = st.text_input("Gemini 图像生成模型", value=app_config.get("GEMINI_IMAGE_MODEL", settings.GEMINI_IMAGE_MODEL), key="settings_model_gemini_image")
            openai_image_model = st.text_input("OpenAI 图像生成模型", value=app_config.get("OPENAI_IMAGE_MODEL", settings.OPENAI_IMAGE_MODEL), key="settings_model_openai_image")

    runtime_config = {
        "DEFAULT_LIST_ANALYZER": analyzer_choice,
        "DEFAULT_IMAGE_GENERATOR": generator_choice,
        "GEMINI_API_KEY": gemini_key,
        "GEMINI_VISION_MODEL": gemini_vision_model,
        "GEMINI_IMAGE_MODEL": gemini_image_model,
        "OPENAI_API_KEY": openai_key,
        "OPENAI_VISION_MODEL": openai_vision_model,
        "OPENAI_IMAGE_MODEL": openai_image_model,
        "ANTHROPIC_API_KEY": anthropic_key,
        "ANTHROPIC_MODEL": anthropic_model,
    }

    b1, b2 = st.columns([1, 1])
    with b1:
        if st.button("保存模型与 API 设置", type="primary", use_container_width=True):
            save_app_config(runtime_config)
            apply_app_config(runtime_config)
            st.success("已保存。")
            st.rerun()
    with b2:
        if st.button("切换为 mock 测试模式", use_container_width=True):
            runtime_config["DEFAULT_LIST_ANALYZER"] = "mock"
            runtime_config["DEFAULT_IMAGE_GENERATOR"] = "mock"
            save_app_config(runtime_config)
            apply_app_config(runtime_config)
            st.success("已切换 mock。")
            st.rerun()

    st.info("本地原型会把 Key 明文保存到 data/app_config.json 和 data/custom_providers.json。正式部署前建议改成环境变量或密钥服务。")

    st.divider()
    st.subheader("自定义 API 提供商")
    providers = load_custom_providers()

    with st.expander("新增 / 编辑自定义 Provider", expanded=False):
        edit_options = [""] + [p.get("id", "") for p in providers]
        selected_edit_id = st.selectbox(
            "选择已有 Provider 编辑",
            edit_options,
            format_func=lambda x: "新建 Provider" if not x else option_label(f"custom:{x}"),
            key="custom_provider_edit_select",
        )
        editing = get_custom_provider(selected_edit_id) if selected_edit_id else None
        default_name = editing.get("name", "") if editing else ""
        default_base_url = editing.get("base_url", "") if editing else ""
        default_api_key = editing.get("api_key", "") if editing else ""
        default_model = editing.get("model", "") if editing else ""
        default_type = editing.get("provider_type", "both") if editing else "both"
        default_enabled = editing.get("enabled", True) if editing else True

        cp1, cp2 = st.columns(2)
        with cp1:
            custom_name = st.text_input("Provider 名称", value=default_name, placeholder="例如：my_openrouter", key="custom_provider_name")
            custom_base_url = st.text_input("Base URL", value=default_base_url, placeholder="例如：https://api.example.com/v1", key="custom_provider_base_url")
            custom_api_key = st.text_input("API Key", value=default_api_key, type="password", key="custom_provider_api_key")
        with cp2:
            custom_model = st.text_input("模型名称", value=default_model, placeholder="例如：google/gemini-2.5-flash-image-preview", key="custom_provider_model")
            type_labels = {
                "vision": "拆解 list / 视觉分析",
                "image": "图像生成 / 编辑",
                "both": "同时用于拆解和生成",
            }
            type_values = ["vision", "image", "both"]
            custom_type = st.selectbox(
                "接口类型",
                type_values,
                index=type_values.index(default_type) if default_type in type_values else 2,
                format_func=lambda x: type_labels.get(x, x),
                key="custom_provider_type",
            )
            custom_format = st.selectbox("请求格式", ["openai_compatible"], index=0, key="custom_provider_format")
            custom_enabled = st.checkbox("启用", value=default_enabled, key="custom_provider_enabled")

        save_col, test_col, del_col = st.columns(3)
        current_provider_payload = {
            "id": selected_edit_id or "",
            "name": custom_name,
            "base_url": custom_base_url,
            "api_key": custom_api_key,
            "model": custom_model,
            "provider_type": custom_type,
            "request_format": custom_format,
            "enabled": custom_enabled,
        }
        with save_col:
            if st.button("保存自定义 Provider", type="primary", use_container_width=True):
                if not custom_name.strip() or not custom_base_url.strip() or not custom_api_key.strip() or not custom_model.strip():
                    st.error("请填写 Provider 名称、Base URL、API Key 和模型名称。")
                else:
                    saved = upsert_custom_provider(current_provider_payload)
                    st.success(f"已保存：{saved.get('name')}")
                    st.rerun()
        with test_col:
            if st.button("测试连接", use_container_width=True):
                try:
                    temp_config = dict(current_provider_payload)
                    if custom_type in {"vision", "both"}:
                        tester = CustomOpenAICompatibleVisionAnalyzer(temp_config)
                        msg = tester.test_connection()
                        st.success(f"视觉分析测试完成：{msg}")
                    else:
                        tester = CustomOpenAICompatibleImageGenerator(temp_config)
                        path = tester.test_connection()
                        st.success("图像生成测试完成。")
                        show_image_if_exists(path, "自定义 Provider 测试图")
                except Exception as e:
                    st.error(f"测试失败：{e}")
        with del_col:
            if selected_edit_id and st.button("删除该 Provider", use_container_width=True):
                delete_custom_provider(selected_edit_id)
                st.success("已删除。")
                st.rerun()

    if providers:
        st.markdown("##### 已保存的自定义 Provider")
        provider_rows = []
        type_label_map = {"vision": "拆解", "image": "生成", "both": "拆解 + 生成"}
        for p in providers:
            provider_rows.append({
                "名称": p.get("name", ""),
                "类型": type_label_map.get(p.get("provider_type", "both"), p.get("provider_type", "")),
                "模型": p.get("model", ""),
                "Base URL": p.get("base_url", ""),
                "启用": "是" if p.get("enabled", True) else "否",
                "ID": p.get("id", ""),
            })
        st.dataframe(pd.DataFrame(provider_rows), hide_index=True, use_container_width=True)
    else:
        st.caption("暂无自定义 Provider。")

def render_prompt_settings_tab():
    st.subheader("提示词设置")
    prompts = load_prompt_templates()
    prompt_keys = list(ACTIVE_PROMPT_KEYS)
    selected_key = st.selectbox("选择要编辑的步骤", prompt_keys, format_func=lambda k: PROMPT_LABELS.get(k, k))
    variables = PROMPT_VARIABLES.get(selected_key, [])
    st.info("可用变量：" + "、".join(variables) if variables else "这个步骤没有变量。")
    edited_prompt = st.text_area("提示词内容", value=prompts.get(selected_key, DEFAULT_PROMPTS[selected_key]), height=420, key=f"prompt_editor_{selected_key}")

    c1, c2, c3 = st.columns(3)
    with c1:
        if st.button("保存当前提示词", type="primary"):
            save_prompt_template(selected_key, edited_prompt)
            st.success("已保存。")
            st.rerun()
    with c2:
        if st.button("重置当前提示词"):
            reset_prompt_template(selected_key)
            st.success("已重置当前提示词。")
            st.rerun()
    with c3:
        if st.button("重置全部提示词"):
            reset_all_prompt_templates()
            st.success("已重置全部提示词。")
            st.rerun()

    st.divider()
    st.subheader("预览渲染后的 Prompt")
    preview_vars = {
        "object_name": "橙黑主角玩偶",
        "object_description": "橙黑配色的潮玩角色，猪鼻造型，穿黑色外套。",
        "parent_name": "复古播放器主体",
        "parent_description": "米白和深灰色方形复古播放器，带黄色提手和绿色频谱屏幕。",
        "parent_position": "画面中央偏上",
        "parent_bbox": "[0.12, 0.12, 0.76, 0.74]",
        "objects_text": "1. 复古播放器主体；外观：米白和深灰色方形复古播放器，带黄色提手和绿色频谱屏幕；位置：画面中央\n2. 黄色磁带；外观：黄色透明磁带，带白色标签和圆形磁带孔；位置：画面左下角",
        "extra_prompt": "减少文字，保持原图配色。",
        "layout": "设计板排版",
        "aspect_ratio": "16:9 横向",
        "split_degree": "仅拆分主体物",
        "references_text": "主编辑图：上传图片 1\n风格参考：上传图片 2",
        "edit_goals": "细化细节、改变光影环境",
        "detail_options": "保持原画风：是；保持原构图：是；细化强度：中",
        "style_options": "未启用",
        "lighting_options": "时间：黄昏；光照：柔光；氛围：梦幻氛围",
        "background_options": "未启用",
        "fusion_options": "未启用",
    }
    st.code(render_template(edited_prompt, preview_vars), language="text")


def render_settings_page():
    tab_model, tab_prompt = st.tabs(["模型 / API", "提示词"])
    with tab_model:
        render_model_settings_tab()
    with tab_prompt:
        render_prompt_settings_tab()


def render_image_edit_page(generator_choice: str):
    st.subheader("图片编辑")
    st.caption("上传一张或多张参考图，给每张图指定用途，再通过预设参数一键生成。")

    upload_col, asset_col = st.columns([1.3, 1])
    with upload_col:
        uploaded_files = st.file_uploader(
            "上传参考图",
            type=["png", "jpg", "jpeg", "webp"],
            accept_multiple_files=True,
            key="image_edit_uploads",
        )
        default_role = st.selectbox("本次上传图片的默认用途", EDIT_REFERENCE_ROLES, index=0, key="image_edit_default_upload_role")
        if uploaded_files:
            for uploaded in uploaded_files:
                path = save_uploaded_file(uploaded, settings.UPLOAD_DIR, "edit_ref")
                role = default_role
                # 多图上传时只自动设置第一张为主编辑图；其余图片作为元素参考，避免多个主图互相覆盖。
                if not st.session_state.get("edit_reference_images"):
                    role = "主编辑图"
                elif default_role == "主编辑图":
                    role = "元素参考"
                add_edit_reference_image(path, uploaded.name, role, "upload")
            ensure_one_main_reference()
    with asset_col:
        selected_ids = st.session_state.get("selected_asset_ids", [])
        selected_assets = [a for a in list_assets() if a.get("asset_id") in selected_ids]
        if selected_assets:
            st.write(f"左侧仓库已选 {len(selected_assets)} 个素材")
            asset_role = st.selectbox("加入已选素材的用途", EDIT_REFERENCE_ROLES, index=3, key="image_edit_asset_role")
            if st.button("将左侧已选素材加入参考图", use_container_width=True):
                for asset in selected_assets:
                    path = asset.get("three_view_path") or asset.get("source_image_path")
                    add_edit_reference_image(path, asset.get("name", "素材"), asset_role, "asset")
                ensure_one_main_reference()
                st.success("已加入参考图。")
                st.rerun()
        else:
            st.info("也可以先在左侧素材仓库点击“加入组合”，再把素材加入图片编辑参考图。")

    refs = st.session_state.get("edit_reference_images", [])
    ensure_one_main_reference()
    refs = st.session_state.get("edit_reference_images", [])
    current_main_refs = [r for r in refs if r.get("role") == "主编辑图"]
    current_main_path = current_main_refs[0].get("path", "") if current_main_refs else ""

    if refs:
        st.markdown("**参考图列表**")
        for i, item in enumerate(list(refs)):
            c1, c2, c3, c4 = st.columns([0.9, 1.1, 1.6, 0.6])
            with c1:
                show_image_if_exists(item.get("path"), item.get("name", "参考图"))
            with c2:
                role_key = f"edit_ref_role_{i}_{hashlib.md5(item.get('path','').encode()).hexdigest()[:8]}"
                current_role = item.get("role", "元素参考")
                role_index = EDIT_REFERENCE_ROLES.index(current_role) if current_role in EDIT_REFERENCE_ROLES else 3
                new_role = st.selectbox("用途", EDIT_REFERENCE_ROLES, index=role_index, key=role_key)
                if new_role != current_role:
                    if new_role == "主编辑图":
                        for j, ref in enumerate(refs):
                            if j != i and ref.get("role") == "主编辑图":
                                ref["role"] = "元素参考"
                    refs[i]["role"] = new_role
                    st.session_state["edit_reference_images"] = refs
                    st.rerun()
            with c3:
                st.write(item.get("name") or Path(item.get("path", "")).name)
                st.caption(f"来源：{item.get('source', 'upload')} / {Path(item.get('path', '')).name}")
            with c4:
                if st.button("删除", key=f"delete_edit_ref_{i}"):
                    remove_edit_reference_image(i)
                    ensure_one_main_reference()
                    st.rerun()
        if st.button("清空参考图", key="clear_edit_refs"):
            st.session_state["edit_reference_images"] = []
            st.rerun()
    else:
        st.info("请先上传至少一张主编辑图。")

    st.divider()
    st.markdown("**编辑目标**")
    edit_goals = st.multiselect(
        "你想做什么？",
        EDIT_GOAL_OPTIONS,
        default=["细化细节"],
        key="image_edit_goals",
    )
    if not edit_goals:
        edit_goals = ["细化细节"]

    with st.expander("预设参数", expanded=True):
        if "细化细节" in edit_goals:
            st.markdown("**细化细节**")
            d1, d2, d3, d4, d5 = st.columns(5)
            with d1:
                detail_strength = st.selectbox("细化强度", ["低", "中", "高"], index=1, key="edit_detail_strength")
            with d2:
                keep_style_for_detail = st.checkbox("保持原画风", value=True, key="edit_keep_style_detail")
            with d3:
                keep_composition_for_detail = st.checkbox("保持原构图", value=True, key="edit_keep_comp_detail")
            with d4:
                cleanup_sketch = st.checkbox("清理草稿感", value=True, key="edit_cleanup_sketch")
            with d5:
                edge_enhance = st.checkbox("增强边缘", value=True, key="edit_edge_enhance")
        else:
            detail_strength, keep_style_for_detail, keep_composition_for_detail, cleanup_sketch, edge_enhance = "中", True, True, True, True

        if "改变画风" in edit_goals:
            st.markdown("**改变画风**")
            s1, s2, s3, s4 = st.columns(4)
            with s1:
                style_mode = st.selectbox("风格方式", ["保持原风格微调", "参考图迁移", "预设风格套用"], index=1, key="edit_style_mode")
            with s2:
                style_strength = st.selectbox("风格强度", ["低", "中", "高"], index=1, key="edit_style_strength")
            with s3:
                keep_color = st.checkbox("保留原配色", value=True, key="edit_keep_color")
            with s4:
                keep_composition_for_style = st.checkbox("保留原构图", value=True, key="edit_keep_comp_style")
            if style_mode == "预设风格套用":
                style_preset = st.selectbox(
                    "预设风格",
                    list(STYLE_PRESETS.keys()),
                    index=0,
                    key="edit_style_preset",
                )
                st.caption(STYLE_PRESETS.get(style_preset, ""))
            else:
                style_preset = ""
        else:
            style_mode, style_strength, style_preset, keep_color, keep_composition_for_style = "参考图迁移", "中", "", True, True

        if "改变光影环境" in edit_goals:
            st.markdown("**改变光影环境**")
            l1, l2, l3 = st.columns(3)
            with l1:
                time_of_day = st.selectbox("时间", ["白天", "黄昏", "夜晚", "室内灯光"], index=0, key="edit_time")
            with l2:
                lighting = st.selectbox("光照", ["柔光", "强聚光", "逆光", "霓虹", "摄影棚"], index=0, key="edit_lighting")
            with l3:
                weather = st.selectbox("天气 / 氛围", ["晴天", "阴天", "雨天", "雾气", "梦幻氛围"], index=0, key="edit_weather")
        else:
            time_of_day, lighting, weather = "白天", "柔光", "晴天"

        if "改变背景" in edit_goals:
            st.markdown("**改变背景**")
            b1, b2, b3 = st.columns(3)
            with b1:
                background_type = st.selectbox("背景类型", ["纯色", "展示台", "室内", "街道", "商店陈列", "参考图背景"], index=1, key="edit_bg_type")
            with b2:
                background_complexity = st.selectbox("背景复杂度", ["低", "中", "高"], index=1, key="edit_bg_complexity")
            with b3:
                keep_foreground = st.checkbox("保留前景摆放", value=True, key="edit_keep_foreground")
        else:
            background_type, background_complexity, keep_foreground = "展示台", "中", True

        if "融合多个参考图" in edit_goals:
            st.markdown("**融合多个参考图**")
            f1, f2, f3, f4 = st.columns(4)
            with f1:
                subject_preserve = st.selectbox("主体保留强度", ["低", "中", "高"], index=1, key="edit_subject_preserve")
            with f2:
                merge_strength = st.selectbox("元素融合强度", ["低", "中", "高"], index=1, key="edit_merge_strength")
            with f3:
                auto_layout = st.checkbox("自动排布", value=True, key="edit_auto_layout")
            with f4:
                keep_composition_for_fusion = st.checkbox("保留原构图", value=True, key="edit_keep_comp_fusion")
        else:
            subject_preserve, merge_strength, auto_layout, keep_composition_for_fusion = "中", "中", True, True

        if "替换局部物件" in edit_goals:
            st.markdown("**替换局部物件**")
            matched_histories = histories_for_image(current_main_path)
            replacement_target_source = st.radio(
                "替换目标定位方式",
                ["手动描述", "从拆解 list 选择"],
                index=1 if matched_histories else 0,
                horizontal=True,
                key="edit_replacement_target_source",
            )
            selected_replacement_history = None
            selected_replacement_object = None
            replacement_target_extra = ""

            if replacement_target_source == "从拆解 list 选择":
                if matched_histories:
                    history_labels = [history_label(h) for h in matched_histories]
                    selected_history_label = searchable_selectbox(
                        "选择主编辑图对应的拆解 list",
                        history_labels,
                        key="edit_replacement_history_select",
                    )
                    selected_history_id = parse_history_id(selected_history_label or "")
                    selected_replacement_history = next((h for h in matched_histories if h.get("history_id") == selected_history_id), matched_histories[0])
                    history_objects = normalize_detected_objects(selected_replacement_history.get("objects", []) or [])
                    if history_objects:
                        object_labels = [object_replacement_label(obj, i) for i, obj in enumerate(history_objects)]
                        selected_object_label = searchable_selectbox(
                            "选择要替换的对象",
                            object_labels,
                            key="edit_replacement_object_select",
                        )
                        selected_obj_index = parse_object_index(selected_object_label)
                        if selected_obj_index is None or selected_obj_index >= len(history_objects):
                            selected_obj_index = 0
                        selected_replacement_object = history_objects[selected_obj_index]
                        replacement_target = replacement_target_text_from_object(selected_replacement_object, selected_replacement_history)

                        vp1, vp2 = st.columns([1, 1])
                        with vp1:
                            annotated_path, visual_objects = build_object_visuals(current_main_path, history_objects, selected_obj_index)
                            show_image_if_exists(annotated_path or current_main_path, "拆解 list 定位预览")
                        with vp2:
                            st.markdown("**当前替换目标**")
                            st.write(selected_replacement_object.get("name", "未命名对象"))
                            st.caption(selected_replacement_object.get("description", ""))
                            st.caption(f"位置：{selected_replacement_object.get('position', '')}")
                            st.caption(f"bbox：{selected_replacement_object.get('bbox', '')}")

                        replacement_target_extra = st.text_area(
                            "替换目标补充说明（可选）",
                            value="",
                            placeholder="例如：只替换这个黄色盒子，不要改动它后面的角色和旁边的道具。",
                            height=70,
                            key="edit_replacement_target_extra",
                        )
                        if replacement_target_extra.strip():
                            replacement_target += "\n用户补充定位说明：" + replacement_target_extra.strip()
                    else:
                        st.warning("这条拆解历史中没有可选对象，请改用手动描述。")
                        replacement_target = st.text_area(
                            "要替换的对象描述",
                            value="",
                            placeholder="例如：画面左下角的黄色小盒子 / 中央角色手上的配件 / 右侧的圆形装饰物",
                            height=80,
                            key="edit_replacement_target_manual_fallback_empty",
                        )
                else:
                    st.info("当前主编辑图没有匹配到拆解历史，请先在“图片拆解”中分析这张图，或改用手动描述。")
                    replacement_target = st.text_area(
                        "要替换的对象描述",
                        value="",
                        placeholder="例如：画面左下角的黄色小盒子 / 中央角色手上的配件 / 右侧的圆形装饰物",
                        height=80,
                        key="edit_replacement_target_manual_fallback",
                    )
            else:
                replacement_target = st.text_area(
                    "要替换的对象描述",
                    value="",
                    placeholder="例如：画面左下角的黄色小盒子 / 中央角色手上的配件 / 右侧的圆形装饰物",
                    height=80,
                    key="edit_replacement_target",
                )

            r1, r2, r3, r4, r5 = st.columns(5)
            with r1:
                replacement_strength = st.selectbox("替换强度", ["保守", "中等", "强"], index=1, key="edit_replacement_strength")
            with r2:
                keep_style_for_replace = st.checkbox("保持原画风", value=True, key="edit_replace_keep_style")
            with r3:
                keep_composition_for_replace = st.checkbox("保持原构图", value=True, key="edit_replace_keep_comp")
            with r4:
                keep_lighting_for_replace = st.checkbox("保持整体光影", value=True, key="edit_replace_keep_light")
            with r5:
                keep_surroundings_for_replace = st.checkbox("周围物件不变", value=True, key="edit_replace_keep_surroundings")
            replacement_refs = [r for r in refs if r.get("role") == "替换物件参考"]
            if replacement_refs:
                st.caption("将使用用途为“替换物件参考”的图片作为替换对象。")
            else:
                st.caption("请把替换对象图片的用途设为“替换物件参考”；如果没有，将尝试使用元素参考图。")
        else:
            replacement_target, replacement_strength = "", "中等"
            replacement_target_source = "未启用"
            selected_replacement_history = None
            selected_replacement_object = None
            replacement_target_extra = ""
            keep_style_for_replace, keep_composition_for_replace, keep_lighting_for_replace, keep_surroundings_for_replace = True, True, True, True

    option_col1, option_col2 = st.columns([2, 1])
    with option_col1:
        extra_prompt = st.text_area(
            "补充说明（可选）",
            value="",
            placeholder="例如：不改变角色表情；背景不要太花；保留透明亚克力质感。",
            height=90,
            key="image_edit_extra_prompt",
        )
    with option_col2:
        aspect_label = st.selectbox(
            "画幅大小",
            list(ASPECT_RATIO_OPTIONS.keys()),
            index=list(ASPECT_RATIO_OPTIONS.keys()).index("自动"),
            key="image_edit_aspect",
        )
    aspect_ratio = ASPECT_RATIO_OPTIONS.get(aspect_label, aspect_label)

    edit_prompt = build_image_edit_prompt_from_options(
        refs=refs,
        edit_goals=edit_goals,
        detail_strength=detail_strength,
        keep_style_for_detail=keep_style_for_detail,
        keep_composition_for_detail=keep_composition_for_detail,
        cleanup_sketch=cleanup_sketch,
        edge_enhance=edge_enhance,
        style_mode=style_mode,
        style_strength=style_strength,
        style_preset=style_preset,
        keep_color=keep_color,
        keep_composition_for_style=keep_composition_for_style,
        time_of_day=time_of_day,
        lighting=lighting,
        weather=weather,
        background_type=background_type,
        background_complexity=background_complexity,
        keep_foreground=keep_foreground,
        subject_preserve=subject_preserve,
        merge_strength=merge_strength,
        auto_layout=auto_layout,
        keep_composition_for_fusion=keep_composition_for_fusion,
        replacement_target=replacement_target,
        replacement_target_source=replacement_target_source,
        replacement_strength=replacement_strength,
        keep_style_for_replace=keep_style_for_replace,
        keep_composition_for_replace=keep_composition_for_replace,
        keep_lighting_for_replace=keep_lighting_for_replace,
        keep_surroundings_for_replace=keep_surroundings_for_replace,
        extra_prompt=extra_prompt,
        aspect_ratio=aspect_ratio,
    )

    with st.expander("查看自动生成提示词", expanded=False):
        st.code(edit_prompt, language="text")

    main_refs = [r for r in refs if r.get("role") == "主编辑图"]
    generate_disabled = not refs or not main_refs
    if st.button("一键生成图片编辑结果", type="primary", disabled=generate_disabled, use_container_width=True):
        try:
            ordered_refs = main_refs + [r for r in refs if r.get("role") != "主编辑图"]
            image_paths = [r.get("path") for r in ordered_refs if r.get("path")]
            generator = get_image_generator(generator_choice)
            with st.spinner("正在生成图片编辑结果..."):
                result = generator.edit_images(image_paths, edit_prompt, aspect_ratio=aspect_ratio)
                saved = add_result({
                    "type": "image_edit",
                    "name": "图片编辑结果",
                    "category": "未分类",
                    "description": "、".join(edit_goals),
                    "source_image_path": main_refs[0].get("path", "") if main_refs else "",
                    "image_path": result.get("image_path", ""),
                    "prompt": result.get("prompt", edit_prompt),
                    "provider": result.get("provider", generator_choice),
                    "meta": {
                        "edit_goals": edit_goals,
                        "aspect_ratio": aspect_ratio,
                        "references": ordered_refs,
                        "extra_prompt": extra_prompt,
                        "style_mode": style_mode if "改变画风" in edit_goals else "",
                        "style_strength": style_strength if "改变画风" in edit_goals else "",
                        "style_preset": style_preset if "改变画风" in edit_goals else "",
                        "replacement_target": replacement_target if "替换局部物件" in edit_goals else "",
                        "replacement_target_source": replacement_target_source if "替换局部物件" in edit_goals else "",
                        "replacement_target_history_id": (selected_replacement_history or {}).get("history_id", "") if "替换局部物件" in edit_goals else "",
                        "replacement_target_object": selected_replacement_object if "替换局部物件" in edit_goals else {},
                        "replacement_strength": replacement_strength if "替换局部物件" in edit_goals else "",
                    },
                })
                st.success("已生成图片编辑结果。请到“生成结果”确认后入库。")
                show_image_if_exists(saved.get("image_path"), "图片编辑结果")
        except Exception as e:
            st.error(str(e))


def main():
    init_state()
    app_config = get_runtime_config()
    analyzer_choice = app_config["DEFAULT_LIST_ANALYZER"]
    generator_choice = app_config["DEFAULT_IMAGE_GENERATOR"]

    render_asset_sidebar()
    st.caption(f"当前模型：拆解 list = {option_label(analyzer_choice)}，图像生成 = {option_label(generator_choice)}。可在“设置”中修改。")

    tab_a, tab_history, tab_edit, tab_results, tab_categories, tab_settings = st.tabs(["图片拆解", "拆解历史", "图片编辑", "生成结果", "分类管理", "设置"])

    with tab_a:
        st.subheader("1. 选择参考图")
        upload_col, library_col, preview_col = st.columns([1, 1, 1.15])
        with upload_col:
            uploaded = st.file_uploader("本地上传图片", type=["png", "jpg", "jpeg", "webp"], key="source_upload")
            if uploaded:
                path = save_uploaded_file(uploaded, settings.UPLOAD_DIR, "source")
                st.session_state["source_image_path"] = path
                st.session_state["detected_objects"] = []
                st.session_state["object_selected_index"] = None
                st.session_state["current_list_history_id"] = ""
                st.success("图片已上传")
        with library_col:
            st.markdown("**从仓库载入**")
            render_source_from_library(list_assets())
        with preview_col:
            show_image_if_exists(st.session_state["source_image_path"], "当前参考图")

        st.divider()
        st.subheader("2. 分层拆解 list")

        # 如果从“拆解历史”载入了不同模式，需要在 radio 实例化前同步 widget key。
        desired_mode = st.session_state.get("analysis_mode", "整体物品")
        if desired_mode not in ANALYSIS_MODES:
            desired_mode = "整体物品"
            st.session_state["analysis_mode"] = desired_mode
        if st.session_state.get("analysis_mode_radio") != desired_mode:
            st.session_state["analysis_mode_radio"] = desired_mode

        mode = st.radio(
            "拆解模式",
            ANALYSIS_MODES,
            horizontal=True,
            key="analysis_mode_radio",
        )
        st.session_state["analysis_mode"] = mode

        parent_object = None
        current_objects_for_parent = normalize_detected_objects(st.session_state.get("detected_objects", []) or [])
        current_parent_index = st.session_state.get("object_selected_index")
        if mode != "整体物品":
            if current_parent_index is not None and current_parent_index < len(current_objects_for_parent):
                parent_object = current_objects_for_parent[current_parent_index]
                st.caption(f"当前父级对象：{parent_object.get('name', '')}。将只在这个对象范围内继续拆解。")
            else:
                st.warning("请先在下方 list 中选择一个完整物品或部件，再使用“主要部件 / 细节元素”模式。")

        analyze_label = "分析完整物品" if mode == "整体物品" else f"拆解{mode}"
        if st.button(analyze_label, type="primary", disabled=not st.session_state["source_image_path"] or (mode != "整体物品" and not parent_object)):
            with st.spinner("正在分析图片..."):
                try:
                    analyzer = get_list_analyzer(analyzer_choice)
                    prompt_text = object_list_prompt(mode, parent_object)
                    result = analyzer.analyze_objects(st.session_state["source_image_path"], prompt_text=prompt_text)
                    normalized_objects = normalize_detected_objects(result.get("objects", []))
                    level = MODE_TO_LEVEL.get(mode, "object")
                    for obj in normalized_objects:
                        obj["level"] = level
                        if parent_object:
                            obj["parent_id"] = str(parent_object.get("id", ""))
                            obj["parent_name"] = parent_object.get("name", "")
                    st.session_state["detected_objects"] = normalized_objects
                    st.session_state["object_selected_index"] = 0 if normalized_objects else None
                    history = add_list_history({
                        "title": Path(st.session_state["source_image_path"]).name,
                        "image_path": st.session_state["source_image_path"],
                        "image_name": Path(st.session_state["source_image_path"]).name,
                        "objects": normalized_objects,
                        "mode": mode,
                        "parent_object": object_for_prompt(parent_object),
                        "provider": result.get("provider", analyzer_choice),
                        "analyzer": analyzer_choice,
                        "raw_results": result.get("raw_results", []),
                    })
                    st.session_state["current_list_history_id"] = history.get("history_id", "")
                    st.success(f"完成，来源：{result.get('provider', analyzer_choice)}。已保存到“拆解历史”。")
                    if result.get("raw_results"):
                        with st.expander("查看多模型原始结果"):
                            st.json(result.get("raw_results"))
                except Exception as e:
                    st.error(str(e))

        objects = st.session_state.get("detected_objects", [])
        if objects:
            st.subheader("3. 识别定位 / 选择生成对象")

            current_selected_index = st.session_state.get("object_selected_index")
            if current_selected_index is None and objects:
                current_selected_index = 0
                st.session_state["object_selected_index"] = 0
            if current_selected_index is not None and current_selected_index >= len(objects):
                current_selected_index = 0 if objects else None
                st.session_state["object_selected_index"] = current_selected_index

            objects = normalize_detected_objects(objects)
            annotated_path, visual_objects = build_object_visuals(
                st.session_state.get("source_image_path", ""),
                objects,
                current_selected_index,
            )
            st.session_state["detected_objects"] = visual_objects

            preview_col, list_col = st.columns([1, 1.25])
            with preview_col:
                st.markdown("**原图定位预览**")
                if annotated_path:
                    show_image_if_exists(annotated_path, "数字点为识别对象，橙框为当前选择")
                else:
                    show_image_if_exists(st.session_state["source_image_path"], "当前参考图")

            with list_col:
                st.markdown("**物件列表**")
                df = pd.DataFrame(visual_objects)
                # Keep only editable/visual columns in the table. bbox is preserved in session state.
                display_df = pd.DataFrame({
                    "选择": [i == current_selected_index for i in range(len(visual_objects))],
                    "删除": [False for _ in range(len(visual_objects))],
                    "编号": [obj.get("id", i + 1) for i, obj in enumerate(visual_objects)],
                    "预览": [obj.get("thumbnail_data_url", "") for obj in visual_objects],
                    "层级": [level_label(obj.get("level", "object")) for obj in visual_objects],
                    "name": [obj.get("name", "") for obj in visual_objects],
                    "description": [obj.get("description", "") for obj in visual_objects],
                    "position": [obj.get("position", "") for obj in visual_objects],
                })
                edited = st.data_editor(
                    display_df,
                    use_container_width=True,
                    hide_index=True,
                    num_rows="dynamic",
                    column_config={
                        "选择": st.column_config.CheckboxColumn("选择", help="当前只支持同时勾选 1 个物件", width="small"),
                        "删除": st.column_config.CheckboxColumn("删除", help="勾选后从 list 中删除该条目", width="small"),
                        "编号": st.column_config.NumberColumn("编号", width="small"),
                        "预览": st.column_config.ImageColumn("局部图", width="small", help="根据 bbox 从原图自动裁切"),
                        "层级": st.column_config.TextColumn("层级", width="small"),
                        "name": st.column_config.TextColumn("物件名称", width="medium"),
                        "description": st.column_config.TextColumn("外观描述", width="large", help="用于后续三视图生成时定位和拆解物件"),
                        "position": st.column_config.TextColumn("位置", width="small"),
                    },
                    column_order=["选择", "删除", "编号", "预览", "层级", "name", "description", "position"],
                    disabled=["编号", "预览", "层级"],
                    key="objects_editor",
                )

            delete_indices = [i for i, value in enumerate(edited.get("删除", [])) if is_checked(value)]
            selected_indices = [i for i, value in enumerate(edited.get("选择", [])) if is_checked(value) and i not in delete_indices]
            edited_rows = edited.drop(columns=["选择", "删除", "编号", "预览", "层级"], errors="ignore").to_dict("records")
            edited_objects_all = merge_edited_objects(visual_objects, edited_rows)
            if delete_indices:
                delete_names = [str(edited_objects_all[i].get("name", f"条目 {i + 1}")) for i in delete_indices if i < len(edited_objects_all)]
                st.warning("已勾选删除：" + "、".join(delete_names))
                confirm_delete_items = st.checkbox("确认删除以上 list 条目", key="confirm_delete_flow_a_items")
                if st.button("确认删除选中条目", key="confirm_delete_flow_a_items_button", disabled=not confirm_delete_items, use_container_width=True):
                    edited_objects = [obj for i, obj in enumerate(edited_objects_all) if i not in delete_indices]
                    st.session_state["detected_objects"] = edited_objects
                    st.session_state["object_selected_index"] = 0 if edited_objects else None
                    if st.session_state.get("current_list_history_id"):
                        update_list_history(st.session_state["current_list_history_id"], {"objects": edited_objects})
                    st.success(f"已删除 {len(delete_indices)} 个 list 条目。")
                    st.rerun()
            edited_objects = edited_objects_all
            # Preserve thumbnails generated above where possible.
            for i, obj in enumerate(edited_objects):
                if i < len(visual_objects):
                    obj["thumbnail_path"] = visual_objects[i].get("thumbnail_path", "")
                    obj["thumbnail_data_url"] = visual_objects[i].get("thumbnail_data_url", "")
            st.session_state["detected_objects"] = edited_objects
            if st.session_state.get("current_list_history_id"):
                update_list_history(st.session_state["current_list_history_id"], {"objects": edited_objects})

            previous_index = st.session_state.get("object_selected_index")
            if len(selected_indices) > 1:
                new_indices = [i for i in selected_indices if i != previous_index]
                selected_index = new_indices[-1] if new_indices else selected_indices[0]
                st.session_state["object_selected_index"] = selected_index
                st.warning("当前只支持同时生成 1 张图，已自动保留一个勾选项。")
                st.rerun()
            elif len(selected_indices) == 1:
                selected_index = selected_indices[0]
                if selected_index != previous_index:
                    st.session_state["object_selected_index"] = selected_index
                    st.rerun()
            else:
                selected_index = None
                if previous_index is not None:
                    st.session_state["object_selected_index"] = None

            selected_row = edited_objects[selected_index] if selected_index is not None and selected_index < len(edited_objects) else None
            st.caption("当前只支持同时生成 1 张三视图，请在列表第一列勾选一个物件。")

            st.subheader("4. 生成三视图")
            st.info("生成结果不会自动入库，会先进入“生成结果”分栏。")
            if selected_row:
                with st.expander("当前生成对象定位信息", expanded=False):
                    st.write(f"编号：{selected_row.get('id', '')}")
                    st.write(f"名称：{selected_row.get('name', '')}")
                    st.write(f"外观描述：{selected_row.get('description', '')}")
                    if selected_row.get("position"):
                        st.write(f"位置：{selected_row.get('position', '')}")
                    if selected_row.get("bbox"):
                        st.write(f"bbox：{selected_row.get('bbox')}")

            single_col1, single_col2 = st.columns([2, 1])
            with single_col1:
                single_extra_prompt = st.text_input("补充要求", value="", placeholder="例如：保持结构清晰、视图间距更大、不要加装饰文字", key="single_three_view_extra_prompt")
            with single_col2:
                single_aspect_label = st.selectbox(
                    "画幅大小",
                    list(ASPECT_RATIO_OPTIONS.keys()),
                    index=list(ASPECT_RATIO_OPTIONS.keys()).index("4:3 横向"),
                    key="single_three_view_aspect",
                )
            single_aspect_ratio = ASPECT_RATIO_OPTIONS.get(single_aspect_label, single_aspect_label)

            if st.button("生成三视图", type="primary", disabled=not selected_row):
                try:
                    generator = get_image_generator(generator_choice)
                    name = selected_row.get("name", "未命名物件")
                    desc = selected_row.get("description", "")
                    loc_text = object_location_text(selected_row)
                    prompt_desc = desc if not loc_text else f"{desc}\n{loc_text}"
                    with st.spinner(f"正在生成：{name}"):
                        result = generator.generate_three_view(
                            st.session_state["source_image_path"],
                            name,
                            prompt_desc,
                            extra_prompt=single_extra_prompt,
                            aspect_ratio=single_aspect_ratio,
                        )
                        saved = add_result({
                            "type": "three_view",
                            "name": name,
                            "category": "未分类",
                            "description": prompt_desc,
                            "source_image_path": st.session_state["source_image_path"],
                            "image_path": result.get("image_path", ""),
                            "prompt": result.get("prompt", ""),
                            "provider": result.get("provider", generator_choice),
                            "meta": {
                                "object_id": selected_row.get("id"),
                                "object_bbox": selected_row.get("bbox"),
                                "object_position": selected_row.get("position"),
                                "extra_prompt": single_extra_prompt,
                                "aspect_ratio": single_aspect_ratio,
                            },
                        })
                        st.success(f"已生成：{saved['name']}。请到“生成结果”确认后入库。")
                        show_image_if_exists(saved.get("image_path"), saved["name"])
                except Exception as e:
                    st.error(str(e))


            st.divider()
            st.subheader("5. 整体拆件三视图")
            st.caption("固定使用当前 list 的全部对象，一次生成一张包含多个对象三视图的总览设计板。")
            ov1, ov2, ov3, ov4 = st.columns([1, 1, 1, 2])
            with ov1:
                overview_layout = st.selectbox("排版方式", ["设计板排版", "网格排版", "横向长图"], key="overview_layout")
            with ov2:
                overview_split_degree = st.selectbox("拆分程度", OVERVIEW_SPLIT_DEGREE_OPTIONS, index=0, key="overview_split_degree")
            with ov3:
                overview_aspect_label = st.selectbox(
                    "画幅大小",
                    list(ASPECT_RATIO_OPTIONS.keys()),
                    index=list(ASPECT_RATIO_OPTIONS.keys()).index("16:9 横向"),
                    key="overview_aspect",
                )
            with ov4:
                overview_extra = st.text_input("补充要求", value="", placeholder="例如：减少文字、强化结构线、保持原图配色", key="overview_extra_prompt")
            overview_aspect_ratio = ASPECT_RATIO_OPTIONS.get(overview_aspect_label, overview_aspect_label)

            if st.button("生成整体拆件三视图", type="primary", key="generate_overview_three_view", disabled=not edited_objects):
                try:
                    with st.spinner("正在生成整体拆件三视图..."):
                        saved = generate_overview_three_view_result(
                            image_path=st.session_state["source_image_path"],
                            objects=edited_objects,
                            generator_choice=generator_choice,
                            extra_prompt=overview_extra,
                            layout=overview_layout,
                            aspect_ratio=overview_aspect_ratio,
                            split_degree=overview_split_degree,
                            source_context=f"图片拆解 / {st.session_state.get('analysis_mode', '当前')} list",
                        )
                        st.success("已生成整体拆件三视图。请到“生成结果”确认后入库。")
                        show_image_if_exists(saved.get("image_path"), saved.get("name", "整体拆件三视图"))
                except Exception as e:
                    st.error(str(e))


    with tab_history:
        render_list_history_page(generator_choice)


    with tab_edit:
        render_image_edit_page(generator_choice)


    with tab_results:
        render_results_page()

    with tab_categories:
        render_category_drag_manager(list_assets())

    with tab_settings:
        render_settings_page()


if __name__ == "__main__":
    main()
