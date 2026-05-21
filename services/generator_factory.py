from config import settings
from services.providers.image_generators.mock_generator import MockImageGenerator
from services.providers.image_generators.gemini_generator import GeminiImageGenerator
from services.providers.image_generators.openai_generator import OpenAIImageGenerator


def get_image_generator(provider_name: str | None = None):
    name = (provider_name or settings.DEFAULT_IMAGE_GENERATOR or "gemini").lower()
    if name == "mock":
        return MockImageGenerator()
    if name == "gemini":
        return GeminiImageGenerator()
    if name == "openai":
        return OpenAIImageGenerator()
    raise ValueError(f"不支持的图像生成模型：{provider_name}")
