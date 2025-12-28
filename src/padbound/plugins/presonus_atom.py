"""
PreSonus Atom MIDI Controller Plugin.

Hardware specifications:
- 16 RGB backlit drum pads (4x4 grid, notes 36-51 on channel 10)
- 4 endless rotary encoders (CC 14-17, relative mode)
- 8 pad banks (hardware-managed, not software-accessible)
- Multiple function buttons with LEDs (various CCs on channel 1)
- Navigation buttons: Up, Down, Left, Right, Select, Zoom
- Transport controls: Click, Record, Play, Stop
- USB MIDI interface, bus powered

Control features:
- Pads send NOTE messages and support full RGB feedback in Native mode
- Encoders send relative CC messages with acceleration (1-63=CW, 65-127=CCW)
- Buttons send CC messages with LED feedback capability

================================================================================
NATIVE CONTROL MODE PROTOCOL
================================================================================

The PreSonus Atom has two operating modes:
1. MIDI mode (default): Device operates autonomously, LEDs self-managed
2. Native Control mode: Software controls LEDs, device becomes "slave"

Mode switching is done via:
    Channel 15, Note 0:
        Velocity 0   = MIDI compatible mode (default)
        Velocity 127 = Native control mode (required for LED control)

--------------------------------------------------------------------------------
PAD RGB LED CONTROL (Native Mode Only)
--------------------------------------------------------------------------------
Each pad's LED requires 4 separate messages:

1. STATE message - Determines LED behavior:
    note_on(channel=0, note=<pad_note>, velocity=<state>)

    States:
        0   = Unlit (off)
        1   = Blink (flashing)
        2   = Breathe (pulsing)
        127 = Solid (steady on)

2. RED channel:
    note_on(channel=1, note=<pad_note>, velocity=<red_0-127>)

3. GREEN channel:
    note_on(channel=2, note=<pad_note>, velocity=<green_0-127>)

4. BLUE channel:
    note_on(channel=3, note=<pad_note>, velocity=<blue_0-127>)

Pad notes: 36-51 (Pad 1 = note 36, Pad 16 = note 51)

Example (set Pad 1 to solid red):
    note_on(channel=0, note=36, velocity=127)  # Solid state
    note_on(channel=1, note=36, velocity=127)  # Red = max
    note_on(channel=2, note=36, velocity=0)    # Green = 0
    note_on(channel=3, note=36, velocity=0)    # Blue = 0

--------------------------------------------------------------------------------
ENCODER MESSAGES (Relative Mode with Acceleration)
--------------------------------------------------------------------------------
CC messages on channel 0:
    Encoder 1: CC 14
    Encoder 2: CC 15
    Encoder 3: CC 16
    Encoder 4: CC 17

Values (relative encoding with acceleration):
    1-63   = Clockwise rotation, value = number of steps
             (1 = slow/single step, higher = faster rotation)
    64     = No change (center, typically not sent)
    65-127 = Counter-clockwise rotation, steps = value - 64
             (65 = -1 step, 70 = -6 steps, etc.)

Examples:
    value=1  -> CW,  delta = +1 (slow rotation)
    value=6  -> CW,  delta = +6 (fast rotation)
    value=65 -> CCW, delta = -1 (slow rotation)
    value=70 -> CCW, delta = -6 (fast rotation)

--------------------------------------------------------------------------------
BUTTON MESSAGES
--------------------------------------------------------------------------------
All buttons send CC messages on channel 0.
Button press: value=127, Button release: value=0

Button CC assignments:
    Note Repeat     = CC 24     Full Level      = CC 25
    Inst Bank       = CC 26     Preset Up/Down  = CC 27
    Inst Show/Hide  = CC 29     Event Nudge     = CC 30
    Event Editor    = CC 31     Shift           = CC 32 (no LED)
    Set Loop        = CC 85     Setup           = CC 86
    Nav Up          = CC 87     Nav Down        = CC 89
    Nav Left        = CC 90     Nav Right       = CC 102
    Nav Select      = CC 103    Nav Zoom        = CC 104
    Click           = CC 105    Record          = CC 107
    Play            = CC 109    Stop            = CC 111

Button LED control (same CC, send value 0=off or 127=on):
    control_change(channel=0, control=<cc>, value=<0 or 127>)

--------------------------------------------------------------------------------
PAD INPUT MESSAGES (Native Mode)
--------------------------------------------------------------------------------
Pads send note messages on channel 1 (index 0):
    Note On:  note_on(channel=0, note=<36-51>, velocity=<velocity>)
    Note Off: note_off(channel=0, note=<36-51>, velocity=0)

================================================================================
References:
- Protocol from: https://github.com/EMATech/AtomCtrl
- Hardware manual: PreSonus ATOM Owner's Manual
================================================================================
"""

from typing import Callable, Optional

import mido
from pydantic import BaseModel, Field

from padbound.controls import (
    ControlCapabilities,
    ControlDefinition,
    ControllerCapabilities,
    ControlState,
    ControlType,
    ControlTypeModes,
    LEDAnimationType,
    LEDMode,
)
from padbound.logging_config import get_logger
from padbound.plugin import (
    BatchFeedbackResult,
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)
from padbound.utils import RGBColor

logger = get_logger(__name__)


class AtomRGBColor(RGBColor):
    """RGB color with PreSonus Atom-specific message generation.

    Extends base RGBColor with methods for generating the MIDI messages
    required by the Atom's Native Control mode LED protocol.
    """

    def to_rgb_messages(self, pad_note: int) -> list[mido.Message]:
        """Generate 3 note_on messages for R, G, B channels.

        The Atom uses separate MIDI channels for each color component:
        - Channel 1: Red (0-127)
        - Channel 2: Green (0-127)
        - Channel 3: Blue (0-127)

        Args:
            pad_note: The pad note number (36-51)

        Returns:
            List of 3 MIDI messages setting R, G, B values
        """
        # Convert from 0-255 to 0-127 (MIDI range)
        r, g, b = self.to_midi_range()
        return [
            mido.Message("note_on", channel=1, note=pad_note, velocity=r),
            mido.Message("note_on", channel=2, note=pad_note, velocity=g),
            mido.Message("note_on", channel=3, note=pad_note, velocity=b),
        ]


class AtomPadLEDState(BaseModel):
    """LED state for a single Atom pad.

    Combines LED state (solid/blink/breathe/off) with RGB color
    and generates the required MIDI messages.
    """

    pad_note: int = Field(ge=36, le=51, description="Pad MIDI note (36-51)")
    state: int = Field(default=127, description="LED state: 0=unlit, 1=blink, 2=breathe, 127=solid")
    color: AtomRGBColor = Field(description="RGB color for the pad")

    def to_messages(self) -> list[mido.Message]:
        """Generate all 4 messages needed to set pad LED.

        Returns:
            List of 4 MIDI messages: [state, red, green, blue]
        """
        messages = [
            # State message on channel 0 (same as input channel)
            mido.Message("note_on", channel=0, note=self.pad_note, velocity=self.state),
        ]
        # Add RGB color messages
        messages.extend(self.color.to_rgb_messages(self.pad_note))
        return messages


class PreSonusAtomPlugin(ControllerPlugin):
    """
    PreSonus Atom plugin with RGB pad control and relative encoders.

    Features:
    - 16 RGB pads with full color control via Native mode
    - 4 endless encoders with relative value reporting
    - 20 function/transport buttons with LED feedback
    - Automatic Native mode initialization for LED control
    """

    # Mode switching
    MODE_CHANNEL = 15
    MODE_NOTE = 0
    MODE_MIDI = 0
    MODE_NATIVE = 127

    # Pads
    PAD_COUNT = 16
    PAD_CHANNEL = 0  # Channel 1 (0-indexed) - Native mode input is on channel 0
    PAD_START_NOTE = 36  # Pad 1 = note 36, Pad 16 = note 51

    # LED states
    LED_UNLIT = 0
    LED_BLINK = 1
    LED_BREATHE = 2
    LED_SOLID = 127

    # RGB channels (0-indexed)
    RED_CHANNEL = 1
    GREEN_CHANNEL = 2
    BLUE_CHANNEL = 3

    # Encoders
    ENCODER_COUNT = 4
    ENCODER_START_CC = 14  # CC 14-17
    ENCODER_CHANNEL = 0
    ENCODER_CW = 1
    ENCODER_CCW = 65

    # Button definitions: name -> CC number
    # All buttons are on channel 0
    BUTTON_CCS = {
        "note_repeat": 24,
        "full_level": 25,
        "inst_bank": 26,
        "preset_up_down": 27,
        "inst_show_hide": 29,
        "event_nudge": 30,
        "event_editor": 31,
        "shift": 32,
        "set_loop": 85,
        "setup": 86,
        "nav_up": 87,
        "nav_down": 89,
        "nav_left": 90,
        "nav_right": 102,
        "nav_select": 103,
        "nav_zoom": 104,
        "click": 105,
        "record": 107,
        "play": 109,
        "stop": 111,
    }

    # Buttons without LED feedback
    BUTTONS_NO_LED = {"shift"}

    def __init__(self):
        """Initialize plugin."""
        super().__init__()
        # Track current pad colors for state management
        self._current_pad_colors: dict[str, tuple[int, int, int]] = {}
        # Track encoder positions for relative-to-absolute conversion
        self._encoder_positions: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "PreSonus Atom"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "ATOM",
            "PreSonus ATOM",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # Banks are hardware-managed
            indexing_scheme="1d",  # Linear pad numbering (1-16)
            supports_persistent_configuration=False,  # No SysEx programming
        )

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls.

        Creates:
        - 16 RGB pads (pad_1 through pad_16) as toggle controls
        - 4 encoders (encoder_1 through encoder_4) as continuous controls
        - 20 buttons as momentary controls
        """
        definitions = []

        # 16 RGB pads - support both TOGGLE and MOMENTARY modes
        for pad_num in range(1, self.PAD_COUNT + 1):
            definitions.append(
                ControlDefinition(
                    control_id=f"pad_{pad_num}",
                    control_type=ControlType.TOGGLE,  # Default to TOGGLE
                    category="pad",
                    type_modes=ControlTypeModes(
                        supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                        default_type=ControlType.TOGGLE,
                        requires_hardware_sync=False,  # Mode is software-only
                    ),
                    capabilities=ControlCapabilities(
                        supports_feedback=True,
                        requires_feedback=True,  # Device needs LED updates
                        supports_led=True,
                        supports_color=True,
                        color_mode="rgb",
                        supported_led_modes=[
                            LEDMode(animation_type=LEDAnimationType.SOLID),
                            LEDMode(animation_type=LEDAnimationType.PULSE),
                            LEDMode(animation_type=LEDAnimationType.BLINK),
                        ],
                        requires_discovery=False,
                    ),
                    display_name=f"Pad {pad_num}",
                ),
            )

        # 4 encoders (relative mode)
        for enc_num in range(1, self.ENCODER_COUNT + 1):
            definitions.append(
                ControlDefinition(
                    control_id=f"encoder_{enc_num}",
                    control_type=ControlType.CONTINUOUS,
                    category="encoder",
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # Encoders are read-only
                        requires_discovery=True,  # Initial position unknown
                    ),
                    min_value=0,
                    max_value=127,
                    display_name=f"Encoder {enc_num}",
                ),
            )

        # Button category mapping
        transport_buttons = {"click", "record", "play", "stop"}
        nav_buttons = {"nav_up", "nav_down", "nav_left", "nav_right", "nav_select", "nav_zoom"}
        # All other buttons are "mode" buttons

        # Buttons
        for btn_name, _cc in self.BUTTON_CCS.items():
            has_led = btn_name not in self.BUTTONS_NO_LED
            # Format display name: "note_repeat" -> "Note Repeat"
            display_name = btn_name.replace("_", " ").title()

            # Determine category
            if btn_name in transport_buttons:
                category = "transport"
            elif btn_name in nav_buttons:
                category = "navigation"
            else:
                category = "mode"

            definitions.append(
                ControlDefinition(
                    control_id=btn_name,
                    control_type=ControlType.MOMENTARY,
                    category=category,
                    capabilities=ControlCapabilities(
                        supports_feedback=has_led,
                        requires_feedback=has_led,
                        supports_led=has_led,
                        supports_color=False,  # Single-color LEDs
                        requires_discovery=False,
                    ),
                    display_name=display_name,
                ),
            )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        - Pads: NOTE_ON/NOTE_OFF on channel 9, notes 36-51
        - Encoders: CONTROL_CHANGE on channel 0, CC 14-17
        - Buttons: CONTROL_CHANGE on channel 0, various CCs
        """
        mappings = []

        # Pad mappings
        for pad_num in range(1, self.PAD_COUNT + 1):
            control_id = f"pad_{pad_num}"
            midi_note = self.PAD_START_NOTE + pad_num - 1

            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=self.PAD_CHANNEL,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=self.PAD_CHANNEL,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                ],
            )

        # Encoder mappings
        for enc_num in range(1, self.ENCODER_COUNT + 1):
            enc_cc = self.ENCODER_START_CC + enc_num - 1
            control_id = f"encoder_{enc_num}"

            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=self.ENCODER_CHANNEL,
                    control=enc_cc,
                    control_id=control_id,
                    signal_type="default",
                ),
            )

        # Button mappings
        for btn_name, cc in self.BUTTON_CCS.items():
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=0,
                    control=cc,
                    control_id=btn_name,
                    signal_type="default",
                ),
            )

        return mappings

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]] = None,
    ) -> dict[str, int]:
        """
        Initialize Atom to Native Control mode.

        Switches to Native mode (required for LED control), then clears
        all LEDs to a known state.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages (unused)

        Returns:
            Empty dict (no discovery needed)
        """
        logger.info("Initializing PreSonus Atom")

        # Switch to Native Control mode
        mode_msg = mido.Message("note_off", channel=self.MODE_CHANNEL, note=self.MODE_NOTE, velocity=self.MODE_NATIVE)
        send_message(mode_msg)
        logger.debug("Switched to Native Control mode")

        # Clear all pad LEDs (set to unlit/black)
        for pad_num in range(1, self.PAD_COUNT + 1):
            pad_note = self.PAD_START_NOTE + pad_num - 1
            led_state = AtomPadLEDState(pad_note=pad_note, state=self.LED_UNLIT, color=AtomRGBColor(r=0, g=0, b=0))
            for msg in led_state.to_messages():
                send_message(msg)

        # Clear all button LEDs
        for btn_name, cc in self.BUTTON_CCS.items():
            if btn_name not in self.BUTTONS_NO_LED:
                msg = mido.Message("control_change", channel=0, control=cc, value=0)
                send_message(msg)

        # Reset color tracking
        self._current_pad_colors = {}

        # Initialize encoder positions to center (64)
        for i in range(1, self.ENCODER_COUNT + 1):
            self._encoder_positions[f"encoder_{i}"] = 64

        logger.info("PreSonus Atom initialization complete")
        return {}

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence - clear LEDs and restore MIDI mode.

        Args:
            send_message: Function to send MIDI messages
        """
        logger.info("Shutting down PreSonus Atom")

        # Clear all pad LEDs
        for pad_num in range(1, self.PAD_COUNT + 1):
            pad_note = self.PAD_START_NOTE + pad_num - 1
            led_state = AtomPadLEDState(pad_note=pad_note, state=self.LED_UNLIT, color=AtomRGBColor(r=0, g=0, b=0))
            for msg in led_state.to_messages():
                send_message(msg)

        # Clear all button LEDs
        for btn_name, cc in self.BUTTON_CCS.items():
            if btn_name not in self.BUTTONS_NO_LED:
                msg = mido.Message("control_change", channel=0, control=cc, value=0)
                send_message(msg)

        # Switch back to MIDI mode (restore default behavior)
        mode_msg = mido.Message("note_off", channel=self.MODE_CHANNEL, note=self.MODE_NOTE, velocity=self.MODE_MIDI)
        send_message(mode_msg)
        logger.debug("Restored MIDI mode")

        logger.info("PreSonus Atom shutdown complete")

    def translate_feedback(
        self,
        control_id: str,
        state: ControlState,
        definition: ControlDefinition,
    ) -> list[mido.Message]:
        """
        Translate control state to LED feedback.

        For PreSonus Atom:
        - Pads: RGB LEDs via 4 note messages (state + R + G + B)
        - Buttons: Single-color LEDs via CC (0=off, 127=on)
        - Encoders: No feedback (read-only)

        Args:
            control_id: Control being updated
            state: Current control state (is_on, value, color, led_mode, etc.)
            definition: Control definition (on_led_mode, off_led_mode, colors, capabilities)

        Returns:
            List of MIDI messages for LED control
        """
        messages = []

        # Handle pad feedback (RGB LEDs)
        if control_id.startswith("pad_"):
            try:
                pad_num = int(control_id.split("_")[1])
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid pad control_id format: {control_id} ({e})")
                return []

            if not (1 <= pad_num <= self.PAD_COUNT):
                logger.warning(f"Pad number {pad_num} out of range (1-{self.PAD_COUNT})")
                return []

            pad_note = self.PAD_START_NOTE + pad_num - 1

            # Determine LED state and color
            is_on = state.is_on or False
            color_str = state.color or "off"
            # Compute definition_led_mode from definition based on is_on state
            definition_led_mode = definition.on_led_mode if is_on else definition.off_led_mode
            # Use state's led_mode if set, otherwise fall back to definition's
            led_mode = state.led_mode or definition_led_mode
            led_mode_str = led_mode.animation_type.value if led_mode else "solid"

            # Parse color
            rgb_color = AtomRGBColor.from_string(color_str)

            # Map led_mode to Atom LED state value
            if is_on:
                led_state_map = {
                    "solid": self.LED_SOLID,  # 127
                    "pulse": self.LED_BREATHE,  # 2
                    "blink": self.LED_BLINK,  # 1
                }
                led_state_value = led_state_map.get(led_mode_str, self.LED_SOLID)
            else:
                # OFF state always uses solid (dim color shown steadily)
                led_state_value = self.LED_SOLID

            # Build LED state message
            led_state = AtomPadLEDState(pad_note=pad_note, state=led_state_value, color=rgb_color)
            messages.extend(led_state.to_messages())

            # Track current color
            self._current_pad_colors[control_id] = (rgb_color.r, rgb_color.g, rgb_color.b)

        # Handle button feedback (single-color LEDs)
        elif control_id in self.BUTTON_CCS:
            if control_id in self.BUTTONS_NO_LED:
                return []  # No LED for this button

            cc = self.BUTTON_CCS[control_id]
            is_on = state.is_on or False
            value = 127 if is_on else 0

            msg = mido.Message("control_change", channel=0, control=cc, value=value)
            messages.append(msg)

        # Encoders have no feedback capability
        return messages

    def translate_feedback_batch(
        self,
        updates: list[tuple[str, ControlState, ControlDefinition]],
    ) -> BatchFeedbackResult:
        """
        Translate multiple control states to MIDI feedback in a batch.

        For PreSonus Atom, there's no batch optimization possible since each pad
        requires 4 separate MIDI messages. This implementation collects all messages
        from translate_feedback() calls.

        No timing delays are needed for this controller.

        Args:
            updates: List of (control_id, state, definition) tuples to process.

        Returns:
            BatchFeedbackResult with all messages, no custom delays.
        """
        messages = []
        for control_id, state, definition in updates:
            messages.extend(self.translate_feedback(control_id, state, definition))
        return BatchFeedbackResult(messages=messages)

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with encoder relative mode handling.

        For encoders, converts relative values:
        - Value 1 (CW) -> +1 increment
        - Value 65 (CCW) -> -1 decrement

        Other messages are handled by default mapping.

        Args:
            msg: MIDI message to translate

        Returns:
            (control_id, value, signal_type) or None to use default mapping
        """
        # Handle encoder relative messages specially
        if msg.type == "control_change" and msg.channel == self.ENCODER_CHANNEL:
            cc = msg.control
            # Check if this is an encoder CC (14-17)
            if self.ENCODER_START_CC <= cc < self.ENCODER_START_CC + self.ENCODER_COUNT:
                enc_num = cc - self.ENCODER_START_CC + 1
                control_id = f"encoder_{enc_num}"

                # Convert relative value to delta with acceleration support
                # Values 1-63: CW rotation (1=+1, 6=+6, etc.)
                # Values 65-127: CCW rotation (65=-1, 70=-6, etc.)
                if 1 <= msg.value <= 63:
                    delta = msg.value  # CW: positive delta
                elif 64 <= msg.value <= 127:
                    delta = -(msg.value - 64)  # CCW: negative delta
                else:
                    delta = 0  # value=0 means no change

                # Return with "relative" signal type to indicate delta value
                return (control_id, delta, "relative")

        # Let default mapping handle everything else (pads, buttons)
        return super().translate_input(msg)

    def compute_control_state(
        self,
        control_id: str,
        value: int,
        signal_type: str,
        current_state: ControlState,
        control_definition: ControlDefinition,
    ) -> tuple[Optional[ControlState], bool]:
        """
        Convert encoder deltas to absolute positions.

        For encoders (signal_type="relative"), this accumulates the delta values
        into a tracked position (0-127) so that all continuous controls return
        consistent normalized values.

        Args:
            control_id: Control identifier (e.g., "encoder_1")
            value: Raw value from translate_input (delta for encoders)
            signal_type: "relative" for encoders, "cc" for absolute controls
            current_state: Current control state
            control_definition: Control definition

        Returns:
            ControlState with accumulated position for encoders,
            None for other controls (use default behavior)
        """
        if signal_type == "relative" and control_id.startswith("encoder_"):
            # Accumulate delta, clamp to 0-127
            current_pos = self._encoder_positions.get(control_id, 64)
            new_pos = max(0, min(127, current_pos + value))
            self._encoder_positions[control_id] = new_pos

            # Return state with accumulated position (not delta)
            return (
                ControlState(
                    control_id=control_id,
                    value=new_pos,
                    normalized_value=new_pos / 127.0,
                ),
                True,
            )

        return (None, True)  # Use default handling for other controls
