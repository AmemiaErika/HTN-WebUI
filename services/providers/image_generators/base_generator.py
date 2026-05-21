from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseImageGenerator(ABC):
    name = "base"

    @abstractmethod
    def generate_three_view(self, image_path: str, object_name: str, object_description: str) -> Dict[str, Any]:
        pass

    @abstractmethod
    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        pass
