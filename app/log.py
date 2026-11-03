"""Logging in the same format as the original Node.js version: `<timestamp> LEVEL: message`."""

import logging

logger = logging.getLogger("ffmpeg-api")


def setup_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s: %(message)s"))
    logger.handlers[:] = [handler]
    logger.setLevel(level.upper() if level.upper() in logging._nameToLevel else "INFO")
    logger.propagate = False
