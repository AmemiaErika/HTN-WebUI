from config import settings
from services.providers.image_generators.mock_generator import MockImageGenerator
from services.providers.image_generators.gemini_generator import GeminiImageGenerator
from services.providers.image_generators.openai_generator import OpenAIImageGenerator
from services.custom_provider_service import is_custom_option, get_custom_provider
from services.providers.custom.openai_compatible import CustomOpenAICompatibleImageGenerator


def get_image_generator(provider_name: str | None = None):
    name = (provider_name or settings.DEFAULT_IMAGE_GENERATOR or "gemini").lower()
    if is_custom_option(name):
        config = get_custom_provider(name)
        if not config:
            raise ValueError(f"找不到自定义图像生成模型：{provider_name}")
        if config.get("provider_type") not in {"image", "both"}:
            raise ValueError(f"自定义 Provider 不支持图像生成：{config.get('name')}")
        return CustomOpenAICompatibleImageGenerator(config)
    if name == "mock":
        return MockImageGenerator()
    if name == "gemini":
        return GeminiImageGenerator()
    if name == "openai":
        return OpenAIImageGenerator()
    raise ValueError(f"不支持的图像生成模型：{provider_name}")
