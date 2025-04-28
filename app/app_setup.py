from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.endpoints import api_router
from app.config import settings
from app.logger import logger


def create_app() -> FastAPI:
    """Creates and configures the FastAPI application instance."""
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.APP_VERSION,
        docs_url=None if settings.is_prod() else "/docs",
        redoc_url=None if settings.is_prod() else "/redoc",
        openapi_url=("/openapi.json" if not settings.is_prod() else None),
    )

    setup_middlewares(app)
    setup_routers(app)
    return app


def setup_routers(app: FastAPI) -> None:
    """Includes API routers in the application."""
    logger.info("Setting up routers")

    app.include_router(api_router)


def setup_middlewares(app: FastAPI) -> None:
    """Configures application middlewares."""
    logger.info("Setting up middlewares")

    if settings.BACKEND_CORS_ORIGINS:
        logger.info(f"Allowed CORS origins: {settings.BACKEND_CORS_ORIGINS}")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        logger.info("No CORS origins configured.")
