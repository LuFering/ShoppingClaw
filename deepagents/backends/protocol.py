import abc
import asyncio
from typing import TypedDict, NotRequired, Any
from dataclasses import dataclass

from dotenv.variables import Literal

FileOperationError = Literal[
    "file_not_found",  # 下载问题，文件不存在
    "permission_denied",  # 访问权限
    "is_directory",
    "invalid_path",

]


class FileInfo(TypedDict):
    """文件数据返回格式"""
    path: str  # 文件路径
    is_dir: NotRequired[bool]  # 是否有文件目录
    size: NotRequired[int]  # 文件大小
    modified_at: NotRequired[str]  # 修改时间


@dataclass  # 相当于spring的@Data,自动注入有参构造等方法
class GrepMatch:
    """搜索结果记录类"""
    path: str
    line: int
    text: str


class WriteResult(TypedDict):
    """写入反馈信息"""
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None


@dataclass
class EditResult:
    """编辑反馈信息"""
    error: str | None = None
    path: str | None = None
    files_update: dict[str, Any] | None = None
    occurrence: int | None = None


@dataclass
class FileUploadResponse:
    path: str
    error: FileOperationError | None = None


@dataclass
class FileDownloadResponse:
    """文件下载响应"""
    path: str
    content: bytes | None = None
    error: FileOperationError | None = None

"""这是抽象类，用于实现backend，功能是对file进行系统级操作"""
class BackendProtocol(abc.ABC):  # abc是抽象基类模块，ABC是抽象类。相当于接口
    def ls_info(self, path: str) -> list["FileInfo"]:
        """从指定路径中获取文件数据信息"""
        raise NotImplementedError

    async def als_info(self, path: str) -> list["FileInfo"]:
        return await asyncio.to_thread(self.ls_info, path)

    def read(self,
             file_path: str,  # 文件路径
             offset: int = 0,  # 阅读偏离量
             limit: int = 2000,  # 最大行限制
             ) -> str:
        """阅读文件内容"""
        raise NotImplementedError

    async def aread(self,
                    file_path: str,
                    offset: int = 0,
                    limit: int = 2000
                    ) -> str:
        return await asyncio.to_thread(self.read, file_path, offset, limit)

    def grep_raw(self,
                 pattern: str,  # 文本搜索模式
                 path: str | None = None,  # 搜索路径
                 glob: str | None = None,  # 文件筛选
                 ) -> list["GrepMatch"] | str:
        """文本搜索"""
        raise NotImplementedError

    async def agep_raw(self,
                       pattern: str,
                       path: str | None = None,
                       glob: str | None = None,
                       ) -> list["GrepMatch"]:
        return await asyncio.to_thread(self.grep_raw, pattern, path, glob)

    def glob_info(self,
                  pattern: str,
                  path: str = "/",
                  ) -> list["FileInfo"]:
        """文件查找"""
        raise NotImplementedError

    async def aglob_info(self,
                         pattern: str,
                         path: str = "/",
                         ) -> list["FileInfo"]:
        return await asyncio.to_thread(self.glob_info, pattern, path)

    def write(self,
              file_path: str,
              content: str,
              ) -> WriteResult:
        """写入操作"""
        raise NotImplementedError

    async def awrite(self,
                     file_path: str,
                     content: str,
                     ) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(self,
             file_path: str,
             old_string: str,  # 查找的旧字符串
             new_string: str,  # 需要的新字符串
             replace_all: bool = False,  # 是否全部替换
             ) -> EditResult:
        """编辑操作"""
        raise NotImplementedError

    async def aedit(self,
                    file_path: str,
                    old_string: str,
                    new_string: str,
                    replace_all: bool = False,
                    ) -> EditResult:
        return await asyncio.to_thread(self.edit, file_path, old_string, new_string, replace_all)

    def upload_files(self,
                     files: list[tuple[str, bytes]],
                     ) -> list[FileUploadResponse]:
        """上传文件"""
        raise NotImplementedError

    async def aupload_files(self,
                            files: list[tuple[str, bytes]],
                            ) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)

    def download_file(self,
                      paths: list[str],
                      ) -> list[FileDownloadResponse]:
        """下载文件"""
        raise NotImplementedError

    async def adownload_file(self,
                             paths: list[str],
                             ) -> list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_file, paths)


class BackendFactory:
    pass
