"""FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.errors import ApiError
from app.log import logger, setup_logging
from app.models import Endpoint
from app.routers import convert, extract, probe

STATIC_DIR = Path(__file__).parent / "static"
SWAGGER_DIR = STATIC_DIR / "swagger"

DESCRIPTION = """
Convert audio, video and image files with [FFmpeg](https://ffmpeg.org/) over HTTP.

* Upload a file as `multipart/form-data` (form field `file`, exactly one file).
* Conversion endpoints return the converted file as the response body.
* Extract endpoints return audio, images or an archive of images from a video.
* `POST /probe` returns the media metadata as JSON.

The service has no authentication. Run it in a trusted network or behind a reverse proxy.
"""

TAGS = [
    {"name": "Convert", "description": "Convert audio, video and image files."},
    {"name": "Extract", "description": "Extract audio and images from a video."},
    {"name": "Probe", "description": "Read media metadata."},
    {"name": "Service", "description": "Service information."},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)
    logger.info(
        f"ffmpeg-api {__version__} started, max upload {settings.file_size_limit_bytes} bytes"
    )
    yield


app = FastAPI(
    title="FFMPEG API",
    version=__version__,
    summary="REST API for converting audio, video and image files with FFmpeg.",
    description=DESCRIPTION,
    license_info={"name": "MIT", "identifier": "MIT"},
    contact={"name": "ffmpeg-api on GitHub", "url": "https://github.com/samisalkosuo/ffmpeg-api"},
    openapi_tags=TAGS,
    docs_url=None,  # served below from local files, so no CDN is needed
    redoc_url=None,
    lifespan=lifespan,
)

app.include_router(convert.router)
app.include_router(extract.router)
app.include_router(probe.router)

if SWAGGER_DIR.is_dir():
    app.mount("/static/swagger", StaticFiles(directory=SWAGGER_DIR), name="swagger")


@app.exception_handler(ApiError)
async def api_error_handler(_: Request, exc: ApiError):
    return JSONResponse({"error": exc.message}, status_code=exc.status_code)


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    message = "route not found" if exc.status_code == 404 else str(exc.detail)
    return JSONResponse({"error": message}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    details = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
    return JSONResponse({"error": details}, status_code=422)


@app.get("/docs", include_in_schema=False)
async def docs():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="FFMPEG API - Swagger UI",
        swagger_js_url="/static/swagger/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger/swagger-ui.css",
        swagger_favicon_url="/static/swagger/favicon-32x32.png",
    )


@app.get(
    "/endpoints",
    tags=["Service"],
    operation_id="listEndpoints",
    summary="List service endpoints",
    description="Returns the endpoints of the service as JSON.",
    response_model=list[Endpoint],
)
async def endpoints():
    result = [{"path": "/", "methods": ["GET"]}]
    for path, operations in app.openapi()["paths"].items():
        result.append({"path": path, "methods": sorted(m.upper() for m in operations)})
    return result


@app.get("/", include_in_schema=False, response_class=HTMLResponse)
async def index():
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get(
    "/health",
    tags=["Service"],
    operation_id="health",
    summary="Health check",
    description='Returns `{"status": "ok"}` when the service is running. '
    "Used by the container health check.",
    responses={200: {"content": {"application/json": {"example": {"status": "ok"}}}}},
)
async def health():
    return {"status": "ok"}
