"""WebSocket endpoints for agent daemon connections and user chat streaming."""

import logging
from typing import Any, cast

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from tellaro_pm.agents.service import agent_service
from tellaro_pm.chat.service import chat_service
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


# ---------------------------------------------------------------------------
# User chat WebSocket — streaming agent responses
# ---------------------------------------------------------------------------


@router.websocket("/ws/chat/{session_id}")
async def chat_websocket(
    websocket: WebSocket,
    session_id: str,
    token: str = Query(...),
) -> None:
    """WebSocket endpoint for streaming chat session output to users.

    Query parameters:
        token: JWT access token for authentication

    The server pushes messages to the client:
        stream_start:  Agent has begun processing
        stream_chunk:  Partial output from the agent
        stream_end:    Agent finished; includes final content
        message:       A new chat message was posted (by any participant)
        work_item_update: Work item status changed
    """
    # Authenticate
    auth_result = _authenticate_ws_token(token)
    if auth_result is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication failed")
        return

    user_id = auth_result[0]

    # Verify session exists and user is a participant
    session = chat_service.get_session(session_id)
    if session is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Session not found")
        return

    participant_ids = session.get("participant_ids", [])
    if user_id not in participant_ids:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Not a session participant")
        return

    await connection_manager.connect_chat(session_id, websocket)

    try:
        while True:
            # Keep connection alive; we don't expect user messages on this WS
            # (messages are sent via REST). But handle pings/keep-alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info("User chat WebSocket disconnected for session %s", session_id)
    except Exception:
        logger.exception("Unexpected error in chat WebSocket for session %s", session_id)
    finally:
        await connection_manager.disconnect_chat(session_id, websocket)
