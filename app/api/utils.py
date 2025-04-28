import asyncio
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import HttpUrl
from sqlalchemy.orm import Session

from app import database
from app.config import settings
from app.logger import logger
from app.models.api_models import ErrorResponse
from app.models.db_models import Screenshot, ScreenshotStatus
from app.services import cache
from app.tasks import generate_screenshot_task
from app.tasks.screenshot import _perform_screenshot_and_upload, _update_db_status


class DomainValidationError(ValueError):
    """Custom exception for domain validation errors."""

    pass


def validate_domain(url: HttpUrl) -> str:
    """
    Validates the domain of the URL against allowed domains in settings.
    Returns the lowercased domain name if valid.
    Raises DomainValidationError if invalid or not allowed.
    """
    try:
        parsed_url = urlparse(str(url))
        domain = parsed_url.netloc.lower()
        if not all([parsed_url.scheme in ["http", "https"], domain]):
            raise DomainValidationError(f"Invalid or unsupported URL scheme: {url}")

        if settings.ALLOWED_SCREENSHOT_DOMAINS:
            is_allowed = False
            for allowed_domain in settings.ALLOWED_SCREENSHOT_DOMAINS:
                if domain == allowed_domain or domain.endswith(f".{allowed_domain}"):
                    is_allowed = True
                    break
            if not is_allowed:
                logger.warning(f"Domain validation failed for {domain} (URL: {url})")
                raise DomainValidationError(
                    f"Domain '{domain}' is not allowed. "
                    f"Please contact {settings.CONTACT_EMAIL} if you want to whitelist it."
                )
        logger.debug(f"Domain validation passed for {domain}")
        return domain
    except ValueError as e:  # Catch potential underlying errors
        logger.error(f"URL parsing/validation error for {url}: {e}")
        raise DomainValidationError(f"URL validation error: {e}")


# --- Cache Operations ---


def check_cache(cache_key: str) -> Optional[dict]:
    """Checks the cache for the given key."""
    cached_data = cache.get_cache(cache_key)
    if cached_data and isinstance(cached_data, dict) and "s3_url" in cached_data:
        logger.info(f"Cache hit for key '{cache_key}'")
        return cached_data
    logger.info(f"Cache miss for key '{cache_key}'")
    return None


def update_cache(cache_key: str, s3_url: str, expiry_time_utc: datetime):
    """Updates the cache with the S3 URL and calculated TTL."""
    now_utc = datetime.now(timezone.utc)
    cache_ttl = max(0, int((expiry_time_utc - now_utc).total_seconds()))
    if cache_ttl > 0 and s3_url:
        logger.info(f"Updating cache for key '{cache_key}' with TTL {cache_ttl}s")
        cache.set_cache(cache_key, {"s3_url": s3_url}, cache_ttl)
    else:
        logger.warning(
            f"Cannot update cache for key '{cache_key}'. TTL={cache_ttl}, S3 URL={s3_url}"
        )


# --- Database Operations ---


def find_existing_record(db: Session, url: str) -> Optional[Screenshot]:
    """Finds the most recent screenshot record for a given URL."""
    return (
        db.query(Screenshot)
        .filter(Screenshot.url == str(url))
        .order_by(Screenshot.created_at.desc())
        .first()
    )


def create_db_record(db: Session, url: str, expires_at: datetime) -> Screenshot:
    """Creates a new PENDING screenshot record."""
    new_record = Screenshot(
        url=str(url), status=ScreenshotStatus.PENDING, expires_at=expires_at
    )
    db.add(new_record)
    try:
        db.commit()
        db.refresh(new_record)
        logger.info(f"Created new DB record {new_record.id} for {url}")
        return new_record
    except Exception as e:
        db.rollback()
        logger.error(f"Database error creating record for {url}: {e}", exc_info=True)
        # Re-raise standard exception
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error during record creation",
        )


# --- Generation Logic ---


def run_sync_generation(
    record_id: UUID,
    url: str,
    width: int,
    height: int,
    cache_key: str,
    expires_at: datetime,
) -> str:
    """
    Handles the synchronous screenshot generation process.
    Updates DB status, performs screenshot/upload, updates DB again, updates cache.
    Returns the S3 URL on success.
    Raises Exception on failure.
    """
    record_id_str = str(record_id)
    s3_url = None
    try:
        # 1. Mark as processing
        with database.SessionLocal() as sync_db:
            _update_db_status(sync_db, record_id, ScreenshotStatus.PROCESSING)

        # 2. Perform the core work
        s3_url = _perform_screenshot_and_upload(record_id_str, str(url), width, height)

        # 3. Mark as completed
        with database.SessionLocal() as sync_db:
            _update_db_status(
                sync_db, record_id, ScreenshotStatus.COMPLETED, s3_path=s3_url
            )

        # 4. Update cache
        update_cache(cache_key, s3_url, expires_at)
        return s3_url

    except Exception as exc:
        logger.error(
            f"Synchronous execution failed for {record_id}: {exc}", exc_info=True
        )
        # Attempt to mark DB as failed
        try:
            with database.SessionLocal() as fail_db:
                _update_db_status(
                    fail_db,
                    record_id,
                    ScreenshotStatus.FAILED,
                    error_message=str(exc),
                )
        except Exception as db_fail_exc:
            logger.error(
                f"Failed to update DB status to FAILED after sync error: {db_fail_exc}"
            )
        # Re-raise the original exception
        raise exc


def dispatch_celery_task(record_id: UUID, url: str, width: int, height: int):
    """Dispatches the Celery task for screenshot generation."""
    try:
        task_result = generate_screenshot_task.delay(
            record_id=str(record_id), url=str(url), width=width, height=height
        )
        logger.info(f"Launched Celery task {task_result.id} for DB record {record_id}")
    except Exception as e:
        logger.error(
            f"Failed to launch Celery task for {record_id}: {e}", exc_info=True
        )
        # Attempt to mark DB as failed
        try:
            with database.SessionLocal() as fail_db:
                _update_db_status(
                    fail_db,
                    record_id,
                    ScreenshotStatus.FAILED,
                    error_message="Failed to queue task",
                )
        except Exception as db_fail_exc:
            logger.error(
                f"Failed to update DB status to FAILED after Celery dispatch error: {db_fail_exc}"
            )
        # Raise an exception for the endpoint
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to queue generation task",
        )


# --- Root Endpoint Specific Logic ---


async def poll_task_completion(task_id: UUID, cache_key: str) -> str:
    """
    Polls the status of a task until completion or timeout (for root endpoint).
    Returns the S3 URL on success.
    Raises HTTPException on failure or timeout.
    """
    logger.info(f"Polling status for task {task_id}...")
    max_wait_seconds = 60
    poll_interval_seconds = 2
    start_time = time.time()

    while time.time() - start_time < max_wait_seconds:
        # Need a new db session for each poll check
        with database.SessionLocal() as poll_db:
            # Fetch record directly
            current_record = (
                poll_db.query(Screenshot).filter(Screenshot.id == task_id).first()
            )

        if current_record:
            if current_record.status == ScreenshotStatus.COMPLETED:
                logger.info(f"Task {task_id} completed. Redirecting.")
                s3_path = current_record.s3_path
                # Update cache before returning
                if s3_path:
                    update_cache(cache_key, s3_path, current_record.expires_at)
                return s3_path
            elif current_record.status == ScreenshotStatus.FAILED:
                logger.error(f"Task {task_id} failed.")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Image generation failed: {current_record.error_message or 'Unknown error'}",
                )
            # Still pending or processing, continue polling
            logger.debug(f"Task {task_id} status: {current_record.status}. Waiting...")
        else:
            logger.error(f"Record {task_id} disappeared during polling?")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error checking generation status. Record not found.",
            )

        await asyncio.sleep(poll_interval_seconds)

    # Timeout reached
    logger.error(f"Timeout waiting for task {task_id} to complete.")
    raise HTTPException(
        status_code=status.HTTP_504_GATEWAY_TIMEOUT,
        detail="Image generation timed out. Please try again later or check API status.",
    )


# --- Response Helpers ---


def create_error_response(status_code: int, message: str) -> JSONResponse:
    """Creates a standardized JSON error response."""
    error_content = ErrorResponse(error=message).model_dump()
    return JSONResponse(status_code=status_code, content=error_content)
