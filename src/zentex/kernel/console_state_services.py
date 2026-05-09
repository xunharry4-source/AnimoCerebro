from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from zentex.common.storage_paths import get_storage_paths
from zentex.kernel.system_identity_store import SystemIdentityStore
from zentex.kernel.workspace_store import WorkspaceStore
from zentex.web_console.cache_manager import WebConsoleCacheManager
from zentex.web_console.internal.event_bus_impl import InProcessEventBus
from zentex.web_console.internal.session_manager_impl import SessionManagerImpl
from zentex.web_console.internal.state_manager_impl import NineQuestionStateManagerImpl
from zentex.kernel.console_nine_question_state_store import SQLiteStateStore
from zentex.kernel.console_session_store import SQLiteSessionStore


@dataclass(frozen=True)
class ConsoleStateServices:
    session_manager: Any
    state_manager: Any
    event_bus: Any
    cache_manager: Any
    workspace_store: Any
    system_identity_store: Any


def build_console_state_services(*, cache_ttl_seconds: int) -> ConsoleStateServices:
    storage_paths = get_storage_paths()
    session_store = SQLiteSessionStore(str(storage_paths.session_db))
    state_store = SQLiteStateStore(str(storage_paths.session_db))
    event_bus = InProcessEventBus()
    cache_manager = WebConsoleCacheManager(default_ttl_seconds=cache_ttl_seconds)
    return ConsoleStateServices(
        session_manager=SessionManagerImpl(
            store=session_store,
            event_bus=event_bus,
            cache_manager=cache_manager,
        ),
        state_manager=NineQuestionStateManagerImpl(
            store=state_store,
            event_bus=event_bus,
            cache_manager=cache_manager,
        ),
        event_bus=event_bus,
        cache_manager=cache_manager,
        workspace_store=WorkspaceStore(storage_paths.workspace_db),
        system_identity_store=SystemIdentityStore(storage_paths.core_db),
    )
