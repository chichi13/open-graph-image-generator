# import logging # Remove old import
import os
from uuid import UUID

from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import SessionLocal
from app.logger import logger
from app.models.db_models import Screenshot, ScreenshotStatus
from app.services.screenshot import take_screenshot
from app.services.storage import upload_to_s3


def _perform_screenshot_and_upload(
    record_id_str: str, url: str, width: int, height: int
) -> str:
    """Core logic: take screenshot, upload to S3, cleanup. Returns S3 URL.
    Raises exceptions on failure.
    """
    db_record_id = UUID(record_id_str)
    screenshot_path = None
    try:
        screenshot_path = take_screenshot(url, width, height)
        logger.info(
            f"Screenshot taken and saved to {screenshot_path} for record {record_id_str}"
        )

        s3_destination_key = f"og_images/{db_record_id}.png"
        s3_url = upload_to_s3(screenshot_path, s3_destination_key)
        logger.info(f"Image uploaded to S3: {s3_url} for record {record_id_str}")
        return s3_url

    finally:
        # Cleanup Temporary File
        if screenshot_path and os.path.exists(screenshot_path):
            try:
                os.remove(screenshot_path)
                logger.info(
                    f"Cleaned up temporary file: {screenshot_path} for record {record_id_str}"
                )
            except OSError as e:
                logger.error(
                    f"Error deleting temporary file {screenshot_path} for record {record_id_str}: {e}"
                )


def _update_db_status(
    db: Session,
    record_id: UUID,
    status: ScreenshotStatus,
    s3_path: str = None,
    error_message: str = None,
):
    """Updates the status of a screenshot record in the database."""
    try:
        record = db.query(Screenshot).filter(Screenshot.id == record_id).first()
        if record:
            record.status = status
            if status == ScreenshotStatus.COMPLETED:
                record.s3_path = s3_path
                record.error_message = None  # Clear previous errors
            elif status == ScreenshotStatus.FAILED:
                record.error_message = str(error_message)[
                    :500
                ]  # Truncate error message
            db.commit()
            logger.info(f"Updated DB record {record_id} status to {status}")
            return True
        else:
            logger.error(f"DB record {record_id} not found for status update {status}")
            return False
    except Exception as e:
        logger.error(f"DB error updating status for {record_id} to {status}: {e}")
        db.rollback()
        raise


@celery_app.task(bind=True)
def generate_screenshot_task(
    self, record_id: str, url: str, width: int = 1200, height: int = 630
):
    """Celery task wrapper: updates status, calls core logic, updates status again."""
    logger.info(f"Celery task started for record_id={record_id}")
    try:
        db_record_id = UUID(record_id)
    except ValueError:
        logger.error(f"[Celery Task] Invalid UUID format for record_id: {record_id}")
        return

    try:
        with SessionLocal() as db:
            if not _update_db_status(db, db_record_id, ScreenshotStatus.PROCESSING):
                return
    except Exception as db_exc:
        logger.error(
            f"[Celery Task] Failed to set PROCESSING status for {db_record_id}: {db_exc}"
        )
        raise db_exc

    # Call the core logic
    try:
        s3_url = _perform_screenshot_and_upload(record_id, url, width, height)

        with SessionLocal() as db:
            _update_db_status(
                db, db_record_id, ScreenshotStatus.COMPLETED, s3_path=s3_url
            )
        return s3_url

    except Exception as exc:
        logger.error(
            f"[Celery Task] Core logic failed for {record_id}: {exc}", exc_info=True
        )
        try:
            with SessionLocal() as db:
                _update_db_status(
                    db, db_record_id, ScreenshotStatus.FAILED, error_message=str(exc)
                )
        except Exception as db_fail_exc:
            logger.error(
                f"[Celery Task] Failed to set FAILED status for {db_record_id}: {db_fail_exc}"
            )
        raise exc
