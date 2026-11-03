"""POST /convert/... endpoints."""

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app import ffmpeg
from app.config import get_settings
from app.files import delete_file, new_id
from app.log import logger
from app.openapi_common import ERROR_RESPONSES, FILE_REQUEST_BODY, binary_response
from app.upload import receive_upload

router = APIRouter(prefix="/convert", tags=["Convert"])


async def _convert(request: Request, fmt: str) -> FileResponse:
    upload = await receive_upload(request)
    output = get_settings().tmp_dir / f"{new_id()}-output.{fmt}"
    logger.debug(f"begin conversion from {upload.path} to {output}")
    try:
        await ffmpeg.convert(upload.path, fmt, output)
    except BaseException:
        delete_file(output)
        raise
    finally:
        delete_file(upload.path)
    return FileResponse(
        output,
        media_type=ffmpeg.MEDIA_TYPES[fmt],
        filename=f"{Path(upload.filename).stem}.{fmt}",
        background=BackgroundTask(delete_file, output),
    )


@router.post(
    "/audio/to/mp3",
    operation_id="convertAudioToMp3",
    summary="Convert audio to MP3",
    description="Converts an audio file to MP3 with the `libmp3lame` encoder.",
    response_class=FileResponse,
    responses={**binary_response("audio/mpeg", "The MP3 file."), **ERROR_RESPONSES},
    openapi_extra=FILE_REQUEST_BODY,
)
async def audio_to_mp3(request: Request):
    return await _convert(request, "mp3")


@router.post(
    "/audio/to/wav",
    operation_id="convertAudioToWav",
    summary="Convert audio to WAV",
    description="Converts an audio file to 16-bit PCM WAV.",
    response_class=FileResponse,
    responses={**binary_response("audio/wav", "The WAV file."), **ERROR_RESPONSES},
    openapi_extra=FILE_REQUEST_BODY,
)
async def audio_to_wav(request: Request):
    return await _convert(request, "wav")


@router.post(
    "/video/to/mp4",
    operation_id="convertVideoToMp4",
    summary="Convert video to MP4",
    description=(
        "Converts a video file to a small web friendly MP4: H.264 (high profile), 15 fps, "
        "height 640, about 500 kbit/s, and AAC audio at 128 kbit/s."
    ),
    response_class=FileResponse,
    responses={**binary_response("video/mp4", "The MP4 file."), **ERROR_RESPONSES},
    openapi_extra=FILE_REQUEST_BODY,
)
async def video_to_mp4(request: Request):
    return await _convert(request, "mp4")


@router.post(
    "/image/to/jpg",
    operation_id="convertImageToJpg",
    summary="Convert image to JPG",
    description="Converts an image file (for example TIFF or PNG) to JPG.",
    response_class=FileResponse,
    responses={**binary_response("image/jpeg", "The JPG file."), **ERROR_RESPONSES},
    openapi_extra=FILE_REQUEST_BODY,
)
async def image_to_jpg(request: Request):
    return await _convert(request, "jpg")
