from config import settings
from services.json_utils import extract_json
from services.prompt_templates import object_list_prompt
from services.providers.list_analyzers.base_analyzer import BaseListAnalyzer
from utils.file_utils import image_to_base64, get_mime_type


class ClaudeListAnalyzer(BaseListAnalyzer):
    name = "claude"

    def __init__(self):
        if not settings.ANTHROPIC_API_KEY or settings.ANTHROPIC_API_KEY.startswith("填你的"):
            raise RuntimeError("缺少 ANTHROPIC_API_KEY。请在 .env 中填写，或选择 mock。")
        import anthropic
        self.client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.ANTHROPIC_MODEL

    def analyze_objects(self, image_path: str) -> dict:
        image_b64 = image_to_base64(image_path)
        media_type = get_mime_type(image_path)
        message = self.client.messages.create(
            model=self.model,
            max_tokens=1800,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_b64,
                            },
                        },
                        {"type": "text", "text": object_list_prompt()},
                    ],
                }
            ],
        )
        text_parts = []
        for block in message.content:
            if getattr(block, "type", None) == "text":
                text_parts.append(block.text)
        data = extract_json("\n".join(text_parts))
        data["provider"] = self.name
        return data
