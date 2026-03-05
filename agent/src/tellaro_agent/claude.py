"""Claude Code subprocess management."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class InstanceStatus(Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ClaudeInstance:
    """A running (or finished) Claude Code subprocess."""

    instance_id: str
    working_directory: str
    _process: asyncio.subprocess.Process
    _status: InstanceStatus = field(default=InstanceStatus.RUNNING, init=False)

    @property
    def pid(self) -> int | None:
        return self._process.pid

    @property
    def status(self) -> InstanceStatus:
        if self._status == InstanceStatus.RUNNING and self._process.returncode is not None:
            self._status = InstanceStatus.COMPLETED if self._process.returncode == 0 else InstanceStatus.FAILED
        return self._status

    async def send_input(self, text: str) -> None:
        """Write text to the subprocess stdin."""
        stdin = self._process.stdin
        if stdin is None:
            print(f"[claude:{self.instance_id}] stdin not available")
            return
        try:
            stdin.write(text.encode())
            await stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            print(f"[claude:{self.instance_id}] stdin write failed: {exc}")

    async def read_output(self) -> AsyncIterator[str]:
        """Stream stdout line-by-line as an async iterator."""
        stdout = self._process.stdout
        if stdout is None:
            return
        while True:
            line = await stdout.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

    async def read_stderr(self) -> AsyncIterator[str]:
        """Stream stderr line-by-line as an async iterator."""
        stderr = self._process.stderr
        if stderr is None:
            return
        while True:
            line = await stderr.readline()
            if not line:
                break
            yield line.decode("utf-8", errors="replace")

    async def wait(self) -> int:
        """Wait for the subprocess to finish and return its exit code."""
        returncode = await self._process.wait()
        self._status = InstanceStatus.COMPLETED if returncode == 0 else InstanceStatus.FAILED
        return returncode

    async def cancel(self) -> None:
        """Terminate the subprocess."""
        if self._process.returncode is not None:
            return
        try:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
        except ProcessLookupError:
            pass
        self._status = InstanceStatus.FAILED
        print(f"[claude:{self.instance_id}] Cancelled (pid={self.pid})")


class ClaudeCodeManager:
    """Manages spawning and tracking Claude Code subprocess instances."""

    def __init__(self, executable: str) -> None:
        self._executable = executable
        self._instances: dict[str, ClaudeInstance] = {}

    async def spawn_instance(
        self,
        working_directory: str,
        persona_prompt: str | None = None,
        skill: str | None = None,
    ) -> ClaudeInstance:
        """Spawn a new Claude Code subprocess.

        Args:
            working_directory: The directory in which Claude Code should operate.
            persona_prompt: Optional system prompt piped via stdin to configure persona.
            skill: Optional skill name (currently unused; reserved for future skill routing).

        Returns:
            A ``ClaudeInstance`` tracking the subprocess.
        """
        instance_id = uuid.uuid4().hex[:12]
        cmd: list[str] = [self._executable, "--dangerously-skip-permissions"]

        if persona_prompt:
            cmd.extend(["--system-prompt", persona_prompt])

        print(f"[claude-mgr] Spawning instance {instance_id} in {working_directory}")
        print(f"[claude-mgr] Command: {' '.join(cmd)}")

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_directory,
        )

        instance = ClaudeInstance(
            instance_id=instance_id,
            working_directory=working_directory,
            _process=process,
        )
        self._instances[instance_id] = instance
        print(f"[claude-mgr] Instance {instance_id} started (pid={process.pid})")
        return instance

    async def list_running(self) -> list[ClaudeInstance]:
        """Return all instances that are still running."""
        running: list[ClaudeInstance] = []
        for instance in self._instances.values():
            if instance.status == InstanceStatus.RUNNING:
                running.append(instance)
        return running

    async def kill_instance(self, instance_id: str) -> None:
        """Cancel and remove a specific instance."""
        instance = self._instances.get(instance_id)
        if instance is None:
            print(f"[claude-mgr] Instance {instance_id} not found")
            return
        await instance.cancel()
        del self._instances[instance_id]

    async def kill_all(self) -> None:
        """Cancel all tracked instances."""
        ids = list(self._instances.keys())
        for instance_id in ids:
            await self.kill_instance(instance_id)
        print("[claude-mgr] All instances killed")
