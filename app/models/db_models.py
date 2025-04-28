import enum
import uuid

from sqlalchemy import UUID, Column, DateTime
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy import String, Text
from sqlalchemy.sql import func

from app.database import Base


# Use standard Python enum.Enum
class ScreenshotStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class Screenshot(Base):
    __tablename__ = "screenshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    url = Column(String, index=True, nullable=False)
    s3_path = Column(String, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # Pass the Enum class directly to SQLAlchemyEnum
    status = Column(
        SQLAlchemyEnum(
            ScreenshotStatus,
            name="screenshot_status_enum",
            create_type=False,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=ScreenshotStatus.PENDING,
        index=True,
    )
    error_message = Column(Text, nullable=True)
