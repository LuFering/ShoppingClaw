"""Memory backends for pluggable file storage."""

from src.agents.common.backends.composite import CompositeBackend
from src.agents.common.backends.filesystem import FilesystemBackend
from src.agents.common.backends.local_shell import LocalShellBackend
from src.agents.common.backends.protocol import BackendProtocol
from src.agents.common.backends.state import StateBackend
from src.agents.common.backends.store import BackendContext, NamespaceFactory, StoreBackend
__all__ = [
    "BackendContext",
    "BackendProtocol",
    "CompositeBackend",
    "FilesystemBackend",
    "LocalShellBackend",
    "NamespaceFactory",
    "StateBackend",
    "StoreBackend",
]


