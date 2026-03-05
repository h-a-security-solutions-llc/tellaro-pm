"""Pydantic schemas for task management endpoints."""

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskStatus(StrEnum):
    """Task workflow status."""

    BACKLOG = "backlog"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"


class TaskPriority(StrEnum):
    """Task priority level."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskCreate(BaseModel):
    project_id: str = Field(min_length=1)
    title: str = Field(min_length=1, max_length=512)
    description: str = Field(default="", max_length=16384)
    priority: TaskPriority = TaskPriority.NORMAL
    parent_task_id: str | None = None
    assignee_id: str | None = None
    labels: list[str] = Field(default_factory=list)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    description: str | None = Field(default=None, max_length=16384)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: str | None = None
    labels: list[str] | None = None
    order: float | None = None


class StatusUpdate(BaseModel):
    status: TaskStatus


class AssignUpdate(BaseModel):
    assignee_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    project_id: str
    parent_task_id: str | None = None
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    assignee_id: str | None = None
    labels: list[str]
    github_issue_url: str | None = None
    github_issue_number: int | None = None
    github_pr_urls: list[str]
    order: float
    created_at: str
    updated_at: str


class TaskListResponse(BaseModel):
    items: list[TaskResponse]
    total: int
