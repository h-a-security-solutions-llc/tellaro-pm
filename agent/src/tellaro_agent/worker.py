"""Work item execution - picks up and executes dispatched work."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tellaro_agent.claude import ClaudeCodeManager, ClaudeInstance
    from tellaro_agent.connection import AgentConnection
    from tellaro_agent.personas import PersonaManager


class WorkerPool:
    """Manages concurrent execution of work items using Claude Code instances.

    Each work item is paired with a persona configuration, a Claude Code
    subprocess is spawned, and output is streamed back to the backend.
    """

    def __init__(
        self,
        claude_manager: ClaudeCodeManager,
        persona_manager: PersonaManager,
        connection: AgentConnection,
    ) -> None:
        self._claude_manager = claude_manager
        self._persona_manager = persona_manager
        self._connection = connection
        self._active_items: dict[str, ClaudeInstance] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}

    @property
    def max_concurrent(self) -> int:
        """Maximum number of concurrent work items, based on persona configuration."""
        total = self._persona_manager.total_max_concurrent
        return max(total, 1)

    @property
    def active_count(self) -> int:
        return len(self._active_items)

    async def execute_work_item(self, work_item: dict[str, Any]) -> None:
        """Start a Claude Code instance for the given work item.

        The work item dict must include: ``work_item_id``, ``persona_id``,
        ``working_directory``, and ``prompt``.
        """
        work_item_id = str(work_item.get("work_item_id", ""))
        persona_id = str(work_item.get("persona_id", ""))
        working_directory = str(work_item.get("working_directory", "."))
        prompt = str(work_item.get("prompt", ""))

        if not work_item_id:
            print("[worker] Received work item without id, ignoring")
            return

        if work_item_id in self._active_items:
            print(f"[worker] Work item {work_item_id} already running, ignoring duplicate")
            return

        if self.active_count >= self.max_concurrent:
            print(f"[worker] At capacity ({self.active_count}/{self.max_concurrent}), rejecting {work_item_id}")
            await self._connection.send({
                "type": "work_item_rejected",
                "work_item_id": work_item_id,
                "reason": "agent_at_capacity",
            })
            return

        # Build the system prompt from persona config
        system_prompt = self._persona_manager.get_system_prompt(persona_id)
        persona = self._persona_manager.get_persona(persona_id)
        skill = persona.skill if persona else None

        # Notify backend that we are starting
        await self._connection.send({
            "type": "work_item_status",
            "work_item_id": work_item_id,
            "status": "running",
        })

        try:
            instance = await self._claude_manager.spawn_instance(
                working_directory=working_directory,
                persona_prompt=system_prompt or None,
                skill=skill,
            )
        except OSError as exc:
            print(f"[worker] Failed to spawn Claude for {work_item_id}: {exc}")
            await self._connection.send({
                "type": "work_item_status",
                "work_item_id": work_item_id,
                "status": "failed",
                "error": str(exc),
            })
            return

        self._active_items[work_item_id] = instance

        # Send the prompt as input
        if prompt:
            await instance.send_input(prompt + "\n")

        # Start streaming task
        task = asyncio.create_task(self._stream_and_wait(work_item_id, instance))
        self._tasks[work_item_id] = task

    async def cancel_work_item(self, work_item_id: str) -> None:
        """Cancel a running work item."""
        instance = self._active_items.get(work_item_id)
        if instance is None:
            print(f"[worker] Work item {work_item_id} not found for cancellation")
            return

        print(f"[worker] Cancelling work item {work_item_id}")

        # Cancel the streaming task
        task = self._tasks.get(work_item_id)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        await instance.cancel()
        self._active_items.pop(work_item_id, None)
        self._tasks.pop(work_item_id, None)

        await self._connection.send({
            "type": "work_item_status",
            "work_item_id": work_item_id,
            "status": "cancelled",
        })

    async def cancel_all(self) -> None:
        """Cancel all running work items."""
        ids = list(self._active_items.keys())
        for work_item_id in ids:
            await self.cancel_work_item(work_item_id)

    # -- Internal ------------------------------------------------------------

    async def _stream_and_wait(self, work_item_id: str, instance: ClaudeInstance) -> None:
        """Stream output from a Claude instance back to the backend, then report completion."""
        try:
            async for line in instance.read_output():
                await self._connection.send({
                    "type": "work_item_output",
                    "work_item_id": work_item_id,
                    "stream": "stdout",
                    "data": line,
                })

            exit_code = await instance.wait()
            status = "completed" if exit_code == 0 else "failed"
            print(f"[worker] Work item {work_item_id} finished with exit code {exit_code}")

            await self._connection.send({
                "type": "work_item_status",
                "work_item_id": work_item_id,
                "status": status,
                "exit_code": exit_code,
            })

        except asyncio.CancelledError:
            print(f"[worker] Streaming cancelled for {work_item_id}")
            raise

        except Exception as exc:
            print(f"[worker] Error streaming work item {work_item_id}: {exc}")
            await self._connection.send({
                "type": "work_item_status",
                "work_item_id": work_item_id,
                "status": "failed",
                "error": str(exc),
            })

        finally:
            self._active_items.pop(work_item_id, None)
            self._tasks.pop(work_item_id, None)
