from __future__ import annotations

from pathlib import Path
import re
import json
import html

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
from services.app_config_store import load_app_config, save_app_config, apply_app_config
from services.prompt_store import (
    PROMPT_LABELS,
    PROMPT_VARIABLES,
    DEFAULT_PROMPTS,
    load_prompt_templates,
    save_prompt_template,
    reset_prompt_template,
    reset_all_prompt_templates,
    render_template,
)
from utils.file_utils import save_uploaded_file

st.set_page_config(page_title="AI 概念设计 WebUI", layout="wide", initial_sidebar_state="expanded")

ANALYZER_OPTIONS = ["gemini", "openai", "claude", "ensemble", "mock"]
GENERATOR_OPTIONS = ["gemini", "openai", "mock"]
RESULT_TYPE_LABELS = {
    "three_view": "三视图",
    "composition": "组合图",
    "sketch_refine": "草图细化",
    "generation": "生成图",
}


def init_state():
    st.session_state.setdefault("source_image_path", "")
    st.session_state.setdefault("detected_objects", [])
    st.session_state.setdefault("last_generation", None)
    st.session_state.setdefault("selected_asset_ids", [])
    st.session_state.setdefault("pending_archive_result_id", "")
    st.session_state.setdefault("object_selected_index", None)


def get_runtime_config():
    config = load_app_config()
    analyzer = config.get("DEFAULT_LIST_ANALYZER", settings.DEFAULT_LIST_ANALYZER) or "gemini"
    generator = config.get("DEFAULT_IMAGE_GENERATOR", settings.DEFAULT_IMAGE_GENERATOR) or "gemini"
    if analyzer not in ANALYZER_OPTIONS:
        analyzer = "gemini"
    if generator not in GENERATOR_OPTIONS:
        generator = "gemini"
    config["DEFAULT_LIST_ANALYZER"] = analyzer
    config["DEFAULT_IMAGE_GENERATOR"] = generator
    apply_app_config(config)
    return config


def show_image_if_exists(path: str, caption: str = ""):
    if path and Path(path).exists():
        st.image(path, caption=caption, use_container_width=True)
    elif path:
        st.warning(f"文件不存在：{path}")


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


def normalize_detected_object(obj: dict) -> dict:
    """Keep the object list focused on name + concise appearance description."""
    if not isinstance(obj, dict):
        return {"name": "未命名物件", "description": str(obj)}

    name = (
        obj.get("name")
        or obj.get("名称")
        or obj.get("物件名称")
        or obj.get("object_name")
        or "未命名物件"
    )
    description = (
        obj.get("description")
        or obj.get("appearance_description")
        or obj.get("外观描述")
        or obj.get("外观")
        or obj.get("描述")
        or ""
    )
    return {
        "name": str(name).strip() or "未命名物件",
        "description": str(description).strip(),
    }


def normalize_detected_objects(objects: list[dict]) -> list[dict]:
    return [normalize_detected_object(obj) for obj in objects if isinstance(obj, dict)]



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


def render_asset_sidebar():
    with st.sidebar:
        st.markdown("### 素材仓库")
        assets = list_assets()

        if not assets:
            st.info("暂无素材。请在“生成结果”中点击入库。")
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
    default_analyzer = app_config.get("DEFAULT_LIST_ANALYZER", settings.DEFAULT_LIST_ANALYZER)
    if default_analyzer not in ANALYZER_OPTIONS:
        default_analyzer = "gemini"
    default_generator = app_config.get("DEFAULT_IMAGE_GENERATOR", settings.DEFAULT_IMAGE_GENERATOR)
    if default_generator not in GENERATOR_OPTIONS:
        default_generator = "gemini"

    st.subheader("模型与 API 设置")
    c1, c2 = st.columns(2)
    with c1:
        analyzer_choice = st.selectbox("拆解 list 模型", ANALYZER_OPTIONS, index=ANALYZER_OPTIONS.index(default_analyzer), key="settings_analyzer_choice")
    with c2:
        generator_choice = st.selectbox("图像生成模型", GENERATOR_OPTIONS, index=GENERATOR_OPTIONS.index(default_generator), key="settings_generator_choice")

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

    st.info("本地原型会把 Key 明文保存到 data/app_config.json。正式部署前建议改成环境变量或密钥服务。")


def render_prompt_settings_tab():
    st.subheader("提示词设置")
    prompts = load_prompt_templates()
    prompt_keys = list(DEFAULT_PROMPTS.keys())
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
        "composition_prompt": "主角放在画面中央，包装盒在后方，礼物盒在左右两侧。",
        "time": "夜晚",
        "lighting": "强聚光",
        "weather": "雾气",
        "style": "潮玩概念设计",
        "camera": "产品摄影视角",
        "refine_prompt": "潮玩盲盒风格，橙黑配色，塑料软胶材质，保留原构图。",
    }
    st.code(render_template(edited_prompt, preview_vars), language="text")


def render_settings_page():
    tab_model, tab_prompt = st.tabs(["模型 / API", "提示词"])
    with tab_model:
        render_model_settings_tab()
    with tab_prompt:
        render_prompt_settings_tab()


def main():
    init_state()
    app_config = get_runtime_config()
    analyzer_choice = app_config["DEFAULT_LIST_ANALYZER"]
    generator_choice = app_config["DEFAULT_IMAGE_GENERATOR"]

    render_asset_sidebar()
    st.caption(f"当前模型：拆解 list = {analyzer_choice}，图像生成 = {generator_choice}。可在“设置”中修改。")

    tab_a, tab_b, tab_c, tab_results, tab_categories, tab_settings = st.tabs(["流 A：图片拆解", "流 B：组合生成", "流 C：草图细化", "生成结果", "分类管理", "设置"])

    with tab_a:
        st.subheader("1. 上传参考图")
        col_left, col_right = st.columns([1, 1])
        with col_left:
            uploaded = st.file_uploader("上传图片", type=["png", "jpg", "jpeg", "webp"], key="source_upload")
            if uploaded:
                path = save_uploaded_file(uploaded, settings.UPLOAD_DIR, "source")
                st.session_state["source_image_path"] = path
                st.success("图片已上传")
        with col_right:
            show_image_if_exists(st.session_state["source_image_path"], "当前参考图")

        st.divider()
        st.subheader("2. 分析物件 list")
        if st.button("分析物件", type="primary", disabled=not st.session_state["source_image_path"]):
            with st.spinner("正在分析图片..."):
                try:
                    analyzer = get_list_analyzer(analyzer_choice)
                    result = analyzer.analyze_objects(st.session_state["source_image_path"])
                    st.session_state["detected_objects"] = normalize_detected_objects(result.get("objects", []))
                    st.session_state["object_selected_index"] = 0 if st.session_state["detected_objects"] else None
                    st.success(f"完成，来源：{result.get('provider', analyzer_choice)}")
                    if result.get("raw_results"):
                        with st.expander("查看多模型原始结果"):
                            st.json(result.get("raw_results"))
                except Exception as e:
                    st.error(str(e))

        objects = st.session_state.get("detected_objects", [])
        if objects:
            st.subheader("3. 编辑物件 / 勾选生成对象")

            current_selected_index = st.session_state.get("object_selected_index")
            if current_selected_index is None and objects:
                current_selected_index = 0
                st.session_state["object_selected_index"] = 0
            if current_selected_index is not None and current_selected_index >= len(objects):
                current_selected_index = 0 if objects else None
                st.session_state["object_selected_index"] = current_selected_index

            objects = normalize_detected_objects(objects)
            st.session_state["detected_objects"] = objects
            df = pd.DataFrame(objects, columns=["name", "description"])
            df.insert(0, "选择", [i == current_selected_index for i in range(len(df))])
            edited = st.data_editor(
                df,
                use_container_width=True,
                num_rows="dynamic",
                column_config={
                    "选择": st.column_config.CheckboxColumn("选择", help="当前只支持同时勾选 1 个物件", width="small"),
                    "name": st.column_config.TextColumn("物件名称", width="medium"),
                    "description": st.column_config.TextColumn("外观描述", width="large", help="用于后续三视图生成时定位和拆解物件"),
                },
                column_order=["选择", "name", "description"],
                key="objects_editor",
            )

            selected_indices = [i for i, value in enumerate(edited.get("选择", [])) if bool(value)]
            edited_rows = normalize_detected_objects(edited.drop(columns=["选择"], errors="ignore").to_dict("records"))
            st.session_state["detected_objects"] = edited_rows

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

            selected_row = edited_rows[selected_index] if selected_index is not None and selected_index < len(edited_rows) else None
            st.caption("当前只支持同时生成 1 张三视图，请在列表第一列勾选一个物件。")

            st.subheader("4. 生成三视图")
            st.info("生成结果不会自动入库，会先进入“生成结果”分栏。")
            if st.button("生成三视图", type="primary", disabled=not selected_row):
                try:
                    generator = get_image_generator(generator_choice)
                    name = selected_row.get("name", "未命名物件")
                    desc = selected_row.get("description", "")
                    with st.spinner(f"正在生成：{name}"):
                        result = generator.generate_three_view(st.session_state["source_image_path"], name, desc)
                        saved = add_result({
                            "type": "three_view",
                            "name": name,
                            "category": "未分类",
                            "description": desc,
                            "source_image_path": st.session_state["source_image_path"],
                            "image_path": result.get("image_path", ""),
                            "prompt": result.get("prompt", ""),
                            "provider": result.get("provider", generator_choice),
                        })
                        st.success(f"已生成：{saved['name']}。请到“生成结果”确认后入库。")
                        show_image_if_exists(saved.get("image_path"), saved["name"])
                except Exception as e:
                    st.error(str(e))


    with tab_b:
        st.subheader("组合生成")
        assets = list_assets()
        if not assets:
            st.info("素材仓库为空。请先在“生成结果”中把满意图片入库。")
        else:
            selected_ids = st.session_state.get("selected_asset_ids", [])
            asset_options = {f"{a.get('name')} / {a.get('category')} / {a.get('asset_id')}": a for a in assets}
            default_labels = [label for label, asset in asset_options.items() if asset.get("asset_id") in selected_ids]
            chosen_labels = st.multiselect("选择素材（也可以从左侧素材仓库点击“加入组合”）", list(asset_options.keys()), default=default_labels, key="composition_asset_multiselect")
            chosen_assets = [asset_options[label] for label in chosen_labels]
            st.session_state["selected_asset_ids"] = [a.get("asset_id") for a in chosen_assets]

            if chosen_assets:
                cols = st.columns(min(4, len(chosen_assets)))
                for i, a in enumerate(chosen_assets):
                    with cols[i % len(cols)]:
                        show_image_if_exists(a.get("three_view_path"), a.get("name", ""))
            else:
                st.info("请从左侧素材仓库加入素材，或在上方下拉框选择素材。")

            composition_text = st.text_area("组合描述", value="主角放在画面中央，包装盒在后方，礼物盒和装饰物放在左右两侧，整体像潮玩产品海报。", height=100)
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1:
                time = st.selectbox("时间", ["白天", "黄昏", "夜晚"])
            with c2:
                lighting = st.selectbox("光照", ["柔光", "强聚光", "逆光", "摄影棚"])
            with c3:
                weather = st.selectbox("天气", ["晴天", "雨天", "雾气", "雪景"])
            with c4:
                style = st.selectbox("风格", ["潮玩概念设计", "盲盒产品渲染", "卡通产品海报", "写实产品摄影"])
            with c5:
                camera = st.selectbox("视角", ["产品摄影视角", "正视图", "俯视图", "等距视角"])

            if st.button("生成组合图", type="primary", disabled=not chosen_assets):
                try:
                    generator = get_image_generator(generator_choice)
                    asset_paths = [a.get("three_view_path") for a in chosen_assets if a.get("three_view_path")]
                    with st.spinner("正在生成组合图..."):
                        result = generator.compose_scene(asset_paths, composition_text, {"time": time, "lighting": lighting, "weather": weather, "style": style, "camera": camera})
                        saved = add_result({
                            "type": "composition",
                            "name": "组合概念图",
                            "category": "未分类",
                            "description": composition_text,
                            "image_path": result.get("image_path", ""),
                            "prompt": result.get("prompt", ""),
                            "provider": result.get("provider", generator_choice),
                            "meta": {"asset_ids": [a.get("asset_id") for a in chosen_assets]},
                        })
                        st.success("完成。请到“生成结果”确认后入库。")
                        show_image_if_exists(saved.get("image_path"), "组合生成结果")
                except Exception as e:
                    st.error(str(e))

    with tab_c:
        st.subheader("草图细化")
        sketch = st.file_uploader("上传草图", type=["png", "jpg", "jpeg", "webp"], key="sketch_upload")
        refine_text = st.text_area("细化要求", value="潮玩盲盒风格，橙黑配色，塑料软胶材质，保留原构图，细节丰富但不要过度写实。", height=120)
        sketch_path = ""
        if sketch:
            sketch_path = save_uploaded_file(sketch, settings.UPLOAD_DIR, "sketch")
            show_image_if_exists(sketch_path, "草图")

        if st.button("细化草图", type="primary", disabled=not sketch_path):
            try:
                generator = get_image_generator(generator_choice)
                with st.spinner("正在细化草图..."):
                    result = generator.refine_sketch(sketch_path, refine_text)
                    saved = add_result({
                        "type": "sketch_refine",
                        "name": "草图细化结果",
                        "category": "未分类",
                        "description": refine_text,
                        "source_image_path": sketch_path,
                        "image_path": result.get("image_path", ""),
                        "prompt": result.get("prompt", ""),
                        "provider": result.get("provider", generator_choice),
                    })
                    st.success("完成。请到“生成结果”确认后入库。")
                    show_image_if_exists(saved.get("image_path"), "细化结果")
            except Exception as e:
                st.error(str(e))

    with tab_results:
        render_results_page()

    with tab_categories:
        render_category_drag_manager(list_assets())

    with tab_settings:
        render_settings_page()


if __name__ == "__main__":
    main()
