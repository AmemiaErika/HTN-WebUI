from __future__ import annotations

import base64
import uuid
from contextlib import ExitStack
from typing import Any, Dict, List
from urllib.request import urlopen, Request

from config import settings
from services.json_utils import extract_json
from services.prompt_templates import three_view_prompt, overview_three_view_prompt, compose_prompt, sketch_refine_prompt
from services.providers.image_generators.base_generator import BaseImageGenerator
from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer
from utils.file_utils import image_to_data_url


class CustomOpenAICompatibleVisionAnalyzer(BaseListAnalyzer):
    name = "custom"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        if not config.get("base_url"):
            raise RuntimeError("自定义 Vision Provider 缺少 Base URL。")
        if not config.get("api_key"):
            raise RuntimeError("自定义 Vision Provider 缺少 API Key。")
        if not config.get("model"):
            raise RuntimeError("自定义 Vision Provider 缺少模型名称。")
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        self.model = config["model"]
        self.name = f"custom:{config.get('name', config.get('id', 'unknown'))}"

    def analyze_objects(self, image_path: str, prompt_text: str | None = None) -> Dict[str, Any]:
        data_url = image_to_data_url(image_path)
        prompt = prompt_text or "请分析图片并返回 JSON。"
        try:
            completion = self.client.chat.completions.create(
                model=self.model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        except Exception:
            completion = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt + "\n只能返回严格 JSON，不要 Markdown。"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        text = completion.choices[0].message.content or ""
        data = extract_json(text)
        data["provider"] = self.name
        return data

    def test_connection(self, image_path: str | None = None) -> str:
        messages = [{"role": "user", "content": "请只返回一句话：连接测试成功。"}]
        completion = self.client.chat.completions.create(model=self.model, messages=messages, max_tokens=40)
        return completion.choices[0].message.content or "连接测试完成。"


class CustomOpenAICompatibleImageGenerator(BaseImageGenerator):
    name = "custom"

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        if not config.get("base_url"):
            raise RuntimeError("自定义 Image Provider 缺少 Base URL。")
        if not config.get("api_key"):
            raise RuntimeError("自定义 Image Provider 缺少 API Key。")
        if not config.get("model"):
            raise RuntimeError("自定义 Image Provider 缺少模型名称。")
        from openai import OpenAI
        self.client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])
        self.model = config["model"]
        self.name = f"custom:{config.get('name', config.get('id', 'unknown'))}"

    def _save_response_image(self, result: Any, prefix: str) -> str:
        if not getattr(result, "data", None):
            raise RuntimeError("自定义图像接口没有返回 data。")
        first = result.data[0]
        out = settings.OUTPUT_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}.png"
        b64_json = getattr(first, "b64_json", None)
        if b64_json:
            with open(out, "wb") as f:
                f.write(base64.b64decode(b64_json))
            return str(out)
        url = getattr(first, "url", None)
        if url:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=120) as resp:
                out.write_bytes(resp.read())
            return str(out)
        raise RuntimeError("自定义图像接口没有返回 b64_json 或 url。")

    def _edit_with_images(self, image_paths: List[str], prompt: str, prefix: str) -> str:
        with ExitStack() as stack:
            files = [stack.enter_context(open(p, "rb")) for p in image_paths if p]
            if files:
                image_arg = files[0] if len(files) == 1 else files
                try:
                    result = self.client.images.edit(model=self.model, image=image_arg, prompt=prompt)
                except Exception as edit_error:
                    # Some OpenAI-compatible services expose generation but not edit.
                    # Retry as text-only generation with the same prompt so the error is less disruptive.
                    try:
                        result = self.client.images.generate(model=self.model, prompt=prompt)
                    except Exception:
                        raise edit_error
            else:
                result = self.client.images.generate(model=self.model, prompt=prompt)
        return self._save_response_image(result, prefix)

    def generate_three_view(self, image_path: str, object_name: str, object_description: str, extra_prompt: str = "", aspect_ratio: str = "自动") -> Dict[str, Any]:
        prompt = three_view_prompt(object_name, object_description, extra_prompt=extra_prompt, aspect_ratio=aspect_ratio)
        out = self._edit_with_images([image_path], prompt, "custom_three_view")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def generate_overview_three_view(self, image_path: str, objects: List[Dict[str, Any]], extra_prompt: str = "", layout: str = "设计板排版", aspect_ratio: str = "自动", split_degree: str = "仅拆分主体物") -> Dict[str, Any]:
        prompt = overview_three_view_prompt(objects, extra_prompt, layout, aspect_ratio=aspect_ratio, split_degree=split_degree)
        out = self._edit_with_images([image_path], prompt, "custom_overview_three_view")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        prompt = compose_prompt(composition_prompt, env_options)
        out = self._edit_with_images(asset_paths, prompt, "custom_composition")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        prompt = sketch_refine_prompt(refine_prompt)
        out = self._edit_with_images([sketch_path], prompt, "custom_sketch")
        return {"provider": self.name, "image_path": out, "prompt": prompt}



    def edit_images(self, image_paths: List[str], edit_prompt: str, aspect_ratio: str = "自动") -> Dict[str, Any]:
        prompt = edit_prompt
        out = self._edit_with_images(image_paths, prompt, "custom_image_edit")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def test_connection(self) -> str:
        result = self.client.images.generate(model=self.model, prompt="生成一张白色背景上的红色立方体小图。")
        path = self._save_response_image(result, "custom_test")
        return path
