"""FastAPI dependencies for auth, OpenSearch, etc."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from tellaro_pm.core.auth import decode_access_token
from tellaro_pm.core.opensearch import USERS_INDEX, CRUDService

security = HTTPBearer()
_users_crud = CRUDService(USERS_INDEX)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, object]:  # noqa: B008
    """Decode JWT and return the user document from OpenSearch."""
    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user = _users_crud.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    if not user.get("is_active", False):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    return user


def require_admin(user: dict[str, object] = Depends(get_current_user)) -> dict[str, object]:  # noqa: B008
    """Require the current user to have admin role."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return user
