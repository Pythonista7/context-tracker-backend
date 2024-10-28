import json
from typing import Dict, Any, Optional

from anthropic import AsyncAnthropic
from utils.llm_types import LLMProvider, LLMProviderFactory, AnalysisPrompt
from PIL import Image

@LLMProviderFactory.register("anthropic")
class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str, model: str = "claude-3-opus-20240229"):
        self.client = AsyncAnthropic(api_key=api_key)
        self.model = model

    async def analyze_image(self, image: Image, prompt: AnalysisPrompt) -> Dict[str, Any]:
        """Analyze image using Anthropic's vision model"""
        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt.template},
                        {"type": "image", "image": self._encode_image(image)}
                    ]
                }],
                system=prompt.system_context
            )
            return json.loads(response.content[0].text)
        except Exception as e:
            raise RuntimeError(f"Anthropic API error: {str(e)}")

    async def generate_text(self, prompt: str, system_context: Optional[str] = None) -> str:
        """Generate text using Anthropic's language model"""
        response = await self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
            system=system_context
        )
        return response.content[0].text

    @property
    def provider_name(self) -> str:
        return "anthropic"