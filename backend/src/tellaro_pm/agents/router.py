"""FastAPI routes for agent management, personas, work items, and work requests."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from tellaro_pm.agents.schemas import (
    AgentHeartbeat,
    AgentListResponse,
    AgentRegister,
    AgentResponse,
    PersonaCreate,
    PersonaResponse,
    PersonaUpdate,
    WorkItemCreate,
    WorkItemListResponse,
    WorkItemResponse,
    WorkItemUpdate,
    WorkRequestCreate,
    WorkRequestListResponse,
    WorkRequestReject,
    WorkRequestResponse,
    WorkRequestStatus,
)
from tellaro_pm.agents.service import agent_service, work_dispatch_service
from tellaro_pm.core.dependencies import get_current_user

router = APIRouter(prefix="/api/v1", tags=["agents"])

CurrentUser = Annotated[dict[str, object], Depends(get_current_user)]


# ---------------------------------------------------------------------------
# Agent endpoints
# ---------------------------------------------------------------------------


@router.post("/agents/register", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def register_agent(body: AgentRegister, user: CurrentUser) -> dict[str, object]:
    """Register a new agent daemon for the authenticated user."""
    user_id = str(user["id"])
    agent = agent_service.register(user_id, body.model_dump())
    agent["personas"] = []
    return agent


@router.post("/agents/{agent_id}/heartbeat", response_model=AgentResponse)
def agent_heartbeat(agent_id: str, body: AgentHeartbeat, user: CurrentUser) -> dict[str, object]:
    """Update agent heartbeat and status."""
    agent = agent_service.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")

    updated = agent_service.heartbeat(agent_id, body.model_dump())
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")

    updated["personas"] = agent_service.list_personas(agent_id=agent_id)
    return updated


@router.get("/agents", response_model=AgentListResponse)
def list_agents(
    _user: CurrentUser,
    user_id: Annotated[str | None, Query()] = None,
    agent_status: Annotated[str | None, Query(alias="status")] = None,
) -> dict[str, object]:
    """List agents with optional user and status filters."""
    agents, total = agent_service.list_agents(user_id=user_id, status=agent_status)
    for agent in agents:
        aid = str(agent["id"])
        agent["personas"] = agent_service.list_personas(agent_id=aid)
    return {"items": agents, "total": total}


@router.get("/agents/{agent_id}", response_model=AgentResponse)
def get_agent(agent_id: str, _user: CurrentUser) -> dict[str, object]:
    """Get a single agent by ID."""
    agent = agent_service.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    agent["personas"] = agent_service.list_personas(agent_id=agent_id)
    return agent


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def deregister_agent(agent_id: str, user: CurrentUser) -> None:
    """Deregister (remove) an agent."""
    agent = agent_service.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")
    agent_service.deregister(agent_id)


# ---------------------------------------------------------------------------
# Persona endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/agents/{agent_id}/personas",
    response_model=PersonaResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_persona(agent_id: str, body: PersonaCreate, user: CurrentUser) -> dict[str, object]:
    """Create a persona for an agent."""
    agent = agent_service.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your agent")

    user_id = str(user["id"])
    return agent_service.create_persona(agent_id, user_id, body.model_dump())


@router.get("/agents/{agent_id}/personas", response_model=list[PersonaResponse])
def list_agent_personas(agent_id: str, _user: CurrentUser) -> list[dict[str, object]]:
    """List all personas for a specific agent."""
    agent = agent_service.get(agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    return agent_service.list_personas(agent_id=agent_id)


@router.patch("/personas/{persona_id}", response_model=PersonaResponse)
def update_persona(persona_id: str, body: PersonaUpdate, user: CurrentUser) -> dict[str, object]:
    """Update a persona."""
    persona = agent_service.get_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    if persona["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your persona")

    updated = agent_service.update_persona(persona_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    return updated


@router.delete("/personas/{persona_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_persona(persona_id: str, user: CurrentUser) -> None:
    """Delete a persona."""
    persona = agent_service.get_persona(persona_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    if persona["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your persona")
    agent_service.delete_persona(persona_id)


# ---------------------------------------------------------------------------
# Work Item endpoints
# ---------------------------------------------------------------------------


@router.post("/work/items", response_model=WorkItemResponse, status_code=status.HTTP_201_CREATED)
def create_work_item(body: WorkItemCreate, user: CurrentUser) -> dict[str, object]:
    """Dispatch a new work item to an agent."""
    agent = agent_service.get(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent["user_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot dispatch work to another user's agent directly; use a work request",
        )

    persona = agent_service.get_persona(body.persona_id)
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Persona not found")
    if persona["agent_id"] != body.agent_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Persona does not belong to this agent")

    return work_dispatch_service.create_work_item(body.model_dump())


@router.get("/work/items", response_model=WorkItemListResponse)
def list_work_items(
    _user: CurrentUser,
    agent_id: Annotated[str | None, Query()] = None,
    item_status: Annotated[str | None, Query(alias="status")] = None,
) -> dict[str, object]:
    """List work items with optional filters."""
    items, total = work_dispatch_service.list_work_items(agent_id=agent_id, status=item_status)
    return {"items": items, "total": total}


@router.get("/work/items/{item_id}", response_model=WorkItemResponse)
def get_work_item(item_id: str, _user: CurrentUser) -> dict[str, object]:
    """Get a work item by ID."""
    item = work_dispatch_service.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")
    return item


@router.patch("/work/items/{item_id}", response_model=WorkItemResponse)
def update_work_item(item_id: str, body: WorkItemUpdate, user: CurrentUser) -> dict[str, object]:
    """Update work item status, output, or artifacts."""
    item = work_dispatch_service.get_work_item(item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")

    agent = agent_service.get(str(item["agent_id"]))
    if agent is not None and agent["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your work item")

    updated = work_dispatch_service.update_work_item(item_id, body.model_dump(exclude_unset=True))
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work item not found")
    return updated


# ---------------------------------------------------------------------------
# Work Request endpoints (cross-user)
# ---------------------------------------------------------------------------


@router.post("/work/requests", response_model=WorkRequestResponse, status_code=status.HTTP_201_CREATED)
def create_work_request(body: WorkRequestCreate, user: CurrentUser) -> dict[str, object]:
    """Create a cross-user work request requiring target user approval."""
    requester_id = str(user["id"])
    if requester_id == body.target_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a work request targeting yourself; dispatch directly",
        )
    return work_dispatch_service.create_work_request(requester_id, body.model_dump())


@router.get("/work/requests", response_model=WorkRequestListResponse)
def list_work_requests(
    user: CurrentUser,
    request_status: Annotated[str | None, Query(alias="status")] = None,
) -> dict[str, object]:
    """List work requests targeting the current user."""
    user_id = str(user["id"])
    requests, total = work_dispatch_service.list_work_requests(user_id, status=request_status)
    return {"items": requests, "total": total}


@router.post("/work/requests/{request_id}/approve", response_model=WorkRequestResponse)
def approve_work_request(request_id: str, body: WorkItemCreate, user: CurrentUser) -> dict[str, object]:
    """Approve a work request and dispatch a work item.

    The approver provides the work item details (agent_id, persona_id, etc.)
    to control where the work is dispatched.
    """
    user_id = str(user["id"])
    work_request = work_dispatch_service.get_work_request(request_id)
    if work_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work request not found")
    if work_request["target_user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the target user can approve")
    if work_request["status"] != WorkRequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work request is not pending")

    agent = agent_service.get(body.agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found")
    if agent["user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Agent does not belong to you")

    result = work_dispatch_service.approve_work_request(request_id, user_id, body.model_dump())
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work request not found")

    updated_request, _ = result
    return updated_request


@router.post("/work/requests/{request_id}/reject", response_model=WorkRequestResponse)
def reject_work_request(request_id: str, body: WorkRequestReject, user: CurrentUser) -> dict[str, object]:
    """Reject a work request with an optional message."""
    user_id = str(user["id"])
    work_request = work_dispatch_service.get_work_request(request_id)
    if work_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work request not found")
    if work_request["target_user_id"] != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the target user can reject")
    if work_request["status"] != WorkRequestStatus.PENDING:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work request is not pending")

    updated = work_dispatch_service.reject_work_request(request_id, user_id, body.message)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work request not found")
    return updated
