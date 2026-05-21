from pathlib import Path
import uuid
from typing import Any, Dict, List

from config.settings import OUTPUT_DIR
from services.prompt_templates import three_view_prompt, compose_prompt, sketch_refine_prompt
from services.providers.image_generators.base_generator import BaseImageGenerator
from utils.file_utils import make_placeholder_image


class MockImageGenerator(BaseImageGenerator):
    name = "mock"

    def _out(self, prefix: str) -> str:
        return str(OUTPUT_DIR / f"{prefix}_{uuid.uuid4().hex[:12]}.png")

    def generate_three_view(self, image_path: str, object_name: str, object_description: str) -> Dict[str, Any]:
        prompt = three_view_prompt(object_name, object_description)
        out = self._out("mock_three_view")
        make_placeholder_image(f"三视图：{object_name}\n{prompt}", out)
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        prompt = compose_prompt(composition_prompt, env_options)
        out = self._out("mock_composition")
        make_placeholder_image(f"组合生成\n素材数量：{len(asset_paths)}\n{prompt}", out)
        return {"provider": self.name, "image_path": out, "prompt": prompt}

    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        prompt = sketch_refine_prompt(refine_prompt)
        out = self._out("mock_sketch")
        make_placeholder_image(f"草图细化\n{prompt}", out)
        return {"provider": self.name, "image_path": out, "prompt": prompt}
