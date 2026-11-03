"""Runtime configuration, read from environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

SERVER_PORT = 3000
FFMPEG_NICE = 10
# Uploads and conversions can take a long time, keep connections open for one hour.
CONNECTION_TIMEOUT_SECONDS = 3600


@dataclass(frozen=True)
class Settings:
    file_size_limit_bytes: int
    external_port: int
    keep_all_files: bool
    log_level: str
    tmp_dir: Path


def get_settings() -> Settings:
    """Read settings from the environment on every call, so tests can change them."""
    return Settings(
        file_size_limit_bytes=int(os.environ.get("FILE_SIZE_LIMIT_BYTES") or 536870912),
        external_port=int(os.environ.get("EXTERNAL_PORT") or SERVER_PORT),
        keep_all_files=os.environ.get("KEEP_ALL_FILES", "false").strip().lower()
        in ("true", "yes", "1"),
        log_level=os.environ.get("LOG_LEVEL", "info").strip().lower(),
        tmp_dir=Path(os.environ.get("TMP_DIR") or "/tmp"),
    )
