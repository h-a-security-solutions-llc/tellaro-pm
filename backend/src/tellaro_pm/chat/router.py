"""FastAPI router for chat sessions and messages."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tellaro_pm.chat.schemas import (
    ChatMessageCreate,
    ChatMessageListResponse,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionListResponse,
    ChatSessionResponse,
    ChatSessionUpdate,
    ScopeType,
)
from tellaro_pm.chat.service import chat_service
from tellaro_pm.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]

# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


@router.post("/sessions", response_model=ChatSessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    body: ChatSessionCreate,
    user: CurrentUser,
) -> dict[str, object]:
    """Create a new chat session scoped to a project, task, subtask, or freeform."""
    creator_id = str(user["id"])

    if body.scope_type != ScopeType.freeform and body.scope_id is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="scope_id is required for non-freeform sessions",
        )

    if body.scope_type != ScopeType.freeform and body.working_directory is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="working_directory is only allowed for freeform sessions",
        )

    return chat_service.create_session(creator_id, body.model_dump())


@router.get("/sessions", response_model=ChatSessionListResponse)
def list_sessions(
    user: CurrentUser,
    scope_type: Annotated[ScopeType | None, Query()] = None,
    scope_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List chat sessions, optionally filtered by scope."""
    user_id = str(user["id"])
    items, total = chat_service.list_sessions(
        scope_type=scope_type.value if scope_type is not None else None,
        scope_id=scope_id,
        user_id=user_id,
    )
    return {"items": items, "total": total}


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
def get_session(
    session_id: str,
    user: CurrentUser,
) -> dict[str, object]:
    """Retrieve a single chat session by ID."""
    _ = user  # ensure authentication
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return session


@router.patch("/sessions/{session_id}", response_model=ChatSessionResponse)
def update_session(
    session_id: str,
    body: ChatSessionUpdate,
    user: CurrentUser,
) -> dict[str, object]:
    """Update a chat session (title, archive status)."""
    _ = user  # ensure authentication
    updated = chat_service.update_session(session_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")
    return updated


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
def send_message(
    session_id: str,
    body: ChatMessageCreate,
    user: CurrentUser,
) -> dict[str, object]:
    """Send a message to a chat session."""
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    sender_id = str(user["id"])
    return chat_service.send_message(
        session_id=session_id,
        sender_id=sender_id,
        sender_type=body.sender_type.value,
        content=body.content,
    )


@router.get("/sessions/{session_id}/messages", response_model=ChatMessageListResponse)
def list_messages(
    session_id: str,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    before_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """List messages in a session (reverse chronological, cursor-paginated)."""
    _ = user  # ensure authentication
    session = chat_service.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Chat session not found")

    items, total = chat_service.list_messages(session_id, limit=limit, before_id=before_id)
    return {"items": items, "total": total}


@router.get("/messages/search", response_model=ChatMessageListResponse)
def search_messages(
    user: CurrentUser,
    q: Annotated[str, Query(min_length=1)],
    session_id: Annotated[str | None, Query()] = None,
) -> dict[str, object]:
    """Full-text search across chat messages."""
    _ = user  # ensure authentication
    results = chat_service.search_messages(q, session_id=session_id)
    return {"items": results, "total": len(results)}
