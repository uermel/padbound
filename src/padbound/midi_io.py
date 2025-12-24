"""
MIDI I/O with background threading for input processing.

This module provides thread-safe MIDI communication with non-blocking
input processing using a background thread.
"""

import queue
import threading
import time
from typing import Callable, Optional

import mido

from padbound.logging_config import get_logger

logger = get_logger(__name__)


class MIDIInterface:
    """
    Thread-safe MIDI interface with background input processing.

    Uses a background thread to read MIDI input without blocking,
    queuing messages for processing by the main thread.
    """

    def __init__(self, on_message: Callable[[mido.Message], None]):
        """
        Initialize MIDI interface.

        Args:
            on_message: Callback for incoming MIDI messages
        """
        self._on_message = on_message

        # Ports
        self._input_port: Optional[mido.ports.BaseInput] = None
        self._output_port: Optional[mido.ports.BaseOutput] = None
        self._input_port_name: Optional[str] = None
        self._output_port_name: Optional[str] = None

        # Threading components
        self._running = threading.Event()
        self._input_thread: Optional[threading.Thread] = None
        self._message_queue: queue.Queue = queue.Queue(maxsize=1000)

        # Thread-safe port access
        self._port_lock = threading.Lock()

        # Statistics
        self._dropped_messages = 0
        self._processed_messages = 0

    @property
    def is_connected(self) -> bool:
        """Check if MIDI ports are connected."""
        with self._port_lock:
            return self._input_port is not None or self._output_port is not None

    @property
    def input_port_name(self) -> Optional[str]:
        """Get connected input port name."""
        return self._input_port_name

    @property
    def output_port_name(self) -> Optional[str]:
        """Get connected output port name."""
        return self._output_port_name

    def connect(self, input_port_name: Optional[str] = None, output_port_name: Optional[str] = None) -> None:
        """
        Connect to MIDI ports and start input thread.

        Args:
            input_port_name: Input port name (None to skip input)
            output_port_name: Output port name (None to skip output)

        Raises:
            ValueError: If both port names are None
            IOError: If ports cannot be opened
        """
        if input_port_name is None and output_port_name is None:
            raise ValueError("At least one port (input or output) must be specified")

        # Open ports
        with self._port_lock:
            try:
                if input_port_name:
                    self._input_port = mido.open_input(input_port_name)
                    self._input_port_name = input_port_name
                    logger.info(f"Opened MIDI input port: {input_port_name}")

                if output_port_name:
                    self._output_port = mido.open_output(output_port_name)
                    self._output_port_name = output_port_name
                    logger.info(f"Opened MIDI output port: {output_port_name}")

            except Exception as e:
                # Clean up if partial connection
                if self._input_port:
                    self._input_port.close()
                    self._input_port = None
                if self._output_port:
                    self._output_port.close()
                    self._output_port = None
                raise IOError(f"Failed to open MIDI ports: {e}") from e

        # Start input thread if we have an input port
        if self._input_port:
            self._running.set()
            self._input_thread = threading.Thread(target=self._input_loop, daemon=True, name="MIDIInputThread")
            self._input_thread.start()
            logger.debug("Started MIDI input thread")

    def disconnect(self) -> None:
        """Stop input thread and close MIDI ports."""
        # Stop input thread
        if self._input_thread and self._input_thread.is_alive():
            logger.debug("Stopping MIDI input thread...")
            self._running.clear()
            self._input_thread.join(timeout=2.0)

            if self._input_thread.is_alive():
                logger.warning("Input thread did not stop gracefully")

            self._input_thread = None

        # Close ports
        with self._port_lock:
            if self._input_port:
                try:
                    self._input_port.close()
                    logger.info(f"Closed MIDI input port: {self._input_port_name}")
                except Exception as e:
                    logger.error(f"Error closing input port: {e}")
                finally:
                    self._input_port = None
                    self._input_port_name = None

            if self._output_port:
                try:
                    self._output_port.close()
                    logger.info(f"Closed MIDI output port: {self._output_port_name}")
                except Exception as e:
                    logger.error(f"Error closing output port: {e}")
                finally:
                    self._output_port = None
                    self._output_port_name = None

        # Process any remaining queued messages
        self._drain_queue()

        logger.debug(f"MIDI interface disconnected. Stats: {self.get_stats()}")

    def _input_loop(self) -> None:
        """
        Background thread: read MIDI input and queue messages.

        Uses iter_pending() for non-blocking reads with low latency.
        """
        logger.debug("MIDI input loop started")

        while self._running.is_set():
            try:
                with self._port_lock:
                    if not self._input_port:
                        break

                    # iter_pending() returns immediately with all available messages
                    for msg in self._input_port.iter_pending():
                        try:
                            self._message_queue.put_nowait(msg)
                        except queue.Full:
                            self._dropped_messages += 1
                            if self._dropped_messages % 100 == 0:
                                logger.warning(f"Dropped {self._dropped_messages} MIDI messages (queue full)")

                # Small sleep to prevent CPU spinning
                # iter_pending() is non-blocking, so we need this
                time.sleep(0.001)  # 1ms

            except Exception as e:
                logger.exception(f"Error in MIDI input loop: {e}")
                # Continue running unless stop requested

        logger.debug("MIDI input loop stopped")

    def process_pending_messages(self) -> int:
        """
        Process all queued MIDI messages (call from main thread).

        Returns:
            Number of messages processed
        """
        count = 0

        while True:
            try:
                msg = self._message_queue.get_nowait()
                logger.debug(f"Received MIDI message: {msg}")
                self._on_message(msg)
                self._processed_messages += 1
                count += 1
            except queue.Empty:
                break
            except Exception as e:
                logger.exception(f"Error processing MIDI message: {e}")

        return count

    def _drain_queue(self) -> None:
        """Process remaining messages in queue."""
        remaining = self.process_pending_messages()
        if remaining > 0:
            logger.debug(f"Processed {remaining} remaining messages on shutdown")

    def send_message(self, msg: mido.Message) -> bool:
        """
        Send MIDI message to output port (thread-safe).

        Args:
            msg: MIDI message to send

        Returns:
            True if sent successfully, False otherwise
        """
        with self._port_lock:
            if not self._output_port:
                logger.warning("Cannot send message: no output port connected")
                return False

            try:
                self._output_port.send(msg)
                return True
            except Exception as e:
                logger.error(f"Error sending MIDI message: {e}")
                return False

    def receive_message(self, timeout: float = 0.5) -> Optional[mido.Message]:
        """
        Receive a single MIDI message with timeout.

        Useful during initialization for query/response patterns (e.g., SysEx).
        Pulls directly from the message queue.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            MIDI message or None if timeout
        """
        try:
            msg = self._message_queue.get(block=True, timeout=timeout)
            logger.debug(f"Received MIDI message (sync): {msg}")
            return msg
        except queue.Empty:
            return None

    def get_stats(self) -> dict[str, int]:
        """
        Get I/O statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            "processed": self._processed_messages,
            "dropped": self._dropped_messages,
            "queued": self._message_queue.qsize(),
        }

    # Port discovery utilities

    @staticmethod
    def list_input_ports() -> list[str]:
        """
        List available MIDI input ports.

        Returns:
            List of input port names
        """
        try:
            return mido.get_input_names()
        except Exception as e:
            logger.error(f"Failed to list input ports: {e}")
            return []

    @staticmethod
    def list_output_ports() -> list[str]:
        """
        List available MIDI output ports.

        Returns:
            List of output port names
        """
        try:
            return mido.get_output_names()
        except Exception as e:
            logger.error(f"Failed to list output ports: {e}")
            return []

    @staticmethod
    def find_ports(pattern: str) -> tuple[list[str], list[str]]:
        """
        Find ports matching pattern.

        Args:
            pattern: String to search for in port names (case-insensitive)

        Returns:
            (input_ports, output_ports) tuple with matching names
        """
        pattern_lower = pattern.lower()

        input_ports = [name for name in MIDIInterface.list_input_ports() if pattern_lower in name.lower()]

        output_ports = [name for name in MIDIInterface.list_output_ports() if pattern_lower in name.lower()]

        return (input_ports, output_ports)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect."""
        self.disconnect()
        return False
