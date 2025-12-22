"""
Plugin architecture for controller-specific implementations.

This module defines the plugin system that allows extending Padbound to support
different MIDI controllers. Plugins define control layouts, MIDI mappings,
and hardware-specific initialization/shutdown sequences.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Callable, Literal, Union, Any, TYPE_CHECKING

import mido
from pydantic import BaseModel, Field

from .controls import (
    ControlDefinition,
    BankDefinition,
)

if TYPE_CHECKING:
    from .config import ControllerConfig, BankConfig


class MIDIMessageType(str, Enum):
    """Types of MIDI messages."""

    NOTE_ON = "note_on"
    NOTE_OFF = "note_off"
    CONTROL_CHANGE = "control_change"
    PROGRAM_CHANGE = "program_change"
    SYSEX = "sysex"
    POLYTOUCH = "polytouch"
    AFTERTOUCH = "aftertouch"
    PITCHWHEEL = "pitchwheel"


class MIDIMessageBase(BaseModel):
    """Base class for all MIDI messages."""

    type: MIDIMessageType
    channel: int = Field(ge=0, le=15, default=0)


class NoteMessage(MIDIMessageBase):
    """Note on/off messages."""

    type: Literal[MIDIMessageType.NOTE_ON, MIDIMessageType.NOTE_OFF]
    note: int = Field(ge=0, le=127)
    velocity: int = Field(ge=0, le=127)


class ControlChangeMessage(MIDIMessageBase):
    """Control change (CC) messages."""

    type: Literal[MIDIMessageType.CONTROL_CHANGE]
    control: int = Field(ge=0, le=127)
    value: int = Field(ge=0, le=127)


class ProgramChangeMessage(MIDIMessageBase):
    """Program change messages."""

    type: Literal[MIDIMessageType.PROGRAM_CHANGE]
    program: int = Field(ge=0, le=127)


class SysExMessage(BaseModel):
    """System Exclusive messages."""

    type: Literal[MIDIMessageType.SYSEX]
    data: bytes


class AftertouchMessage(MIDIMessageBase):
    """Channel aftertouch messages."""

    type: Literal[MIDIMessageType.AFTERTOUCH]
    value: int = Field(ge=0, le=127)


class PolytouchMessage(MIDIMessageBase):
    """Polyphonic aftertouch messages."""

    type: Literal[MIDIMessageType.POLYTOUCH]
    note: int = Field(ge=0, le=127)
    value: int = Field(ge=0, le=127)


class PitchwheelMessage(MIDIMessageBase):
    """Pitchwheel messages."""

    type: Literal[MIDIMessageType.PITCHWHEEL]
    pitch: int = Field(ge=-8192, le=8191)


# Union type for all MIDI messages
MIDIMessage = Union[
    NoteMessage,
    ControlChangeMessage,
    ProgramChangeMessage,
    SysExMessage,
    AftertouchMessage,
    PolytouchMessage,
    PitchwheelMessage,
]


class MIDIMapping(BaseModel):
    """
    Maps MIDI input to a control ID.

    Defines how incoming MIDI messages map to abstract controls.
    """

    # MIDI message pattern to match
    message_type: MIDIMessageType
    channel: Optional[int] = None  # None = any channel
    note: Optional[int] = None  # For note messages
    control: Optional[int] = None  # For CC messages

    # Target control ID (e.g., "pad_1@bank_1" or just "pad_1")
    control_id: str

    # Optional value transformation
    invert: bool = False  # Invert value (127 - value)
    scale: Optional[float] = None  # Scale factor

    # Signal type for callback routing (e.g., "note", "cc", "pc", "default")
    signal_type: str = "default"

    model_config = {"arbitrary_types_allowed": True}

    def matches(self, msg: mido.Message) -> bool:
        """
        Check if a MIDI message matches this mapping.

        Args:
            msg: MIDI message to check

        Returns:
            True if message matches pattern
        """
        # Check message type
        if msg.type != self.message_type.value:
            return False

        # Check channel (if specified)
        if self.channel is not None and hasattr(msg, 'channel'):
            if msg.channel != self.channel:
                return False

        # Check note (if specified)
        if self.note is not None and hasattr(msg, 'note'):
            if msg.note != self.note:
                return False

        # Check control (if specified)
        if self.control is not None and hasattr(msg, 'control'):
            if msg.control != self.control:
                return False

        return True

    def transform_value(self, value: int) -> int:
        """
        Apply transformation to value.

        Args:
            value: Input value (0-127)

        Returns:
            Transformed value
        """
        result = value

        if self.invert:
            result = 127 - result

        if self.scale is not None:
            result = int(result * self.scale)
            result = max(0, min(127, result))  # Clamp

        return result


class FeedbackMapping(BaseModel):
    """
    Maps control state to MIDI feedback.

    Defines how to send MIDI messages back to hardware for visual feedback
    (LEDs, colors, motorized faders).
    """

    control_id: str

    # MIDI message template
    message_type: MIDIMessageType
    channel: int = Field(ge=0, le=15, default=0)
    note: Optional[int] = None  # For note messages
    control: Optional[int] = None  # For CC messages

    # State-to-value mapping function name
    # Plugins can override to provide custom mapping logic
    value_source: Literal["value", "is_on", "color"] = "value"

    model_config = {"arbitrary_types_allowed": True}


class BankMapping(BaseModel):
    """
    Maps MIDI messages to bank switch events.

    Defines which MIDI messages trigger bank changes.
    """

    # MIDI message pattern
    message_type: MIDIMessageType
    channel: Optional[int] = None
    note: Optional[int] = None
    control: Optional[int] = None
    value: Optional[int] = None  # Specific value to trigger

    # Target bank ID
    bank_id: str

    def matches(self, msg: mido.Message) -> bool:
        """
        Check if message triggers this bank switch.

        Args:
            msg: MIDI message

        Returns:
            True if message matches pattern
        """
        if msg.type != self.message_type.value:
            return False

        if self.channel is not None and hasattr(msg, 'channel'):
            if msg.channel != self.channel:
                return False

        if self.note is not None and hasattr(msg, 'note'):
            if msg.note != self.note:
                return False

        if self.control is not None and hasattr(msg, 'control'):
            if msg.control != self.control:
                return False

        if self.value is not None:
            # Check value field (velocity for notes, value for CC)
            msg_value = getattr(msg, 'velocity', None) or getattr(msg, 'value', None)
            if msg_value != self.value:
                return False

        return True


class ControllerPlugin(ABC):
    """
    Abstract base class for controller-specific plugins.

    Plugins define:
    - Control layout and capabilities
    - MIDI message mappings (input and feedback)
    - Bank structure (if applicable)
    - Initialization and shutdown sequences
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Plugin name (should match controller name).

        Returns:
            Controller name (e.g., "Example Pad Controller")
        """
        pass

    @property
    def port_patterns(self) -> list[str]:
        """
        Port name patterns for auto-detection.

        Returns:
            List of strings/patterns to match against MIDI port names
        """
        return []

    def get_capabilities(self) -> 'ControllerCapabilities':
        """
        Get controller-level capabilities.

        Override this method to declare controller capabilities including
        persistent configuration support.

        Default implementation auto-detects persistent configuration support
        by checking if configure_programs() has been overridden.

        Returns:
            ControllerCapabilities with accurate feature support flags
        """
        from .controls import ControllerCapabilities

        # Auto-detect: check if configure_programs was overridden
        base_method = ControllerPlugin.configure_programs
        current_method = type(self).configure_programs
        supports_persistent = (current_method is not base_method)

        return ControllerCapabilities(
            supports_persistent_configuration=supports_persistent
        )

    @abstractmethod
    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]]
    ) -> None:
        """
        Initialize controller to known state.

        REQUIRED: This method must be implemented to set the controller
        to a predictable state when the library connects. Typically:
        - Query device state (e.g., current program/bank)
        - Clear all LEDs (set to off state)
        - Set any default colors/states
        - Put controller in expected mode (if applicable)

        Args:
            send_message: Function to send MIDI messages to controller
            receive_message: Function to receive MIDI message with timeout (seconds).
                Returns None if timeout. Useful for SysEx query/response patterns.
        """
        pass

    def configure_programs(
        self,
        send_message: Callable[[mido.Message], None],
        config: 'ControllerConfig'
    ) -> None:
        """
        Program persistent configuration into device memory (optional).

        OPTIONAL: Only implement this if the controller supports persistent
        configuration that survives program/bank switches or power cycles.

        Called after init() to write user configuration to device non-volatile
        memory. This allows configuration (colors, control types, channels, etc.)
        to persist across program switches.

        Distinction from init():
        - init(): Sets controller to known state (clears, resets)
        - configure_programs(): Programs user configuration into device memory

        Distinction from translate_feedback():
        - configure_programs(): Persistent config (survives program switch)
        - translate_feedback(): Temporary state updates (lost on switch)

        What can be configured (device-dependent):
        - Colors (OFF/ON states)
        - Control types (toggle/momentary)
        - MIDI channels
        - Knob ranges
        - Pressure modes
        - Other device-specific settings

        Args:
            send_message: Function to send MIDI messages to controller
            config: Full controller configuration with resolved settings

        Implementation notes:
            - Extract relevant config for each program/bank
            - Convert config types to device-specific format
            - Send SysEx or other MIDI to program device memory
            - Add appropriate delays for device processing

        Example:
            def configure_programs(self, send_message, config):
                for bank_id, bank_config in config.banks.items():
                    # Extract colors, types, etc.
                    # Build device-specific SysEx
                    # Send to controller
                    send_message(program_sysex)
        """
        # Default implementation: do nothing
        # Controllers without persistent config support don't need to override
        pass

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Clean up controller on disconnect (optional).

        Called when Controller is closed. Can send cleanup MIDI like:
        - Clear all LEDs
        - Return to default mode
        - Send farewell SysEx message

        Default implementation does nothing.

        Args:
            send_message: Function to send MIDI messages to controller
        """
        pass

    def validate_bank_config(
        self,
        bank_id: str,
        bank_config: 'BankConfig',
        strict_mode: bool = True
    ) -> None:
        """
        Validate bank configuration against hardware constraints (optional).

        Override in subclasses to add hardware-specific validation. For example,
        a controller with global toggle mode per bank can validate that pad-level
        type configs don't conflict with the bank-level toggle_mode setting.

        Default implementation does nothing.

        Args:
            bank_id: Bank identifier (e.g., "bank_1")
            bank_config: Bank configuration to validate
            strict_mode: If True, raise ConfigurationError on invalid config.
                If False, log warnings only.

        Raises:
            ConfigurationError: In strict mode, if validation fails
        """
        pass

    def complete_initialization(
        self,
        msg: mido.Message,
        send_message: Callable[[mido.Message], None]
    ) -> Optional[str]:
        """
        Complete initialization using first input message (optional).

        Called only when ControllerCapabilities.requires_initialization_handshake
        is True. The first MIDI input after connect() is consumed (not passed
        to callbacks) and used to detect the controller's current state.

        Use cases:
        - Detect current bank/program when hardware cannot be queried
        - Detect mode when controller has multiple modes
        - Initialize state that depends on first user interaction

        After this method returns, the Controller will:
        - Update internal bank state (if bank_id returned)
        - Apply LED colors for the detected bank
        - Resume normal operation (subsequent inputs trigger callbacks)

        Args:
            msg: First MIDI message received after connect()
            send_message: Function to send MIDI messages to controller

        Returns:
            Detected bank_id if applicable, None otherwise
        """
        return None

    @abstractmethod
    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Get all control definitions.

        Returns:
            List of control definitions with accurate capability declarations
        """
        pass

    @abstractmethod
    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Get MIDI-to-control mappings.

        Returns:
            List of mappings from MIDI messages to control IDs
        """
        pass

    def get_feedback_mappings(self) -> list[FeedbackMapping]:
        """
        Get control-to-MIDI feedback mappings.

        Returns:
            List of feedback mappings (empty if no feedback support)
        """
        return []

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Get bank definitions.

        Returns:
            List of banks (empty list if no banks)
        """
        return []

    def get_bank_mappings(self) -> list[BankMapping]:
        """
        Get bank switch mappings.

        Returns:
            List of MIDI messages that trigger bank switches
        """
        return []

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate incoming MIDI message to control ID, value, and signal type.

        Default implementation uses input mappings. Override for complex logic.

        Args:
            msg: Incoming MIDI message

        Returns:
            (control_id, value, signal_type) tuple or None if no mapping found
        """
        for mapping in self.get_input_mappings():
            if mapping.matches(msg):
                # Extract value from message
                value = self._extract_value(msg)
                if value is not None:
                    value = mapping.transform_value(value)
                    return (mapping.control_id, value, mapping.signal_type)

        return None

    def translate_feedback(
        self, control_id: str, state_dict: dict[str, Any]
    ) -> list[mido.Message]:
        """
        Translate control state to MIDI feedback messages.

        Default implementation uses feedback mappings. Override for complex logic.

        Args:
            control_id: Control identifier
            state_dict: State dictionary (is_on, value, color, etc.)

        Returns:
            List of MIDI messages to send (empty if no feedback)
        """
        messages = []

        for mapping in self.get_feedback_mappings():
            if mapping.control_id == control_id:
                msg = self._build_feedback_message(mapping, state_dict)
                if msg:
                    messages.append(msg)

        return messages

    def translate_bank_switch(self, msg: mido.Message) -> Optional[str]:
        """
        Translate MIDI message to bank switch.

        Args:
            msg: MIDI message

        Returns:
            Bank ID if message triggers bank switch, None otherwise
        """
        for mapping in self.get_bank_mappings():
            if mapping.matches(msg):
                return mapping.bank_id

        return None

    # Helper methods

    def _extract_value(self, msg: mido.Message) -> Optional[int]:
        """
        Extract value from MIDI message.

        Args:
            msg: MIDI message

        Returns:
            Value (0-127) or None
        """
        # Try velocity (note messages)
        if hasattr(msg, 'velocity'):
            return msg.velocity

        # Try value (CC messages)
        if hasattr(msg, 'value'):
            return msg.value

        # Try pitch (pitchwheel)
        if hasattr(msg, 'pitch'):
            # Convert -8192 to 8191 → 0 to 127
            pitch = msg.pitch + 8192
            return int(pitch / 16383 * 127)

        return None

    def _build_feedback_message(
        self, mapping: FeedbackMapping, state_dict: dict[str, Any]
    ) -> Optional[mido.Message]:
        """
        Build MIDI message from feedback mapping and state.

        Args:
            mapping: Feedback mapping
            state_dict: State dictionary

        Returns:
            MIDI message or None
        """
        # Extract value from state based on mapping
        if mapping.value_source == "is_on":
            value = 127 if state_dict.get("is_on", False) else 0
        elif mapping.value_source == "color":
            # Color mapping is controller-specific, subclasses should override
            value = 0
        else:  # "value"
            value = state_dict.get("value", 0)

        # Build message based on type
        try:
            if mapping.message_type == MIDIMessageType.NOTE_ON:
                return mido.Message(
                    'note_on',
                    channel=mapping.channel,
                    note=mapping.note or 0,
                    velocity=value
                )
            elif mapping.message_type == MIDIMessageType.CONTROL_CHANGE:
                return mido.Message(
                    'control_change',
                    channel=mapping.channel,
                    control=mapping.control or 0,
                    value=value
                )
            # Add other message types as needed

        except Exception:
            return None

        return None
