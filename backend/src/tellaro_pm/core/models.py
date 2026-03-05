"""Base document models for OpenSearch storage."""

from datetime import UTC, datetime
from uuid import uuid4

from pydantic import BaseModel, Field


class BaseDocument(BaseModel):
    """Base for all OpenSearch documents."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_opensearch(self) -> dict[str, object]:
        """Serialize to OpenSearch document body."""
        return self.model_dump()

    def touch(self) -> None:
        """Update the updated_at timestamp."""
        self.updated_at = datetime.now(UTC).isoformat()
