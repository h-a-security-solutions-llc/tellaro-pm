"""Tellaro Agent - CLI entry point and daemon startup."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import signal
import sys
from typing import Any, cast

from tellaro_agent.claude import ClaudeCodeManager
from tellaro_agent.config import AgentSettings, get_agent_settings
from tellaro_agent.connection import AgentConnection
from tellaro_agent.discovery import SkillDiscovery
from tellaro_agent.personas import PersonaManager
from tellaro_agent.worker import WorkerPool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Tellaro PM Agent - manages Claude Code on your behalf")
    parser.add_argument("--backend-url", help="WebSocket URL for backend connection")
    parser.add_argument("--backend-api-url", help="HTTP URL for backend API")
    parser.add_argument("--agent-name", help="Human-readable agent name")
    parser.add_argument("--agent-token", help="Authentication token")
    parser.add_argument("--claude-executable", help="Path to Claude Code executable")
    parser.add_argument("--log-level", help="Log level (DEBUG, INFO, WARNING, ERROR)")
    return parser.parse_args()


class AgentDaemon:
    """Top-level orchestrator that wires all subsystems together and runs the agent loop."""

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._stop_event = asyncio.Event()

        # Subsystems
        self._connection = AgentConnection(settings)
        self._claude_manager = ClaudeCodeManager(settings.CLAUDE_EXECUTABLE)
        self._persona_manager = PersonaManager()
        self._discovery = SkillDiscovery(settings.CLAUDE_EXECUTABLE)
        self._worker_pool = WorkerPool(self._claude_manager, self._persona_manager, self._connection)

        # Register message handler
        self._connection.on_message(self._handle_message)

    async def start(self) -> None:
        """Run the full agent lifecycle: connect, discover, register, main loop, shutdown."""
        print(f"Tellaro Agent '{self._settings.AGENT_NAME}' starting...")
        print(f"  Backend: {self._settings.BACKEND_URL}")
        print(f"  Claude:  {self._settings.CLAUDE_EXECUTABLE}")

        # Install signal handlers
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self._handle_signal)

        # Run discovery scan before connecting
        print("[agent] Running capability discovery...")
        capabilities = await self._discovery.get_capabilities()
        skills_count = len(cast("list[object]", capabilities["skills"])) if "skills" in capabilities else 0
        profiles_count = len(cast("list[object]", capabilities["profiles"])) if "profiles" in capabilities else 0
        print(
            f"[agent] Discovered: {skills_count} skill(s), "
            f"{profiles_count} profile(s), "
            f"Claude version: {capabilities.get('claude_version', 'unknown')}"
        )

        # Start the connection + heartbeat + main loop concurrently
        tasks: list[asyncio.Task[None]] = [
            asyncio.create_task(self._connection_loop(), name="connection_loop"),
            asyncio.create_task(self._heartbeat_loop(), name="heartbeat_loop"),
            asyncio.create_task(self._registration_loop(capabilities), name="registration"),
        ]

        # Wait until stop is requested
        await self._stop_event.wait()

        # Shutdown
        print("[agent] Shutting down...")
        await self._shutdown(tasks)
        print("Agent stopped.")

    def _handle_signal(self) -> None:
        print("\nShutting down...")
        self._stop_event.set()

    # -- Connection management -----------------------------------------------

    async def _connection_loop(self) -> None:
        """Runs the WebSocket reconnect loop until the stop event fires."""
        with contextlib.suppress(asyncio.CancelledError):
            await self._connection.reconnect_loop()

    async def _registration_loop(self, capabilities: dict[str, object]) -> None:
        """Wait for a connection, then register the agent with the backend."""
        try:
            # Wait until connected
            while not self._connection.is_connected and not self._stop_event.is_set():
                await asyncio.sleep(0.5)

            if self._stop_event.is_set():
                return

            # Send registration message with capabilities
            await self._connection.send({
                "type": "agent_register",
                "agent_name": self._settings.AGENT_NAME,
                "capabilities": capabilities,
            })
            print("[agent] Registration sent to backend")

        except asyncio.CancelledError:
            pass

    # -- Heartbeat -----------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats to the backend."""
        interval = self._settings.HEARTBEAT_INTERVAL_SECONDS
        try:
            while not self._stop_event.is_set():
                if self._connection.is_connected:
                    running = await self._claude_manager.list_running()
                    await self._connection.send({
                        "type": "heartbeat",
                        "agent_name": self._settings.AGENT_NAME,
                        "active_work_items": self._worker_pool.active_count,
                        "max_concurrent": self._worker_pool.max_concurrent,
                        "running_instances": len(running),
                    })
                # Use wait with timeout instead of sleep so we can react to stop_event quickly
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                    break  # stop_event was set
                except TimeoutError:
                    pass  # interval elapsed, send next heartbeat
        except asyncio.CancelledError:
            pass

    # -- Message dispatching -------------------------------------------------

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Dispatch incoming WebSocket messages to the appropriate handler."""
        msg_type = message.get("type", "")

        match msg_type:
            case "work_item_assigned":
                await self._handle_work_item_assigned(message)
            case "work_item_cancel":
                await self._handle_work_item_cancel(message)
            case "persona_update":
                await self._handle_persona_update(message)
            case "ping":
                await self._handle_ping(message)
            case "agent_registered":
                print(f"[agent] Backend acknowledged registration: {message.get('message', '')}")
            case "error":
                print(f"[agent] Backend error: {message.get('message', message)}")
            case _:
                print(f"[agent] Unknown message type: {msg_type}")

    async def _handle_work_item_assigned(self, message: dict[str, Any]) -> None:
        """Handle a new work item dispatched from the backend."""
        raw: object = message.get("work_item", message)
        work_item: dict[str, Any] = cast("dict[str, Any]", raw) if isinstance(raw, dict) else message
        work_item_id = work_item.get("work_item_id", "unknown")
        print(f"[agent] Work item assigned: {work_item_id}")
        await self._worker_pool.execute_work_item(work_item)

    async def _handle_work_item_cancel(self, message: dict[str, Any]) -> None:
        """Handle a cancellation request from the backend."""
        work_item_id = str(message.get("work_item_id", ""))
        if work_item_id:
            print(f"[agent] Cancelling work item: {work_item_id}")
            await self._worker_pool.cancel_work_item(work_item_id)

    async def _handle_persona_update(self, message: dict[str, Any]) -> None:
        """Handle persona configuration updates from the backend."""
        raw_personas: object = message.get("personas", [])
        if not isinstance(raw_personas, list):
            print(f"[agent] Invalid persona_update payload: {message}")
            return
        personas = cast("list[dict[str, Any]]", raw_personas)
        self._persona_manager.update_from_backend(personas)

    async def _handle_ping(self, message: dict[str, Any]) -> None:
        """Respond to a ping with a pong."""
        await self._connection.send({
            "type": "pong",
            "agent_name": self._settings.AGENT_NAME,
            "echo": message.get("data"),
        })

    # -- Shutdown ------------------------------------------------------------

    async def _shutdown(self, tasks: list[asyncio.Task[None]]) -> None:
        """Cancel all work, disconnect, and clean up background tasks."""
        # Cancel all running work items
        await self._worker_pool.cancel_all()

        # Kill any remaining Claude instances
        await self._claude_manager.kill_all()

        # Disconnect from backend
        await self._connection.disconnect()

        # Cancel background tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def run_agent() -> None:
    args = parse_args()

    base_settings = get_agent_settings()
    cli_overrides: dict[str, str | int | bool | None] = {
        "backend_url": args.backend_url,
        "backend_api_url": args.backend_api_url,
        "agent_name": args.agent_name,
        "agent_token": args.agent_token,
        "claude_executable": args.claude_executable,
        "log_level": args.log_level,
    }
    settings = base_settings.override_from_cli(**cli_overrides)

    if not settings.AGENT_NAME:
        print("Error: --agent-name is required (or set AGENT_NAME env var)", file=sys.stderr)
        sys.exit(1)

    daemon = AgentDaemon(settings)
    await daemon.start()


def main() -> None:
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run_agent())


if __name__ == "__main__":
    main()
