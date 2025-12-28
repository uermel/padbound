"""
WebSocket server for broadcasting controller state changes.

This module provides a StateBroadcaster class that embeds a WebSocket
server within the Controller to broadcast state changes to connected
debug TUI clients.
"""

import asyncio
import contextlib
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from padbound.logging_config import get_logger

if TYPE_CHECKING:
    from websockets.asyncio.server import Server, ServerConnection

    from padbound.controls import ControlDefinition, ControlState
    from padbound.debug.layout import DebugLayout
    from padbound.debug.messages import FullStateMessage

logger = get_logger(__name__)


class StateBroadcaster:
    """
    WebSocket server for broadcasting controller state changes.

    Runs an async WebSocket server in a background thread. Provides
    thread-safe methods for broadcasting state changes from the main
    Controller thread.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        """
        Initialize the broadcaster.

        Args:
            host: Host to bind the WebSocket server to
            port: Port to bind the WebSocket server to
        """
        self._host = host
        self._port = port
        self._server: Optional["Server"] = None
        self._clients: set["ServerConnection"] = set()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Cached full state for new client connections
        self._cached_full_state: Optional["FullStateMessage"] = None

    @property
    def host(self) -> str:
        """Get the server host."""
        return self._host

    @property
    def port(self) -> int:
        """Get the server port."""
        return self._port

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    @property
    def client_count(self) -> int:
        """Get the number of connected clients."""
        with self._lock:
            return len(self._clients)

    def start(self) -> None:
        """Start the WebSocket server in a background thread."""
        if self._running:
            logger.warning("StateBroadcaster is already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

        # Wait for server to start
        timeout = 5.0
        start_time = datetime.now()
        while self._loop is None and (datetime.now() - start_time).total_seconds() < timeout:
            import time

            time.sleep(0.01)

        if self._loop is None:
            self._running = False
            raise RuntimeError("Failed to start WebSocket server")

        logger.info(f"StateBroadcaster started on ws://{self._host}:{self._port}")

    def stop(self) -> None:
        """Stop the WebSocket server."""
        if not self._running:
            return

        self._running = False

        # Close all client connections
        if self._loop and self._clients:
            future = asyncio.run_coroutine_threadsafe(self._close_all_clients(), self._loop)
            try:
                future.result(timeout=2.0)
            except Exception as e:
                logger.warning(f"Error closing clients: {e}")

        # Stop the server and wait for it to fully close
        if self._server and self._loop:
            self._server.close()
            # Wait for the server to finish its async close tasks
            future = asyncio.run_coroutine_threadsafe(
                self._server.wait_closed(),
                self._loop,
            )
            try:
                future.result(timeout=2.0)
            except Exception as e:
                logger.warning(f"Error waiting for server close: {e}")

        # Stop the event loop
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)

        # Wait for thread to finish
        if self._thread:
            self._thread.join(timeout=2.0)

        self._server = None
        self._loop = None
        self._thread = None
        self._clients.clear()

        logger.info("StateBroadcaster stopped")

    def set_full_state(
        self,
        plugin_name: str,
        layout: Optional["DebugLayout"],
        states: dict[str, "ControlState"],
        definitions: dict[str, "ControlDefinition"],
    ) -> None:
        """
        Cache the full controller state for new client connections.

        This should be called after the controller connects and whenever
        the full state needs to be updated.

        Args:
            plugin_name: Name of the active plugin
            layout: Debug layout from the plugin (or None)
            states: Dictionary of control_id -> ControlState
            definitions: Dictionary of control_id -> ControlDefinition
        """
        from padbound.debug.messages import FullStateMessage

        # Use model_construct() to skip re-validation - nested models are already valid
        self._cached_full_state = FullStateMessage.model_construct(
            type="full_state",
            timestamp=datetime.now(),
            plugin_name=plugin_name,
            layout=layout,
            states=states,
            definitions=definitions,
        )

    def broadcast_state_change(self, control_id: str, state: "ControlState") -> None:
        """
        Broadcast a state change to all connected clients.

        This method is thread-safe and can be called from the main thread.

        Args:
            control_id: ID of the control that changed
            state: New state of the control
        """
        if not self._running or not self._loop:
            return

        from padbound.debug.messages import StateChangeMessage

        # Use model_construct() to skip re-validation - state is already valid
        message = StateChangeMessage.model_construct(
            type="state_change",
            timestamp=datetime.now(),
            control_id=control_id,
            state=state,
        )

        asyncio.run_coroutine_threadsafe(self._broadcast(message.model_dump_json()), self._loop)

    def _run_server(self) -> None:
        """Run the WebSocket server in the background thread."""
        import websockets.asyncio.server

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def serve():
            self._server = await websockets.asyncio.server.serve(
                self._handle_client,
                self._host,
                self._port,
            )
            await self._server.wait_closed()

        try:
            self._loop.run_until_complete(serve())
        except Exception as e:
            if self._running:  # Only log if not intentionally stopped
                logger.error(f"WebSocket server error: {e}")
        finally:
            self._loop.close()

    async def _handle_client(self, websocket: "ServerConnection") -> None:
        """
        Handle a new client connection.

        Args:
            websocket: The WebSocket connection
        """
        with self._lock:
            self._clients.add(websocket)

        logger.debug(f"Debug client connected from {websocket.remote_address}")

        try:
            # Send cached full state to new client
            if self._cached_full_state:
                await websocket.send(self._cached_full_state.model_dump_json())

            # Keep connection open and handle incoming messages
            async for message in websocket:
                # Currently we don't process incoming messages from clients
                # but this could be extended for bidirectional control
                logger.debug(f"Received message from client: {message}")

        except Exception as e:
            logger.debug(f"Client disconnected: {e}")
        finally:
            with self._lock:
                self._clients.discard(websocket)
            logger.debug(f"Debug client disconnected from {websocket.remote_address}")

    async def _broadcast(self, message: str) -> None:
        """
        Broadcast a message to all connected clients.

        Args:
            message: JSON-encoded message to broadcast
        """
        with self._lock:
            clients = self._clients.copy()

        if not clients:
            return

        # Send to all clients, removing any that fail
        failed_clients = []
        for client in clients:
            try:
                await client.send(message)
            except Exception:
                failed_clients.append(client)

        # Clean up failed clients
        if failed_clients:
            with self._lock:
                for client in failed_clients:
                    self._clients.discard(client)

    async def _close_all_clients(self) -> None:
        """Close all client connections."""
        with self._lock:
            clients = self._clients.copy()

        for client in clients:
            with contextlib.suppress(Exception):
                await client.close()
