from abc import ABC, abstractmethod
from typing import Optional
from pathlib import Path
import logging
from PIL import Image
import pyautogui

logger = logging.getLogger(__name__)

class ScreenCapture(ABC):
    """Abstract base class for screen capture implementations"""
    
    @abstractmethod
    def capture(self) -> Image.Image:
        """Capture screen and return PIL Image"""
        pass

class PyAutoGUICapture(ScreenCapture):
    """Screen capture implementation using pyautogui"""
    
    def __init__(self, region: Optional[tuple[int, int, int, int]] = None):
        """
        Initialize screen capture
        Args:
            region: Optional tuple of (left, top, width, height) for partial capture
        """
        self.region = region
    
    def capture(self) -> Image.Image:
        """Capture screen or screen region using pyautogui"""
        try:
            if self.region:
                screenshot = pyautogui.screenshot(region=self.region)
            else:
                screenshot = pyautogui.screenshot()
            
            logger.debug(
                f"Captured screenshot: {screenshot.size[0]}x{screenshot.size[1]} pixels"
            )
            return screenshot
            
        except Exception as e:
            logger.error(f"Screen capture failed: {str(e)}")
            raise RuntimeError(f"Failed to capture screen: {str(e)}")

# Factory for creating screen capture instances
class ScreenCaptureFactory:
    @staticmethod
    def create(capture_type: str = "pyautogui", **kwargs) -> ScreenCapture:
        """
        Create a screen capture instance
        Args:
            capture_type: Type of screen capture to create
            **kwargs: Additional arguments for the specific capture type
        """
        if capture_type == "pyautogui":
            return PyAutoGUICapture(**kwargs)
        else:
            raise ValueError(f"Unknown screen capture type: {capture_type}")