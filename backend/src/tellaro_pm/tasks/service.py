"""Service layer for task CRUD, status transitions, and assignment."""

from tellaro_pm.core.models import BaseDocument
from tellaro_pm.core.opensearch import TASKS_INDEX, CRUDService
from tellaro_pm.tasks.schemas import TaskCreate, TaskStatus, TaskUpdate


class TaskService:
    """Manages tasks in OpenSearch."""

    def __init__(self) -> None:
        self._crud = CRUDService(TASKS_INDEX)

    def create(self, data: TaskCreate) -> dict[str, object]:
        """Create a new task within a project."""
        doc = BaseDocument()
        status = TaskStatus.ASSIGNED if data.assignee_id else TaskStatus.BACKLOG
        task: dict[str, object] = {
            **doc.to_opensearch(),
            "project_id": data.project_id,
            "parent_task_id": data.parent_task_id,
            "title": data.title,
            "description": data.description,
            "status": status,
            "priority": data.priority,
            "assignee_id": data.assignee_id,
            "labels": data.labels,
            "github_issue_url": None,
            "github_issue_number": None,
            "github_pr_urls": [],
            "order": 0.0,
        }
        self._crud.create(doc.id, task)
        return task

    def get(self, task_id: str) -> dict[str, object] | None:
        """Retrieve a single task by ID."""
        return self._crud.get(task_id)

    def list_by_project(
        self,
        project_id: str,
        *,
        status_filter: TaskStatus | None = None,
        assignee_id: str | None = None,
    ) -> list[dict[str, object]]:
        """List tasks for a project, optionally filtered by status and/or assignee."""
        must_clauses: list[dict[str, object]] = [{"term": {"project_id": project_id}}]
        if status_filter is not None:
            must_clauses.append({"term": {"status": status_filter}})
        if assignee_id is not None:
            must_clauses.append({"term": {"assignee_id": assignee_id}})

        query: dict[str, object] = {
            "query": {"bool": {"must": must_clauses}},
            "sort": [{"order": {"order": "asc"}}, {"created_at": {"order": "asc"}}],
        }
        return self._crud.search(query, size=500)

    def list_subtasks(self, parent_task_id: str) -> list[dict[str, object]]:
        """List direct children of a parent task."""
        query: dict[str, object] = {
            "query": {"term": {"parent_task_id": parent_task_id}},
            "sort": [{"order": {"order": "asc"}}, {"created_at": {"order": "asc"}}],
        }
        return self._crud.search(query, size=200)

    def update(self, task_id: str, data: TaskUpdate) -> dict[str, object]:
        """Partially update a task. Returns the full updated document."""
        updates = data.model_dump(exclude_unset=True)
        doc = BaseDocument()
        updates["updated_at"] = doc.updated_at

        self._crud.update(task_id, updates)
        result = self._crud.get(task_id)
        assert result is not None
        return result

    def delete(self, task_id: str) -> bool:
        """Delete a task by ID. Returns ``True`` if it existed."""
        return self._crud.delete(task_id)

    def update_status(self, task_id: str, new_status: TaskStatus) -> dict[str, object]:
        """Update only the status field of a task."""
        doc = BaseDocument()
        self._crud.update(task_id, {"status": new_status, "updated_at": doc.updated_at})
        result = self._crud.get(task_id)
        assert result is not None
        return result

    def assign(self, task_id: str, user_id: str | None) -> dict[str, object]:
        """Assign a task to a user (or unassign when *user_id* is ``None``)."""
        updates: dict[str, object] = {"assignee_id": user_id}
        doc = BaseDocument()
        updates["updated_at"] = doc.updated_at

        # Auto-transition from backlog to assigned when someone is assigned
        task = self._crud.get(task_id)
        if task is not None and task.get("status") == TaskStatus.BACKLOG and user_id is not None:
            updates["status"] = TaskStatus.ASSIGNED

        self._crud.update(task_id, updates)
        result = self._crud.get(task_id)
        assert result is not None
        return result


task_service = TaskService()
