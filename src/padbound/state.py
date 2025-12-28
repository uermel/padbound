"""
Thread-safe state management for MIDI controllers.

This module provides centralized state tracking with progressive discovery,
bank management, and state history.
"""

import threading
from collections import deque
from typing import Optional

from padbound.controls import (
    Control,
    ControlDefinition,
    ControllerCapabilities,
    ControlState,
    ControlType,
)


class BankState:
    """
    Tracks active bank per control type.

    Bank tracking is capability-dependent. Most controllers do NOT report
    when the user changes banks on the hardware, so bank tracking is often
    unavailable even if the controller has banks.
    """

    def __init__(self, supports_bank_feedback: bool):
        """
        Initialize bank state.

        Args:
            supports_bank_feedback: Whether controller reports bank changes via MIDI
        """
        self._supports_feedback = supports_bank_feedback
        self._active_banks: dict[ControlType, Optional[str]] = {
            ControlType.TOGGLE: None,
            ControlType.MOMENTARY: None,
            ControlType.CONTINUOUS: None,
        }
        self._lock = threading.RLock()

    def set_active_bank(self, control_type: ControlType, bank_id: str) -> None:
        """
        Set active bank for a control type.

        Args:
            control_type: Type of controls in this bank
            bank_id: Bank identifier

        Note:
            Silent no-op if bank feedback not supported. Caller should
            check support or handle in strict/permissive mode.
        """
        if not self._supports_feedback:
            return

        with self._lock:
            self._active_banks[control_type] = bank_id

    def get_active_bank(self, control_type: ControlType) -> Optional[str]:
        """
        Get active bank for control type.

        Args:
            control_type: Type of controls

        Returns:
            Bank ID if supported and set, None otherwise
        """
        if not self._supports_feedback:
            return None

        with self._lock:
            return self._active_banks[control_type]

    def is_bank_tracking_supported(self) -> bool:
        """Check if bank tracking is supported."""
        return self._supports_feedback


class ControllerState:
    """
    Centralized, thread-safe state management for all controls.

    Provides progressive state discovery, state history tracking,
    and bank management.
    """

    def __init__(self, capabilities: ControllerCapabilities):
        """
        Initialize controller state.

        Args:
            capabilities: Controller-level capabilities
        """
        self._capabilities = capabilities
        self._controls: dict[str, Control] = {}
        self._bank_state = BankState(capabilities.supports_bank_feedback)
        self._lock = threading.RLock()

        # History tracking (last 1000 changes)
        self._history: deque[tuple[str, ControlState]] = deque(maxlen=1000)

    @property
    def capabilities(self) -> ControllerCapabilities:
        """Get controller capabilities."""
        return self._capabilities

    def register_control(self, control: Control) -> None:
        """
        Register a control (called during initialization).

        Args:
            control: Control instance to register
        """
        with self._lock:
            self._controls[control.definition.control_id] = control

    def get_control(self, control_id: str) -> Optional[Control]:
        """
        Get control by ID.

        Args:
            control_id: Control identifier

        Returns:
            Control instance or None if not found
        """
        with self._lock:
            return self._controls.get(control_id)

    def update_state(self, control_id: str, value: int, **kwargs) -> ControlState:
        """
        Update control state from MIDI value.

        Args:
            control_id: Control identifier
            value: MIDI value (0-127)
            **kwargs: Additional type-specific parameters

        Returns:
            New state snapshot

        Raises:
            ValueError: If control_id not found
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                raise ValueError(f"Unknown control: {control_id}")

            # Update control state
            new_state = control.update_from_midi(value, **kwargs)

            # Track in history
            self._history.append((control_id, new_state))

            return new_state

    def set_control_state(
        self,
        control_id: str,
        new_state: ControlState,
    ) -> ControlState:
        """
        Set control state directly (for plugin-computed state).

        Use this when a plugin computes state itself rather than
        relying on the control's default state computation logic.

        Args:
            control_id: Control identifier
            new_state: Pre-computed state from plugin

        Returns:
            The new state

        Raises:
            ValueError: If control_id not found
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                raise ValueError(f"Unknown control: {control_id}")

            # Update control's internal state directly
            control._state = new_state

            # Track in history
            self._history.append((control_id, new_state))

            return new_state

    def get_state(self, control_id: str) -> Optional[ControlState]:
        """
        Get current state for a control.

        Args:
            control_id: Control identifier

        Returns:
            Current state or None if control not found
        """
        with self._lock:
            control = self._controls.get(control_id)
            return control.state if control else None

    def get_all_states(self) -> dict[str, ControlState]:
        """
        Get all control states.

        Returns:
            Dictionary mapping control_id to ControlState
        """
        with self._lock:
            return {control_id: control.state for control_id, control in self._controls.items()}

    def get_all_definitions(self) -> dict[str, ControlDefinition]:
        """
        Get all control definitions (with resolved colors from config).

        Returns:
            Dictionary mapping control_id to ControlDefinition
        """
        with self._lock:
            return {control_id: control.definition for control_id, control in self._controls.items()}

    def get_discovered_controls(self) -> list[str]:
        """
        Get list of controls that have been discovered (interacted with).

        Returns:
            List of control IDs with known state
        """
        with self._lock:
            return [control_id for control_id, control in self._controls.items() if control.state.is_discovered]

    def get_undiscovered_controls(self) -> list[str]:
        """
        Get list of controls that haven't been discovered yet.

        Returns:
            List of control IDs with unknown state
        """
        with self._lock:
            return [control_id for control_id, control in self._controls.items() if not control.state.is_discovered]

    def get_controls_by_type(self, control_type: ControlType) -> list[str]:
        """
        Get all control IDs of a specific type.

        Args:
            control_type: Type of controls to find

        Returns:
            List of control IDs
        """
        with self._lock:
            return [
                control_id
                for control_id, control in self._controls.items()
                if control.definition.control_type == control_type
            ]

    def get_history(self, limit: Optional[int] = None) -> list[tuple[str, ControlState]]:
        """
        Get state change history.

        Args:
            limit: Maximum number of entries to return (None for all)

        Returns:
            List of (control_id, state) tuples, most recent last
        """
        with self._lock:
            history_list = list(self._history)
            if limit:
                return history_list[-limit:]
            return history_list

    def clear_history(self) -> None:
        """Clear state change history."""
        with self._lock:
            self._history.clear()

    # Bank management methods

    def set_active_bank(self, control_type: ControlType, bank_id: str) -> None:
        """
        Set active bank for control type.

        Args:
            control_type: Type of controls
            bank_id: Bank identifier

        Note:
            Silent no-op if bank tracking not supported by controller.
        """
        self._bank_state.set_active_bank(control_type, bank_id)

    def get_active_bank(self, control_type: ControlType) -> Optional[str]:
        """
        Get active bank for control type.

        Args:
            control_type: Type of controls

        Returns:
            Bank ID if tracking supported and set, None otherwise
        """
        return self._bank_state.get_active_bank(control_type)

    def is_bank_tracking_supported(self) -> bool:
        """
        Check if bank tracking is supported.

        Returns:
            True if controller reports bank changes via MIDI
        """
        return self._bank_state.is_bank_tracking_supported()

    # Capability validation helpers

    def can_set_feedback(self, control_id: str) -> bool:
        """
        Check if control supports feedback (can receive state updates).

        Args:
            control_id: Control identifier

        Returns:
            True if feedback supported, False otherwise
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                return False
            return control.definition.capabilities.supports_feedback

    def can_set_value(self, control_id: str) -> bool:
        """
        Check if control supports value setting (e.g., motorized fader).

        Args:
            control_id: Control identifier

        Returns:
            True if value setting supported, False otherwise
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                return False
            return control.definition.capabilities.supports_value_setting

    def can_set_color(self, control_id: str) -> bool:
        """
        Check if control supports color feedback.

        Args:
            control_id: Control identifier

        Returns:
            True if color supported, False otherwise
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                return False
            return control.definition.capabilities.supports_color

    def validate_color(self, control_id: str, color: str) -> bool:
        """
        Validate color against control's palette.

        Args:
            control_id: Control identifier
            color: Color name to validate

        Returns:
            True if color is valid for this control, False otherwise
        """
        with self._lock:
            control = self._controls.get(control_id)
            if not control:
                return False

            capabilities = control.definition.capabilities
            if not capabilities.supports_color:
                return False

            palette = capabilities.color_palette
            if palette is None:
                # No palette defined, accept any color
                return True

            return color in palette
