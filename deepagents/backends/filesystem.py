from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langgraph.typing import ContextT

from deepagents.backends.protocol import BackendProtocol, BackendFactory
from deepagents.backends.state import StateBackend


class FilesystemState:
    pass


class FilesystemMiddleware(AgentMiddleware[FilesystemState, ContextT, ResponseT]):
    state_schema = FilesystemState

    def __init__(self,
                 *,
                 backend: BackendProtocol | BackendFactory | None = None,
                 system_prompt: str | None = None,
                 tool_token_limit_before_evict: int | None = 2000,
                 custom_tool_description: dict[str, str] | None,
                 ) -> None:
        self.backend = backend if backend is not None else StateBackend
        self._custom_system_prompt = system_prompt
        self._custom_tool_description = custom_tool_description
        self._custom_tool_limit_before_evict = tool_token_limit_before_evict

        self.tools=[
            self._create_ls_tool(),
            self._create_read_file_tool(),
            self._create_write_file_tool(),
            self._create_edit_file_tool(),
            self._create_glob_tool(),
            self._create_grep_tool(),
            self._create_execute_tool(),
        ]

    def _create_ls_tool(self):
        pass

    def _create_read_file_tool(self):
        pass

    def _create_write_file_tool(self):
        pass

    def _create_edit_file_tool(self):
        pass

    def _create_glob_tool(self):
        pass

    def _create_grep_tool(self):
        pass

    def _create_execute_tool(self):
        pass
