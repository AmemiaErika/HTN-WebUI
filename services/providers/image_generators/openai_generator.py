import base64
import uuid
from contextlib import ExitStack
from typing import Any, Dict, List

from config import settings
from services.prompt_templates import three_view_prompt, compose_prompt, sketch_refine_prompt
from services.providers.image_generators.base_generator import BaseImageGenerator


class OpenAIImageGenerator(BaseImageGenerator):
    name = "openai"

    def __init__(self):
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("填你的"):
            raise RuntimeError("缺少 OPENAI_API_KEY。请在 .env 中填写，或选择 mock。")
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_IMAGE_MODEL

    def _save_b64(self, b64_json: str, prefix: str) -> str:
        out = settings.OUTPUT_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}.png"
        with open(out, "wb") as f:
            f.write(base64.b64decode(b64_json))
        return str(out)

    def _edit_with_images(self, image_paths: List[str], prompt: str, prefix: str) -> str:
        with ExitStack() as stack:
            files = [stack.enter_context(open(p, "rb")) for p in image_paths if p]
            if not files:
                result = self.client.images.generate(model=self.model, prompt=prompt)
            else:
                image_arg = files[0] if len(files) == 1 else files
                result = self.client.images.edit(model=self.model, image=image_arg, prompt=prompt)
        return self._save_b64(result.data[0].b64_json, prefix)

    def generate_three_view(self, image_path: str, object_name: str, object_description: str) -> Dict[str, Any]:
        prompt = three_view_prompt(object_name, object_description)
        out = self._edit_with_images([image_path], prompt, "openai_three_view")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        prompt = compose_prompt(composition_prompt, env_options)
        out = self._edit_with_images(asset_paths, prompt, "openai_composition")
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        prompt = sketch_refine_prompt(refine_prompt)
        out = self._edit_with_images([sketch_path], prompt, "openai_sketch")
        return {"provider": self.name, "image_path": out, "prompt": prompt}
