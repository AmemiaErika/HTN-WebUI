from abc import ABC, abstractmethod
from typing import Any, Dict


class BaseListAnalyzer(ABC):
    name = "base"

    @abstractmethod
    def analyze_objects(self, image_path: str) -> Dict[str, Any]:
        pass
