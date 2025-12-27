"""
Core control abstractions and state models for Padbound.

This module defines the fundamental control types (Toggle, Momentary, Continuous)
and their associated state models using Pydantic for validation and serialization.
"""

import threading
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class ControlType(str, Enum):
    """Three fundamental control types for MIDI controllers."""

    TOGGLE = "toggle"  # Binary on/off state (e.g., pads acting as switches)
    MOMENTARY = "momentary"  # Trigger-based actions with no persistent state
    CONTINUOUS = "continuous"  # Range-based values (e.g., knobs, faders)

class LEDAnimationType(str, Enum):
    """Three LED animation types for MIDI controllers."""

    SOLID = "solid"
    BLINK = "blink"
    PULSE = "pulse"

class LEDMode(BaseModel):
    """LED animation type and (optional frequency in pulses per second)."""
    animation_type: LEDAnimationType = LEDAnimationType.SOLID
    frequency: Optional[int] = None

    def __hash__(self):
        """Make hashable for use in sets and as dict keys."""
        return hash((self.animation_type, self.frequency))

class ControlCapabilities(BaseModel):
    """
    Per-control hardware capability declarations.

    Defines what feedback and operations each control supports.
    Most MIDI controllers have asymmetric capabilities - they can send input
    but have limited or no ability to receive state updates.
    """

    # Can receive feedback at all? (capability exists for API use)
    supports_feedback: bool = False

    # Does device NEED automatic feedback on input? (hardware doesn't manage LEDs)
    # False = device manages its own LED state (e.g., LPD8 with programmed colors)
    # True = library must send LED updates when state changes
    requires_feedback: bool = False

    # For pads with LEDs
    supports_led: bool = False
    supports_color: bool = False
    color_mode: Literal["rgb", "velocity", "indexed", "none"] = "none"
    color_palette: Optional[list[str]] = None  # e.g., ["off", "green", "red", "yellow"]

    # LED animation modes supported by hardware
    # None = only solid supported (most controllers)
    # [LEDMode(...), ...] = full animation support (e.g. PreSonus Atom, APC mini)
    supported_led_modes: Optional[list[LEDMode]] = None

    # For rare motorized/value-setting controls
    supports_value_setting: bool = False

    # Does control report initial state or require discovery?
    requires_discovery: bool = True  # True for most knobs/faders


class ControlTypeModes(BaseModel):
    """
    Defines which control types a physical control supports.

    Most controls support only one type (fixed hardware behavior).
    Configurable controllers like LPD8 support multiple types.
    """

    supported_types: list[ControlType]  # e.g., [TOGGLE, MOMENTARY]
    default_type: ControlType  # Plugin's recommended default
    requires_hardware_sync: bool = False  # Does mode change require MIDI/SysEx?

    @field_validator("supported_types")
    @classmethod
    def validate_non_empty(cls, v):
        if not v:
            raise ValueError("supported_types cannot be empty")
        return v

    @field_validator("default_type")
    @classmethod
    def validate_default_in_supported(cls, v, info):
        if "supported_types" in info.data and v not in info.data["supported_types"]:
            raise ValueError(f"default_type {v} must be in supported_types")
        return v


class ControllerCapabilities(BaseModel):
    """
    Controller-level capabilities.

    Defines capabilities that apply to the entire controller, not individual controls.
    """

    # Does controller report bank changes via MIDI? (most do NOT)
    supports_bank_feedback: bool = False

    # Control ID indexing scheme (plugin defines this based on controller layout)
    # "1d": Linear indexing (pad_1, pad_2, ..., pad_64) - most controllers
    # "2d": Grid indexing (pad_0_0, pad_0_1, ..., pad_7_7) - for grid controllers
    indexing_scheme: Literal["1d", "2d"] = "1d"

    # Grid dimensions (only used if indexing_scheme == "2d")
    grid_rows: Optional[int] = None
    grid_cols: Optional[int] = None

    # Does controller support persistent configuration via configure_programs()?
    supports_persistent_configuration: bool = False

    # Delay (seconds) to wait after init() before sending initial LED states.
    # Needed for devices with async initialization (e.g., APC mini intro message).
    post_init_delay: float = Field(default=0.0, ge=0.0)

    # Delay (seconds) between feedback messages during initialization.
    # Needed for devices with limited SysEx processing throughput.
    feedback_message_delay: float = Field(default=0.0, ge=0.0)


class BankDefinition(BaseModel):
    """
    Defines a bank of controls.

    Many MIDI controllers organize controls into banks that can be switched
    to access more controls than physical hardware.
    """

    bank_id: str  # e.g., "bank_1", "bank_2"
    control_type: ControlType  # Which control type this bank is for
    display_name: Optional[str] = None  # User-friendly name


class ControlDefinition(BaseModel):
    """
    Metadata defining a control.

    Defines the control's type, capabilities, and optional bank membership.
    """

    control_id: str  # e.g., "pad_1", "fader_1", "pad_1@bank_1"
    control_type: ControlType
    category: Optional[str] = None  # e.g., "pad", "transport", "navigation", "mode", "encoder"
    capabilities: ControlCapabilities
    bank_id: Optional[str] = None  # Optional bank membership
    display_name: Optional[str] = None  # User-friendly name

    # Optional parameters for continuous controls
    min_value: int = 0
    max_value: int = 127

    # Multi-mode support (optional for backward compatibility)
    type_modes: Optional[ControlTypeModes] = None

    # Signal types this control can emit (for multi-signal routing)
    signal_types: list[str] = Field(default_factory=lambda: ["default"])  # e.g., ["note", "cc", "pc"]

    # Color configuration (resolved from user config)
    on_color: Optional[str] = None  # Color when control is ON/active
    off_color: Optional[str] = None  # Color when control is OFF/inactive

    # LED animation mode (resolved from user config)
    on_led_mode: Optional[LEDMode] = None
    off_led_mode: Optional[LEDMode] = None

    @model_validator(mode="after")
    def validate_type_modes_consistency(self):
        """Ensure control_type matches type_modes if both provided."""
        if self.type_modes and self.control_type != self.type_modes.default_type:
            raise ValueError(
                f"control_type {self.control_type} must match "
                f"type_modes.default_type {self.type_modes.default_type}",
            )
        return self


class ControlState(BaseModel):
    """
    Immutable state snapshot for a control.

    Represents the state of a control at a specific point in time.
    Immutability (frozen=True) prevents race conditions in multi-threaded access.
    """

    control_id: str
    timestamp: datetime = Field(default_factory=datetime.now)

    # Discovery tracking
    is_discovered: bool = False
    first_discovered_at: Optional[datetime] = None

    # State values (depends on control type)
    value: Optional[int] = None  # Raw MIDI value 0-127
    normalized_value: Optional[float] = None  # 0.0-1.0
    is_on: Optional[bool] = None  # For toggles
    color: Optional[str] = None
    led_mode: Optional[LEDMode] = None  # LED animation mode when ON

    model_config = {"frozen": True}  # Immutability


class CapabilityError(Exception):
    """
    Raised when attempting an operation unsupported by the controller's capabilities.

    Only raised in strict mode. In permissive mode, unsupported operations
    log warnings instead.
    """

    pass


class Control(ABC):
    """
    Abstract base class for all control types.

    Handles state management and discovery tracking. Subclasses implement
    type-specific state computation logic.
    """

    def __init__(self, definition: ControlDefinition):
        """
        Initialize control with its definition.

        Args:
            definition: Control metadata including capabilities
        """
        self._definition = definition
        self._state = ControlState(control_id=definition.control_id, is_discovered=False)
        self._lock = threading.RLock()

    @property
    def definition(self) -> ControlDefinition:
        """Get control definition (immutable)."""
        return self._definition

    @property
    def state(self) -> ControlState:
        """Get current state (thread-safe)."""
        with self._lock:
            return self._state

    def update_from_midi(self, value: int, **kwargs) -> ControlState:
        """
        Update state from incoming MIDI, mark as discovered.

        Args:
            value: MIDI value (0-127 for most messages)
            **kwargs: Additional type-specific parameters (e.g., velocity, note)

        Returns:
            New state snapshot
        """
        with self._lock:
            # Track discovery
            first_discovered_at = datetime.now() if not self._state.is_discovered else self._state.first_discovered_at

            # Compute new state (subclass-specific)
            new_state = self._compute_new_state(value, **kwargs)

            # Mark as discovered
            self._state = new_state.model_copy(
                update={"is_discovered": True, "first_discovered_at": first_discovered_at},
            )

            return self._state

    @abstractmethod
    def _compute_new_state(self, value: int, **kwargs) -> ControlState:
        """
        Compute new state from MIDI value (subclass implements).

        Args:
            value: MIDI value (0-127)
            **kwargs: Additional parameters

        Returns:
            New ControlState (without discovery tracking)
        """
        pass


class ToggleControl(Control):
    """
    Toggle control - maintains binary on/off state.

    Toggles state on each press. Used for pads acting as switches.
    """

    def __init__(self, definition: ControlDefinition):
        """Initialize toggle control with off state."""
        super().__init__(definition)
        # Start in off state (discovered=False) with off_color
        self._state = ControlState(
            control_id=definition.control_id,
            is_discovered=False,
            is_on=False,
            color=definition.off_color,
        )

    def _compute_new_state(self, value: int, **kwargs) -> ControlState:
        """
        Toggle state based on MIDI value.

        True toggle behavior:
        - velocity > 0 (button press) → FLIP the current state
        - velocity = 0 (button release) → maintain current state (do nothing)

        Args:
            value: MIDI velocity (0-127)

        Returns:
            New state with toggled is_on and appropriate color
        """
        # Only toggle on press (velocity > 0), ignore release
        new_is_on = not self._state.is_on if value > 0 else self._state.is_on

        # Set color based on new state
        color = self._definition.on_color if new_is_on else self._definition.off_color

        # LED mode based on state (on_led_mode when ON, off_led_mode when OFF)
        led_mode = self._definition.on_led_mode if new_is_on else self._definition.off_led_mode

        return ControlState(
            control_id=self._definition.control_id,
            timestamp=datetime.now(),
            is_on=new_is_on,
            value=value,
            color=color,
            led_mode=led_mode,
        )


class MomentaryControl(Control):
    """
    Momentary control - trigger events only, no persistent state.

    Used for buttons that trigger actions on press without maintaining state.
    LED lights up while pressed, turns off when released.
    """

    def __init__(self, definition: ControlDefinition):
        """Initialize momentary control with off state."""
        super().__init__(definition)
        # Start in off state (discovered=False)
        self._state = ControlState(
            control_id=definition.control_id,
            is_discovered=False,
            is_on=False,
            color=definition.off_color,  # May be None for non-color buttons
        )

    def _compute_new_state(self, value: int, **kwargs) -> ControlState:
        """
        Create state snapshot for momentary trigger.

        Momentary controls don't maintain state, but we track the trigger
        event for callbacks.

        Args:
            value: MIDI velocity (0-127)

        Returns:
            New state with trigger value and appropriate color
        """
        # Only trigger on press (velocity > 0)
        is_triggered = value > 0
        color = self._definition.on_color if is_triggered else self._definition.off_color
        led_mode = self._definition.on_led_mode if is_triggered else self._definition.off_led_mode

        return ControlState(
            control_id=self._definition.control_id,
            timestamp=datetime.now(),
            value=value,
            is_on=is_triggered,  # Treat trigger as momentary "on"
            color=color,
            led_mode=led_mode,
        )


class ContinuousControl(Control):
    """
    Continuous control - range-based values (knobs, faders).

    Tracks both raw MIDI value (0-127) and normalized value (0.0-1.0).
    Always requires discovery - initial position unknown until first movement.
    """

    def _compute_new_state(self, value: int, **kwargs) -> ControlState:
        """
        Update continuous control value.

        Args:
            value: MIDI value (0-127 for CC, or custom range)

        Returns:
            New state with value and normalized_value
        """
        # Normalize to 0.0-1.0 range
        value_range = self._definition.max_value - self._definition.min_value
        normalized = (value - self._definition.min_value) / value_range if value_range > 0 else 0.0
        normalized = max(0.0, min(1.0, normalized))  # Clamp to [0.0, 1.0]

        return ControlState(
            control_id=self._definition.control_id,
            timestamp=datetime.now(),
            value=value,
            normalized_value=normalized,
        )
