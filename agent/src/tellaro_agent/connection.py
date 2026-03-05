"""WebSocket connection to Tellaro PM backend."""

from __future__ import annotations

import asyncio
import contextlib
import json
import uuid
from typing import TYPE_CHECKING, Any

import websockets
import websockets.asyncio.client

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from tellaro_agent.config import AgentSettings


class AgentConnection:
    """Manages the WebSocket connection to the Tellaro PM backend.

    Handles authentication, automatic reconnection with exponential backoff,
    and message send/receive with JSON serialisation.
    """

    def __init__(self, settings: AgentSettings) -> None:
        self._settings = settings
        self._ws: websockets.asyncio.client.ClientConnection | None = None
        self._connection_id: str = ""
        self._is_connected: bool = False
        self._on_message_callbacks: list[Callable[[dict[str, Any]], Awaitable[None]]] = []
        self._reconnect_task: asyncio.Task[None] | None = None
        self._receive_task: asyncio.Task[None] | None = None
        self._should_run: bool = False

        # Exponential backoff parameters
        self._backoff_base: float = 1.0
        self._backoff_max: float = 60.0

    # -- Properties ----------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        return self._is_connected and self._ws is not None

    @property
    def connection_id(self) -> str:
        return self._connection_id

    # -- Callback registration -----------------------------------------------

    def on_message(self, callback: Callable[[dict[str, Any]], Awaitable[None]]) -> None:
        """Register an async callback to be invoked for every received message."""
        self._on_message_callbacks.append(callback)

    # -- Core connection lifecycle -------------------------------------------

    async def connect(self) -> None:
        """Establish a WebSocket connection and authenticate with the backend."""
        url = self._settings.BACKEND_URL
        self._connection_id = uuid.uuid4().hex[:12]

        extra_headers = {
            "Authorization": f"Bearer {self._settings.AGENT_TOKEN}",
            "X-Agent-Name": self._settings.AGENT_NAME,
            "X-Connection-Id": self._connection_id,
        }

        print(f"[connection] Connecting to {url} (id={self._connection_id})...")

        try:
            self._ws = await websockets.asyncio.client.connect(
                url,
                additional_headers=extra_headers,
                open_timeout=10,
                close_timeout=5,
            )
            self._is_connected = True
            print(f"[connection] Connected (id={self._connection_id})")

            # Send auth handshake message
            await self.send({
                "type": "agent_auth",
                "agent_name": self._settings.AGENT_NAME,
                "connection_id": self._connection_id,
            })

        except (OSError, websockets.exceptions.WebSocketException) as exc:
            self._is_connected = False
            self._ws = None
            print(f"[connection] Failed to connect: {exc}")
            raise

    async def disconnect(self) -> None:
        """Gracefully close the WebSocket connection and stop background tasks."""
        self._should_run = False

        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._reconnect_task
            self._reconnect_task = None

        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
            self._receive_task = None

        if self._ws is not None:
            with contextlib.suppress(websockets.exceptions.WebSocketException):
                await self._ws.close()
            self._ws = None

        self._is_connected = False
        print("[connection] Disconnected")

    # -- Send / Receive ------------------------------------------------------

    async def send(self, message: dict[str, Any]) -> None:
        """Send a JSON-encoded message over the WebSocket."""
        if self._ws is None or not self._is_connected:
            print("[connection] Cannot send: not connected")
            return
        try:
            payload = json.dumps(message)
            await self._ws.send(payload)
        except websockets.exceptions.WebSocketException as exc:
            print(f"[connection] Send failed: {exc}")
            self._is_connected = False

    async def receive(self) -> dict[str, Any]:
        """Receive and decode a single JSON message from the WebSocket.

        Raises ``ConnectionError`` if the connection is not open, and propagates
        ``websockets.exceptions.ConnectionClosed`` on unexpected closure.
        """
        if self._ws is None:
            raise ConnectionError("WebSocket is not connected")
        raw = await self._ws.recv()
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data: dict[str, Any] = json.loads(raw)
        return data

    # -- Background loops ----------------------------------------------------

    async def reconnect_loop(self) -> None:
        """Maintain the connection, reconnecting with exponential backoff on failure.

        This coroutine runs indefinitely until ``disconnect()`` is called. It drives
        the receive loop internally; registered ``on_message`` callbacks will be
        invoked for every incoming message.
        """
        self._should_run = True
        backoff = self._backoff_base

        while self._should_run:
            # Connect if not already
            if not self.is_connected:
                try:
                    await self.connect()
                    backoff = self._backoff_base  # reset on success
                except (OSError, websockets.exceptions.WebSocketException):
                    print(f"[connection] Reconnecting in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self._backoff_max)
                    continue

            # Receive loop — runs until the connection drops
            try:
                await self._receive_loop()
            except (
                websockets.exceptions.ConnectionClosed,
                websockets.exceptions.ConnectionClosedError,
                ConnectionError,
            ) as exc:
                print(f"[connection] Connection lost: {exc}")
                self._is_connected = False
                self._ws = None
                if self._should_run:
                    print(f"[connection] Reconnecting in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, self._backoff_max)

    async def _receive_loop(self) -> None:
        """Read messages from the WebSocket and dispatch to callbacks."""
        while self.is_connected and self._should_run:
            message = await self.receive()
            for callback in self._on_message_callbacks:
                try:
                    await callback(message)
                except Exception as exc:
                    print(f"[connection] Callback error: {exc}")
