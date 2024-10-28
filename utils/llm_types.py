from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass
from PIL import Image

from data import ScreenCaptureData


@dataclass
class AnalysisPrompt:
    """Template for vision analysis prompts"""
    template: str
    system_context: Optional[str] = None

    def format(self, **kwargs) -> str:
        return self.template.format(**kwargs)


class LLMProvider(ABC):
    """Abstract base class for LLM providers"""

    @abstractmethod
    async def analyze_image(self, image: Image, prompt: AnalysisPrompt) -> ScreenCaptureData:
        """Analyze image using the provider's vision model"""
        pass

    @abstractmethod
    async def generate_text(self, prompt: str, system_context: Optional[str] = None) -> str:
        """Generate text using the provider's language model"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the provider"""
        pass


class LLMProviderFactory:
    """Factory for creating LLM providers"""
    _providers: Dict[str, type] = {}

    @classmethod
    def register(cls, provider_name: str):
        """Register a new provider class"""

        def wrapper(provider_class):
            cls._providers[provider_name] = provider_class
            return provider_class

        return wrapper

    @classmethod
    def create(cls, provider_name: str, **kwargs) -> LLMProvider:
        """Create a provider instance"""
        if provider_name not in cls._providers:
            raise ValueError(f"Unknown provider: {provider_name}")
        return cls._providers[provider_name](**kwargs)