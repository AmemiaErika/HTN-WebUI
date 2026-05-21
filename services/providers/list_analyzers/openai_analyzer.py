from config import settings
from services.json_utils import extract_json
from services.prompt_templates import object_list_prompt
from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer
from utils.file_utils import image_to_data_url


class OpenAIListAnalyzer(BaseListAnalyzer):
    name = "openai"

    def __init__(self):
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY.startswith("填你的"):
            raise RuntimeError("缺少 OPENAI_API_KEY。请在 .env 中填写，或选择 mock。")
        from openai import OpenAI
        self.client = OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.OPENAI_VISION_MODEL

    def analyze_objects(self, image_path: str) -> dict:
        data_url = image_to_data_url(image_path)
        prompt = object_list_prompt()
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
                            {"type": "text", "text": prompt + "\n只能返回 JSON。"},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
        text = completion.choices[0].message.content or ""
        data = extract_json(text)
        data["provider"] = self.name
        return data
