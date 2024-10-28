from typing import Dict, Type

from pydantic import BaseModel

from data import ScreenCaptureData
from utils.llm_types import AnalysisPrompt

def generate_schema_description(model: Type[BaseModel]) -> str:
    """Generate a description string from a Pydantic model's fields"""
    descriptions = []
    for field_name, field in model.model_fields.items():
        description = field.description or "No description provided"
        field_type = field.annotation.__name__ if hasattr(field.annotation, '__name__') else str(field.annotation)
        descriptions.append(f"- {field_name} ({field_type}): {description}")
    return "\n".join(descriptions)

DEFAULT_VISION_SYSTEM_CONTEXT = """
You are a knowladge-worker context analyzer. Your role is to observe and understand
what the knowladge-worker is working on from their screen content. Focus on:
1. Identifying the type of development activity
2. Technical stack and tools in use
3. Relevant documentation or resources visible
Provide structured, accurate analysis without any subjective interpretation.
"""

DEFAULT_PROMPTS = {
    "screen_activity_observation": AnalysisPrompt(
        system_context=DEFAULT_VISION_SYSTEM_CONTEXT,
        template=f"""In the following context:
{{context}}
Given the following information about the previous screen capture:
{{previous_analysis}}
Focusing on new information only, do not repeat previously known info, Analyze this screenshot and identify the required information as mentioned below and format response as JSON with these exact keys: 
        {generate_schema_description(ScreenCaptureData)}
        
Note: 
    - DO NOT make up any information.
    - DO NOT output a markdown block of json, just the json ONLY.
    - If you cannot identify any of the new information, set the value to null.
    - Always stick to the schema described above. If you cannot identify a field, set the value to null or an appropriate default value if null is not an option.
"""
    ),
    "context_switch": AnalysisPrompt(
        system_context=DEFAULT_VISION_SYSTEM_CONTEXT,
        template="""
        Determine if the knowladge-worker has switched context:
        1. Current visible project/topic
        2. Technologies in view
        3. Type of work being done
        Format as JSON: {{"new_context": "", "confidence": 0.0, "reason": ""}}
        """
    )
}


class PromptsManager:
    def __init__(self, custom_prompts: Dict[str, AnalysisPrompt] = None):
        self._prompts = DEFAULT_PROMPTS.copy()
        if custom_prompts:
            self._prompts.update(custom_prompts)

    def get_prompt(self, prompt_name: str) -> AnalysisPrompt:
        """Get a prompt by name"""
        if prompt_name not in self._prompts:
            raise ValueError(f"Unknown prompt: {prompt_name}")
        return self._prompts[prompt_name]

    def add_prompt(self, name: str, prompt: AnalysisPrompt):
        """Add or update a prompt"""
        self._prompts[name] = prompt

    def remove_prompt(self, name: str):
        """Remove a prompt"""
        if name in DEFAULT_PROMPTS:
            raise ValueError(f"Cannot remove default prompt: {name}")
        self._prompts.pop(name, None)