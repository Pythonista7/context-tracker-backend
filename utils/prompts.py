from typing import Dict, Type

from pydantic import BaseModel

from data import ScreenCaptureData, SessionSummary
from utils.llm_types import AnalysisPrompt

def generate_schema_description(model: Type[BaseModel]) -> str:
    """Generate a description string from a Pydantic model's fields"""
    descriptions = []
    for field_name, field in model.model_fields.items():
        description = field.description or "No description provided"
        field_type = field.annotation.__name__ if hasattr(field.annotation, '__name__') else str(field.annotation)
        descriptions.append(f"- {field_name} ({field_type}): {description}")
    return "\n".join(descriptions)

VISION_SYSTEM_CONTEXT = """
You are a knowladge-worker context analyzer. Your role is to observe and understand
what the knowladge-worker is working on from their screen content. Focus on:
1. Identifying the type of development activity
2. Technical stack and tools in use
3. Relevant documentation or resources visible
Provide structured, accurate analysis without any subjective interpretation.
"""

DEFAULT_PROMPTS = {
    "screen_activity_observation": AnalysisPrompt(
        system_context=VISION_SYSTEM_CONTEXT,
        template=f"""In the following context:
{{context}}
Given the following information about the previous screen capture:
{{previous_analysis}}
Analyze this screenshot and identify the required information as mentioned below and format response as JSON with these exact keys: 
        {generate_schema_description(ScreenCaptureData)}
        
Note: 
        - DO NOT make up any information.
        - DO NOT output a markdown block of json, just the json ONLY.
        - If you cannot identify any of the information, set the value to null.
        - Always stick to the schema described above. If you cannot identify a field, set the value to null or an appropriate default value if null is not an option.
        """
    ),

    "session_summary": AnalysisPrompt(
        system_context="",
        template=f"""
You are tasked with generating a comprehensive summary of events for a specific session. The events data is stored in a table with various fields including context_id, session_id, note, resource, main_topic, summary, is_learning_moment, and learning_observations. Your goal is to analyze this data and create an informative overview that highlights the key events and learnings from the session.

Here is the events data for the session:
<events_data>
{{EVENTS_DATA}}
</events_data>

Your task is to summarize the events for session ID: {{SESSION_ID}}

Follow these steps to generate the summary:

1. Analyze the provided events data, focusing on entries that match the given session_id.

2. Identify the main topics covered in the session by examining the 'main_topic' field.

3. Look for events marked as learning moments (is_learning_moment = 1) and pay special attention to their learning_observations.

4. Review the 'summary' field of each event to understand the key points discussed or actions taken.

5. Note any resources used or referenced during the session.

6. Identify any patterns or themes that emerge across multiple events in the session.

7. Synthesize this information into a coherent summary that provides an overview of the session, highlighting:
   - The primary focus or objective of the session
   - Key topics covered
   - Important learning moments and observations
   - Significant actions or decisions made
   - Resources utilized
   - Any notable patterns or themes

8. Ensure your summary is concise yet comprehensive, capturing the essence of the session's events.

Provide your response in the following format:

<session_summary>
<overview>
[A brief paragraph providing a high-level overview of the session]
</overview>

<key_topics>
- [Topic 1]
- [Topic 2]
- [...]
</key_topics>

<learning_highlights>
- [Key learning moment or observation 1]
- [Key learning moment or observation 2]
- [...]
</learning_highlights>

<resources_used>
- [Resource 1]
- [Resource 2]
- [...]
</resources_used>

<conclusion>
[A brief concluding paragraph summarizing the session's importance or main takeaways]
</conclusion>
</session_summary>

Remember to base your summary solely on the information provided in the events data. Do not include any external information or assumptions beyond what is present in the given data.
Return the required information EXACTLY as mentioned below and format it as JSON with these exact keys, do not wrap it in any markdown block, tags or any other text, just the JSON:
{generate_schema_description(SessionSummary)}
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