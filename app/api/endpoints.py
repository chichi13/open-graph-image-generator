from datetime import datetime, timedelta, timezone
from typing import Optional, Union
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from app import database
from app.api.crud import get_screenshot_record
from app.api.utils import (
    DomainValidationError,
    check_cache,
    create_db_record,
    create_error_response,
    dispatch_celery_task,
    find_existing_record,
    poll_task_completion,
    run_sync_generation,
    update_cache,
    validate_domain,
)
from app.config import settings
from app.logger import logger
from app.models.api_models import (
    CachedResponse,
    ErrorResponse,
    ProcessingResponse,
    StatusResponse,
)
from app.models.db_models import ScreenshotStatus
from app.templating import templates

api_router = APIRouter()


@api_router.get(
    "/generate",
    response_model=Union[ProcessingResponse, CachedResponse],
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        status.HTTP_200_OK: {
            "model": CachedResponse,
            "description": "Image found in cache or DB (returned with 202 status)",
        },
        status.HTTP_202_ACCEPTED: {
            "model": ProcessingResponse,
            "description": "Image generation started",
        },
        status.HTTP_400_BAD_REQUEST: {"model": ErrorResponse},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"model": ErrorResponse},
    },
)
async def generate_og_image(
    request: Request,
    url: HttpUrl = Query(..., description="URL to capture"),
    ttl: int | None = Query(
        None, description="Cache validity duration in hours (defaults to config)"
    ),
    width: int | None = Query(1200, description="Screenshot width in pixels"),
    height: int | None = Query(630, description="Screenshot height in pixels"),
    force_refresh: bool = Query(
        False, description="Force regeneration even if cache is valid"
    ),
    db: Session = Depends(database.get_db),
):
    """Handles request to generate or retrieve a cached OG image."""
    logger.info(f"Received generation request for URL: {url}, Force: {force_refresh}")

    request_width = width if width is not None else 1200
    request_height = height if height is not None else 630

    # --- Domain Validation ---
    try:
        validate_domain(url)
    except DomainValidationError as e:
        return create_error_response(status.HTTP_400_BAD_REQUEST, str(e))
    except Exception as e:
        logger.error(f"Unexpected validation error for {url}: {e}", exc_info=True)
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal validation error"
        )

    # --- Cache Check ---
    cache_key = f"og_image:{url}:{request_width}:{request_height}"
    if not force_refresh:
        cached_data = check_cache(cache_key)
        if cached_data:
            return CachedResponse(status="cached", image_url=cached_data["s3_url"])

    now_utc = datetime.now(timezone.utc)
    ttl_seconds = (ttl * 3600) if ttl is not None else settings.SCREENSHOT_DEFAULT_TTL
    future_expiry_time = now_utc + timedelta(seconds=ttl_seconds)

    # --- Database Check ---
    existing_record = find_existing_record(db, str(url))

    if existing_record and not force_refresh:
        if (
            existing_record.status == ScreenshotStatus.COMPLETED
            and existing_record.expires_at > now_utc
        ):
            logger.info(
                f"Found valid COMPLETED record in DB for {url}: {existing_record.id}"
            )
            if existing_record.s3_path:
                update_cache(
                    cache_key, existing_record.s3_path, existing_record.expires_at
                )
                return CachedResponse(
                    status="cached", image_url=existing_record.s3_path
                )
            else:
                logger.warning(
                    f"DB record {existing_record.id} has status COMPLETED but no s3_path. Treating as expired/failed."
                )

        elif (
            existing_record.status
            in [ScreenshotStatus.PENDING, ScreenshotStatus.PROCESSING]
            and existing_record.expires_at > now_utc
        ):
            logger.info(
                f"Found PENDING/PROCESSING record in DB for {url}: {existing_record.id}"
            )
            status_url = request.url_for(
                "get_task_status", task_id=str(existing_record.id)
            )
            return ProcessingResponse(
                status="processing",
                task_id=existing_record.id,
                check_status_url=str(status_url),
            )
        else:
            logger.info(
                f"Existing record {existing_record.id} found but is failed or expired. Will generate new."
            )

    # --- Create New Record and Trigger Generation ---
    logger.info(
        f"No valid cached/DB record, or refresh forced for {url}. Processing..."
    )
    try:
        new_record = create_db_record(db, str(url), future_expiry_time)
    except HTTPException as http_exc:  # Catch DB errors from create_db_record
        return create_error_response(http_exc.status_code, http_exc.detail)
    except Exception as e:  # Catch unexpected errors
        logger.error(
            f"Unexpected error creating DB record for {url}: {e}", exc_info=True
        )
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, "Failed to initiate generation"
        )

    # --- Execute Synchronously or Asynchronously ---
    try:
        if settings.CELERY_ENABLED:
            dispatch_celery_task(new_record.id, str(url), request_width, request_height)
            status_url = request.url_for("get_task_status", task_id=str(new_record.id))
            return ProcessingResponse(
                status="processing",
                task_id=new_record.id,
                check_status_url=str(status_url),
            )
        else:
            s3_url = run_sync_generation(
                new_record.id,
                str(url),
                request_width,
                request_height,
                cache_key,
                future_expiry_time,
            )
            return CachedResponse(status="generated", image_url=s3_url)

    except HTTPException as http_exc:  # Catch errors from dispatch_celery_task
        return create_error_response(http_exc.status_code, http_exc.detail)
    except Exception as exc:  # Catch errors from run_sync_generation
        logger.error(
            f"Generation process failed for {new_record.id}: {exc}", exc_info=True
        )
        return create_error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Generation failed: {exc}"
        )


@api_router.get("/status/{task_id}", response_model=StatusResponse)
async def get_task_status(task_id: UUID, db: Session = Depends(database.get_db)):
    """Gets the status of a screenshot generation task."""
    record = await get_screenshot_record(task_id, db)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Task/Record not found"
        )

    return StatusResponse(
        status=record.status,
        image_url=(
            record.s3_path if record.status == ScreenshotStatus.COMPLETED else None
        ),
        error_message=(
            record.error_message if record.status == ScreenshotStatus.FAILED else None
        ),
    )


@api_router.get("/image/{image_id}", status_code=status.HTTP_307_TEMPORARY_REDIRECT)
async def get_image(image_id: UUID, db: Session = Depends(database.get_db)):
    """Gets the actual image file by redirecting to its S3 URL."""
    record = await get_screenshot_record(image_id, db)
    if not record or record.status != ScreenshotStatus.COMPLETED or not record.s3_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Image not found, not ready, or URL missing",
        )

    return RedirectResponse(url=record.s3_path)


@api_router.get("/", response_class=HTMLResponse)
async def root_handler(
    request: Request,
    url: Optional[HttpUrl] = Query(None, description="URL to generate screenshot for"),
    ttl: int | None = Query(
        None, description="Cache validity duration in hours (defaults to config)"
    ),
    width: int | None = Query(1200, description="Screenshot width in pixels"),
    height: int | None = Query(630, description="Screenshot height in pixels"),
    force_refresh: bool = Query(
        False, description="Force regeneration even if cache is valid"
    ),
    db: Session = Depends(database.get_db),
):
    """Handles root requests. Shows info page or generates/redirects to image."""
    if not url:
        logger.info("Serving root info page.")
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "default_ttl_hours": settings.SCREENSHOT_DEFAULT_TTL // 3600,
            },
        )

    logger.info(f"Root request to generate image for: {url}, Force: {force_refresh}")

    request_width = width if width is not None else 1200
    request_height = height if height is not None else 630

    # --- Domain Validation ---
    try:
        validate_domain(url)
    except DomainValidationError as e:
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>URL validation failed: {str(e)}</p></body></html>",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    except Exception as e:
        logger.error(f"Unexpected root validation error for {url}: {e}", exc_info=True)
        return HTMLResponse(
            content="<html><body><h1>Error</h1><p>Internal validation error.</p></body></html>",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    cache_key = f"og_image:{url}:{request_width}:{request_height}"
    now_utc = datetime.now(timezone.utc)
    ttl_seconds = (ttl * 3600) if ttl is not None else settings.SCREENSHOT_DEFAULT_TTL
    future_expiry_time = now_utc + timedelta(seconds=ttl_seconds)

    # --- 1. Check Cache ---
    if not force_refresh:
        cached_data = check_cache(cache_key)
        if cached_data and cached_data.get("s3_url"):
            logger.info(f"Cache hit for {url} via root.")
            return RedirectResponse(
                url=cached_data["s3_url"],
                status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            )

    # --- 2. Check DB ---
    task_id_to_poll = None
    record = None
    if not force_refresh:
        record = find_existing_record(db, str(url))

    if record:
        if record.status == ScreenshotStatus.COMPLETED and record.expires_at > now_utc:
            logger.info(f"DB hit (completed) for {url} via root.")
            if record.s3_path:
                update_cache(cache_key, record.s3_path, record.expires_at)
                return RedirectResponse(
                    url=record.s3_path, status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )
            else:
                logger.warning(
                    f"Root found completed record {record.id} without s3_path."
                )
        elif (
            record.status in [ScreenshotStatus.PENDING, ScreenshotStatus.PROCESSING]
            and record.expires_at > now_utc
        ):
            logger.info(
                f"DB hit (pending/processing) for {url} via root. Task ID: {record.id}"
            )
            if settings.CELERY_ENABLED:
                task_id_to_poll = record.id
            else:
                logger.warning(
                    f"Found pending/processing record {record.id} in sync mode via root. Generating new."
                )
                record = None  # Force generation below
        else:
            logger.info(
                f"Found failed/expired record {record.id} via root. Generating new."
            )
            record = None  # Force generation below

    # --- 3. Generate New or Poll Existing Async Task ---
    s3_url = None
    try:
        if record is None and task_id_to_poll is None:
            logger.info(
                f"Generating new for {url} via root (sync: {not settings.CELERY_ENABLED})."
                f"Size: {request_width}x{request_height}"
            )
            new_record = create_db_record(db, str(url), future_expiry_time)

            if settings.CELERY_ENABLED:
                dispatch_celery_task(
                    new_record.id, str(url), request_width, request_height
                )
                task_id_to_poll = new_record.id
            else:
                s3_url = run_sync_generation(
                    new_record.id,
                    str(url),
                    request_width,
                    request_height,
                    cache_key,
                    future_expiry_time,
                )
                return RedirectResponse(
                    url=s3_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
                )

        if settings.CELERY_ENABLED and task_id_to_poll:
            s3_url = await poll_task_completion(task_id_to_poll, cache_key)
            return RedirectResponse(
                url=s3_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT
            )

        if not settings.CELERY_ENABLED and not s3_url:
            logger.error("Sync execution path ended without redirect or error.")
            raise HTTPException(
                status_code=500, detail="Internal error after sync processing."
            )

    except HTTPException as http_exc:
        logger.error(
            f"HTTPException during root processing for {url}: {http_exc.detail}"
        )
        return HTMLResponse(
            content=f"<html><body><h1>Error</h1><p>Image generation failed: {http_exc.detail}</p></body></html>",
            status_code=http_exc.status_code,
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during root processing for {url}: {e}", exc_info=True
        )
        return HTMLResponse(
            content="<html><body><h1>Error</h1><p>An unexpected error occurred during image generation.</p></body></html>",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    logger.warning(
        f"Root handler reached end without redirect or explicit error for {url}"
    )
    return HTMLResponse(
        content="<html><body><h1>Processing</h1>"
        "<p>Image generation is in progress or encountered an issue. "
        "Please check API status or try again.</p></body></html>",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
