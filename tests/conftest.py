"""Shared fixtures. All media is generated with ffmpeg at test time, nothing is committed."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

HAS_FFMPEG = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None

requires_ffmpeg = pytest.mark.skipif(not HAS_FFMPEG, reason="ffmpeg/ffprobe not installed")


def pytest_collection_modifyitems(items):
    for item in items:
        if "media" in item.fixturenames or "client_media" in item.fixturenames:
            item.add_marker(pytest.mark.integration)
            item.add_marker(requires_ffmpeg)


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        stdin=subprocess.DEVNULL,
    )


def ffprobe(path: Path) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-of", "json", "-show_streams", "-show_format", str(path)],
        check=True,
        capture_output=True,
    ).stdout
    return json.loads(out)


@pytest.fixture(scope="session")
def media(tmp_path_factory) -> dict[str, Path]:
    """Tiny generated inputs: 3 s video+audio (MOV), stereo WAV, M4A, 64x64 TIFF."""
    d = tmp_path_factory.mktemp("media")
    files = {
        "video": d / "input.mov",
        "wav": d / "input.wav",
        "m4a": d / "input.m4a",
        "tiff": d / "input.tiff",
        "invalid": d / "invalid.bin",
    }
    _ffmpeg(
        "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        "-ac", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(files["video"]),
    )  # fmt: skip
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-ac", "2", str(files["wav"]))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=2", "-c:a", "aac", str(files["m4a"]))
    _ffmpeg("-f", "lavfi", "-i", "testsrc2=size=64x64:rate=1", "-frames:v", "1", str(files["tiff"]))
    files["invalid"].write_bytes(b"this is not media")
    return files


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Test client with an isolated temp directory."""
    monkeypatch.setenv("TMP_DIR", str(tmp_path))
    monkeypatch.setenv("EXTERNAL_PORT", "3000")
    monkeypatch.delenv("KEEP_ALL_FILES", raising=False)
    monkeypatch.delenv("FILE_SIZE_LIMIT_BYTES", raising=False)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_media(client):
    return client


def upload(path: Path, field: str = "file"):
    return {field: (path.name, path.read_bytes())}
