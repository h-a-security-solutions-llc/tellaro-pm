"""User management API router."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tellaro_pm.core.dependencies import get_current_user, require_admin
from tellaro_pm.users.schemas import UserCreate, UserListResponse, UserResponse, UserUpdate
from tellaro_pm.users.service import user_service

router = APIRouter(prefix="/api/v1/users", tags=["users"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]
AdminUser = Annotated[dict[str, object], Depends(require_admin)]


@router.get("", response_model=UserListResponse)
async def list_users(
    _user: CurrentUser,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    role: Annotated[str | None, Query(pattern=r"^(admin|member)$")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
) -> dict[str, object]:
    if q:
        results = user_service.search(q, limit=limit)
        return {"users": results, "total": len(results)}

    users, total = user_service.list_users(skip=skip, limit=limit, role=role)
    return {"users": users, "total": total}


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, _user: CurrentUser) -> dict[str, object]:
    user = user_service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(body: UserCreate, _admin: AdminUser) -> dict[str, object]:
    if user_service.get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")
    if user_service.get_by_username(body.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")
    return user_service.create(body.model_dump())


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(user_id: str, body: UserUpdate, current_user: CurrentUser) -> dict[str, object]:
    is_admin = current_user.get("role") == "admin"
    is_self = str(current_user.get("id")) == user_id

    if not is_admin and not is_self:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot update other users")

    if not is_admin and (body.role is not None or body.is_active is not None):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can change role or active status")

    update_data = body.model_dump(exclude_unset=True)

    if "email" in update_data:
        existing = user_service.get_by_email(update_data["email"])
        if existing and str(existing.get("id")) != user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already in use")

    if "username" in update_data:
        existing = user_service.get_by_username(update_data["username"])
        if existing and str(existing.get("id")) != user_id:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already taken")

    updated = user_service.update(user_id, update_data)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return updated


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: str, admin: AdminUser) -> None:
    if str(admin.get("id")) == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete yourself")
    if not user_service.delete(user_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
