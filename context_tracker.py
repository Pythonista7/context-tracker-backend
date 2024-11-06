import asyncio
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Dict, Optional, List
from logging import getLogger, basicConfig, INFO, DEBUG
from PIL import Image
from constants import CONTEXT_PATH, OBSIDIAN_PATH
from context import Context
from data import ContextData, ScreenCaptureData, SessionSummary
from llm_providers.openai_provider import OpenAIProvider
from screen_capture import ScreenCapture, ScreenCaptureFactory
from session import Session
from storage import ContextStorage
from utils.llm_types import LLMProvider, AnalysisPrompt
from utils.prompts import PromptsManager
from logging import getLogger
from pydantic import BaseModel, Field, ValidationError

from utils.utils import parse_json_string_to_model

basicConfig(
    level=INFO,  # Set to DEBUG to see all log messages
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

logger = getLogger(__name__)

class ContextTracker:

    def __init__(
        self, 
        session: Session,
        context: ContextData,
        base_dir: str = OBSIDIAN_PATH,
        llm_provider: LLMProvider = OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY")
        ),
        context_storage: ContextStorage = None,
        custom_prompts: Dict[str, AnalysisPrompt] = None,
        screen_capture: Optional[ScreenCapture] = None,
    ):
        self.base_dir = Path(base_dir).expanduser()
        self.llm = llm_provider
        self.prompts = PromptsManager(custom_prompts)
        self.screen_capture = screen_capture or ScreenCaptureFactory.create("pyautogui")
        # TODO: self.setup_directories() # This is for the obsidian vault
        
        self.storage = context_storage

        self.session = session 

        self._current_context = context

    def capture_screen(self) -> Image.Image:
        """
        Capture the current screen using configured screen capture implementation
        """
        try:
            return self.screen_capture.capture()
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            raise
    
    @property
    def current_context(self) -> ContextData:
        """Get current context with lazy initialization"""
        return self._current_context
    
    async def analyze_screen(self, image: Image,context: ContextData, previous_analysis: Optional[ScreenCaptureData] = None) -> Optional[ScreenCaptureData]:
        """Analyze screen content using configured LLM provider"""
        try:
            prompt = self.prompts.get_prompt("screen_activity_observation").format(
                context=context.description,
                previous_analysis=previous_analysis.model_dump_json() if previous_analysis else ""
            )
            logger.debug(f"Prompt: {prompt}")
            logger.debug(f"Analyzing screen with {self.llm.provider_name}")
            
            result = await self.llm.analyze_image(image, prompt)
            result = ScreenCaptureData(**result)
            
            logger.info(f"Session: {self.session.session_id} - Screen analysis complete: {result.main_topic} - important:{result.is_learning_moment}")
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
    
    def persist_event(self, analysis: ScreenCaptureData) -> None:
        """Persist context information to Sqlite DB"""
        # overwrite the context_id with the current context id
        analysis.context_id = self.current_context.id
        analysis.created_at = datetime.now()
        analysis.session_id = self.session.session_id
        try:
            self.storage.save_event(**analysis.serialize())
            return
        except Exception as e:
            logger.error(f"Failed to persist context info: {e}")
            return
    
    async def start_session(self) -> int:
        """Start a new session and return its ID"""
        new_session_id = await self.session.start()
        print(f"Started session with id: {new_session_id} == {self.session.session_id}")
        return new_session_id
    
    async def end_session(self) -> None:
        """End a session and optionally add a summary"""
        await self.session.summarize_and_save()

    async def run_capture_cycle(self, interval: int = 30):
        context = self.current_context
        previous_analysis = None
        
        if self.session is None:
            raise ValueError("Session is not set, please set a session before running capture cycle")

        session_id = await self.start_session()
        logger.info(f"Tracker started session with id: {session_id} for context: {context.id} at {datetime.now()}")
        
        while self.session.is_active():
            """Run one capture cycle"""
            logger.debug(f"Running capture cycle for context: {context.id} , session: {session_id} at {datetime.now()}")
            image = self.capture_screen()

            logger.debug(f"Storing event for context: {context.id} , session: {session_id} at {datetime.now()}")
            # Analyze current activity
            analysis = await self.analyze_screen(image=image, context=context,previous_analysis=previous_analysis)
            if analysis is None:
                logger.error("Screen analysis failed, skipping capture cycle for timestamp: %s", datetime.now())
            else:
                print(f"Persisting context info for {self.current_context}\n {analysis}")
                previous_analysis = self.persist_event(analysis)
                # break # TODO: remove this after debugging
            logger.debug(f"Sleeping for {interval} seconds at {datetime.now()}")
            await asyncio.sleep(interval)
        
        logger.info(f"Ending session with id: {session_id} for context: {context.id} at {datetime.now()}")