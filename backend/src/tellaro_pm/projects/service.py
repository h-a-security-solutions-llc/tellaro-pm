"""Service layer for project CRUD and membership management."""

from tellaro_pm.core.models import BaseDocument
from tellaro_pm.core.opensearch import PROJECTS_INDEX, CRUDService
from tellaro_pm.projects.schemas import ProjectCreate, ProjectStatus, ProjectUpdate


class ProjectService:
    """Manages projects in OpenSearch."""

    def __init__(self) -> None:
        self._crud = CRUDService(PROJECTS_INDEX)

    def create(self, owner_id: str, data: ProjectCreate) -> dict[str, object]:
        """Create a new project owned by *owner_id*."""
        doc = BaseDocument()
        project: dict[str, object] = {
            **doc.to_opensearch(),
            "name": data.name,
            "description": data.description,
            "owner_id": owner_id,
            "member_ids": [owner_id],
            "github_repos": [repo.model_dump() for repo in data.github_repos],
            "status": ProjectStatus.ACTIVE,
        }
        self._crud.create(doc.id, project)
        return project

    def get(self, project_id: str) -> dict[str, object] | None:
        """Retrieve a single project by ID."""
        return self._crud.get(project_id)

    def list_for_user(self, user_id: str, *, include_archived: bool = False) -> list[dict[str, object]]:
        """Return projects where *user_id* is the owner **or** a member."""
        must_clauses: list[dict[str, object]] = [
            {
                "bool": {
                    "should": [
                        {"term": {"owner_id": user_id}},
                        {"term": {"member_ids": user_id}},
                    ],
                    "minimum_should_match": 1,
                }
            },
        ]
        if not include_archived:
            must_clauses.append({"term": {"status": ProjectStatus.ACTIVE}})

        query: dict[str, object] = {"query": {"bool": {"must": must_clauses}}}
        return self._crud.search(query, size=200)

    def update(self, project_id: str, data: ProjectUpdate) -> dict[str, object]:
        """Partially update a project. Returns the full updated document."""
        updates = data.model_dump(exclude_unset=True)
        if "github_repos" in updates and updates["github_repos"] is not None:
            updates["github_repos"] = [repo.model_dump() for repo in data.github_repos or []]

        doc = BaseDocument()
        updates["updated_at"] = doc.updated_at

        self._crud.update(project_id, updates)
        result = self._crud.get(project_id)
        assert result is not None
        return result

    def delete(self, project_id: str) -> bool:
        """Delete a project by ID. Returns ``True`` if it existed."""
        return self._crud.delete(project_id)

    def add_member(self, project_id: str, user_id: str) -> dict[str, object]:
        """Add *user_id* to the project's member list (idempotent)."""
        project = self._crud.get(project_id)
        if project is None:
            msg = f"Project {project_id} not found"
            raise ValueError(msg)

        member_ids: list[str] = list(project.get("member_ids") or [])  # type: ignore[arg-type]
        if user_id not in member_ids:
            member_ids.append(user_id)

        doc = BaseDocument()
        self._crud.update(project_id, {"member_ids": member_ids, "updated_at": doc.updated_at})
        result = self._crud.get(project_id)
        assert result is not None
        return result

    def remove_member(self, project_id: str, user_id: str) -> dict[str, object]:
        """Remove *user_id* from the project's member list."""
        project = self._crud.get(project_id)
        if project is None:
            msg = f"Project {project_id} not found"
            raise ValueError(msg)

        member_ids: list[str] = list(project.get("member_ids") or [])  # type: ignore[arg-type]
        if user_id in member_ids:
            member_ids.remove(user_id)

        doc = BaseDocument()
        self._crud.update(project_id, {"member_ids": member_ids, "updated_at": doc.updated_at})
        result = self._crud.get(project_id)
        assert result is not None
        return result


project_service = ProjectService()
