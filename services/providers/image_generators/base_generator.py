from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseImageGenerator(ABC):
    name = "base"

    @abstractmethod
    def generate_three_view(self, image_path: str, object_name: str, object_description: str, extra_prompt: str = "", aspect_ratio: str = "自动") -> Dict[str, Any]:
        pass

    @abstractmethod
    def generate_overview_three_view(
        self,
        image_path: str,
        objects: List[Dict[str, Any]],
        extra_prompt: str = "",
        layout: str = "设计板排版",
        aspect_ratio: str = "自动",
        split_degree: str = "仅拆分主体物",
    ) -> Dict[str, Any]:
        pass

    @abstractmethod
    def compose_scene(self, asset_paths: List[str], composition_prompt: str, env_options: Dict[str, Any]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def refine_sketch(self, sketch_path: str, refine_prompt: str) -> Dict[str, Any]:
        pass


    @abstractmethod
    def edit_images(self, image_paths: List[str], edit_prompt: str, aspect_ratio: str = "自动") -> Dict[str, Any]:
        pass
