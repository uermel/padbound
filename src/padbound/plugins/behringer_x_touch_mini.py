"""
Behringer X-Touch Mini MIDI Controller Plugin.

Hardware specifications:
- 8 rotary encoders with push-buttons (knob-buttons)
- 16 pad buttons (2 rows of 8)
- 1 fader (not motorized)
- 2 banks (Layer A, Layer B) - hardware button switches
- USB MIDI interface

Control features:
- Knob-buttons: MOMENTARY controls (press/release)
- Pads: Software-managed TOGGLE with LED feedback
- Knobs: CONTINUOUS (LED rings auto-reflect value)
- Fader: CONTINUOUS, read-only

MIDI Mapping (Channel 11):
- All controls use MIDI channel 11 (0x0A in status byte)
- Bank detection by note/CC range (not channel)

================================================================================
MIDI MAPPING TABLE
================================================================================

Control              | Layer A          | Layer B
---------------------|------------------|------------------
Knob buttons 1-8     | Notes 0-7        | Notes 24-31
Pads 1-8 (row 1)     | Notes 8-15       | Notes 32-39
Pads 9-16 (row 2)    | Notes 16-23      | Notes 40-47
Knobs 1-8            | CC 1-8           | CC 11-18
Fader                | CC 9             | CC 10

================================================================================
LED FEEDBACK
================================================================================

- Pads/Knob-buttons: Send Note On with velocity 0x7F (on) or 0x00 (off)
- Knobs: Send CC to set value (LED rings auto-reflect)
- Fader: No feedback (read-only)

================================================================================
SYSEX PROTOCOL (Reference - not used in this plugin)
================================================================================

Header: F0 40 41 42 <cmd> ... F7

Commands:
- 0x51: Query device info
- 0x52: Query layer configuration (01=Layer A, 02=Layer B)
- 0x59: Set mode (00=Standard, 01=MC)
- 0x60: Set device ID
- 0x61: Set global channel

================================================================================
"""

from typing import Callable, Optional

import mido

from ..controls import (
    BankDefinition,
    ControlCapabilities,
    ControlDefinition,
    ControllerCapabilities,
    ControlState,
    ControlType,
    ControlTypeModes,
)
from ..logging_config import get_logger
from ..plugin import (
    ControllerPlugin,
    FeedbackMapping,
    MIDIMapping,
    MIDIMessageType,
)

logger = get_logger(__name__)


# =============================================================================
# MIDI Constants
# =============================================================================

MIDI_CHANNEL = 10  # 0-indexed (channel 11 in user terms)

# Layer A note mappings
LAYER_A_KNOB_BUTTONS = list(range(0, 8))  # Notes 0-7
LAYER_A_PADS_ROW1 = list(range(8, 16))  # Notes 8-15
LAYER_A_PADS_ROW2 = list(range(16, 24))  # Notes 16-23
LAYER_A_PADS = LAYER_A_PADS_ROW1 + LAYER_A_PADS_ROW2  # Notes 8-23

# Layer A CC mappings
LAYER_A_KNOBS = list(range(1, 9))  # CC 1-8
LAYER_A_FADER = 9  # CC 9

# Layer B note mappings
LAYER_B_KNOB_BUTTONS = list(range(24, 32))  # Notes 24-31
LAYER_B_PADS_ROW1 = list(range(32, 40))  # Notes 32-39
LAYER_B_PADS_ROW2 = list(range(40, 48))  # Notes 40-47
LAYER_B_PADS = LAYER_B_PADS_ROW1 + LAYER_B_PADS_ROW2  # Notes 32-47

# Layer B CC mappings
LAYER_B_KNOBS = list(range(11, 19))  # CC 11-18
LAYER_B_FADER = 10  # CC 10

# All notes/CCs for quick lookup
ALL_LAYER_A_NOTES = LAYER_A_KNOB_BUTTONS + LAYER_A_PADS  # 0-23
ALL_LAYER_B_NOTES = LAYER_B_KNOB_BUTTONS + LAYER_B_PADS  # 24-47
ALL_LAYER_A_CCS = LAYER_A_KNOBS + [LAYER_A_FADER]  # 1-9
ALL_LAYER_B_CCS = LAYER_B_KNOBS + [LAYER_B_FADER]  # 10-18


# =============================================================================
# SysEx Protocol Constants (for reference/future use)
# =============================================================================


class XTouchMiniSysEx:
    """SysEx protocol constants for X-Touch Mini (reference)."""

    MANUFACTURER_ID = [0x40, 0x41, 0x42]
    CMD_DEVICE_INFO = 0x51
    CMD_GET_CONFIG = 0x52
    CMD_SET_MODE = 0x59
    CMD_SET_DEVICE_ID = 0x60
    CMD_SET_GLOBAL_CH = 0x61


# =============================================================================
# Plugin Implementation
# =============================================================================


class BehringerXTouchMiniPlugin(ControllerPlugin):
    """
    Behringer X-Touch Mini MIDI Controller plugin.

    Features:
    - 8 knob-buttons (MOMENTARY) with LED feedback
    - 16 pads (TOGGLE) with software-managed state and LED feedback
    - 8 knobs (CONTINUOUS) with auto-reflecting LED rings
    - 1 fader (CONTINUOUS, read-only)
    - 2 banks (Layer A, Layer B) with automatic detection
    """

    # Hardware configuration
    KNOB_BUTTON_COUNT = 8
    PAD_COUNT = 16
    KNOB_COUNT = 8
    BANK_COUNT = 2

    def __init__(self):
        """Initialize plugin with bank tracking and deferred feedback support."""
        super().__init__()
        self._last_active_bank: Optional[str] = None
        # For deferred feedback (LEDs set after button release)
        self._send_message: Optional[Callable[[mido.Message], None]] = None
        self._pending_feedback: dict[str, bool] = {}  # control_id -> is_on state
        self._note_to_pad_control: dict[int, str] = {}  # note number -> control_id

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "X-Touch Mini"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "X-TOUCH MINI",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # Hardware manages bank LED
            indexing_scheme="1d",  # Linear numbering
            supports_persistent_configuration=False,  # No SysEx config needed
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 2 banks (Layer A and Layer B).
        """
        return [
            BankDefinition(bank_id="layer_a", control_type=ControlType.TOGGLE, display_name="Layer A"),
            BankDefinition(bank_id="layer_b", control_type=ControlType.TOGGLE, display_name="Layer B"),
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across both banks.

        Creates 2 banks × (8 knob-buttons + 16 pads + 8 knobs + 1 fader) = 66 controls total.
        """
        definitions = []

        for layer in ["layer_a", "layer_b"]:
            # 8 knob-buttons per bank (MOMENTARY)
            for i in range(1, self.KNOB_BUTTON_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_button_{i}@{layer}",
                        control_type=ControlType.MOMENTARY,
                        category="knob_button",
                        capabilities=ControlCapabilities(
                            supports_feedback=True,
                            requires_feedback=False,
                            supports_led=True,
                            requires_discovery=False,
                        ),
                        bank_id=layer,
                        display_name=f"{'A' if layer == 'layer_a' else 'B'} Knob Btn {i}",
                    ),
                )

            # 16 pads per bank (TOGGLE with LED feedback, configurable to MOMENTARY)
            for i in range(1, self.PAD_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{i}@{layer}",
                        control_type=ControlType.TOGGLE,
                        category="pad",
                        type_modes=ControlTypeModes(
                            supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                            default_type=ControlType.TOGGLE,
                            requires_hardware_sync=False,  # Mode is software-only
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=True,
                            requires_feedback=True,  # Library must send LED updates
                            supports_led=True,
                            requires_discovery=False,
                        ),
                        bank_id=layer,
                        display_name=f"{'A' if layer == 'layer_a' else 'B'} Pad {i}",
                    ),
                )

            # 8 knobs per bank (CONTINUOUS, LED rings auto-reflect)
            for i in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{i}@{layer}",
                        control_type=ControlType.CONTINUOUS,
                        category="knob",
                        capabilities=ControlCapabilities(
                            supports_feedback=True,  # Can send CC to set value
                            requires_feedback=False,
                            requires_discovery=True,  # Position unknown until moved
                        ),
                        bank_id=layer,
                        min_value=0,
                        max_value=127,
                        display_name=f"{'A' if layer == 'layer_a' else 'B'} Knob {i}",
                    ),
                )

            # 1 fader per bank (CONTINUOUS, read-only)
            definitions.append(
                ControlDefinition(
                    control_id=f"fader@{layer}",
                    control_type=ControlType.CONTINUOUS,
                    category="fader",
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # Not motorized
                        requires_feedback=False,
                        requires_discovery=True,  # Position unknown until moved
                    ),
                    bank_id=layer,
                    min_value=0,
                    max_value=127,
                    display_name=f"{'A' if layer == 'layer_a' else 'B'} Fader",
                ),
            )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        Both layers use channel 11. Bank detection is by note/CC range.
        """
        mappings = []

        # Layer A mappings
        layer = "layer_a"

        # Knob buttons (Notes 0-7)
        for i, note in enumerate(LAYER_A_KNOB_BUTTONS, start=1):
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"knob_button_{i}@{layer}",
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"knob_button_{i}@{layer}",
                        signal_type="note",
                    ),
                ],
            )

        # Pads (Notes 8-23) - NOTE_ON and NOTE_OFF for both TOGGLE and MOMENTARY support
        for i, note in enumerate(LAYER_A_PADS, start=1):
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"pad_{i}@{layer}",
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"pad_{i}@{layer}",
                        signal_type="note",
                    ),
                ],
            )

        # Knobs (CC 1-8)
        for i, cc in enumerate(LAYER_A_KNOBS, start=1):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=MIDI_CHANNEL,
                    control=cc,
                    control_id=f"knob_{i}@{layer}",
                    signal_type="cc",
                ),
            )

        # Fader (CC 9)
        mappings.append(
            MIDIMapping(
                message_type=MIDIMessageType.CONTROL_CHANGE,
                channel=MIDI_CHANNEL,
                control=LAYER_A_FADER,
                control_id=f"fader@{layer}",
                signal_type="cc",
            ),
        )

        # Layer B mappings
        layer = "layer_b"

        # Knob buttons (Notes 24-31)
        for i, note in enumerate(LAYER_B_KNOB_BUTTONS, start=1):
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"knob_button_{i}@{layer}",
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"knob_button_{i}@{layer}",
                        signal_type="note",
                    ),
                ],
            )

        # Pads (Notes 32-47) - NOTE_ON and NOTE_OFF for both TOGGLE and MOMENTARY support
        for i, note in enumerate(LAYER_B_PADS, start=1):
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"pad_{i}@{layer}",
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=MIDI_CHANNEL,
                        note=note,
                        control_id=f"pad_{i}@{layer}",
                        signal_type="note",
                    ),
                ],
            )

        # Knobs (CC 11-18)
        for i, cc in enumerate(LAYER_B_KNOBS, start=1):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=MIDI_CHANNEL,
                    control=cc,
                    control_id=f"knob_{i}@{layer}",
                    signal_type="cc",
                ),
            )

        # Fader (CC 10)
        mappings.append(
            MIDIMapping(
                message_type=MIDIMessageType.CONTROL_CHANGE,
                channel=MIDI_CHANNEL,
                control=LAYER_B_FADER,
                control_id=f"fader@{layer}",
                signal_type="cc",
            ),
        )

        return mappings

    def get_feedback_mappings(self) -> list[FeedbackMapping]:
        """
        Map control state to MIDI feedback.

        - Pads/Knob-buttons: Note On with velocity for LED state
        - Knobs: CC for value (LED rings auto-reflect)
        """
        mappings = []

        # Layer A feedback
        layer = "layer_a"

        # Knob buttons (Notes 0-7)
        for i, note in enumerate(LAYER_A_KNOB_BUTTONS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"knob_button_{i}@{layer}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=MIDI_CHANNEL,
                    note=note,
                    value_source="is_on",
                ),
            )

        # Pads (Notes 8-23)
        for i, note in enumerate(LAYER_A_PADS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"pad_{i}@{layer}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=MIDI_CHANNEL,
                    note=note,
                    value_source="is_on",
                ),
            )

        # Knobs (CC 1-8) - for initialization to center
        for i, cc in enumerate(LAYER_A_KNOBS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"knob_{i}@{layer}",
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=MIDI_CHANNEL,
                    control=cc,
                    value_source="value",
                ),
            )

        # Layer B feedback
        layer = "layer_b"

        # Knob buttons (Notes 24-31)
        for i, note in enumerate(LAYER_B_KNOB_BUTTONS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"knob_button_{i}@{layer}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=MIDI_CHANNEL,
                    note=note,
                    value_source="is_on",
                ),
            )

        # Pads (Notes 32-47)
        for i, note in enumerate(LAYER_B_PADS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"pad_{i}@{layer}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=MIDI_CHANNEL,
                    note=note,
                    value_source="is_on",
                ),
            )

        # Knobs (CC 11-18) - for initialization to center
        for i, cc in enumerate(LAYER_B_KNOBS, start=1):
            mappings.append(
                FeedbackMapping(
                    control_id=f"knob_{i}@{layer}",
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=MIDI_CHANNEL,
                    control=cc,
                    value_source="value",
                ),
            )

        return mappings

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]] = None,
    ) -> dict[str, int]:
        """
        Initialize X-Touch Mini to known state.

        - Turn off all pad LEDs (clean state)
        - Initialize all knobs to center position (64)

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            Empty dict (positions unknown until user moves controls)
        """
        logger.info("Initializing X-Touch Mini")

        # Store send_message for deferred feedback (used in translate_input)
        self._send_message = send_message

        # Build note-to-control mapping for Note Off handling
        for i, note in enumerate(LAYER_A_PADS, start=1):
            self._note_to_pad_control[note] = f"pad_{i}@layer_a"
        for i, note in enumerate(LAYER_B_PADS, start=1):
            self._note_to_pad_control[note] = f"pad_{i}@layer_b"

        # Turn off all pad LEDs for both layers
        for note in LAYER_A_PADS + LAYER_B_PADS:
            msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Turn off all knob-button LEDs for both layers
        for note in LAYER_A_KNOB_BUTTONS + LAYER_B_KNOB_BUTTONS:
            msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Initialize all knobs to center position (64) for both layers
        for cc in LAYER_A_KNOBS + LAYER_B_KNOBS:
            msg = mido.Message("control_change", channel=MIDI_CHANNEL, control=cc, value=64)
            send_message(msg)

        # Set initial active bank (assume Layer A)
        self._last_active_bank = "layer_a"

        logger.info("X-Touch Mini initialization complete")
        return {}

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence for X-Touch Mini.

        Turn off all LEDs for clean state.
        """
        logger.info("Shutting down X-Touch Mini")

        # Turn off all pad LEDs
        for note in LAYER_A_PADS + LAYER_B_PADS:
            msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Turn off all knob-button LEDs
        for note in LAYER_A_KNOB_BUTTONS + LAYER_B_KNOB_BUTTONS:
            msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        logger.info("X-Touch Mini shutdown complete")

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with automatic bank detection and deferred pad feedback.

        Bank detection is by note/CC range:
        - Notes 0-23 or CC 1-9 -> Layer A
        - Notes 24-47 or CC 10-18 -> Layer B

        Deferred feedback for pads:
        - Note Off for pads triggers deferred LED feedback
        - Returns None to skip callbacks (callback already fired on Note On)

        Args:
            msg: MIDI message to translate

        Returns:
            (control_id, value, signal_type) or None
        """
        # Handle Note Off for pads - send deferred feedback, skip callbacks
        if msg.type == "note_off" and msg.channel == MIDI_CHANNEL:
            control_id = self._note_to_pad_control.get(msg.note)
            if control_id and control_id in self._pending_feedback:
                # Send deferred LED feedback
                is_on = self._pending_feedback.pop(control_id)
                feedback_note = self._get_feedback_note(control_id)
                if feedback_note is not None and self._send_message:
                    velocity = 127 if is_on else 0
                    feedback_msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=feedback_note, velocity=velocity)
                    logger.info(f"DEFERRED FEEDBACK: {control_id} -> note={feedback_note} velocity={velocity}")
                    self._send_message(feedback_msg)
                return None  # Skip normal processing - no callbacks

        # Detect bank from message
        new_bank = self._detect_bank(msg)
        if new_bank and new_bank != self._last_active_bank:
            logger.info(f"X-Touch Mini bank switch: {self._last_active_bank} -> {new_bank}")
            self._last_active_bank = new_bank

        # Use default mapping lookup
        return super().translate_input(msg)

    def _detect_bank(self, msg: mido.Message) -> Optional[str]:
        """
        Detect bank from MIDI message.

        Args:
            msg: MIDI message

        Returns:
            Bank ID ("layer_a" or "layer_b") or None if can't determine
        """
        if msg.type in ("note_on", "note_off"):
            note = msg.note
            if note in ALL_LAYER_A_NOTES:
                return "layer_a"
            elif note in ALL_LAYER_B_NOTES:
                return "layer_b"

        elif msg.type == "control_change":
            cc = msg.control
            if cc in ALL_LAYER_A_CCS:
                return "layer_a"
            elif cc in ALL_LAYER_B_CCS:
                return "layer_b"

        return None

    def compute_control_state(
        self,
        control_id: str,
        value: int,
        signal_type: str,
        current_state: ControlState,
        control_definition: ControlDefinition,
    ) -> Optional[ControlState]:
        """
        Compute control state with deferred feedback for TOGGLE pads.

        For TOGGLE pads (Note On only):
        - Toggle the state (flip is_on)
        - Mark for deferred feedback (LED will be set on Note Off)

        For MOMENTARY pads:
        - Use default framework behavior (is_on follows Note On/Off)

        Args:
            control_id: Control identifier (e.g., "pad_1@layer_a")
            value: Raw MIDI value (0-127)
            signal_type: Signal type from translate_input
            current_state: Current control state
            control_definition: Control definition (resolved with config overrides)

        Returns:
            ControlState for TOGGLE pads (with deferred feedback marked),
            None for MOMENTARY pads and other controls (use default behavior)
        """
        # Only apply custom toggle logic for TOGGLE pads
        # MOMENTARY pads use default framework behavior
        is_pad = "pad_" in control_id and "button" not in control_id
        is_toggle = control_definition.control_type == ControlType.TOGGLE

        if is_pad and is_toggle and value > 0:
            # TOGGLE pad: flip state on Note On, defer feedback until Note Off
            new_is_on = not current_state.is_on
            # Mark for deferred feedback (will be sent on Note Off)
            self._pending_feedback[control_id] = new_is_on

            # LED mode only applies when ON
            led_mode = control_definition.led_mode if new_is_on else None

            # Return new state (callback will fire once here)
            # NOTE: control_id is REQUIRED by ControlState
            return ControlState(
                control_id=control_id,  # REQUIRED!
                is_on=new_is_on,
                value=value,
                color=control_definition.on_color if new_is_on else control_definition.off_color,
                led_mode=led_mode,
            )

        return None  # Use default behavior for MOMENTARY pads and other controls

    def translate_feedback(self, control_id: str, state_dict: dict) -> list[mido.Message]:
        """
        Translate control state to MIDI feedback messages.

        For TOGGLE pads: Returns empty list (deferred feedback sent in translate_input on Note Off)
        For MOMENTARY pads: Immediate feedback (Note On with velocity)
        For knob-buttons: Note On with velocity 127 (on) or 0 (off)
        For knobs: CC for value setting

        Args:
            control_id: Control identifier (e.g., "pad_1@layer_a")
            state_dict: State dictionary (is_on, value, etc.)

        Returns:
            List of MIDI messages to send
        """
        messages = []
        is_on = state_dict.get("is_on", False)

        # Handle pads
        if "pad_" in control_id and "button" not in control_id:
            # TOGGLE pads have pending feedback - suppress auto-feedback
            # MOMENTARY pads don't have pending feedback - allow immediate feedback
            if control_id in self._pending_feedback:
                logger.debug(f"FEEDBACK SUPPRESSED for {control_id} (using deferred feedback)")
                return []  # Deferred feedback will be sent on Note Off
            else:
                # MOMENTARY pad - send immediate feedback
                note = self._get_feedback_note(control_id)
                if note is not None:
                    velocity = 127 if is_on else 0
                    msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=velocity)
                    logger.debug(f"MOMENTARY FEEDBACK: {control_id} -> note={note} velocity={velocity}")
                    messages.append(msg)
                return messages

        # Handle knob-buttons (Note On for LED)
        elif "knob_button_" in control_id:
            note = self._get_feedback_note(control_id)
            if note is not None:
                velocity = 127 if is_on else 0
                msg = mido.Message("note_on", channel=MIDI_CHANNEL, note=note, velocity=velocity)
                logger.info(f"FEEDBACK: {control_id} -> note={note} velocity={velocity}")
                messages.append(msg)

        # Handle knobs (CC for value - used during init)
        elif "knob_" in control_id and "button" not in control_id:
            value = state_dict.get("value", 64) or 64
            cc = self._get_feedback_cc(control_id)
            if cc is not None:
                msg = mido.Message("control_change", channel=MIDI_CHANNEL, control=cc, value=value)
                messages.append(msg)

        return messages

    def _get_feedback_note(self, control_id: str) -> Optional[int]:
        """
        Get the MIDI note number for feedback to a pad or knob-button.

        Args:
            control_id: Control identifier (e.g., "pad_1@layer_a", "knob_button_3@layer_b")

        Returns:
            MIDI note number or None if not found
        """
        parts = control_id.split("@")
        control_part = parts[0]  # e.g., "pad_1" or "knob_button_3"
        layer = parts[1] if len(parts) > 1 else "layer_a"

        if control_part.startswith("pad_"):
            pad_num = int(control_part.split("_")[1])  # 1-16
            if layer == "layer_a":
                # Pads 1-16 map to notes 8-23
                return LAYER_A_PADS[pad_num - 1]
            else:
                # Pads 1-16 map to notes 32-47
                return LAYER_B_PADS[pad_num - 1]

        elif control_part.startswith("knob_button_"):
            btn_num = int(control_part.split("_")[2])  # 1-8
            if layer == "layer_a":
                # Knob buttons 1-8 map to notes 0-7
                return LAYER_A_KNOB_BUTTONS[btn_num - 1]
            else:
                # Knob buttons 1-8 map to notes 24-31
                return LAYER_B_KNOB_BUTTONS[btn_num - 1]

        return None

    def _get_feedback_cc(self, control_id: str) -> Optional[int]:
        """
        Get the MIDI CC number for feedback to a knob.

        Args:
            control_id: Control identifier (e.g., "knob_1@layer_a")

        Returns:
            MIDI CC number or None if not found
        """
        parts = control_id.split("@")
        control_part = parts[0]  # e.g., "knob_1"
        layer = parts[1] if len(parts) > 1 else "layer_a"

        if control_part.startswith("knob_") and "button" not in control_part:
            knob_num = int(control_part.split("_")[1])  # 1-8
            if layer == "layer_a":
                # Knobs 1-8 map to CC 1-8
                return LAYER_A_KNOBS[knob_num - 1]
            else:
                # Knobs 1-8 map to CC 11-18
                return LAYER_B_KNOBS[knob_num - 1]

        return None
