from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.db_models import Screenshot


async def get_screenshot_record(task_id: UUID, db: Session) -> Optional[Screenshot]:
    """Fetches a screenshot record by its ID."""
    record = db.query(Screenshot).filter(Screenshot.id == task_id).first()
    return record
