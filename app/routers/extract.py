"""/video/extract endpoints: extract audio or images from a video."""

import asyncio
import tarfile
import zipfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi import Path as PathParam
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app import ffmpeg
from app.config import get_settings
from app.errors import ApiError
from app.files import DOWNLOADABLE_NAME, delete_file, new_id
from app.log import logger
from app.models import ExtractedImages
from app.openapi_common import ERROR_RESPONSES, FILE_REQUEST_BODY, binary_response
from app.upload import receive_upload

router = APIRouter(prefix="/video/extract", tags=["Extract"])


@router.post(
    "/audio",
    operation_id="extractAudio",
    summary="Extract the audio track of a video",
    description=(
        "Extracts the audio track of a video as a WAV file. By default the result is mono "
        "(1 channel). Use `mono=no` to keep all channels of the input."
    ),
    response_class=FileResponse,
    responses={**binary_response("audio/wav", "The WAV file."), **ERROR_RESPONSES},
    openapi_extra=FILE_REQUEST_BODY,
)
async def extract_audio(
    request: Request,
    mono: Annotated[
        str,
        Query(description="`yes` (default) or `true`: 1 channel. Any other value: all channels."),
    ] = "yes",
):
    upload = await receive_upload(request)
    output = get_settings().tmp_dir / f"{new_id()}.wav"
    options = ["-vn", "-f", "wav"]
    if mono.lower() in ("yes", "true"):
        logger.debug("extracting audio, 1 channel only")
        options += ["-ac", "1"]
    else:
        logger.debug("extracting audio, all channels")
    try:
        await ffmpeg.run_ffmpeg(upload.path, options, output)
    except BaseException:
        delete_file(output)
        raise
    finally:
        delete_file(upload.path)
    return FileResponse(
        output,
        media_type=ffmpeg.MEDIA_TYPES["wav"],
        filename=output.name,
        background=BackgroundTask(delete_file, output),
    )


def _archive(files: list[Path], target: Path, kind: str) -> None:
    if kind == "gzip":
        with tarfile.open(target, "w:gz", compresslevel=9) as tar:
            for f in files:
                tar.add(f, arcname=f.name)
    else:
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for f in files:
                zf.write(f, arcname=f.name)


@router.post(
    "/images",
    operation_id="extractImages",
    summary="Extract images (frames) from a video",
    description=(
        "Extracts frames of a video as PNG images, 1 frame per second by default.\n\n"
        "Without `compress` the response is JSON that lists a download URL for each image "
        "(see `GET /video/extract/download/{filename}`). With `compress=zip` or "
        "`compress=gzip` the response is a ZIP or tar.gz archive of all images."
    ),
    response_model=ExtractedImages,
    responses={
        200: {
            "description": "JSON list of images, or an archive when `compress` is used.",
            "content": {
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
                "application/gzip": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        **ERROR_RESPONSES,
    },
    openapi_extra=FILE_REQUEST_BODY,
)
async def extract_images(
    request: Request,
    fps: Annotated[
        float,
        Query(gt=0, description="Frames per second to extract. 0.5 is one image every 2 seconds."),
    ] = 1,
    compress: Annotated[
        Literal["zip", "gzip"] | None,
        Query(description="Return all images as a `zip` or `gzip` (tar.gz) archive."),
    ] = None,
):
    settings = get_settings()
    upload = await receive_upload(request)
    prefix = new_id()
    pattern = settings.tmp_dir / f"{prefix}-%04d.png"
    try:
        await ffmpeg.run_ffmpeg(upload.path, ["-vf", f"fps={fps}"], pattern)
    finally:
        delete_file(upload.path)
    files = sorted(settings.tmp_dir.glob(f"{prefix}-*.png"))

    if compress:
        extension = "tar.gz" if compress == "gzip" else "zip"
        archive = settings.tmp_dir / f"{prefix}.{extension}"
        logger.debug(f"starting {compress} process {archive}")
        try:
            await asyncio.to_thread(_archive, files, archive, compress)
        except BaseException:
            delete_file(archive)
            raise
        finally:
            for f in files:
                delete_file(f)
        return FileResponse(
            archive,
            media_type=ffmpeg.MEDIA_TYPES[extension],
            filename=archive.name,
            background=BackgroundTask(delete_file, archive),
        )

    port = settings.external_port
    base = f"{request.url.scheme}://{request.url.hostname}:{port}/video/extract/download"
    return ExtractedImages(
        totalfiles=len(files),
        description=(
            "Extracted image files and URLs to download them. By default, downloading image "
            "also deletes the image from server. Note that port "
            f"{port} in the URL may not be the same as the real port, especially if server is "
            "running on Docker/Kubernetes."
        ),
        files=[{"name": f.name, "url": f"{base}/{f.name}"} for f in files],
    )


@router.get(
    "/download/{filename}",
    operation_id="downloadExtractedFile",
    summary="Download an extracted image or archive",
    description=(
        "Downloads a file created by `POST /video/extract/images`. The file is deleted from "
        "the server after the download, unless `delete=no` is used."
    ),
    response_class=FileResponse,
    responses={
        200: {
            "description": "The file.",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
                "application/gzip": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        404: {"description": "No such file."},
    },
)
async def download(
    filename: Annotated[
        str,
        PathParam(
            description="File name from the extract images response.",
            examples=["ba0f565c-0001.png"],
        ),
    ],
    delete: Annotated[
        str, Query(description="`no` keeps the file on the server. Default is to delete it.")
    ] = "true",
):
    if not DOWNLOADABLE_NAME.match(filename):
        raise ApiError(404, "route not found")
    path = get_settings().tmp_dir / filename
    if not path.is_file():
        raise ApiError(404, "route not found")
    media_type = ffmpeg.MEDIA_TYPES[
        "png" if filename.endswith(".png") else "zip" if filename.endswith(".zip") else "tar.gz"
    ]
    task = BackgroundTask(delete_file, path) if delete.lower() in ("true", "yes") else None
    return FileResponse(path, media_type=media_type, filename=filename, background=task)
