"""API error type and the JSON error body used by every endpoint."""

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(description="Human readable error message.")

    model_config = {"json_schema_extra": {"examples": [{"error": "route not found"}]}}


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
