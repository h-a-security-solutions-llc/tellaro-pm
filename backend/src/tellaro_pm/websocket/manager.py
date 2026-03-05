"""WebSocket connection manager for agent communication."""

import logging
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

from tellaro_pm.agents.schemas import WorkItemStatus
from tellaro_pm.agents.service import agent_service, work_dispatch_service

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections from agent daemons.

    Each agent maintains a single persistent WebSocket connection used to:
    - Receive heartbeats and status updates
    - Push persona configurations
    - Dispatch work items in real-time
    - Receive work item progress and results
    """

    def __init__(self) -> None:
        # agent_id → WebSocket
        self._connections: dict[str, WebSocket] = {}
        # agent_id → user_id (for broadcasting to all agents of a user)
        self._agent_user_map: dict[str, str] = {}

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

    async def handle_message(self, agent_id: str, message: dict[str, Any]) -> None:
        """Route an incoming WebSocket message from an agent to the appropriate handler."""
        msg_type = message.get("type")

        if msg_type == "heartbeat":
            await self._handle_heartbeat(agent_id, message)
        elif msg_type == "work_item_update":
            await self._handle_work_item_update(agent_id, message)
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

        await self.send_to_agent(
            agent_id,
            {
                "type": "work_item_ack",
                "work_item_id": item_id,
                "status": updated.get("status"),
            },
        )

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
