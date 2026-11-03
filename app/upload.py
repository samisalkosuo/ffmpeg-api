"""Streaming multipart upload handling.

The body is parsed chunk by chunk and written straight to a temporary file, so a large
upload is never held in memory. Rules (same as the original Node.js version):

* exactly one file is used, additional files are ignored
* non-file form fields are rejected with 400
* files above FILE_SIZE_LIMIT_BYTES are rejected
"""

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request
from python_multipart.multipart import MultipartParser, parse_options_header

from app.config import get_settings
from app.errors import ApiError
from app.files import delete_file, new_id, safe_filename
from app.log import logger


@dataclass
class Upload:
    path: Path
    filename: str


class _Collector:
    def __init__(self, tmp_dir: Path, limit: int):
        self.tmp_dir = tmp_dir
        self.limit = limit
        self.upload: Upload | None = None
        self.error: ApiError | None = None
        self.bytes = 0
        self._handle = None
        self._active = False  # current part is the file being saved
        self._header_name = b""
        self._header_value = b""
        self._headers: dict[bytes, bytes] = {}

    # --- callbacks used by python-multipart -------------------------------------------------
    def on_part_begin(self):
        self._headers = {}
        self._active = False

    def on_header_field(self, data, start, end):
        self._header_name += data[start:end]

    def on_header_value(self, data, start, end):
        self._header_value += data[start:end]

    def on_header_end(self):
        self._headers[self._header_name.lower()] = self._header_value
        self._header_name = b""
        self._header_value = b""

    def on_headers_finished(self):
        if self.error:
            return
        _, params = parse_options_header(self._headers.get(b"content-disposition", b""))
        filename = params.get(b"filename")
        if filename is None:
            self.error = ApiError(400, "Non-file field detected. Only files can be POSTed.")
            return
        if self.upload is not None:
            return  # only the first file is used, ignore the rest
        name = safe_filename(filename.decode("utf-8", errors="replace"))
        path = self.tmp_dir / f"{new_id()}-{name}"
        self.upload = Upload(path=path, filename=name)
        self._handle = path.open("wb")
        self._active = True
        logger.debug(f"uploading {name} to {path}")

    def on_part_data(self, data, start, end):
        if not self._active or self.error:
            return
        self.bytes += end - start
        if self.bytes > self.limit:
            name = self.upload.filename if self.upload else "file"
            self.error = ApiError(
                413, f"{name} exceeds max size limit. max file size {self.limit} bytes."
            )
            return
        self._handle.write(data[start:end])

    def on_part_end(self):
        if self._active and self._handle:
            self._handle.close()
            self._handle = None
        self._active = False

    def close(self):
        if self._handle:
            self._handle.close()
            self._handle = None


async def receive_upload(request: Request) -> Upload:
    """FastAPI dependency: save the uploaded file to the temp directory and return it."""
    settings = get_settings()
    content_type = request.headers.get("content-type", "")
    ctype, params = parse_options_header(content_type)
    boundary = params.get(b"boundary")
    if ctype != b"multipart/form-data" or not boundary:
        raise ApiError(400, "Request must be multipart/form-data with a file.")

    collector = _Collector(settings.tmp_dir, settings.file_size_limit_bytes)
    parser = MultipartParser(
        boundary,
        {
            "on_part_begin": collector.on_part_begin,
            "on_header_field": collector.on_header_field,
            "on_header_value": collector.on_header_value,
            "on_header_end": collector.on_header_end,
            "on_headers_finished": collector.on_headers_finished,
            "on_part_data": collector.on_part_data,
            "on_part_end": collector.on_part_end,
        },
    )
    try:
        async for chunk in request.stream():
            parser.write(chunk)
            if collector.error:
                break
        parser.finalize()
    except Exception as exc:  # malformed multipart body
        collector.close()
        if collector.upload:
            delete_file(collector.upload.path)
        if isinstance(exc, ApiError):
            raise
        raise ApiError(400, f"Invalid multipart body: {exc}") from exc
    collector.close()

    if collector.error:
        if collector.upload:
            delete_file(collector.upload.path)
        logger.error(collector.error.message)
        raise collector.error
    if collector.upload is None:
        raise ApiError(400, "No file in request. POST a multipart form with a file.")
    logger.debug(f"upload complete. file: {collector.upload.filename}, bytes: {collector.bytes}")
    return collector.upload
