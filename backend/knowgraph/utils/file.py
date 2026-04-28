import os
import re
from base64 import b64decode, b64encode
from collections.abc import Buffer
from hashlib import sha256
from io import BytesIO
from mimetypes import guess_extension
from os import PathLike
from pathlib import Path
from typing import Literal, Self, overload
from urllib.parse import quote
from uuid import UUID, uuid7

from anyio import Path as AsyncPath
from asyncer import asyncify, syncify
from fastapi import HTTPException, UploadFile
from httpx import URL, AsyncClient, Client
from magika import Magika
from pydantic import UUID7, BaseModel, ConfigDict
from starlette.responses import StreamingResponse

from .environments import TMP_DIR


class FileStream(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    stream: BytesIO
    file_hash: str
    base_name: str = ""
    mimetype: str = ""
    extension: str = ""
    size: int = 0
    file_type: Literal["document", "image", "video", "audio", "text", "binary"] = "document"
    file_id: UUID7

    def __init__(
        self,
        name: str,
        stream: BytesIO | Buffer | str,
        file_hash: str | None = None,
        file_type: Literal["document", "image", "video", "audio", "text", "binary"] = "document",
        file_id: UUID | None = None,
    ) -> None:
        if file_id is None:
            file_id = uuid7()
        name = re.sub(r"\s", "_", name)
        name = name.replace(" ", "_")
        base_name = Path(name).stem
        if isinstance(stream, str):
            stream = BytesIO(stream.encode("utf-8"))
        elif isinstance(stream, Buffer):
            stream = BytesIO(stream)
        if not (
            file_hash
            and isinstance(file_hash, str)
            and len(file_hash) == 64
            and re.fullmatch(r"[0-9a-fA-F]{64}", file_hash)
        ):
            file_hash = sha256(stream.getvalue()).hexdigest()
        else:
            file_hash = file_hash.lower()
        super().__init__(name=name, stream=stream, file_hash=file_hash, file_type=file_type, file_id=file_id)
        self._detect_mime_and_ext()
        self.base_name = base_name
        self.name = f"{base_name}{self.extension}"
        self.file_hash = file_hash
        stream.seek(0, os.SEEK_END)
        self.size = stream.tell()
        stream.seek(0)

    def _detect_mime_and_ext(self) -> None:
        name = self.name
        stream = self.stream

        orig_ext = Path(name).suffix.lower()
        magika = Magika()
        magika_result = magika.identify_bytes(stream.getvalue()).output
        exts = magika_result.extensions
        exts = [f".{ext.lower()}" for ext in exts]
        self.mimetype = magika_result.mime_type
        if self.mimetype == "application/wps-office.docx":
            self.mimetype = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        elif self.mimetype == "application/wps-office.xlsx":
            self.mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif self.mimetype == "application/wps-office.pptx":
            self.mimetype = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

        if orig_ext in exts:
            self.extension = orig_ext
        else:
            self.extension = exts[0]
        if magika_result.group in {"image", "video", "audio", "text", "document", "binary"}:
            self.file_type = magika_result.group  # type: ignore
        elif self.mimetype.startswith("image/"):
            self.file_type = "image"
        elif self.mimetype.startswith("video/"):
            self.file_type = "video"
        elif self.mimetype.startswith("audio/"):
            self.file_type = "audio"
        elif self.mimetype.startswith("text/"):
            self.file_type = "text"
        elif self.extension in {
            ".pdf",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
            ".xls",
            ".xlsx",
            ".odt",
            ".odp",
            ".ods",
        }:
            self.file_type = "document"
        else:
            self.file_type = "binary"

    @classmethod
    async def afrom_request(cls, file: UploadFile) -> Self:
        if file.filename is None:
            return cls(name="unnamed_file", stream=await file.read())
        return cls(name=file.filename, stream=await file.read())

    async def ato_response(self) -> StreamingResponse:
        headers = {
            "Content-Length": str(self.size),
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(self.name, safe='')}",
        }
        return StreamingResponse(
            content=self.stream,
            media_type=self.mimetype,
            headers=headers,
        )

    @classmethod
    def from_url(cls, url: str | URL) -> Self:
        url = URL(url)
        with Client() as client:
            response = client.get(url)
        if response.status_code != 200:
            msg = f"Failed to fetch file from {url}. Status code: {response.status_code}"
            raise ValueError(msg)
        content = response.content
        name = url.path.split("/")[-1] or "downloaded_file"
        return cls(name=name, stream=BytesIO(content))

    @classmethod
    async def afrom_url(cls, url: URL) -> Self:
        url = URL(url)
        async with AsyncClient() as client:
            response = await client.get(url)
        if response.status_code != 200:
            msg = f"Failed to fetch file from {url}. Status code: {response.status_code}"
            raise ValueError(msg)
        content = response.content
        name = url.path.split("/")[-1] or "downloaded_file"
        return cls(name=name, stream=BytesIO(content))

    @classmethod
    def from_path(cls, path: PathLike) -> Self:
        path = Path(path)
        if not path.is_file():
            msg = f"{path} is not a valid file."
            raise ValueError(msg)
        content = path.read_bytes()
        return cls(name=path.name, stream=BytesIO(content))

    @classmethod
    async def afrom_path(cls, path: PathLike) -> Self:
        path = AsyncPath(path)
        if not await path.is_file():
            msg = f"{path} is not a valid file."
            raise ValueError(msg)
        content = await path.read_bytes()
        return cls(name=path.name, stream=BytesIO(content))

    @classmethod
    def from_base64(cls, name: str, code: str) -> Self:
        try:
            content = b64decode(code)
        except Exception as e:
            msg = f"Invalid Base64 string: {e}"
            raise ValueError(msg) from e
        return cls(name=name, stream=BytesIO(content))

    @classmethod
    def from_data_uri(cls, data_uri: str, name: str | None = None) -> Self:
        match = re.match(r"data:(.*?);base64,(.*)", data_uri)
        if not match:
            msg = "Invalid Data URI format."
            raise ValueError(msg)
        mimetype, base64_str = match.groups()
        try:
            content = b64decode(base64_str)
        except Exception as e:
            msg = f"Invalid Base64 string in Data URI: {e}"
            raise ValueError(msg) from e
        extension = guess_extension(mimetype) or ""
        name = name or f"file{extension}"
        return cls(name=name, stream=BytesIO(content))

    def to_base64(self) -> str:
        return b64encode(self.stream.getvalue()).decode(encoding="utf-8")

    def to_data_uri(self) -> str:
        base64_str = self.to_base64()
        return f"data:{self.mimetype};base64,{base64_str}"

    def to_path(self, dir_path: PathLike | None = None) -> Path:
        if dir_path is None:
            dir_path = TMP_DIR / uuid7().hex[:8]
        else:
            dir_path = Path(dir_path)
        path = dir_path / self.name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(self.stream.getvalue())
        return path

    async def ato_path(self, dir_path: PathLike | None = None) -> AsyncPath:
        base_dir = AsyncPath(TMP_DIR / uuid7().hex[:8]) if dir_path is None else AsyncPath(dir_path)
        path = AsyncPath(base_dir) / self.name
        await path.parent.mkdir(parents=True, exist_ok=True)
        await path.write_bytes(self.stream.getvalue())
        return path

    ato_base64 = asyncify(to_base64)
    afrom_base64 = asyncify(from_base64)
    to_response = syncify(ato_response, raise_sync_error=False)
    from_request = syncify(afrom_request, raise_sync_error=False)


@overload
def get_cache_file_path(file_path: str, async_mode: Literal[False]) -> Path: ...
@overload
def get_cache_file_path(file_path: str, async_mode: Literal[True]) -> AsyncPath: ...
def get_cache_file_path(file_path: str, async_mode: bool = False) -> Path | AsyncPath:
    file_path_obj = Path(file_path)
    if file_path_obj.is_absolute():
        raise HTTPException(status_code=400, detail="Invalid file path.")
    full_path = (TMP_DIR / file_path_obj).resolve()
    if not str(full_path).startswith(str(TMP_DIR.resolve())):
        raise HTTPException(status_code=400, detail="Invalid file path.")
    if async_mode:
        return AsyncPath(full_path)
    return full_path
