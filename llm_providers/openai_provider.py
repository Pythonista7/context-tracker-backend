import json
from typing import Dict, Any, Optional
import openai
from PIL import Image
import base64
from io import BytesIO

from utils.llm_types import LLMProvider, LLMProviderFactory, AnalysisPrompt

from logging import getLogger

logger = getLogger(__name__)

@LLMProviderFactory.register("openai")
class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, vision_model: str = "gpt-4o",
                 text_model: str = "gpt-4"):
        self.api_key = api_key
        openai.api_key = api_key
        self.vision_model = vision_model
        self.text_model = text_model

    def _encode_image(self, image: Image) -> str:
        """Convert PIL Image to base64"""
        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()

    async def analyze_image(self, image: Image, prompt: AnalysisPrompt) -> Dict[str, Any]:
        """Analyze image using OpenAI's vision model"""
        try:
            response = openai.chat.completions.create(
                model=self.vision_model,
                messages=[
                    *([] if not prompt.system_context else [{"role": "system", "content": prompt.system_context}]),
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt.template},
                            {
                                "type": "image_url", 
                                "image_url": {
                                    "url": f"data:image/png;base64,{self._encode_image(image)}"
                                }
                            }
                        ]
                    }
                ]
            )
            return json.loads(response.choices[0].message.content)
        except json.JSONDecodeError:
            logger.error("Failed to parse JSON response from OpenAI: %s", response.choices[0].message.content)
            raise ValueError("Failed to parse JSON response from OpenAI")
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    async def generate_text(self, prompt: str, system_context: Optional[str] = None) -> str:
        """Generate text using OpenAI's text model"""
        try:
            messages = []
            if system_context:
                messages.append({"role": "system", "content": system_context})
            messages.append({"role": "user", "content": prompt})

            response = openai.chat.completions.create(
                model=self.text_model,
                messages=messages
            )
            return response.choices[0].message.content
        except Exception as e:
            raise RuntimeError(f"OpenAI API error: {str(e)}")

    @property
    def provider_name(self) -> str:
        return "openai"