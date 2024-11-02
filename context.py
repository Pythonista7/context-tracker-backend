from dataclasses import Field
from datetime import datetime
import os
from typing import Optional
from pydantic import BaseModel
from data import ContextData
from storage import ContextStorage
import logging 

logger = logging.getLogger(__name__)

class Context():
    """Note: This is a shared contract with the user interface , currently just raycast."""
    def __init__(self,storage: ContextStorage):
        self.storage = storage
        self._current_context = None

    def create(self,name: str, id: Optional[int]=None) -> ContextData:
        """Create a new context"""
        try:
            # Check if context already exists
            existing_context = self.storage.get_context(context_id=id,name=name)
            if existing_context:
                logger.info(f"Context \"{name}\" already exists: {existing_context.id}")
                self._current_context = existing_context
                return existing_context
            else:
                context_data = ContextData(id=id,name=name,color="#FF6B6B",last_active=datetime.now())
                id = self.storage.create_context(context_data)
                context_data.id = id
                self._current_context = context_data
                return context_data
        except Exception as e:
            logger.error(f"Failed to create context: {e}")
            raise e

    def _load_current_context(self) -> ContextData:
        """
        Load current context from interface file, falling back to defaults if not found
        """
        try:
            current = self.storage.get_last_active_context()
            if current:
                self._current_context = ContextData(
                    id=current.id,
                    name=current.name,
                    description=current.description,
                    color=current.color,
                    last_active=current.last_active
                )
                logger.info(f"Loaded context : {current['id']}")
                return self._current_context
            else:
                logger.error("No current context found in DB, using default")
                self._current_context = ContextData(
                    id='work',
                    name='work',
                    description='Default context',
                    color='#FF6B6B',
                    last_active=datetime.now()
                )
                logger.debug("Initialized default context: work")
                return self._current_context
        except Exception as e:
            logger.warning(f"Failed to load previous context : {e}")
            # Fall back to default if file doesn't exist or no current context found
            self._current_context = ContextData(
                id='work',
                name='work',
                color='#FF6B6B',
                last_active=datetime.now(),
                notes=[],
                resources=[]
            )
            logger.debug("Initialized default context: work")
            return self._current_context