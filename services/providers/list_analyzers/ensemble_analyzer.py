from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer
from services.providers.list_analyzers.mock_analyzer import MockListAnalyzer


class EnsembleListAnalyzer(BaseListAnalyzer):
    name = "ensemble"

    def __init__(self, analyzers=None):
        self.analyzers = analyzers or []
        if not self.analyzers:
            self.analyzers = [MockListAnalyzer()]

    def analyze_objects(self, image_path: str) -> dict:
        raw_results = []
        for analyzer in self.analyzers:
            try:
                raw_results.append(analyzer.analyze_objects(image_path))
            except Exception as e:
                raw_results.append({"provider": analyzer.name, "error": str(e), "objects": []})

        merged = []
        seen = set()
        for result in raw_results:
            for obj in result.get("objects", []):
                key = f"{obj.get('name','')[:12]}_{obj.get('description','')[:18]}".lower()
                if key in seen:
                    continue
                seen.add(key)
                obj = dict(obj)
                obj["source_provider"] = result.get("provider", "unknown")
                merged.append(obj)

        return {
            "provider": self.name,
            "raw_results": raw_results,
            "objects": merged,
        }
