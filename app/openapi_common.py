"""Shared OpenAPI pieces for the routers."""

from typing import Any

from app.errors import ErrorResponse

# The upload is parsed by app.upload (streamed to disk), so the multipart request body
# is described explicitly here for the OpenAPI document and Swagger "Try it out".
FILE_REQUEST_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "description": "Multipart form with exactly one file. Non-file fields are rejected.",
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "file": {
                            "type": "string",
                            "format": "binary",
                            "description": "Any file that FFmpeg can read.",
                        }
                    },
                    "required": ["file"],
                }
            }
        },
    }
}

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorResponse,
        "description": "Bad request: not a multipart upload, no file, or a non-file field.",
    },
    413: {"model": ErrorResponse, "description": "File is larger than FILE_SIZE_LIMIT_BYTES."},
    422: {"model": ErrorResponse, "description": "Invalid query parameter."},
    500: {
        "model": ErrorResponse,
        "description": "FFmpeg failed, for example because the input is not valid media.",
    },
}


def binary_response(media_type: str, description: str) -> dict[int | str, dict[str, Any]]:
    return {
        200: {
            "description": description,
            "content": {media_type: {"schema": {"type": "string", "format": "binary"}}},
        }
    }
