"""FastAPI router for task endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tellaro_pm.core.dependencies import get_current_user
from tellaro_pm.core.settings import settings
from tellaro_pm.projects.service import project_service
from tellaro_pm.tasks.schemas import (
    AssignUpdate,
    StatusUpdate,
    TaskCreate,
    TaskListResponse,
    TaskResponse,
    TaskStatus,
    TaskUpdate,
)
from tellaro_pm.tasks.service import task_service

router = APIRouter(
    prefix=f"/api/{settings.API_VERSION_STR}/tasks",
    tags=["tasks"],
)

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]


def _check_project_access(project_id: str, user: dict[str, object]) -> None:
    """Raise 404/403 if the project does not exist or the user is not a member."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user_id = str(user["id"])
    member_ids: list[object] = list(project.get("member_ids") or [])  # type: ignore[arg-type]
    if user_id not in member_ids and user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")


@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, user: CurrentUser) -> dict[str, object]:
    """Create a new task inside a project."""
    _check_project_access(data.project_id, user)
    return task_service.create(data)


@router.get("/", response_model=TaskListResponse)
def list_tasks(
    user: CurrentUser,
    project_id: Annotated[str, Query(min_length=1)],
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
    assignee_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List tasks for a project, with optional status and assignee filters."""
    _check_project_access(project_id, user)
    items = task_service.list_by_project(project_id, status_filter=task_status, assignee_id=assignee_id)
    return {"items": items, "total": len(items)}


@router.get("/{task_id}", response_model=TaskResponse)
def get_task(task_id: str, user: CurrentUser) -> dict[str, object]:
    """Retrieve a single task by ID."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    return task


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task(task_id: str, data: TaskUpdate, user: CurrentUser) -> dict[str, object]:
    """Partially update a task."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    return task_service.update(task_id, data)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, user: CurrentUser) -> None:
    """Delete a task."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    task_service.delete(task_id)


@router.get("/{task_id}/subtasks", response_model=TaskListResponse)
def list_subtasks(task_id: str, user: CurrentUser) -> dict[str, object]:
    """List direct child tasks of a parent task."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    items = task_service.list_subtasks(task_id)
    return {"items": items, "total": len(items)}


@router.patch("/{task_id}/status", response_model=TaskResponse)
def update_task_status(task_id: str, data: StatusUpdate, user: CurrentUser) -> dict[str, object]:
    """Update only the status of a task."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    return task_service.update_status(task_id, data.status)


@router.patch("/{task_id}/assign", response_model=TaskResponse)
def assign_task(task_id: str, data: AssignUpdate, user: CurrentUser) -> dict[str, object]:
    """Assign (or unassign) a task to a user."""
    task = task_service.get(task_id)
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    _check_project_access(str(task["project_id"]), user)
    return task_service.assign(task_id, data.assignee_id)
