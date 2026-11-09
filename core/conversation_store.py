"""
Persists chats on disk (SQLite): conversation titles and every message, including tool calls
and tool results, so a conversation can be continued after a restart. The only module that
touches conversations.db; does not run the assistant or decide what gets said.
"""

from __future__ import annotations

import sqlite3
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from core.exceptions import ConversationNotFoundError, NimbusError
from models.chat import ChatMessage, ConversationSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);
"""
TITLE_MAX_CHARS = 60


class ConversationStore:
    """Thread-safe access to conversations.db."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """Opens (creating if needed) the conversations database."""
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.executescript(SCHEMA)
        except (OSError, sqlite3.Error) as e:
            raise NimbusError(f"Couldn't open chat history at {self._db_path}: {e}") from e

    def create(self, first_message: str) -> str:
        """Starts a conversation titled after its first message; returns its id."""
        conversation_id = uuid.uuid4().hex
        now = time.time()
        self._write(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            [(conversation_id, make_title(first_message), now, now)],
        )
        return conversation_id

    def append(self, conversation_id: str, messages: list[ChatMessage]) -> None:
        """Adds messages to the end of a conversation and bumps its last-updated time."""
        self.require(conversation_id)
        rows = [(conversation_id, m.model_dump_json()) for m in messages]
        self._write("INSERT INTO messages (conversation_id, payload) VALUES (?, ?)", rows)
        self._write("UPDATE conversations SET updated_at = ? WHERE id = ?", [(time.time(), conversation_id)])

    def load(self, conversation_id: str) -> list[ChatMessage]:
        """Every message of a conversation, oldest first."""
        self.require(conversation_id)
        rows = self._read("SELECT payload FROM messages WHERE conversation_id = ? ORDER BY id", (conversation_id,))
        return [ChatMessage.model_validate_json(row[0]) for row in rows]

    def list_recent(self, limit: int = 30) -> list[ConversationSummary]:
        """Most recently active conversations first."""
        rows = self._read("SELECT id, title, updated_at FROM conversations ORDER BY updated_at DESC LIMIT ?", (limit,))
        return [ConversationSummary(id=r[0], title=r[1], updated_at=datetime.fromtimestamp(r[2])) for r in rows]

    def delete(self, conversation_id: str) -> None:
        self._write("DELETE FROM conversations WHERE id = ?", [(conversation_id,)])

    def require(self, conversation_id: str) -> None:
        """Raises ConversationNotFoundError for an unknown id."""
        if not self._read("SELECT 1 FROM conversations WHERE id = ?", (conversation_id,)):
            raise ConversationNotFoundError(f"There's no chat with id {conversation_id}. It may have been deleted.")

    def _read(self, sql: str, params: tuple[object, ...]) -> list[tuple]:
        with self._lock:
            try:
                return self._connection().execute(sql, params).fetchall()
            except sqlite3.Error as e:
                raise NimbusError(f"Chat history read failed: {e}") from e

    def _write(self, sql: str, rows: list[tuple]) -> None:
        with self._lock:
            conn = self._connection()
            try:
                with conn:
                    conn.executemany(sql, rows)
            except sqlite3.Error as e:
                raise NimbusError(f"Chat history write failed: {e}") from e

    def _connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise NimbusError("Chat history isn't open yet — call connect() first.")
        return self._conn


def make_title(text: str) -> str:
    """A one-line title from a chat's first message."""
    flat = " ".join(text.split())
    return flat if len(flat) <= TITLE_MAX_CHARS else flat[: TITLE_MAX_CHARS - 1].rstrip() + "…"
