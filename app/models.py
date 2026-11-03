"""Response models. They are also the source of the OpenAPI schemas."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExtractedImage(BaseModel):
    name: str = Field(
        description="File name of the extracted image.", examples=["ba0f565c-0001.png"]
    )
    url: str = Field(
        description="URL for downloading the image. Downloading deletes the image from the "
        "server unless `delete=no` is used.",
        examples=["http://127.0.0.1:3000/video/extract/download/ba0f565c-0001.png"],
    )


class ExtractedImages(BaseModel):
    totalfiles: int = Field(description="Number of extracted images.", examples=[5])
    description: str = Field(description="Human readable note about the download URLs.")
    files: list[ExtractedImage] = Field(description="Extracted images, in frame order.")


class ProbeResult(BaseModel):
    """Output of `ffprobe -of json -show_streams -show_format -show_chapters`."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "examples": [
                {
                    "streams": [
                        {
                            "index": 0,
                            "codec_name": "h264",
                            "codec_type": "video",
                            "width": 1280,
                            "height": 720,
                        },
                        {
                            "index": 1,
                            "codec_name": "aac",
                            "codec_type": "audio",
                            "sample_rate": "48000",
                            "channels": 2,
                        },
                    ],
                    "chapters": [],
                    "format": {
                        "filename": "/tmp/5f69ae62-input.mov",
                        "nb_streams": 2,
                        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                        "duration": "60.056000",
                        "size": "13379040",
                        "bit_rate": "1782208",
                    },
                }
            ]
        },
    )

    streams: list[dict[str, Any]] = Field(default_factory=list, description="One entry per stream.")
    chapters: list[dict[str, Any]] = Field(default_factory=list, description="Chapters, if any.")
    format: dict[str, Any] = Field(default_factory=dict, description="Container information.")


class Endpoint(BaseModel):
    path: str = Field(examples=["/convert/audio/to/mp3"])
    methods: list[str] = Field(examples=[["POST"]])
