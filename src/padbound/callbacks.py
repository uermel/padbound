"""
Error-isolated callback dispatch system.

This module provides callback management with error isolation to prevent
callback failures from crashing the system.
"""

import threading
from collections import defaultdict
from typing import Callable, Optional

from padbound.controls import ControlState, ControlType
from padbound.logging_config import get_logger

logger = get_logger(__name__)

# Callback type signatures
GlobalCallback = Callable[[str, ControlState], None]
ControlCallback = Callable[[ControlState], None]
TypeCallback = Callable[[str, ControlState], None]
CategoryCallback = Callable[[str, ControlState], None]  # (control_id, state)
BankCallback = Callable[[str], None]


class CallbackManager:
    """
    Manages callback registration and dispatch with error isolation.

    Supports five types of callbacks:
    1. Global callbacks - fired for any control change
    2. Per-control callbacks - specific control by ID
    3. Type-based callbacks - all toggles, all continuous, etc.
    4. Category-based callbacks - all controls in a category (e.g., "transport", "pad")
    5. Bank change callbacks - per control type

    All callbacks support signal type filtering for multi-signal routing.
    Callbacks are wrapped in error handling to prevent cascade failures.
    """

    def __init__(self):
        """Initialize callback storage with signal type filtering support."""
        # Each callback stored as (callback, signal_type_filter)
        # signal_type_filter=None means fire for all signal types
        self._global_callbacks: list[tuple[GlobalCallback, Optional[str]]] = []
        self._control_callbacks: defaultdict[str, list[tuple[ControlCallback, Optional[str]]]] = defaultdict(list)
        self._type_callbacks: defaultdict[ControlType, list[tuple[TypeCallback, Optional[str]]]] = defaultdict(list)
        self._category_callbacks: defaultdict[str, list[tuple[CategoryCallback, Optional[str]]]] = defaultdict(list)
        self._bank_callbacks: defaultdict[ControlType, list[BankCallback]] = defaultdict(list)

        self._lock = threading.RLock()

    # Registration methods

    def register_global(self, callback: GlobalCallback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for all control changes.

        Args:
            callback: Function(control_id: str, state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        with self._lock:
            self._global_callbacks.append((callback, signal_type))
            logger.debug(f"Registered global callback: {callback.__name__} (signal_type: {signal_type or 'all'})")

    def register_control(self, control_id: str, callback: ControlCallback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for specific control.

        Args:
            control_id: Control identifier
            callback: Function(state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        with self._lock:
            self._control_callbacks[control_id].append((callback, signal_type))
            logger.debug(
                f"Registered callback for control '{control_id}': {callback.__name__} "
                f"(signal_type: {signal_type or 'all'})",
            )

    def register_type(
        self,
        control_type: ControlType,
        callback: TypeCallback,
        signal_type: Optional[str] = None,
    ) -> None:
        """
        Register callback for all controls of a type.

        Args:
            control_type: Type of controls
            callback: Function(control_id: str, state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        with self._lock:
            self._type_callbacks[control_type].append((callback, signal_type))
            logger.debug(
                f"Registered callback for type '{control_type}': {callback.__name__} "
                f"(signal_type: {signal_type or 'all'})",
            )

    def register_category(self, category: str, callback: CategoryCallback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for all controls in a category.

        Args:
            category: Category name (e.g., "transport", "navigation", "pad")
            callback: Function(control_id: str, state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        with self._lock:
            self._category_callbacks[category].append((callback, signal_type))
            logger.debug(
                f"Registered callback for category '{category}': {callback.__name__} "
                f"(signal_type: {signal_type or 'all'})",
            )

    def register_bank(self, control_type: ControlType, callback: BankCallback) -> None:
        """
        Register callback for bank changes.

        Args:
            control_type: Type of controls in bank
            callback: Function(bank_id: str) -> None
        """
        with self._lock:
            self._bank_callbacks[control_type].append(callback)
            logger.debug(f"Registered bank callback for type '{control_type}': {callback.__name__}")

    # Unregistration methods

    def unregister_global(self, callback: GlobalCallback) -> bool:
        """
        Unregister global callback.

        Args:
            callback: Callback to remove

        Returns:
            True if callback was registered and removed
        """
        with self._lock:
            # Search for callback in (callback, signal_type) tuples
            for i, (cb, _) in enumerate(self._global_callbacks):
                if cb == callback:
                    self._global_callbacks.pop(i)
                    logger.debug(f"Unregistered global callback: {callback.__name__}")
                    return True
        return False

    def unregister_control(self, control_id: str, callback: ControlCallback) -> bool:
        """
        Unregister per-control callback.

        Args:
            control_id: Control identifier
            callback: Callback to remove

        Returns:
            True if callback was registered and removed
        """
        with self._lock:
            if control_id in self._control_callbacks:
                callbacks = self._control_callbacks[control_id]
                for i, (cb, _) in enumerate(callbacks):
                    if cb == callback:
                        callbacks.pop(i)
                        logger.debug(f"Unregistered callback for control '{control_id}': {callback.__name__}")
                        return True
        return False

    def unregister_type(self, control_type: ControlType, callback: TypeCallback) -> bool:
        """
        Unregister type-based callback.

        Args:
            control_type: Type of controls
            callback: Callback to remove

        Returns:
            True if callback was registered and removed
        """
        with self._lock:
            if control_type in self._type_callbacks:
                callbacks = self._type_callbacks[control_type]
                for i, (cb, _) in enumerate(callbacks):
                    if cb == callback:
                        callbacks.pop(i)
                        logger.debug(f"Unregistered callback for type '{control_type}': {callback.__name__}")
                        return True
        return False

    def unregister_category(self, category: str, callback: CategoryCallback) -> bool:
        """
        Unregister category-based callback.

        Args:
            category: Category name
            callback: Callback to remove

        Returns:
            True if callback was registered and removed
        """
        with self._lock:
            if category in self._category_callbacks:
                callbacks = self._category_callbacks[category]
                for i, (cb, _) in enumerate(callbacks):
                    if cb == callback:
                        callbacks.pop(i)
                        logger.debug(f"Unregistered callback for category '{category}': {callback.__name__}")
                        return True
        return False

    def unregister_bank(self, control_type: ControlType, callback: BankCallback) -> bool:
        """
        Unregister bank callback.

        Args:
            control_type: Type of controls
            callback: Callback to remove

        Returns:
            True if callback was registered and removed
        """
        with self._lock:
            if control_type in self._bank_callbacks:
                callbacks = self._bank_callbacks[control_type]
                if callback in callbacks:
                    callbacks.remove(callback)
                    logger.debug(f"Unregistered bank callback for type '{control_type}': {callback.__name__}")
                    return True
        return False

    # Dispatch methods

    def on_control_change(
        self,
        control_id: str,
        state: ControlState,
        control_type: ControlType,
        signal_type: str = "default",
        category: Optional[str] = None,
    ) -> None:
        """
        Dispatch callbacks for a control change with signal type filtering.

        Only calls callbacks matching the signal type filter.
        Callbacks with signal_type=None fire for all signals.

        Callbacks are executed in order:
        1. Per-control callbacks (most specific)
        2. Category-based callbacks
        3. Type-based callbacks
        4. Global callbacks (least specific)

        Args:
            control_id: Control identifier
            state: New control state
            control_type: Type of control
            signal_type: Signal type from MIDI translation (e.g., "note", "cc", "pc")
            category: Optional category of control (e.g., "transport", "pad")
        """
        # Copy callback lists under lock (copy-before-dispatch pattern)
        with self._lock:
            control_cbs = self._control_callbacks[control_id].copy()
            category_cbs = self._category_callbacks[category].copy() if category else []
            type_cbs = self._type_callbacks[control_type].copy()
            global_cbs = self._global_callbacks.copy()

        # Execute callbacks WITHOUT holding lock (prevent deadlock)
        # Order: specific to general

        # Per-control callbacks
        for callback, filter_type in control_cbs:
            if filter_type is None or filter_type == signal_type:
                self._safe_call(callback, state)

        # Category-based callbacks
        for callback, filter_type in category_cbs:
            if filter_type is None or filter_type == signal_type:
                self._safe_call(callback, control_id, state)

        # Type-based callbacks
        for callback, filter_type in type_cbs:
            if filter_type is None or filter_type == signal_type:
                self._safe_call(callback, control_id, state)

        # Global callbacks
        for callback, filter_type in global_cbs:
            if filter_type is None or filter_type == signal_type:
                self._safe_call(callback, control_id, state)

    def on_bank_change(self, control_type: ControlType, bank_id: str) -> None:
        """
        Dispatch bank change callbacks.

        Args:
            control_type: Type of controls in bank
            bank_id: New active bank ID
        """
        # Copy callbacks under lock
        with self._lock:
            callbacks = self._bank_callbacks[control_type].copy()

        # Execute without lock
        for callback in callbacks:
            self._safe_call(callback, bank_id)

    # Helper methods

    def _safe_call(self, callback: Callable, *args) -> None:
        """
        Execute callback with exception isolation.

        Wraps callback execution in try/except to prevent cascade failures.
        Logs errors but continues with other callbacks.

        Args:
            callback: Callable to execute
            *args: Arguments to pass to callback
        """
        try:
            callback(*args)
        except Exception as e:
            # Get callback name for logging
            callback_name = getattr(callback, "__name__", repr(callback))
            logger.exception(f"Error in callback '{callback_name}': {e}")
            # Continue with other callbacks

    # Utility methods

    def clear_all(self) -> None:
        """Clear all registered callbacks."""
        with self._lock:
            self._global_callbacks.clear()
            self._control_callbacks.clear()
            self._type_callbacks.clear()
            self._category_callbacks.clear()
            self._bank_callbacks.clear()
            logger.debug("Cleared all callbacks")

    def get_callback_counts(self) -> dict[str, int]:
        """
        Get count of registered callbacks by type.

        Returns:
            Dictionary with callback counts
        """
        with self._lock:
            return {
                "global": len(self._global_callbacks),
                "control": sum(len(cbs) for cbs in self._control_callbacks.values()),
                "type": sum(len(cbs) for cbs in self._type_callbacks.values()),
                "category": sum(len(cbs) for cbs in self._category_callbacks.values()),
                "bank": sum(len(cbs) for cbs in self._bank_callbacks.values()),
            }
