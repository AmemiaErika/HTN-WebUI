import uuid
from typing import Any, Dict, List

from PIL import Image

from config import settings
from services.prompt_templates import three_view_prompt, compose_prompt, sketch_refine_prompt
from services.providers.image_generators.base_generator import BaseImageGenerator


class GeminiImageGenerator(BaseImageGenerator):
    name = "gemini"

    def __init__(self):
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("填你的"):
            raise RuntimeError("缺少 GEMINI_API_KEY。请在 .env 中填写，或选择 mock。")
        from google import genai
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_IMAGE_MODEL

    def _save_first_image(self, response, prefix: str) -> str:
        out = settings.OUTPUT_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}.png"
        # google-genai 的 response.parts 支持 part.as_image()
        parts = getattr(response, "parts", None)
        if parts is None and getattr(response, "candidates", None):
            parts = response.candidates[0].content.parts
        for part in parts or []:
            inline_data = getattr(part, "inline_data", None) or getattr(part, "inlineData", None)
            if inline_data is not None:
                if hasattr(part, "as_image"):
                    img = part.as_image()
                    img.save(out)
                    return str(out)
                data = getattr(inline_data, "data", None)
                if data:
                    from io import BytesIO
                    img = Image.open(BytesIO(data))
                    img.save(out)
                    return str(out)
        raise RuntimeError("Gemini 没有返回图片。请调整 prompt 或检查模型权限。")

    def generate_three_view(self, image_path: str, object_name: str, object_description: str) -> Dict[str, Any]:
        prompt = three_view_prompt(object_name, object_description)
        image = Image.open(image_path)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, image],
        )
        out = self._save_first_image(response, "gemini_three_view")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        prompt = compose_prompt(composition_prompt, env_options)
        contents = [prompt]
        for p in asset_paths:
            contents.append(Image.open(p))
        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
        )
        out = self._save_first_image(response, "gemini_composition")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        prompt = sketch_refine_prompt(refine_prompt)
        image = Image.open(sketch_path)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[prompt, image],
        )
        out = self._save_first_image(response, "gemini_sketch")
        return {"provider": self.name, "image_path": out, "prompt": prompt}
