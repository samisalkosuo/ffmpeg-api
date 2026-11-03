"""Run the server: `python -m app`."""

import uvicorn

from app.config import CONNECTION_TIMEOUT_SECONDS, SERVER_PORT

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # noqa: S104 - container service
        port=SERVER_PORT,
        timeout_keep_alive=CONNECTION_TIMEOUT_SECONDS,
        log_level="warning",
    )
