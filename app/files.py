"""Temporary file helpers."""

import re
import uuid
from pathlib import Path

from app.config import get_settings
from app.log import logger

# Names produced by the image extraction endpoint: <8 hex>-0001.png, <8 hex>.zip, <8 hex>.tar.gz
DOWNLOADABLE_NAME = re.compile(r"^[0-9a-f]{8}(-\d{4}\.png|\.zip|\.tar\.gz)$")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def safe_filename(name: str) -> str:
    """Keep only the file name part and replace characters that are unsafe in paths."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).lstrip(".")
    return base or "upload"


def delete_file(path: Path) -> None:
    """Delete a file unless KEEP_ALL_FILES is set."""
    if get_settings().keep_all_files:
        logger.debug(f"NOT deleted {path}")
        return
    try:
        path.unlink()
        logger.debug(f"deleted {path}")
    except FileNotFoundError:
        pass
