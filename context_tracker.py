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
    CONTEXT_FILE = CONTEXT_PATH / "contexts.json"

    def __init__(
        self, 
        base_dir: str = OBSIDIAN_PATH,
        llm_provider: LLMProvider = None,
        custom_prompts: Dict[str, AnalysisPrompt] = None,
        screen_capture: Optional[ScreenCapture] = None
    ):
        self.base_dir = Path(base_dir).expanduser()
        self.llm = llm_provider or OpenAIProvider(
            api_key=os.getenv("OPENAI_API_KEY")
        )
        self.prompts = PromptsManager(custom_prompts)
        self.screen_capture = screen_capture or ScreenCaptureFactory.create("pyautogui")
        # TODO: self.setup_directories() # This is for the obsidian vault
        
        # Initialize current context last to ensure all dependencies are set up
        self._current_context = None
        self._load_current_context()
        
        self.storage = ContextStorage()

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
    def current_context(self) -> Context:
        """Get current context with lazy initialization"""
        if self._current_context is None:
            self._load_current_context()
        return self._current_context
    
    def _load_current_context(self) -> None:
        """
        Load current context from interface file, falling back to defaults if not found
        """
        try:
            if self.CONTEXT_FILE.exists():
                with open(self.CONTEXT_FILE, 'r') as f:
                    contexts = json.load(f)
                    # Find context marked as current
                    current = next(
                        (ctx for ctx in contexts if ctx.get("lastActive") == "current"),
                        None
                    )
                    if current:
                        self._current_context = Context(
                            id=current['id'],
                            name=current['name'],
                            color=current.get('color', '#FF6B6B'),
                            last_active=datetime.now(),
                            notes=current.get('notes', []),
                            resources=current.get('resources', [])
                        )
                        logger.debug(f"Loaded context from file: {current['id']}")
                        return
                    
            logger.debug("No current context found in file, using default")
        except Exception as e:
            logger.warning(f"Failed to load context file: {e}")
        
        # Fall back to default if file doesn't exist or no current context found
        self._current_context = Context(
            id='work',
            name='work',
            color='#FF6B6B',
            last_active=datetime.now(),
            notes=[],
            resources=[]
        )
        logger.debug("Initialized default context: work")

    async def analyze_screen(self, image: Image) -> Optional[dict]:
        """Analyze screen content using configured LLM provider"""
        try:
            prompt = self.prompts.get_prompt("screen_activity_observation")
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
        self.storage.save_context_info(**analysis.model_dump())

    async def run_capture_cycle(self):
        """Run one capture cycle"""
        image = self.capture_screen()

        # Analyze current activity
        analysis = await self.analyze_screen(image)
        if analysis is None:
            logger.error("Screen analysis failed, skipping capture cycle for timestamp: %s", datetime.now())
            return None
        print(f"Persisting context info for {self.current_context}\n {analysis}")
        note_path = self.persist_context_info(
            self.current_context.id, 
            analysis
        )
        return note_path
