"""POST /probe endpoint."""

from fastapi import APIRouter, Request

from app import ffmpeg
from app.files import delete_file
from app.models import ProbeResult
from app.openapi_common import ERROR_RESPONSES, FILE_REQUEST_BODY
from app.upload import receive_upload

router = APIRouter(tags=["Probe"])


@router.post(
    "/probe",
    operation_id="probeMedia",
    summary="Probe a media file",
    description=(
        "Returns the metadata of an audio, video or image file. The result is the same JSON "
        "as `ffprobe -of json -show_streams -show_format -show_chapters <file>`."
    ),
    response_model=ProbeResult,
    responses=ERROR_RESPONSES,
    openapi_extra=FILE_REQUEST_BODY,
)
async def probe(request: Request):
    upload = await receive_upload(request)
    try:
        return await ffmpeg.probe(upload.path)
    finally:
        delete_file(upload.path)
