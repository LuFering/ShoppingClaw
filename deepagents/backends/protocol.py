import abc
import asyncio


class FileInfo:
    pass


class GrepMatch:
    pass


class WriteResult:
    pass


class EditResult:
    pass


class FileUploadResponse:
    pass


class FileDownloadResponse:
    pass


class BackendProtocol(abc.ABC):
    def ls_info(self, path: str) -> list["FileInfo"]:
        """从指定目录中列出所有带有metadata的文件"""
        raise NotImplementedError

    async def als_info(self, path: str) -> list["FileInfo"]:
        return await asyncio.to_thread(self.ls_info, path)

    def read(self,
             file_path: str,
             offset: int = 0,
             limit: int = 2000,
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
                 pattern: str,
                 path: str | None = None,
                 glob: str | None = None,
                 ) -> list["GrepMatch"]:
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
        raise NotImplementedError

    async def awrite(self,
                     file_path: str,
                     content: str,
                     ) -> WriteResult:
        return await asyncio.to_thread(self.write, file_path, content)

    def edit(self,
             file_path: str,
             old_string: str,
             new_string: str,
             replace_all: bool = False,
             ) -> EditResult:
        raise NotImplementedError

    async def aedit(self,
                    file_name: str,
                    old_string: str,
                    new_string: str,
                    replace_all: bool = False,
                    ) -> EditResult:
        return await asyncio.to_thread(self.edit, file_name, old_string, new_string, replace_all)

    def upload_files(self,
                     files: list[tuple[str, bytes]],
                     ) -> list[FileUploadResponse]:
        raise NotImplementedError

    async def aupload_files(self,
                            files: list[tuple[str, bytes]],
                            ) -> list[FileUploadResponse]:
        return await asyncio.to_thread(self.upload_files, files)
    def download_file(self,
                      paths:list[str],
                      )->list[FileDownloadResponse]:
        raise NotImplementedError

    async def adownload_file(self,
                             paths:list[str],
                             )->list[FileDownloadResponse]:
        return await asyncio.to_thread(self.download_file,paths)


class BackendFactory:
    pass
