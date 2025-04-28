from typing import Literal, Optional

from pydantic import UUID4, BaseModel, Field, HttpUrl


class GenerateRequest(BaseModel):
    url: HttpUrl = Field(..., description="URL to capture")
    ttl: Optional[int] = Field(None, description="Cache validity duration in hours")
    width: Optional[int] = Field(None, description="Screenshot width in pixels")
    height: Optional[int] = Field(None, description="Screenshot height in pixels")


class CachedResponse(BaseModel):
    status: Literal["cached"] = "cached"
    image_url: HttpUrl = Field(..., description="URL of the cached image in S3")


class ProcessingResponse(BaseModel):
    status: Literal["processing"] = "processing"
    task_id: UUID4 = Field(..., description="ID of the background processing task")
    check_status_url: str = Field(..., description="URL to check the task status")


class StatusResponse(BaseModel):
    status: Literal["pending", "processing", "completed", "failed"]
    image_url: Optional[HttpUrl] = Field(
        None, description="URL of the generated image (if completed)"
    )
    error_message: Optional[str] = Field(None, description="Error details (if failed)")


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Description of the error")
