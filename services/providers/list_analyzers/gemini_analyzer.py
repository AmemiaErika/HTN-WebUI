from PIL import Image

from config import settings
from services.json_utils import extract_json
from services.prompt_templates import object_list_prompt
from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer


class GeminiListAnalyzer(BaseListAnalyzer):
    name = "gemini"

    def __init__(self):
        if not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY.startswith("填你的"):
            raise RuntimeError("缺少 GEMINI_API_KEY。请在 .env 中填写，或选择 mock。")
        from google import genai
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model = settings.GEMINI_VISION_MODEL

    def analyze_objects(self, image_path: str) -> dict:
        image = Image.open(image_path)
        response = self.client.models.generate_content(
            model=self.model,
            contents=[object_list_prompt(), image],
        )
        text = getattr(response, "text", None) or ""
        data = extract_json(text)
        data["provider"] = self.name
        return data
