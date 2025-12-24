"""
Example MIDI Controller Plugin.

This is a comprehensive reference implementation demonstrating all essential
plugin API patterns using modern best practices.

Hardware specifications:
- 16 RGB backlit pads per bank (toggle/momentary switchable)
- 4 endless rotary knobs per bank (continuous, read-only)
- 2 mode buttons per bank (momentary with LED feedback)
- 2 banks (Bank 1, Bank 2) with automatic detection via note/CC range
- USB MIDI interface

Control features:
- Pads: RGB LED feedback using velocity-based color palette
- Pads: Software-configurable toggle/momentary mode (no hardware sync needed)
- Knobs: Continuous values (0-127), read-only
- Buttons: Single-color LED feedback (on/off)

================================================================================
MIDI MAPPING TABLE
================================================================================

All controls use MIDI channel 1 (channel 0 in 0-indexed notation).
Bank detection is automatic via note/CC range.

BANK 1:
  Pads 1-16:    Notes 36-51  (channel 0)
  Knobs 1-4:    CC 16-19     (channel 0)
  Shift button: Note 64      (channel 0)
  Select button: Note 65     (channel 0)

BANK 2:
  Pads 1-16:    Notes 52-67  (channel 0)
  Knobs 1-4:    CC 20-23     (channel 0)
  Shift button: Note 66      (channel 0)
  Select button: Note 67     (channel 0)

================================================================================
LED CONTROL PROTOCOL
================================================================================

RGB Pads (velocity-based color palette):
  Format: note_on(channel=0, note=<pad_note>, velocity=<color_value>)

  Color Palette:
    0  = Off (black)     - No LED
    5  = Red             - Error/stop states
    21 = Green           - Success/go states
    13 = Yellow          - Warning/caution states
    45 = Blue            - Info/selected states
    53 = Magenta         - Special modes
    37 = Cyan            - Alternative states
    3  = White           - Active/highlighted states

Buttons (simple on/off):
  Format: note_on(channel=0, note=<button_note>, velocity=<0 or 127>)
    velocity 127 = LED ON (button active)
    velocity 0   = LED OFF (button inactive)

Knobs (no feedback):
  Read-only controls, no LED feedback capability.
  Initial position unknown until knob is moved.

================================================================================
EXAMPLE USAGE
================================================================================

```python
from padbound import PadboundController

# Initialize controller
controller = PadboundController("Example MIDI")

# Register pad callback (works for both banks)
@controller.on_control("pad_1@bank_1")
def on_pad_1(state):
    print(f"Pad 1 (Bank 1): {'ON' if state.is_on else 'OFF'}")
    print(f"Color: {state.color}")

# Register callback for all pads using category
@controller.on_category("pad")
def on_any_pad(control_id, state):
    print(f"{control_id}: {state.is_on}")

# Register knob callback
@controller.on_control("knob_1@bank_1")
def on_knob_1(state):
    print(f"Knob 1: {state.value} (normalized: {state.normalized_value:.2f})")

# Set pad color programmatically
controller.set_control_color("pad_1@bank_1", "green")

# Toggle pad mode (toggle/momentary)
controller.set_control_type("pad_1@bank_1", ControlType.MOMENTARY)
```

================================================================================
"""

from typing import Callable, Optional

import mido

from padbound.controls import (
    BankDefinition,
    ControlCapabilities,
    ControlDefinition,
    ControllerCapabilities,
    ControlType,
    ControlTypeModes,
)
from padbound.logging_config import get_logger
from padbound.plugin import (
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)

logger = get_logger(__name__)


class ExampleMIDIController(ControllerPlugin):
    """
    Example MIDI Controller plugin demonstrating all essential patterns.

    This reference implementation shows:
    - Multi-bank support with automatic detection
    - Mixed control types (toggle pads, continuous knobs, momentary buttons)
    - RGB LED feedback via velocity-based color palette
    - Toggle/Momentary mode switching for pads
    - Category-based control organization
    - Comprehensive capability declarations
    """

    # =============================================================================
    # Hardware Configuration
    # =============================================================================

    PAD_COUNT = 16
    KNOB_COUNT = 4
    BUTTON_COUNT = 2
    BANK_COUNT = 2

    # MIDI channel (0-indexed: 0 = MIDI channel 1)
    MIDI_CHANNEL = 0

    # =============================================================================
    # Bank 1 MIDI Assignments
    # =============================================================================

    BANK1_PAD_START_NOTE = 36  # Notes 36-51 (16 pads)
    BANK1_KNOB_START_CC = 16  # CC 16-19 (4 knobs)
    BANK1_BUTTON_SHIFT = 64  # Note 64 (shift button)
    BANK1_BUTTON_SELECT = 65  # Note 65 (select button)

    # =============================================================================
    # Bank 2 MIDI Assignments
    # =============================================================================

    BANK2_PAD_START_NOTE = 52  # Notes 52-67 (16 pads)
    BANK2_KNOB_START_CC = 20  # CC 20-23 (4 knobs)
    BANK2_BUTTON_SHIFT = 66  # Note 66 (shift button)
    BANK2_BUTTON_SELECT = 67  # Note 67 (select button)

    # =============================================================================
    # Color Palette (Velocity Values)
    # =============================================================================

    COLOR_PALETTE = {
        "off": 0,
        "red": 5,
        "green": 21,
        "yellow": 13,
        "blue": 45,
        "magenta": 53,
        "cyan": 37,
        "white": 3,
    }

    def __init__(self):
        """Initialize plugin with bank tracking."""
        super().__init__()
        self._last_active_bank: Optional[str] = None
        self._send_message: Optional[Callable[[mido.Message], None]] = None

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "Example MIDI Controller"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return ["Example MIDI", "ExampleMIDI"]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # Bank detection via note/CC range
            indexing_scheme="1d",  # Linear numbering (pad_1...pad_16)
            supports_persistent_configuration=False,  # No SysEx programming
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 2 banks.

        Each bank contains the same control layout (16 pads + 4 knobs + 2 buttons)
        but uses different MIDI note/CC ranges for automatic detection.
        """
        return [
            BankDefinition(
                bank_id="bank_1",
                control_type=ControlType.TOGGLE,
                display_name="Bank 1",  # Primary control type
            ),
            BankDefinition(
                bank_id="bank_2",
                control_type=ControlType.TOGGLE,
                display_name="Bank 2",  # Primary control type
            ),
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across both banks.

        Creates 2 banks × (16 pads + 4 knobs + 2 buttons) = 44 controls total.
        """
        definitions = []

        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"

            # 16 RGB pads per bank (toggle/momentary switchable)
            for pad_num in range(1, self.PAD_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{pad_num}@{bank_id}",
                        control_type=ControlType.TOGGLE,  # Default to TOGGLE
                        category="pad",
                        type_modes=ControlTypeModes(
                            supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                            default_type=ControlType.TOGGLE,
                            requires_hardware_sync=False,  # Software-only mode switching
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=True,
                            requires_feedback=True,  # Library must send LED updates
                            supports_led=True,
                            supports_color=True,
                            color_mode="velocity",
                            color_palette=list(self.COLOR_PALETTE.keys()),
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        bank_id=bank_id,
                        display_name=f"B{bank_num} Pad {pad_num}",
                    ),
                )

            # 4 knobs per bank (continuous, read-only)
            for knob_num in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{knob_num}@{bank_id}",
                        control_type=ControlType.CONTINUOUS,
                        category="knob",
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Read-only (no motorized feedback)
                            requires_discovery=True,  # Initial position unknown
                        ),
                        bank_id=bank_id,
                        min_value=0,
                        max_value=127,
                        display_name=f"B{bank_num} Knob {knob_num}",
                    ),
                )

            # 2 buttons per bank (momentary with LED)
            for button_name in ["shift", "select"]:
                definitions.append(
                    ControlDefinition(
                        control_id=f"{button_name}@{bank_id}",
                        control_type=ControlType.MOMENTARY,
                        category="mode" if button_name == "shift" else "navigation",
                        capabilities=ControlCapabilities(
                            supports_feedback=True,
                            requires_feedback=True,  # Library must send LED updates
                            supports_led=True,
                            supports_color=False,  # Single-color LED (no RGB)
                            requires_discovery=False,
                        ),
                        bank_id=bank_id,
                        display_name=f"B{bank_num} {button_name.title()}",
                    ),
                )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        Each bank uses a different note/CC range for automatic bank detection.
        """
        mappings = []

        # =============================================================================
        # Bank 1 Mappings
        # =============================================================================

        # Pads 1-16: Notes 36-51
        for i in range(self.PAD_COUNT):
            note = self.BANK1_PAD_START_NOTE + i
            control_id = f"pad_{i+1}@bank_1"
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=self.MIDI_CHANNEL,
                        note=note,
                        control_id=control_id,
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=self.MIDI_CHANNEL,
                        note=note,
                        control_id=control_id,
                    ),
                ],
            )

        # Knobs 1-4: CC 16-19
        for i in range(self.KNOB_COUNT):
            cc = self.BANK1_KNOB_START_CC + i
            control_id = f"knob_{i+1}@bank_1"
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=self.MIDI_CHANNEL,
                    control=cc,
                    control_id=control_id,
                ),
            )

        # Buttons: Notes 64-65
        mappings.extend(
            [
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK1_BUTTON_SHIFT,
                    control_id="shift@bank_1",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK1_BUTTON_SHIFT,
                    control_id="shift@bank_1",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK1_BUTTON_SELECT,
                    control_id="select@bank_1",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK1_BUTTON_SELECT,
                    control_id="select@bank_1",
                ),
            ],
        )

        # =============================================================================
        # Bank 2 Mappings
        # =============================================================================

        # Pads 1-16: Notes 52-67
        for i in range(self.PAD_COUNT):
            note = self.BANK2_PAD_START_NOTE + i
            control_id = f"pad_{i+1}@bank_2"
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=self.MIDI_CHANNEL,
                        note=note,
                        control_id=control_id,
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=self.MIDI_CHANNEL,
                        note=note,
                        control_id=control_id,
                    ),
                ],
            )

        # Knobs 1-4: CC 20-23
        for i in range(self.KNOB_COUNT):
            cc = self.BANK2_KNOB_START_CC + i
            control_id = f"knob_{i+1}@bank_2"
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=self.MIDI_CHANNEL,
                    control=cc,
                    control_id=control_id,
                ),
            )

        # Buttons: Notes 66-67
        mappings.extend(
            [
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK2_BUTTON_SHIFT,
                    control_id="shift@bank_2",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK2_BUTTON_SHIFT,
                    control_id="shift@bank_2",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK2_BUTTON_SELECT,
                    control_id="select@bank_2",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=self.MIDI_CHANNEL,
                    note=self.BANK2_BUTTON_SELECT,
                    control_id="select@bank_2",
                ),
            ],
        )

        return mappings

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]] = None,
    ) -> dict[str, int]:
        """
        Initialize controller to known state.

        Clears all pad and button LEDs to off state.
        Knobs are read-only and don't need initialization.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages (unused)

        Returns:
            Empty dict (no discovered values - knobs unknown until moved)
        """
        logger.info("Initializing Example MIDI Controller")

        # Store callback for bank detection in translate_input()
        self._send_message = send_message

        # Clear all Bank 1 pads (velocity=0 = off)
        for i in range(self.PAD_COUNT):
            note = self.BANK1_PAD_START_NOTE + i
            msg = mido.Message("note_on", channel=self.MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Clear all Bank 2 pads
        for i in range(self.PAD_COUNT):
            note = self.BANK2_PAD_START_NOTE + i
            msg = mido.Message("note_on", channel=self.MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Clear all buttons (both banks)
        for note in [
            self.BANK1_BUTTON_SHIFT,
            self.BANK1_BUTTON_SELECT,
            self.BANK2_BUTTON_SHIFT,
            self.BANK2_BUTTON_SELECT,
        ]:
            msg = mido.Message("note_on", channel=self.MIDI_CHANNEL, note=note, velocity=0)
            send_message(msg)

        # Set initial active bank
        self._last_active_bank = "bank_1"

        logger.info("Example MIDI Controller initialization complete")
        return {}

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence - clear all LEDs.

        Same as init() - turns off all pad and button LEDs.

        Args:
            send_message: Function to send MIDI messages
        """
        logger.info("Shutting down Example MIDI Controller")

        # Same as init - clear all LEDs
        self.init(send_message)

        logger.info("Example MIDI Controller shutdown complete")

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with automatic bank detection.

        Detects bank from note/CC range:
        - Bank 1: Notes 36-65, CC 16-19
        - Bank 2: Notes 52-67, CC 20-23

        Args:
            msg: MIDI message to translate

        Returns:
            (control_id, value, signal_type) or None
        """
        # Detect bank from message
        new_bank = None

        if msg.type in ("note_on", "note_off"):
            note = msg.note
            # Bank 1 notes: 36-51 (pads), 64-65 (buttons)
            if (36 <= note <= 51) or (64 <= note <= 65):
                new_bank = "bank_1"
            # Bank 2 notes: 52-67 (pads), 66-67 (buttons)
            elif 52 <= note <= 67:
                new_bank = "bank_2"

        elif msg.type == "control_change":
            cc = msg.control
            # Bank 1 CCs: 16-19
            if 16 <= cc <= 19:
                new_bank = "bank_1"
            # Bank 2 CCs: 20-23
            elif 20 <= cc <= 23:
                new_bank = "bank_2"

        # Update active bank if changed
        if new_bank and new_bank != self._last_active_bank:
            logger.info(f"Bank switch: {self._last_active_bank} → {new_bank}")
            self._last_active_bank = new_bank

        # Use default mapping lookup (handles message routing automatically)
        return super().translate_input(msg)

    def translate_feedback(
        self,
        control_id: str,
        state_dict: dict,
    ) -> list[mido.Message]:
        """
        Translate control state to LED feedback.

        For Example MIDI Controller:
        - Pads: Velocity-based color palette (8 colors)
        - Buttons: Simple on/off (velocity 0 or 127)
        - Knobs: No feedback (read-only)

        Args:
            control_id: Control being updated (e.g., "pad_1@bank_1")
            state_dict: New state (is_on, value, color, etc.)

        Returns:
            List of MIDI messages for LED control
        """
        messages = []

        # Handle pad feedback (RGB via velocity palette)
        if "pad_" in control_id:
            # Extract pad number and bank
            parts = control_id.split("@")
            pad_str = parts[0].split("_")[1]
            pad_num = int(pad_str)
            bank = parts[1]  # "bank_1" or "bank_2"

            # Get MIDI note for this pad
            if bank == "bank_1":
                note = self.BANK1_PAD_START_NOTE + pad_num - 1
            else:
                note = self.BANK2_PAD_START_NOTE + pad_num - 1

            # Determine color based on state
            is_on = state_dict.get("is_on", False)
            color = state_dict.get("color", "off")

            # Map color string to velocity value
            velocity = self.COLOR_PALETTE.get(color, 0)

            # If pad is off, always use velocity 0
            if not is_on:
                velocity = 0

            msg = mido.Message("note_on", channel=self.MIDI_CHANNEL, note=note, velocity=velocity)
            messages.append(msg)

        # Handle button feedback (simple on/off)
        elif control_id.startswith(("shift@", "select@")):
            parts = control_id.split("@")
            button_name = parts[0]
            bank = parts[1]

            # Get MIDI note for this button
            if bank == "bank_1":
                note = self.BANK1_BUTTON_SHIFT if button_name == "shift" else self.BANK1_BUTTON_SELECT
            else:
                note = self.BANK2_BUTTON_SHIFT if button_name == "shift" else self.BANK2_BUTTON_SELECT

            is_on = state_dict.get("is_on", False)
            velocity = 127 if is_on else 0

            msg = mido.Message("note_on", channel=self.MIDI_CHANNEL, note=note, velocity=velocity)
            messages.append(msg)

        # Knobs have no feedback capability (read-only controls)
        return messages
