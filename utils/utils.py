
"""
Utility functions
"""

import json

from pydantic import BaseModel, ValidationError

import logging

logger = logging.getLogger(__name__)

def parse_json_string_to_model(json_string: str, model: BaseModel) -> BaseModel:
    """Parse a JSON string to a Pydantic model"""
    try:
        return model(**json.loads(json_string))
    except ValidationError as e:
        logger.error(f"Invalid response format from LLM: {e}\n Response: {json_string}")
        raise ValueError(f"Invalid response format: {e}")
