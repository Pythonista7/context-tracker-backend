
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import asdict

from constants import CONTEXT_PATH
from data import Context

class ContextStorage:
    def __init__(self, db_path: str = f"{CONTEXT_PATH}/context.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Initialize database tables if they don't exist"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create contexts table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS contexts (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    color TEXT NOT NULL,
                    last_active TIMESTAMP NOT NULL
                )
            """)

            # Create context_info table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS context_info (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    context_id TEXT NOT NULL,
                    note TEXT,
                    resource TEXT,
                    main_topic TEXT,
                    summary TEXT,
                    is_learning_moment BOOLEAN,
                    learning_observations TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (context_id) REFERENCES contexts(id)
                )
            """)
            
            conn.commit()
            
    def save_context_info(self, context_id: str, notes: Optional[str], resources: Optional[str], main_topic: Optional[str], summary: Optional[str], is_learning_moment: Optional[bool], learning_observations: Optional[str],created_at: Optional[datetime]) -> None:
        """Save or update a context info"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO context_info (context_id, note, resource, main_topic, summary, is_learning_moment, learning_observations, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (context_id, notes, resources, main_topic, summary, is_learning_moment, "\n".join(learning_observations), created_at))
            conn.commit()

    def save_context(self, context:Context) -> None:
        """Save or update a context"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO contexts (id, name, color, last_active)
                VALUES (?, ?, ?, ?)
            """, (context.id, context.name, context.color, context.last_active))
            
            # Save associated notes and resources
            # if context.notes or context.resources:
            #     context_id = context.id
                
            #     # Save notes
            #     for note in context.notes:
            #         cursor.execute("""
            #             INSERT INTO context_info (context_id, note)
            #             VALUES (?, ?)
            #         """, (context_id, note))
                
            #     # Save resources
            #     for resource in context.resources:
            #         cursor.execute("""
            #             INSERT INTO context_info (context_id, resource)
            #             VALUES (?, ?)
            #         """, (context_id, resource))
            
            conn.commit()

    def get_context(self, context_id: str) -> Optional[dict]:
        """Retrieve a context and its associated info"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get context
            cursor.execute("""
                SELECT id, name, color, last_active
                FROM contexts
                WHERE id = ?
            """, (context_id,))
            
            context_row = cursor.fetchone()
            if not context_row:
                return None
                
            # Get associated notes and resources
            cursor.execute("""
                SELECT note, resource
                FROM context_info
                WHERE context_id = ?
            """, (context_id,))
            
            notes = []
            resources = []
            for note, resource in cursor.fetchall():
                if note:
                    notes.append(note)
                if resource:
                    resources.append(resource)
            
            return {
                "id": context_row[0],
                "name": context_row[1],
                "color": context_row[2],
                "last_active": datetime.fromisoformat(context_row[3]),
                "notes": notes,
                "resources": resources
            }

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
        """Delete a context and its associated info"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM context_info WHERE context_id = ?", (context_id,))
            cursor.execute("DELETE FROM contexts WHERE id = ?", (context_id,))
            conn.commit()