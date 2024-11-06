import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict
import time
from contextlib import contextmanager
import queue
from flask import current_app, g

from constants import CONTEXT_PATH
from data import ContextData, SessionSummary
from logging import getLogger

logger = getLogger(__name__)

class ContextStorage:
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, db_path: str = f"{CONTEXT_PATH}/context.db"):
        if self._initialized:
            return
            
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.timeout = 30.0
        
        # Create a connection pool
        self._pool = queue.Queue(maxsize=10)  # Limit to 10 connections
        for _ in range(5):  # Start with 5 connections
            self._pool.put(self._create_connection())
            
        self._init_db()
        self._initialized = True
    
    def _create_connection(self):
        """Create a new database connection"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.timeout,
            isolation_level='IMMEDIATE',
            check_same_thread=False  # Allow cross-thread usage
        )
        return conn
    
    def _get_connection(self):
        """Get connection for current context/thread"""
        if 'db' not in g:
            g.db = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                isolation_level='IMMEDIATE'
            )
        return g.db
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = self._get_connection()
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            raise e
    
    def _execute_with_retry(self, query_func, max_retries=3):
        """Execute a database operation with retry logic"""
        for attempt in range(max_retries):
            try:
                with self.get_connection() as conn:
                    return query_func(conn)
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying... ({attempt + 1}/{max_retries})")
                    time.sleep(0.1 * (attempt + 1))
                    continue
                raise
            except Exception as e:
                logger.error(f"Database error: {e}")
                raise
    
    def _init_db(self):
        """Initialize database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create contexts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contexts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    name TEXT NOT NULL,
                    color TEXT NOT NULL,
                    description TEXT,
                    last_active TIMESTAMP NOT NULL,
                    UNIQUE (name)
                )
            """)
            
            # Create new sessions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    context_id TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    overview TEXT,
                    key_topics TEXT,
                    learning_highlights TEXT,
                    resources_used TEXT,
                    conclusion TEXT,
                    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE,
                    UNIQUE (context_id, start_time)
                )
            """)

            # Create events table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
                    context_id TEXT NOT NULL,
                    session_id INTEGER,
                    note TEXT,
                    resource TEXT,
                    main_topic TEXT,
                    summary TEXT,
                    is_learning_moment BOOLEAN,
                    learning_observations TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (context_id) REFERENCES contexts(id) ON DELETE CASCADE,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE SET NULL
                )
            """)

            
            
            conn.commit()
            logger.info("Database initialized successfully.")
            
    def save_event(self, context_id: str, session_id: Optional[int], notes: Optional[str], resources: Optional[str], main_topic: Optional[str], summary: Optional[str], is_learning_moment: Optional[bool], learning_observations: Optional[str], created_at: Optional[datetime]) -> None:
        """Save or update an event"""
        def _save(conn):
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO events (context_id, session_id, note, resource, main_topic, summary, 
                                            is_learning_moment, learning_observations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (context_id, session_id, notes, resources, main_topic, summary, 
                 is_learning_moment, learning_observations, created_at))
            conn.commit()
        self._execute_with_retry(_save)
    
    def create_context(self, context:ContextData) -> int:
        """Create a new context and return the id"""
        def _create(conn):
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO contexts (name, color, description, last_active)
                VALUES ( ?, ?, ?, ?)
                RETURNING id
            """, (context.name, context.color, context.description, context.last_active))   
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
        return self._execute_with_retry(_create)

    def save_context(self, context:ContextData) -> None:
        """Save or update a context"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO contexts (id, name, color, description, last_active)
                VALUES (?, ?, ?, ?, ?)
            """, (context.id, context.name, context.color, context.description, context.last_active))
            
            conn.commit()

    def get_last_active_context(self) -> Optional[ContextData]:
        """Retrieve the last active context"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM contexts ORDER BY last_active DESC LIMIT 1")
            context_id = cursor.fetchone()
            logger.info(f"Last active context: {context_id}")
            if context_id:
                return self.get_context(context_id)
            return None

    def get_context(self, context_id: Optional[str] = None, name: Optional[str] = None) -> Optional[ContextData]:
        """Retrieve a context and its associated info"""
        if not context_id and not name:
            logger.error("No context_id or name provided!!")
            return None
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            if context_id:
                query = "SELECT id, name, color, description, last_active FROM contexts WHERE id = ?"
                params = (context_id,)
            elif name:
                query = "SELECT id, name, color, description, last_active FROM contexts WHERE name = ?"
                params = (name,)
            else:
                return None
            
            cursor.execute(query, params)
            
            context_row = cursor.fetchone()
            if not context_row:
                return None
            
            return ContextData( 
                id = context_row[0],
                name = context_row[1],
                color = context_row[2],
                description = context_row[3],
                last_active = datetime.fromisoformat(context_row[4]),  
            )

    def get_all_contexts(self) -> List[dict]:
        """Retrieve all contexts"""
        contexts = []
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM contexts")
            context_ids = cursor.fetchall()
            
            for (context_id,) in context_ids:
                context = self.get_context(context_id)
                if context:
                    contexts.append(context)
                    
        return contexts

    def delete_context(self, context_id: str) -> None:
        """Delete a context (associated events and sessions will be deleted automatically)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM contexts WHERE id = ?", (context_id,))
            conn.commit()

    def create_session(self, context_id: str, start_time: datetime) -> int:
        """Create a new session with retry logic"""
        def _create(conn) -> int:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (context_id, start_time)
                VALUES (?, ?)
                RETURNING id
            """, (context_id, start_time))
            new_id = cursor.fetchone()[0]
            conn.commit()
            return new_id
        return self._execute_with_retry(_create)


    def end_session_updating_summary(self, session_id: int, end_time: datetime, session_summary: SessionSummary) -> None:
        """End a session and optionally add a summary"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE sessions 
                SET end_time = ?, overview = ?, key_topics = ?, learning_highlights = ?, resources_used = ?, conclusion = ?
                WHERE id = ?
            """, (end_time, session_summary.overview, "\n".join(session_summary.key_topics), "\n".join(session_summary.learning_highlights), "".join(session_summary.resources_used), session_summary.conclusion, session_id))
            conn.commit()
    
    def get_session(self, session_id: int) -> Optional[dict]:
        """Retrieve a session and its associated info"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            return cursor.fetchone()
    
    def get_session_events(self, session_id: int) -> List[dict]:
        """Retrieve all events associated with a session"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM events WHERE session_id = ?", (session_id,))
            return cursor.fetchall()