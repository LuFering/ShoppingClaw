"""只读 Backend 包装 —— 拦掉所有写操作。

背景（PR #7 review 跟进项 1）：
  planning agent 通过 CompositeBackend 把 `/skills/` 路由到真实源码目录后，
  FilesystemMiddleware 同时暴露 write_file / edit_file，实测能改写源码里的
  SKILL.md。商品标题等第三方数据可能诱导模型写入（跨会话提示注入）。
  故在 common 层加这层包装：读操作原样转发，写操作返回可读错误（不抛异常，
  避免 agent 崩溃），mainagent 主/子接线同样适用。

用法：
  CompositeBackend(
      default=StateBackend(runtime),
      routes={"/skills/": ReadOnlyBackend(FilesystemBackend(...))},
  )
"""

from __future__ import annotations

from .protocol import BackendProtocol, EditResult, FileUploadResponse, WriteResult

_ERR = "permission denied: backend is read-only"


class ReadOnlyBackend(BackendProtocol):
    """只读包装：读操作转发给 inner，写操作一律拒绝。"""

    def __init__(self, inner: BackendProtocol) -> None:
        self._inner = inner

    # ── 读：原样转发 ──

    def ls_info(self, path: str):
        return self._inner.ls_info(path)

    async def als_info(self, path: str):
        return await self._inner.als_info(path)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return self._inner.read(file_path, offset, limit)

    async def aread(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        return await self._inner.aread(file_path, offset, limit)

    def grep_raw(self, pattern: str, path: str | None = None, glob: str | None = None):
        return self._inner.grep_raw(pattern, path, glob)

    async def agrep_raw(self, pattern: str, path: str | None = None, glob: str | None = None):
        return await self._inner.agrep_raw(pattern, path, glob)

    def glob_info(self, pattern: str, path: str = "/"):
        return self._inner.glob_info(pattern, path)

    async def aglob_info(self, pattern: str, path: str = "/"):
        return await self._inner.aglob_info(pattern, path)

    def download_files(self, paths: list[str]):
        return self._inner.download_files(paths)

    async def adownload_files(self, paths: list[str]):
        return await self._inner.adownload_files(paths)

    def id(self) -> str:
        return "readonly"

    # ── 写：拒绝（返回 error，不抛异常） ──

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_ERR, path=None, files_update=None)

    async def awrite(self, file_path: str, content: str) -> WriteResult:
        return self.write(file_path, content)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return EditResult(error=_ERR, path=None, files_update=None, occurrences=None)

    async def aedit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        return self.edit(file_path, old_string, new_string, replace_all)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=p, error="permission_denied") for p, _ in files]

    async def aupload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return self.upload_files(files)
