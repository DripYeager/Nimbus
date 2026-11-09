"""
Builds every engine service once and wires them together: storage, indexing, the file
watcher, the app catalog, the model provider, tools and the assistant. Also starts, stops and
re-configures them as a unit. The composition root for the engine — no UI, no HTTP.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from config.paths import notes_dir
from config.settings import get_settings
from core.agent import Agent
from core.chat_service import ChatService
from core.conversation_store import ConversationStore
from core.embedder import get_embedder
from core.fast_path import FastPath
from core.file_catalog import FileCatalog
from core.file_watcher import FileWatcher
from core.index_service import IndexService
from core.indexer import Indexer
from core.logger import get_logger
from core.rag_answer import RagAnswerer
from core.retriever import Retriever
from core.usage_meter import UsageMeter
from core.vector_store import VectorStore
from llm.active_provider import ActiveProvider
from llm.prompts import build_system_prompt
from tools.action_toolbox import ActionToolbox
from tools.app_catalog import AppCatalog
from tools.file_toolbox import FileToolbox
from tools.registry import ToolRegistry

logger = get_logger(__name__)

SettingsListener = Callable[[], None]


class AppServices:
    """Holds the long-lived engine services. Build with AppServices.build(), then start()."""

    def __init__(self) -> None:
        self.catalog: FileCatalog | None = None
        self.store: VectorStore | None = None
        self.index: IndexService | None = None
        self.watcher: FileWatcher | None = None
        self.apps: AppCatalog | None = None
        self.provider: ActiveProvider | None = None
        self.conversations: ConversationStore | None = None
        self.chat: ChatService | None = None
        self.usage: UsageMeter | None = None
        self._settings_listeners: list[SettingsListener] = []

    @classmethod
    def build(cls) -> AppServices:
        """Opens storage and constructs every service, without starting background work."""
        services = cls()
        settings = get_settings()
        services.catalog = FileCatalog(settings.catalog_path)
        services.catalog.connect()
        services.store = VectorStore()
        services.store.connect()
        services.conversations = ConversationStore(settings.conversations_path)
        services.conversations.connect()
        services.usage = UsageMeter(settings.data_dir / "usage.json")
        services.provider = ActiveProvider(services.usage)
        services.index = IndexService(services.catalog, services.store, Indexer(services.store, get_embedder()))
        services.watcher = FileWatcher(services.index)
        services.apps = AppCatalog()
        services._build_chat()
        return services

    def start(self) -> None:
        """Starts indexing, the watcher, and the app-catalog scan. Returns immediately."""
        settings = get_settings()
        self.index.start(settings.embedding_model)
        self.watcher.start(settings.sources)
        threading.Thread(target=self._load_app_catalog, name="app-catalog", daemon=True).start()

    def stop(self) -> None:
        self.watcher.stop()
        self.index.stop()

    def add_settings_listener(self, listener: SettingsListener) -> None:
        """Registers a callback for after settings change — e.g. the UI rebinding the hotkey."""
        self._settings_listeners.append(listener)

    def apply_settings(self) -> None:
        """Pushes freshly saved settings into every running service. The provider goes last: it
        can refuse an incomplete choice (e.g. no base URL yet), and that mustn't stop the
        already-saved folder and hotkey changes from taking effect."""
        self.index.apply_settings()
        self.watcher.restart(get_settings().sources)
        for listener in self._settings_listeners:
            listener()
        self.provider.reload()

    def is_path_shared(self, path: Path) -> bool:
        """True for a path the user shared with Nimbus, or one of Nimbus's own notes."""
        if self.index.rules.is_covered(path):
            return True
        return notes_dir().resolve() in path.resolve().parents

    def _build_chat(self) -> None:
        """Wires tools, the assistant and the fast path into the chat service."""
        retriever = Retriever(self.store, get_embedder())
        registry = ToolRegistry()
        FileToolbox(retriever, self.catalog, self.is_path_shared, self.provider).register(registry)
        actions = ActionToolbox(self.apps, self.is_path_shared)
        actions.register(registry)
        agent = Agent(self.provider, registry, _system_prompt, RagAnswerer(retriever, self.provider).answer)
        self.chat = ChatService(self.conversations, agent, FastPath(self.catalog, actions), self.index.status)

    def _load_app_catalog(self) -> None:
        """Loads (or builds, ~1-2s) the installed-app list off the startup path."""
        try:
            self.apps.load_or_build()
        except Exception:
            logger.exception("Couldn't build the app catalog; app launching won't work this session")


def _system_prompt() -> str:
    """Rebuilt per turn so the time and folder list are always current."""
    folders = [source.path.name or str(source.path) for source in get_settings().sources]
    return build_system_prompt(folders, datetime.now())
