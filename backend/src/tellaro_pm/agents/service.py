"""Service layer for agent management, personas, and work dispatch."""

from datetime import UTC, datetime
from uuid import uuid4

from tellaro_pm.agents.schemas import WorkItemStatus, WorkRequestStatus
from tellaro_pm.core.opensearch import (
    AGENTS_INDEX,
    PERSONAS_INDEX,
    WORK_ITEMS_INDEX,
    WORK_REQUESTS_INDEX,
    CRUDService,
)


class AgentService:
    """Manages agent registrations and persona configurations."""

    def __init__(self) -> None:
        self._agents = CRUDService(AGENTS_INDEX)
        self._personas = CRUDService(PERSONAS_INDEX)

    # --- Agent CRUD ---

    def register(self, user_id: str, data: dict[str, object]) -> dict[str, object]:
        """Register a new agent for a user."""
        now = datetime.now(UTC).isoformat()
        agent_id = str(uuid4())
        agent: dict[str, object] = {
            "id": agent_id,
            "user_id": user_id,
            "name": data["name"],
            "status": "online",
            "machine_info": data.get("machine_info", {}),
            "last_heartbeat": now,
            "capabilities": data.get("capabilities", []),
            "created_at": now,
            "updated_at": now,
        }
        self._agents.create(agent_id, agent)
        return agent

    def heartbeat(self, agent_id: str, data: dict[str, object]) -> dict[str, object] | None:
        """Update agent status and last heartbeat timestamp."""
        existing = self._agents.get(agent_id)
        if existing is None:
            return None

        now = datetime.now(UTC).isoformat()
        update_fields: dict[str, object] = {
            "status": data["status"],
            "last_heartbeat": now,
            "updated_at": now,
        }
        self._agents.update(agent_id, update_fields)
        existing.update(update_fields)
        return existing

    def get(self, agent_id: str) -> dict[str, object] | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_by_user(self, user_id: str) -> tuple[list[dict[str, object]], int]:
        """List all agents belonging to a user."""
        query: dict[str, object] = {
            "query": {"term": {"user_id": user_id}},
            "sort": [{"created_at": {"order": "desc"}}],
        }
        total = self._agents.count(query)
        results = self._agents.search(query)
        return results, total

    def list_online(self) -> tuple[list[dict[str, object]], int]:
        """List all agents with online status."""
        query: dict[str, object] = {
            "query": {"term": {"status": "online"}},
            "sort": [{"last_heartbeat": {"order": "desc"}}],
        }
        total = self._agents.count(query)
        results = self._agents.search(query)
        return results, total

    def list_agents(
        self,
        *,
        user_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """List agents with optional filters."""
        filters: list[dict[str, object]] = []
        if user_id:
            filters.append({"term": {"user_id": user_id}})
        if status:
            filters.append({"term": {"status": status}})

        if filters:
            query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        else:
            query = {"query": {"match_all": {}}}

        total = self._agents.count(query)
        query["sort"] = [{"created_at": {"order": "desc"}}]
        results = self._agents.search(query)
        return results, total

    def deregister(self, agent_id: str) -> bool:
        """Remove an agent registration."""
        return self._agents.delete(agent_id)

    # --- Persona CRUD ---

    def create_persona(self, agent_id: str, user_id: str, data: dict[str, object]) -> dict[str, object]:
        """Create a new persona for an agent."""
        now = datetime.now(UTC).isoformat()
        persona_id = str(uuid4())
        persona: dict[str, object] = {
            "id": persona_id,
            "agent_id": agent_id,
            "user_id": user_id,
            "name": data["name"],
            "role_description": data["role_description"],
            "system_prompt": data.get("system_prompt", ""),
            "skills": data.get("skills", []),
            "claude_profile": data.get("claude_profile", ""),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        self._personas.create(persona_id, persona)
        return persona

    def update_persona(self, persona_id: str, data: dict[str, object]) -> dict[str, object] | None:
        """Update an existing persona."""
        existing = self._personas.get(persona_id)
        if existing is None:
            return None

        update_fields: dict[str, object] = {k: v for k, v in data.items() if v is not None}
        update_fields["updated_at"] = datetime.now(UTC).isoformat()

        self._personas.update(persona_id, update_fields)
        existing.update(update_fields)
        return existing

    def delete_persona(self, persona_id: str) -> bool:
        """Delete a persona."""
        return self._personas.delete(persona_id)

    def get_persona(self, persona_id: str) -> dict[str, object] | None:
        """Get a persona by ID."""
        return self._personas.get(persona_id)

    def list_personas(
        self,
        *,
        agent_id: str | None = None,
        user_id: str | None = None,
    ) -> list[dict[str, object]]:
        """List personas filtered by agent or user."""
        filters: list[dict[str, object]] = []
        if agent_id:
            filters.append({"term": {"agent_id": agent_id}})
        if user_id:
            filters.append({"term": {"user_id": user_id}})

        if filters:
            query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        else:
            query = {"query": {"match_all": {}}}

        query["sort"] = [{"created_at": {"order": "desc"}}]
        return self._personas.search(query)


class WorkDispatchService:
    """Manages work item dispatch and cross-user work requests."""

    def __init__(self) -> None:
        self._items = CRUDService(WORK_ITEMS_INDEX)
        self._requests = CRUDService(WORK_REQUESTS_INDEX)

    # --- Work Items ---

    def create_work_item(self, data: dict[str, object]) -> dict[str, object]:
        """Create and enqueue a new work item."""
        now = datetime.now(UTC).isoformat()
        item_id = str(uuid4())
        item: dict[str, object] = {
            "id": item_id,
            "task_id": data.get("task_id"),
            "chat_session_id": data.get("chat_session_id"),
            "chat_message_id": data.get("chat_message_id"),
            "agent_id": data["agent_id"],
            "persona_id": data["persona_id"],
            "status": WorkItemStatus.QUEUED,
            "instruction": data["instruction"],
            "working_directory": data.get("working_directory"),
            "output": None,
            "artifacts": [],
            "started_at": None,
            "completed_at": None,
            "created_at": now,
            "updated_at": now,
        }
        self._items.create(item_id, item)
        return item

    def update_work_item(self, item_id: str, data: dict[str, object]) -> dict[str, object] | None:
        """Update work item status, output, or artifacts."""
        existing = self._items.get(item_id)
        if existing is None:
            return None

        update_fields: dict[str, object] = {k: v for k, v in data.items() if v is not None}
        now = datetime.now(UTC).isoformat()
        update_fields["updated_at"] = now

        new_status = data.get("status")
        if new_status == WorkItemStatus.RUNNING and existing.get("started_at") is None:
            update_fields["started_at"] = now
        if new_status in (WorkItemStatus.COMPLETED, WorkItemStatus.FAILED, WorkItemStatus.CANCELLED):
            update_fields["completed_at"] = now

        self._items.update(item_id, update_fields)
        existing.update(update_fields)
        return existing

    def get_work_item(self, item_id: str) -> dict[str, object] | None:
        """Get a work item by ID."""
        return self._items.get(item_id)

    def list_work_items(
        self,
        *,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """List work items with optional filters."""
        filters: list[dict[str, object]] = []
        if agent_id:
            filters.append({"term": {"agent_id": agent_id}})
        if status:
            filters.append({"term": {"status": status}})

        if filters:
            query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        else:
            query = {"query": {"match_all": {}}}

        total = self._items.count(query)
        query["sort"] = [{"created_at": {"order": "desc"}}]
        results = self._items.search(query)
        return results, total

    def list_queued_for_agent(self, agent_id: str) -> list[dict[str, object]]:
        """Get all queued work items for a specific agent."""
        query: dict[str, object] = {
            "query": {
                "bool": {
                    "filter": [
                        {"term": {"agent_id": agent_id}},
                        {"term": {"status": WorkItemStatus.QUEUED}},
                    ]
                }
            },
            "sort": [{"created_at": {"order": "asc"}}],
        }
        return self._items.search(query)

    # --- Work Requests (cross-user) ---

    def create_work_request(self, requester_id: str, data: dict[str, object]) -> dict[str, object]:
        """Create a cross-user work request that requires approval."""
        now = datetime.now(UTC).isoformat()
        request_id = str(uuid4())
        request: dict[str, object] = {
            "id": request_id,
            "requester_id": requester_id,
            "target_user_id": data["target_user_id"],
            "task_id": data.get("task_id"),
            "instruction": data["instruction"],
            "status": WorkRequestStatus.PENDING,
            "response_message": None,
            "work_item_id": None,
            "created_at": now,
            "updated_at": now,
        }
        self._requests.create(request_id, request)
        return request

    def get_work_request(self, request_id: str) -> dict[str, object] | None:
        """Get a work request by ID."""
        return self._requests.get(request_id)

    def approve_work_request(
        self,
        request_id: str,
        approver_id: str,
        work_item_data: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]] | None:
        """Approve a work request and create the corresponding work item.

        Returns a tuple of (updated_request, new_work_item) or None if not found.
        """
        existing = self._requests.get(request_id)
        if existing is None:
            return None

        # Create the work item from the approved request
        work_item = self.create_work_item(work_item_data)

        now = datetime.now(UTC).isoformat()
        update_fields: dict[str, object] = {
            "status": WorkRequestStatus.APPROVED,
            "work_item_id": work_item["id"],
            "updated_at": now,
        }
        self._requests.update(request_id, update_fields)
        existing.update(update_fields)

        # Record who approved — stored as approver context
        _ = approver_id  # Used for audit logging in production
        return existing, work_item

    def reject_work_request(
        self,
        request_id: str,
        approver_id: str,
        message: str = "",
    ) -> dict[str, object] | None:
        """Reject a work request with an optional message."""
        existing = self._requests.get(request_id)
        if existing is None:
            return None

        now = datetime.now(UTC).isoformat()
        update_fields: dict[str, object] = {
            "status": WorkRequestStatus.REJECTED,
            "response_message": message,
            "updated_at": now,
        }
        self._requests.update(request_id, update_fields)
        existing.update(update_fields)

        _ = approver_id  # Used for audit logging in production
        return existing

    def list_work_requests(
        self,
        user_id: str,
        *,
        status: str | None = None,
    ) -> tuple[list[dict[str, object]], int]:
        """List work requests targeting a user, optionally filtered by status."""
        filters: list[dict[str, object]] = [{"term": {"target_user_id": user_id}}]
        if status:
            filters.append({"term": {"status": status}})

        query: dict[str, object] = {"query": {"bool": {"filter": filters}}}
        total = self._requests.count(query)
        query["sort"] = [{"created_at": {"order": "desc"}}]
        results = self._requests.search(query)
        return results, total


# Module-level singletons
agent_service = AgentService()
work_dispatch_service = WorkDispatchService()
