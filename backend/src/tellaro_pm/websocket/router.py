"""WebSocket endpoint for agent daemon connections."""

import logging
from typing import Any, cast

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from tellaro_pm.agents.service import agent_service
from tellaro_pm.core.auth import decode_access_token
from tellaro_pm.core.opensearch import USERS_INDEX, CRUDService
from tellaro_pm.websocket.manager import connection_manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])

_users_crud = CRUDService(USERS_INDEX)


def _authenticate_ws_token(token: str) -> tuple[str, str] | None:
    """Validate a JWT token and return (user_id, agent_id_hint) or None.

    For WebSocket connections, the token is passed as a query parameter
    because browsers do not support custom headers on WebSocket upgrade.
    """
    payload = decode_access_token(token)
    if payload is None:
        return None

    user_id = payload.get("sub")
    if not isinstance(user_id, str):
        return None

    user = _users_crud.get(user_id)
    if user is None or not user.get("is_active", False):
        return None

    return user_id, user_id


@router.websocket("/ws/agent")
async def agent_websocket(
    websocket: WebSocket,
    token: str = Query(...),
    agent_id: str = Query(...),
) -> None:
    """WebSocket endpoint for agent daemon connections.

    Query parameters:
        token: JWT access token for authentication
        agent_id: ID of the registered agent connecting

    Protocol:
        After connection, the agent sends JSON messages with a "type" field.
        Supported types: heartbeat, work_item_update, capability_report.
        The server pushes persona_sync, work_item_dispatch, and ack messages.
    """
    # Authenticate before accepting the connection
    auth_result = _authenticate_ws_token(token)
    if auth_result is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    user_id = auth_result[0]

    # Verify the agent exists and belongs to this user
    agent = agent_service.get(agent_id)
    if agent is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Agent not found")
        return
    if agent["user_id"] != user_id:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Agent does not belong to you")
        return

    # Register the connection (this calls websocket.accept())
    await connection_manager.connect(agent_id, user_id, websocket)

    try:
        while True:
            raw: object = await websocket.receive_json()

            if not isinstance(raw, dict):
                await connection_manager.send_to_agent(
                    agent_id,
                    {
                        "type": "error",
                        "detail": "Messages must be JSON objects",
                    },
                )
                continue

            message = cast("dict[str, Any]", raw)
            await connection_manager.handle_message(agent_id, message)

    except WebSocketDisconnect:
        logger.info("Agent %s WebSocket disconnected normally", agent_id)
    except Exception:
        logger.exception("Unexpected error in WebSocket loop for agent %s", agent_id)
    finally:
        await connection_manager.disconnect(agent_id)
