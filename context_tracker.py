import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from logging import getLogger
from PIL import Image
from constants import CONTEXT_PATH, OBSIDIAN_PATH
from data import Context, ScreenCaptureData
from llm_providers.openai_provider import OpenAIProvider
from screen_capture import ScreenCapture, ScreenCaptureFactory
from storage import ContextStorage
from utils.llm_types import LLMProvider, AnalysisPrompt
from utils.prompts import PromptsManager
from logging import getLogger
from pydantic import BaseModel, Field, ValidationError

logger = getLogger(__name__)

class ContextTracker:
    def __init__(
        self,
        base_dir: str = OBSIDIAN_PATH,
        llm_provider: LLMProvider = OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY")
        ),
        context: Context = None,
        context_storage: ContextStorage = None,
        custom_prompts: Dict[str, AnalysisPrompt] = None,
        screen_capture: Optional[ScreenCapture] = None
    ):
        self.base_dir = Path(base_dir).expanduser()
        self.llm = llm_provider
        self.prompts = PromptsManager(custom_prompts)
        self.screen_capture = screen_capture or ScreenCaptureFactory.create("pyautogui")
        # TODO: self.setup_directories() # This is for the obsidian vault
        
        if context is None:
            raise ValueError("Context is required")
        
        self._current_context = context
        
        if context_storage is None:
            raise ValueError("Context storage is required")
        
        self.storage = context_storage
    

    def capture_screen(self) -> Image.Image:
        """
        Capture the current screen using configured screen capture implementation
        """
        try:
            return self.screen_capture.capture()
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            raise
    
    async def analyze_screen(self, image: Image,context: Context, previous_analysis: Optional[ScreenCaptureData] = None) -> Optional[ScreenCaptureData]:
        """Analyze screen content using configured LLM provider"""
        try:
            prompt = self.prompts.get_prompt("screen_activity_observation").format(
                context=context.description,
                previous_analysis=previous_analysis.model_dump_json() if previous_analysis else ""
            )
            logger.debug(f"Prompt: {prompt}")
            logger.debug(f"Analyzing screen with {self.llm.provider_name}")
            
            result = await self.llm.analyze_image(image, prompt)
            
            try:
                result = ScreenCaptureData(**result)
            except ValidationError as e:
                logger.error(f"Invalid response format: {e}")
                raise ValueError(f"Invalid response format: {e}")
            
            logger.info(f"Screen analysis complete: {result.main_topic} - important:{result.is_learning_moment}")
            return result
            
        except ValueError as e:
            logger.error(f"Invalid analysis result: {str(e)}")
            return {
                "activity": "unknown",
                "topic": "unknown",
                "resources": []
            }
        except Exception as e:
            logger.error(f"Screen analysis failed with {self.llm.provider_name}: {str(e)}")
            return None
    
    def persist_context_info(self, context_id: str, analysis: ScreenCaptureData) -> Optional[str]:
        """Persist context information to Sqlite DB"""
        # overwrite the context_id with the current context id
        analysis.context_id = context_id
        analysis.created_at = datetime.now()
        try:
            self.storage.save_context_info(**analysis.model_dump())
            return analysis
        except Exception as e:
            logger.error(f"Failed to persist context info: {e}")
            return None
        
    async def run_capture_cycle(self, interval: int = 30):
        previous_analysis = None
        while True:
            """Run one capture cycle"""
            image = self.capture_screen()

            # Analyze current activity
            analysis = await self.analyze_screen(image=image, context=self._current_context,previous_analysis=previous_analysis)
            if analysis is None:
                logger.error("Screen analysis failed, skipping capture cycle for timestamp: %s", datetime.now())
            else:
                print(f"Persisting context info for {self._current_context}\n {analysis}")
                previous_analysis = self.persist_context_info(
                    self._current_context.id, 
                    analysis
                )
                break # TODO: remove this after debugging
            await asyncio.sleep(interval)
