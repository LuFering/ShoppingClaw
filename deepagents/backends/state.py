from langgraph.prebuilt import ToolRuntime
from protocol import FileInfo, GrepMatch

from deepagents.backends.protocol import BackendProtocol, WriteResult, EditResult, FileUploadResponse, \
    FileDownloadResponse

"""基于langgraph中state状态的短期文件操控，提供测试、搜索近期上下文、编辑的功能"""


class StateBackend(BackendProtocol):
    def __init__(self, runtime: "ToolRuntime") -> None:
        """runtime用于接收Langgraph内部ToolRuntime(含state属性)"""
        self.runtime = runtime

    # 实现BackendProtocol抽象方法
    def ls_info(self, path: str) -> list[FileInfo]:
        pass

    def read(self,
             file_path: str,
             offset: int = 0,
             limit: int = 2000,
             ) -> str:
        pass

    def write(self,
              file_path: str,
              content: str,
              ) -> WriteResult:
        pass

    def edit(self,
             file_path: str,
             old_string: str,
             new_string: str,
             replace_all: bool = False,
             ) -> EditResult:
        pass

    def grep_raw(self,
                 pattern: str,
                 path: str | None = None,
                 glob: str | None = None,
                 ) -> list[GrepMatch] | str:
        pass

    def glob_info(self,
                  pattern: str,
                  path: str = "/",
                  ) -> list["FileInfo"]:
        pass

    def upload_files(self,
                     files: list[tuple[str, bytes]],
                     ) -> list[FileUploadResponse]:
        pass

    def download_file(self,
                      paths: list[str],
                      ) -> list[FileDownloadResponse]:
        pass
