import logging
import sys

from app.config import settings

log_formatter = logging.Formatter(
    "%(levelname)s: %(asctime)s - %(name)s - %(module)s:%(lineno)d - %(funcName)s - %(message)s"
)

logger = logging.getLogger("py_og_image_service")
logger.setLevel(settings.LOGGING_LEVEL.upper())

if not logger.handlers:
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    logger.addHandler(stream_handler)
