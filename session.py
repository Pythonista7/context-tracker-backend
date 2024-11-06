from datetime import datetime
import asyncio
import os
from typing import Dict, Optional

import logging

from data import SessionSummary
from llm_providers.openai_provider import OpenAIProvider
from storage import ContextStorage
from utils.llm_types import AnalysisPrompt, LLMProvider
from utils.prompts import PromptsManager
from utils.utils import parse_json_string_to_model

logger = logging.getLogger(__name__)

class Session:
    def __init__(
        self,
        storage: ContextStorage,
        context_id: int,
        session_id: Optional[int] = None,
        start_time: datetime = None,
        llm: LLMProvider = None,
        custom_prompts: Optional[Dict[str, AnalysisPrompt]] = None
    ):
        self.storage = storage
        self.context_id = context_id
        self.session_id = session_id
        self.start_time = start_time
        self._end_session_event = asyncio.Event()
        self.llm = llm or OpenAIProvider(api_key=os.getenv("OPENAI_API_KEY"))
        self.custom_prompts = custom_prompts
        self.prompts = PromptsManager(custom_prompts)
        self.end_time = None

    @classmethod
    async def create_and_start(
        cls,
        storage: ContextStorage,
        context_id: int,
        session_id: Optional[int] = None,
        start_time: datetime = None,
        llm: LLMProvider = None,
        custom_prompts: Optional[Dict[str, AnalysisPrompt]] = None
    ) -> 'Session':
        session = cls(
            storage=storage,
            context_id=context_id,
            session_id=session_id,
            start_time=start_time,
            llm=llm,
            custom_prompts=custom_prompts
        )
        session.session_id = await session.start()
        logger.info(f"Created session with id: {session.session_id}")
        return session

    async def start(self) -> int:
        """Start the session and return the session id"""
        if self.session_id is not None and self.is_active():
            logger.warning("Session already active, skipping start")
            return self.session_id

        try:
            self.start_time = datetime.now()
            session_id = self.storage.create_session(context_id=self.context_id, start_time=self.start_time)
            logger.info(f"Session created with id: {session_id}")
            self.session_id = session_id
            logger.info(f"Session started with id: {self.session_id}")
            return session_id
        except Exception as e:
            logger.error(f"Failed to start session: {e}")
            raise

    async def end(self):
        """End the current session"""
        if not self.is_active():
            logger.warning("Session already ended")
            return

        logger.info(f"Ending session with id: {self.session_id} at {datetime.now()}")
        self._end_session_event.set()
        await self.summarize_and_save()

    def is_active(self) -> bool:
        """Check if session is still active"""
        return not self._end_session_event.is_set()

    async def summarize_and_save(self):
        self.end_time = datetime.now()
        try:
            session_summary = await self.generate_session_summary(self.session_id)
            logger.info(f"Generated session summary: {session_summary}")
            self.storage.end_session_updating_summary(self.session_id, self.end_time, session_summary)
            return session_summary
        except Exception as e:
            logger.error(f"Failed to end session: {e}")

    async def generate_session_summary(self, session_id: int) -> SessionSummary:
        """Generate a summary for a session"""
        try:
            events = self.storage.get_session_events(session_id)
            session_summary_prompt = self.prompts.get_prompt("session_summary").format(
                EVENTS_DATA=events,
                SESSION_ID=session_id
            )
            session_summary = await self.llm.generate_text(
                prompt=session_summary_prompt.template,
                system_context=session_summary_prompt.system_context
            )
            return parse_json_string_to_model(session_summary, SessionSummary)
        except Exception as e:
            logger.error(f"[Session {self.session_id}] Failed to generate session summary: {e}")
            raise

    # async def __aenter__(self) -> 'Session':
    #     await self.start()
    #     return self

    # async def __aexit__(self, exc_type, exc_val, exc_tb):
    #     await self.end()