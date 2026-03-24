from typing import Annotated, NotRequired, TypedDict, Any

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ResponseT
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.prebuilt import ToolRuntime
from langgraph.typing import ContextT

from deepagents.backends.protocol import BackendProtocol, BackendFactory
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import validate_path, truncate_if_tool_long


class FileData(TypedDict):
    """文件数据结构"""
    content: list[str]
    created_at: str
    modified_at: str


def _file_data_reducer(left: dict[str, FileData] | None,
                       right: dict[str, FileData | None],
                       ) -> dict[str, FileData]:
    """file的注释，暂未理解代码"""
    pass


class FilesystemState(AgentState):
    file: Annotated[NotRequired[dict[str, FileData]], _file_data_reducer]


class FilesystemMiddleware(AgentMiddleware[FilesystemState, ContextT, ResponseT]):
    state_schema = FilesystemState

    def __init__(self,
                 *,
                 backend: BackendProtocol | BackendFactory | None = None,
                 system_prompt: str | None = None,
                 tool_token_limit_before_evict: int | None = 2000,
                 custom_tool_description: dict[str, str] | None = None,
                 ) -> None:
        self.backend = backend if backend is not None else StateBackend
        self._custom_system_prompt = system_prompt
        self._custom_tool_description = custom_tool_description
        self._custom_tool_limit_before_evict = tool_token_limit_before_evict

        self.tools = [
            self._create_ls_tool(),
            self._create_read_file_tool(),
            self._create_write_file_tool(),
            self._create_edit_file_tool(),
            self._create_glob_tool(),
            self._create_grep_tool(),
            self._create_execute_tool(),
        ]

    def _get_backend(self,
                     runtime: ToolRuntime[Any, Any, Any]
                     ) -> BackendProtocol:
        """有runtime后再获取backend"""
        if callable(self.backend):
            return self.backend(runtime)

    def _create_ls_tool(self) -> BaseTool:
        """通过backend使用函数,在转化成tool"""
        tool_description = self._custom_tool_description.get("ls")

        def sync_ls(
                runtime: ToolRuntime[None, FilesystemState],
                path: Annotated[str, "Absolute path to the directory to list. Must be absolute, not relative."]
        ) -> str:
            resolved_backend = self._get_backend(runtime)  # 重点：由中间件调取backend的tool去实现LLM的命令

            try:
                validated_path = validate_path(path)  # 变量和函数不能同名
            except ValueError as e:
                return f"Error: {e}"
            infos = resolved_backend.ls_info(validated_path)
            paths = [fi.get("path", "") for fi in infos]
            results = truncate_if_tool_long(paths)
            return str(results)

        async def async_ls(
                runtime: ToolRuntime[None, FilesystemState],
                path: Annotated[str, "Absolute path to the directory to list. Must be absolute, not relative."]
        ) -> str:
            resolved_backend = self.backend(runtime)
            try:
                validated_path = validate_path(path)
            except ValueError as e:
                return f"Error: {e}"
            infos = await resolved_backend.als_info(validated_path)
            paths = [fi.get("path", "") for fi in infos]
            result = truncate_if_tool_long(paths)
            return str(result)

        return StructuredTool.from_function(  # 把函数转换成langchain支持的tool
            name="ls",
            description=tool_description,
            func=sync_ls,
            coroutine=async_ls
        )

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
