from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

from deepagents.backends.protocol import BackendProtocol, BackendFactory


class MemoryState:
    pass


class MemoryMiddleware(AgentMiddleware[MemoryState,ContextT,ResponseT]):
    state_schema = MemoryState

    def __init__(self,
                 *,
                 backend:BackendProtocol|BackendFactory,
                 sources:list[str],
                 )->None:
        self.backend=backend
        self.sources=sources