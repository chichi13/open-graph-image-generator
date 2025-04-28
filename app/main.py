from app.app_setup import create_app
from app.config import settings
from app.logger import logger

app = create_app()

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting uvicorn directly from main.py")
    uvicorn.run(
        "app.main:app",
        host=settings.UVICORN_HOST,
        port=settings.UVICORN_PORT,
        reload=settings.UVICORN_RELOAD,
        log_level=(settings.LOGGING_LEVEL).lower(),
    )
