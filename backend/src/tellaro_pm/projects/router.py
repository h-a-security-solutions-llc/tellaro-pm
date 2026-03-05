"""FastAPI router for project endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from tellaro_pm.core.dependencies import get_current_user
from tellaro_pm.core.settings import settings
from tellaro_pm.projects.schemas import ProjectCreate, ProjectListResponse, ProjectResponse, ProjectUpdate
from tellaro_pm.projects.service import project_service

router = APIRouter(
    prefix=f"/api/{settings.API_VERSION_STR}/projects",
    tags=["projects"],
)

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]


@router.post("/", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(data: ProjectCreate, user: CurrentUser) -> dict[str, object]:
    """Create a new project. The caller becomes the owner."""
    owner_id = str(user["id"])
    return project_service.create(owner_id, data)


@router.get("/", response_model=ProjectListResponse)
def list_projects(user: CurrentUser, include_archived: bool = False) -> dict[str, object]:
    """List projects the current user owns or is a member of."""
    user_id = str(user["id"])
    items = project_service.list_for_user(user_id, include_archived=include_archived)
    return {"items": items, "total": len(items)}


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: str, user: CurrentUser) -> dict[str, object]:
    """Get a single project by ID."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user_id = str(user["id"])
    member_ids: list[object] = list(project.get("member_ids") or [])  # type: ignore[arg-type]
    if user_id not in member_ids and user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a member of this project")

    return project


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(project_id: str, data: ProjectUpdate, user: CurrentUser) -> dict[str, object]:
    """Partially update a project. Only the owner or an admin may update."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user_id = str(user["id"])
    if project.get("owner_id") != user_id and user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner or an admin can update")

    return project_service.update(project_id, data)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, user: CurrentUser) -> None:
    """Delete a project. Only the owner or an admin may delete."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    user_id = str(user["id"])
    if project.get("owner_id") != user_id and user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner or an admin can delete")

    project_service.delete(project_id)


@router.post("/{project_id}/members/{user_id}", response_model=ProjectResponse)
def add_member(project_id: str, user_id: str, current_user: CurrentUser) -> dict[str, object]:
    """Add a user to the project's member list."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    caller_id = str(current_user["id"])
    if project.get("owner_id") != caller_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the owner or an admin can add members")

    return project_service.add_member(project_id, user_id)


@router.delete("/{project_id}/members/{user_id}", response_model=ProjectResponse)
def remove_member(project_id: str, user_id: str, current_user: CurrentUser) -> dict[str, object]:
    """Remove a user from the project's member list."""
    project = project_service.get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    caller_id = str(current_user["id"])
    owner_id = project.get("owner_id")
    if user_id == str(owner_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove the project owner")

    if caller_id != user_id and owner_id != caller_id and current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the owner, an admin, or the member themselves can remove membership",
        )

    return project_service.remove_member(project_id, user_id)
