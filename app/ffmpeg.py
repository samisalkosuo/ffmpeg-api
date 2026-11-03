"""Thin async wrapper around the ffmpeg and ffprobe command line tools."""

import asyncio
import json
import os
import sys
from pathlib import Path

from app.config import FFMPEG_NICE
from app.errors import ApiError
from app.log import logger

# Output options per conversion, same as the original Node.js version.
# The only change is MP4 audio: libfdk_aac is non-free and not part of the image,
# so FFmpeg's native AAC encoder is used instead.
CONVERSIONS: dict[str, list[str]] = {
    "mp3": ["-codec:a", "libmp3lame"],
    "wav": ["-codec:a", "pcm_s16le"],
    "mp4": [
        "-codec:v",
        "libx264",
        "-profile:v",
        "high",
        "-r",
        "15",
        "-crf",
        "23",
        "-preset",
        "ultrafast",
        "-b:v",
        "500k",
        "-maxrate",
        "500k",
        "-bufsize",
        "1000k",
        "-vf",
        "scale=-2:640",
        "-threads",
        "8",
        "-codec:a",
        "aac",
        "-b:a",
        "128k",
    ],
    "jpg": ["-pix_fmt", "yuv422p"],
}

MEDIA_TYPES = {
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "mp4": "video/mp4",
    "jpg": "image/jpeg",
    "png": "image/png",
    "zip": "application/zip",
    "tar.gz": "application/gzip",
}


async def _run(args: list[str]) -> tuple[bytes, bytes]:
    logger.debug("running: " + " ".join(args))
    kwargs = {}
    if sys.platform != "win32":
        kwargs["preexec_fn"] = lambda: os.nice(FFMPEG_NICE)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            **kwargs,
        )
    except FileNotFoundError as exc:
        raise ApiError(500, f"{args[0]} is not installed") from exc
    try:
        stdout, stderr = await proc.communicate()
    except asyncio.CancelledError:  # client disconnected, do not leave ffmpeg running
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace").strip().splitlines()[-5:]
        raise ApiError(500, f"{args[0]} exited with code {proc.returncode}: " + " | ".join(tail))
    return stdout, stderr


async def run_ffmpeg(input_file: Path, output_options: list[str], output: Path) -> None:
    await _run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(input_file),
            *output_options,
            str(output),
        ]
    )


async def convert(input_file: Path, fmt: str, output: Path) -> None:
    await run_ffmpeg(input_file, CONVERSIONS[fmt], output)


async def probe(input_file: Path) -> dict:
    stdout, _ = await _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-of",
            "json",
            "-show_streams",
            "-show_format",
            "-show_chapters",
            str(input_file),
        ]
    )
    return json.loads(stdout)
