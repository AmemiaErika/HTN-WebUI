from config import settings
from services.providers.list_analyzers.mock_analyzer import MockListAnalyzer
from services.providers.list_analyzers.gemini_analyzer import GeminiListAnalyzer
from services.providers.list_analyzers.openai_analyzer import OpenAIListAnalyzer
from services.providers.list_analyzers.claude_analyzer import ClaudeListAnalyzer
from services.providers.list_analyzers.ensemble_analyzer import EnsembleListAnalyzer
from services.custom_provider_service import is_custom_option, get_custom_provider
from services.providers.custom.openai_compatible import CustomOpenAICompatibleVisionAnalyzer


def get_list_analyzer(provider_name: str | None = None):
    name = (provider_name or settings.DEFAULT_LIST_ANALYZER or "gemini").lower()
    if is_custom_option(name):
        config = get_custom_provider(name)
        if not config:
            raise ValueError(f"找不到自定义拆解模型：{provider_name}")
        if config.get("provider_type") not in {"vision", "both"}:
            raise ValueError(f"自定义 Provider 不支持拆解 list：{config.get('name')}")
        return CustomOpenAICompatibleVisionAnalyzer(config)
    if name == "mock":
        return MockListAnalyzer()
    if name == "gemini":
        return GeminiListAnalyzer()
    if name == "openai":
        return OpenAIListAnalyzer()
    if name == "claude":
        return ClaudeListAnalyzer()
    if name == "ensemble":
        analyzers = []
        for cls in [GeminiListAnalyzer, OpenAIListAnalyzer, ClaudeListAnalyzer]:
            try:
                analyzers.append(cls())
            except Exception:
                pass
        if not analyzers:
            analyzers = [MockListAnalyzer()]
        return EnsembleListAnalyzer(analyzers)
    raise ValueError(f"不支持的拆解模型：{provider_name}")
