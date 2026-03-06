"""WebSocket connection manager for agent communication."""

import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

from tellaro_pm.agents.logs import store_log_batch
from tellaro_pm.agents.schemas import WorkItemStatus
from tellaro_pm.agents.service import agent_service, work_dispatch_service

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections from agent daemons and user chat sessions.

    Each agent maintains a single persistent WebSocket connection used to:
    - Receive heartbeats and status updates
    - Push persona configurations
    - Dispatch work items in real-time
    - Receive work item progress and results

    Users connect via per-session WebSockets to receive streaming output.
    """

    def __init__(self) -> None:
        # agent_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # agent_id → user_id (for broadcasting to all agents of a user)
        self._agent_user_map: dict[str, str] = {}
        # session_id → list[WebSocket] (user chat WebSocket connections)
        self._chat_connections: dict[str, list[WebSocket]] = {}

    @property
    def active_connections(self) -> dict[str, WebSocket]:
        """Read-only view of active connections."""
        return dict(self._connections)

    async def connect(self, agent_id: str, user_id: str, websocket: WebSocket) -> None:
        """Accept a WebSocket connection and register it for an agent."""
        await websocket.accept()
        self._connections[agent_id] = websocket
        self._agent_user_map[agent_id] = user_id
        logger.info("Agent %s connected (user=%s)", agent_id, user_id)

        # Push current persona configs on connect
        await self._push_personas(agent_id)

        # Push any queued work items
        await self._push_queued_work(agent_id)

    async def disconnect(self, agent_id: str) -> None:
        """Remove an agent connection and mark it offline."""
        self._connections.pop(agent_id, None)
        self._agent_user_map.pop(agent_id, None)

        # Mark agent as offline in the data store
        agent_service.heartbeat(agent_id, {"status": "offline"})
        logger.info("Agent %s disconnected", agent_id)

    async def send_to_agent(self, agent_id: str, message: dict[str, Any]) -> bool:
        """Send a JSON message to a specific agent. Returns True if sent."""
        ws = self._connections.get(agent_id)
        if ws is None or ws.client_state != WebSocketState.CONNECTED:
            return False
        try:
            await ws.send_json(message)
            return True
        except Exception:
            logger.exception("Failed to send message to agent %s", agent_id)
            return False

    async def broadcast_to_user_agents(self, user_id: str, message: dict[str, Any]) -> int:
        """Send a message to all connected agents belonging to a user.

        Returns the count of agents the message was successfully sent to.
        """
        sent = 0
        for agent_id, uid in list(self._agent_user_map.items()):
            if uid == user_id and await self.send_to_agent(agent_id, message):
                sent += 1
        return sent

    # --- User chat WebSocket management ---

    async def connect_chat(self, session_id: str, websocket: WebSocket) -> None:
        """Register a user WebSocket connection for a chat session."""
        await websocket.accept()
        if session_id not in self._chat_connections:
            self._chat_connections[session_id] = []
        self._chat_connections[session_id].append(websocket)
        logger.info("User chat WebSocket connected for session %s", session_id)

    async def disconnect_chat(self, session_id: str, websocket: WebSocket) -> None:
        """Remove a user WebSocket connection for a chat session."""
        conns = self._chat_connections.get(session_id, [])
        if websocket in conns:
            conns.remove(websocket)
        if not conns:
            self._chat_connections.pop(session_id, None)
        logger.info("User chat WebSocket disconnected for session %s", session_id)

    async def send_to_chat_session(self, session_id: str, message: dict[str, Any]) -> int:
        """Send a message to all user WebSockets connected to a chat session.

        Returns the number of clients the message was successfully sent to.
        """
        conns = self._chat_connections.get(session_id, [])
        sent = 0
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
                    sent += 1
                else:
                    dead.append(ws)
            except Exception:
                dead.append(ws)
        # Clean up dead connections
        for ws in dead:
            if ws in conns:
                conns.remove(ws)
        return sent

    async def handle_message(self, agent_id: str, message: dict[str, Any]) -> None:
        """Route an incoming WebSocket message from an agent to the appropriate handler."""
        msg_type = message.get("type")

        if msg_type == "heartbeat":
            await self._handle_heartbeat(agent_id, message)
        elif msg_type == "log_batch":
            await self._handle_log_batch(agent_id, message)
        elif msg_type == "work_item_update":
            await self._handle_work_item_update(agent_id, message)
        elif msg_type == "stream_chunk":
            await self._handle_stream_chunk(agent_id, message)
        elif msg_type == "stream_start":
            await self._handle_stream_event(agent_id, message, "stream_start")
        elif msg_type == "stream_end":
            await self._handle_stream_end(agent_id, message)
        elif msg_type == "capability_report":
            await self._handle_capability_report(agent_id, message)
        else:
            logger.warning("Unknown message type '%s' from agent %s", msg_type, agent_id)
            await self.send_to_agent(
                agent_id,
                {
                    "type": "error",
                    "detail": f"Unknown message type: {msg_type}",
                },
            )

    # --- Internal handlers ---

    async def _handle_heartbeat(self, agent_id: str, message: dict[str, Any]) -> None:
        """Process a heartbeat message from an agent."""
        status_value = message.get("status", "online")
        active_items = message.get("active_work_item_ids", [])

        agent_service.heartbeat(
            agent_id,
            {
                "status": status_value,
                "active_work_item_ids": active_items,
            },
        )

        await self.send_to_agent(agent_id, {"type": "heartbeat_ack"})

    async def _handle_work_item_update(self, agent_id: str, message: dict[str, Any]) -> None:
        """Process a work item status update from an agent."""
        item_id = message.get("work_item_id")
        if not isinstance(item_id, str):
            await self.send_to_agent(
                agent_id,
                {
                    "type": "error",
                    "detail": "work_item_update requires a 'work_item_id' string field",
                },
            )
            return

        update_data: dict[str, object] = {}
        if "status" in message:
            update_data["status"] = message["status"]
        if "output" in message:
            update_data["output"] = message["output"]
        if "artifacts" in message:
            update_data["artifacts"] = message["artifacts"]

        if not update_data:
            return

        updated = work_dispatch_service.update_work_item(item_id, update_data)
        if updated is None:
            await self.send_to_agent(
                agent_id,
                {
                    "type": "error",
                    "detail": f"Work item {item_id} not found",
                },
            )
            return

        # Forward status update to user chat WebSocket if linked to a chat session
        chat_session_id = updated.get("chat_session_id")
        if isinstance(chat_session_id, str):
            await self.send_to_chat_session(
                chat_session_id,
                {
                    "type": "work_item_update",
                    "work_item_id": item_id,
                    "status": updated.get("status"),
                },
            )

        await self.send_to_agent(
            agent_id,
            {
                "type": "work_item_ack",
                "work_item_id": item_id,
                "status": updated.get("status"),
            },
        )

    async def _handle_stream_chunk(self, agent_id: str, message: dict[str, Any]) -> None:
        """Forward a streaming output chunk from agent to the user's chat WebSocket."""
        work_item_id = message.get("work_item_id")
        chat_session_id = message.get("chat_session_id")
        content = message.get("content", "")

        if not isinstance(chat_session_id, str) and isinstance(work_item_id, str):
            item = work_dispatch_service.get_work_item(work_item_id)
            if item:
                chat_session_id = item.get("chat_session_id")

        if isinstance(chat_session_id, str):
            await self.send_to_chat_session(
                chat_session_id,
                {
                    "type": "stream_chunk",
                    "work_item_id": work_item_id,
                    "content": content,
                },
            )

    async def _handle_stream_event(self, agent_id: str, message: dict[str, Any], event_type: str) -> None:
        """Forward a stream lifecycle event (start) to the user's chat WebSocket."""
        work_item_id = message.get("work_item_id")
        chat_session_id = message.get("chat_session_id")

        if not isinstance(chat_session_id, str) and isinstance(work_item_id, str):
            item = work_dispatch_service.get_work_item(work_item_id)
            if item:
                chat_session_id = item.get("chat_session_id")

        if isinstance(chat_session_id, str):
            await self.send_to_chat_session(
                chat_session_id,
                {
                    "type": event_type,
                    "work_item_id": work_item_id,
                },
            )

    async def _handle_stream_end(self, agent_id: str, message: dict[str, Any]) -> None:
        """Handle end of streaming — save final output as agent message in chat session."""
        work_item_id = message.get("work_item_id")
        chat_session_id = message.get("chat_session_id")
        final_content = message.get("content", "")

        if not isinstance(chat_session_id, str) and isinstance(work_item_id, str):
            item = work_dispatch_service.get_work_item(work_item_id)
            if item:
                chat_session_id = item.get("chat_session_id")

        # Save final output as an agent message in the chat session
        if isinstance(chat_session_id, str) and final_content:
            from tellaro_pm.chat.service import chat_service

            chat_service.send_message(
                session_id=chat_session_id,
                sender_id=agent_id,
                sender_type="agent",
                content=final_content,
            )

        if isinstance(chat_session_id, str):
            await self.send_to_chat_session(
                chat_session_id,
                {
                    "type": "stream_end",
                    "work_item_id": work_item_id,
                    "content": final_content,
                },
            )

    async def _handle_log_batch(self, agent_id: str, message: dict[str, Any]) -> None:
        """Store a batch of log entries from an agent."""
        entries = message.get("entries", [])
        if not isinstance(entries, list) or not entries:
            return

        user_id = self._agent_user_map.get(agent_id, "")
        try:
            stored = store_log_batch(agent_id, user_id, entries)
            logger.debug("Stored %d log entries from agent %s", stored, agent_id)
        except Exception:
            logger.exception("Failed to store logs from agent %s", agent_id)

    async def _handle_capability_report(self, agent_id: str, message: dict[str, Any]) -> None:
        """Process a capability report from an agent (e.g., after plugin load)."""
        capabilities = message.get("capabilities", [])
        if not isinstance(capabilities, list):
            return

        agent = agent_service.get(agent_id)
        if agent is not None:
            from datetime import UTC, datetime

            from tellaro_pm.core.opensearch import AGENTS_INDEX, CRUDService

            crud = CRUDService(AGENTS_INDEX)
            crud.update(
                agent_id,
                {
                    "capabilities": capabilities,
                    "updated_at": datetime.now(UTC).isoformat(),
                },
            )

        await self.send_to_agent(agent_id, {"type": "capability_ack"})

    async def _push_personas(self, agent_id: str) -> None:
        """Push the current persona configurations to a newly connected agent."""
        personas = agent_service.list_personas(agent_id=agent_id)
        active_personas = [p for p in personas if p.get("is_active", True)]

        await self.send_to_agent(
            agent_id,
            {
                "type": "persona_sync",
                "personas": active_personas,
            },
        )

    async def _push_queued_work(self, agent_id: str) -> None:
        """Push any queued work items to a newly connected agent."""
        queued_items = work_dispatch_service.list_queued_for_agent(agent_id)
        for item in queued_items:
            await self.send_to_agent(
                agent_id,
                {
                    "type": "work_item_dispatch",
                    "work_item": item,
                },
            )

    async def dispatch_work_item(self, agent_id: str, work_item: dict[str, object]) -> bool:
        """Dispatch a work item to a connected agent in real-time.

        If the agent is not connected, the item stays queued and will be
        pushed when the agent reconnects.
        """
        sent = await self.send_to_agent(
            agent_id,
            {
                "type": "work_item_dispatch",
                "work_item": work_item,
            },
        )
        if sent:
            # Mark as running since the agent received it
            work_dispatch_service.update_work_item(str(work_item["id"]), {"status": WorkItemStatus.RUNNING})
        return sent

    async def push_persona_update(self, agent_id: str) -> None:
        """Re-push all personas to an agent after a persona change."""
        await self._push_personas(agent_id)


# Module-level singleton
connection_manager = ConnectionManager()
