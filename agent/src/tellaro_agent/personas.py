"""Persona management - receives persona configs from backend via WebSocket."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PersonaConfig:
    """A persona configuration pushed from the Tellaro PM backend."""

    persona_id: str
    name: str
    system_prompt: str
    skill: str | None = None
    max_concurrent: int = 1
    active: bool = True
    metadata: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())


class PersonaManager:
    """Tracks persona configurations received from the backend.

    Personas are pushed from the backend via WebSocket messages and stored
    locally.  The agent uses them to configure Claude Code instances before
    dispatching work items.
    """

    def __init__(self) -> None:
        self._personas: dict[str, PersonaConfig] = {}

    def update_from_backend(self, personas: list[dict[str, Any]]) -> None:
        """Replace the local persona set with configurations pushed from the backend.

        Each dict in *personas* must contain at least ``persona_id``, ``name``,
        and ``system_prompt``.  Unknown keys are stored in ``metadata``.
        """
        new_personas: dict[str, PersonaConfig] = {}
        for raw in personas:
            persona_id = str(raw.get("persona_id", ""))
            if not persona_id:
                print(f"[personas] Skipping persona with missing id: {raw}")
                continue

            new_personas[persona_id] = PersonaConfig(
                persona_id=persona_id,
                name=str(raw.get("name", "Unnamed")),
                system_prompt=str(raw.get("system_prompt", "")),
                skill=raw.get("skill"),
                max_concurrent=int(raw.get("max_concurrent", 1)),
                active=bool(raw.get("active", True)),
                metadata={k: v for k, v in raw.items() if k not in {
                    "persona_id", "name", "system_prompt", "skill", "max_concurrent", "active",
                }},
            )

        removed = set(self._personas.keys()) - set(new_personas.keys())
        added = set(new_personas.keys()) - set(self._personas.keys())
        if removed:
            print(f"[personas] Removed: {removed}")
        if added:
            print(f"[personas] Added: {added}")

        self._personas = new_personas
        print(f"[personas] Updated: {len(self._personas)} persona(s) active")

    def get_persona(self, persona_id: str) -> PersonaConfig | None:
        """Return the persona config for the given id, or ``None``."""
        return self._personas.get(persona_id)

    def get_system_prompt(self, persona_id: str) -> str:
        """Build the system prompt string for a given persona.

        Returns an empty string if the persona is not found.
        """
        persona = self._personas.get(persona_id)
        if persona is None:
            return ""

        parts: list[str] = []
        parts.append(f"You are the '{persona.name}' persona in the Tellaro PM system.")
        if persona.system_prompt:
            parts.append(persona.system_prompt)
        return "\n\n".join(parts)

    def list_active(self) -> list[PersonaConfig]:
        """Return all personas that are currently marked active."""
        return [p for p in self._personas.values() if p.active]

    @property
    def total_max_concurrent(self) -> int:
        """Sum of max_concurrent across all active personas."""
        return sum(p.max_concurrent for p in self._personas.values() if p.active)
