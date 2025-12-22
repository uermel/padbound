"""
AKAI APC mini MK2 MIDI Controller Plugin.

Hardware specifications:
- 8x8 grid of RGB backlit pads (64 pads)
- 9 faders (8 channel + 1 master)
- 17 UI buttons (8 track + 8 scene launch + 1 shift)
- RGB LED control via MIDI Note On messages
- USB MIDI interface

Control features:
- Pads send NOTE messages and support RGB feedback
- Faders send CC messages (read-only, no motorized feedback)
- Track/Scene buttons send NOTE messages with single-color LED feedback
- 3 modes: Session View, Drum Mode, Note Mode (hardware switchable)

References:
- Protocol documentation: protocols/akai_apc_mini/APC mini mk2 - Communication Protocol - v1.0.pdf
"""

from typing import Callable, Optional

import mido

from ..plugin import (
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)
from ..controls import (
    ControlDefinition,
    ControlType,
    ControlCapabilities,
    ControllerCapabilities,
)
from ..logging_config import get_logger

logger = get_logger(__name__)


class AkaiAPCminiMK2Plugin(ControllerPlugin):
    """
    AKAI APC mini MK2 plugin with RGB pad grid and faders.

    Features:
    - 8x8 RGB pad grid (64 pads total) with velocity-indexed color palette
    - 9 faders (continuous controls, read-only)
    - 8 track buttons with red LED feedback
    - 8 scene launch buttons with green LED feedback
    - 1 shift button (no LED)
    - RGB LED control with brightness/blink/pulse modes
    """

    # Hardware configuration
    PAD_ROWS = 8
    PAD_COLS = 8
    PAD_COUNT = 64
    FADER_COUNT = 9
    TRACK_BUTTON_COUNT = 8
    SCENE_BUTTON_COUNT = 8

    # MIDI note assignments
    # Pads: 8x8 grid from bottom-left (0x00) to top-right (0x3F)
    PAD_START_NOTE = 0x00  # Bottom-left pad

    # UI Buttons
    TRACK_BUTTON_START = 0x64  # Track buttons 1-8 (100-107)
    SCENE_BUTTON_START = 0x70  # Scene launch buttons 1-8 (112-119)
    SHIFT_BUTTON_NOTE = 0x7A   # Shift button (122)

    # Faders: CC numbers
    FADER_START_CC = 0x30  # Faders 1-9 (48-56)

    # RGB LED behavior - MIDI channel determines mode
    LED_BRIGHTNESS_10 = 0x90   # Channel 0
    LED_BRIGHTNESS_25 = 0x91   # Channel 1
    LED_BRIGHTNESS_50 = 0x92   # Channel 2
    LED_BRIGHTNESS_65 = 0x93   # Channel 3
    LED_BRIGHTNESS_75 = 0x94   # Channel 4
    LED_BRIGHTNESS_90 = 0x95   # Channel 5
    LED_BRIGHTNESS_100 = 0x96  # Channel 6 (default)
    LED_PULSE_1_16 = 0x97      # Channel 7
    LED_PULSE_1_8 = 0x98       # Channel 8
    LED_PULSE_1_4 = 0x99       # Channel 9
    LED_PULSE_1_2 = 0x9A       # Channel 10
    LED_BLINK_1_24 = 0x9B      # Channel 11
    LED_BLINK_1_16 = 0x9C      # Channel 12
    LED_BLINK_1_8 = 0x9D       # Channel 13
    LED_BLINK_1_4 = 0x9E       # Channel 14
    LED_BLINK_1_2 = 0x9F       # Channel 15

    # Single LED control (track/scene buttons)
    SINGLE_LED_CHANNEL = 0x90  # Always channel 0
    SINGLE_LED_OFF = 0x00
    SINGLE_LED_ON = 0x01
    SINGLE_LED_BLINK = 0x02

    # Velocity-to-color mapping (128 predefined colors)
    # This is a subset of the full palette from the protocol spec
    COLOR_PALETTE = {
        'off': 0,
        'black': 0,
        'dark_grey': 1,
        'grey': 2,
        'white': 3,
        'red_dim': 4,
        'red': 5,
        'red_dark': 6,
        'orange_dim': 8,
        'orange': 9,
        'orange_dark': 10,
        'yellow': 13,
        'lime': 16,
        'green': 21,
        'green_dark': 22,
        'cyan': 37,
        'blue': 45,
        'blue_dark': 46,
        'purple': 49,
        'magenta': 53,
        'pink': 56,
    }

    def __init__(self):
        """Initialize plugin."""
        super().__init__()
        # Track current pad colors for state management
        self._current_pad_colors: dict[str, int] = {}

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "AKAI APC mini MK2"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "APC mini mk2",
            "APC MINI MK2",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # No automatic bank feedback
            indexing_scheme="2d",          # 8x8 grid indexing
            grid_rows=self.PAD_ROWS,
            grid_cols=self.PAD_COLS,
            supports_persistent_configuration=False  # No SysEx programming
        )

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls.

        Creates:
        - 64 RGB pads (8x8 grid) as toggle controls
        - 9 faders as continuous controls
        - 8 track buttons as momentary controls with red LED
        - 8 scene launch buttons as momentary controls with green LED
        - 1 shift button as momentary control (no LED)
        """
        definitions = []

        # 8x8 RGB pad grid (indexed as pad_row_col)
        # Row 0 = bottom, Row 7 = top
        # Col 0 = left, Col 7 = right
        for row in range(self.PAD_ROWS):
            for col in range(self.PAD_COLS):
                pad_note = self.PAD_START_NOTE + (row * 8) + col
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{row}_{col}",
                        control_type=ControlType.TOGGLE,
                        capabilities=ControlCapabilities(
                            supports_feedback=True,
                            requires_feedback=True,  # Device needs LED updates from library
                            supports_led=True,
                            supports_color=True,
                            color_mode="indexed",
                            color_palette=list(self.COLOR_PALETTE.keys()),
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        display_name=f"Pad {row},{col}",
                    )
                )

        # 9 faders (continuous, read-only)
        for fader_num in range(1, self.FADER_COUNT + 1):
            display_name = f"Fader {fader_num}" if fader_num < 9 else "Master Fader"
            definitions.append(
                ControlDefinition(
                    control_id=f"fader_{fader_num}",
                    control_type=ControlType.CONTINUOUS,
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # Faders are read-only
                        requires_discovery=True,  # Initial position unknown
                    ),
                    min_value=0,
                    max_value=127,
                    display_name=display_name,
                )
            )

        # 8 track buttons (momentary with red LED)
        for btn_num in range(1, self.TRACK_BUTTON_COUNT + 1):
            definitions.append(
                ControlDefinition(
                    control_id=f"track_{btn_num}",
                    control_type=ControlType.MOMENTARY,
                    capabilities=ControlCapabilities(
                        supports_feedback=True,
                        requires_feedback=True,  # Device needs LED updates from library
                        supports_led=True,
                        supports_color=False,  # Single red LED only
                        requires_discovery=False,
                    ),
                    display_name=f"Track {btn_num}",
                )
            )

        # 8 scene launch buttons (momentary with green LED)
        for btn_num in range(1, self.SCENE_BUTTON_COUNT + 1):
            definitions.append(
                ControlDefinition(
                    control_id=f"scene_{btn_num}",
                    control_type=ControlType.MOMENTARY,
                    capabilities=ControlCapabilities(
                        supports_feedback=True,
                        requires_feedback=True,  # Device needs LED updates from library
                        supports_led=True,
                        supports_color=False,  # Single green LED only
                        requires_discovery=False,
                    ),
                    display_name=f"Scene {btn_num}",
                )
            )

        # Shift button (momentary, no LED)
        definitions.append(
            ControlDefinition(
                control_id="shift",
                control_type=ControlType.MOMENTARY,
                capabilities=ControlCapabilities(
                    supports_feedback=False,
                    requires_discovery=False,
                ),
                display_name="Shift",
            )
        )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        All controls use MIDI channel 0 by default.
        """
        mappings = []

        # Pad mappings - note on/off for 8x8 grid
        for row in range(self.PAD_ROWS):
            for col in range(self.PAD_COLS):
                control_id = f"pad_{row}_{col}"
                midi_note = self.PAD_START_NOTE + (row * 8) + col

                mappings.extend([
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=0,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=0,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                ])

        # Fader mappings - CC messages
        for fader_num in range(1, self.FADER_COUNT + 1):
            fader_cc = self.FADER_START_CC + fader_num - 1
            control_id = f"fader_{fader_num}"

            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=0,
                    control=fader_cc,
                    control_id=control_id,
                    signal_type="default",
                )
            )

        # Track button mappings - note on/off
        for btn_num in range(1, self.TRACK_BUTTON_COUNT + 1):
            midi_note = self.TRACK_BUTTON_START + btn_num - 1
            control_id = f"track_{btn_num}"

            mappings.extend([
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=midi_note,
                    control_id=control_id,
                    signal_type="note",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=0,
                    note=midi_note,
                    control_id=control_id,
                    signal_type="note",
                ),
            ])

        # Scene launch button mappings - note on/off
        for btn_num in range(1, self.SCENE_BUTTON_COUNT + 1):
            midi_note = self.SCENE_BUTTON_START + btn_num - 1
            control_id = f"scene_{btn_num}"

            mappings.extend([
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=midi_note,
                    control_id=control_id,
                    signal_type="note",
                ),
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_OFF,
                    channel=0,
                    note=midi_note,
                    control_id=control_id,
                    signal_type="note",
                ),
            ])

        # Shift button mapping
        mappings.extend([
            MIDIMapping(
                message_type=MIDIMessageType.NOTE_ON,
                channel=0,
                note=self.SHIFT_BUTTON_NOTE,
                control_id="shift",
                signal_type="note",
            ),
            MIDIMapping(
                message_type=MIDIMessageType.NOTE_OFF,
                channel=0,
                note=self.SHIFT_BUTTON_NOTE,
                control_id="shift",
                signal_type="note",
            ),
        ])

        return mappings

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]] = None
    ) -> None:
        """
        Initialize APC mini MK2 to known state.

        Clears all pad LEDs and button LEDs.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages (unused)
        """
        logger.info("Initializing AKAI APC mini MK2")

        # Clear all pad LEDs (set to off/black)
        for row in range(self.PAD_ROWS):
            for col in range(self.PAD_COLS):
                pad_note = self.PAD_START_NOTE + (row * 8) + col
                msg = mido.Message(
                    'note_on',
                    channel=6,  # 100% brightness channel
                    note=pad_note,
                    velocity=0  # Black/off
                )
                send_message(msg)

        # Clear all track button LEDs
        for btn_num in range(self.TRACK_BUTTON_COUNT):
            midi_note = self.TRACK_BUTTON_START + btn_num
            msg = mido.Message(
                'note_on',
                channel=0,
                note=midi_note,
                velocity=self.SINGLE_LED_OFF
            )
            send_message(msg)

        # Clear all scene launch button LEDs
        for btn_num in range(self.SCENE_BUTTON_COUNT):
            midi_note = self.SCENE_BUTTON_START + btn_num
            msg = mido.Message(
                'note_on',
                channel=0,
                note=midi_note,
                velocity=self.SINGLE_LED_OFF
            )
            send_message(msg)

        # Reset color tracking
        self._current_pad_colors = {}

        logger.info("APC mini MK2 initialization complete")

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence - clear all LEDs.
        """
        logger.info("Shutting down AKAI APC mini MK2")
        # Reuse init to clear all LEDs
        self.init(send_message, None)

    def translate_feedback(
        self,
        control_id: str,
        state_dict: dict,
    ) -> list[mido.Message]:
        """
        Translate control state to LED feedback.

        For APC mini MK2:
        - Pads: RGB LEDs via Note On with velocity-indexed colors
        - Track/Scene buttons: Single-color LEDs (on/off/blink)
        - Faders: No feedback (read-only)

        Args:
            control_id: Control being updated
            state_dict: New state (is_on, value, color, etc.)

        Returns:
            List of MIDI messages for LED control
        """
        messages = []

        # Handle pad feedback (RGB LEDs)
        if control_id.startswith("pad_"):
            try:
                # Extract row and col from control_id (e.g., "pad_3_5" -> row=3, col=5)
                parts = control_id.split("_")
                row = int(parts[1])
                col = int(parts[2])
                pad_note = self.PAD_START_NOTE + (row * 8) + col
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid pad control_id format: {control_id} ({e})")
                return []

            # Get color from state - controller already passes the correct color
            # (on_color when is_on=True, off_color when is_on=False)
            color = state_dict.get('color', 'off')

            # Map color name to velocity value
            velocity = self._get_color_velocity(color)

            # Store current color
            self._current_pad_colors[control_id] = velocity

            # Send RGB LED update (100% brightness)
            msg = mido.Message(
                'note_on',
                channel=6,  # 0x96 = 100% brightness
                note=pad_note,
                velocity=velocity
            )
            messages.append(msg)

        # Handle track button feedback (single red LED)
        elif control_id.startswith("track_"):
            try:
                btn_num = int(control_id.split("_")[1])
                midi_note = self.TRACK_BUTTON_START + btn_num - 1
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid track button control_id format: {control_id} ({e})")
                return []

            is_on = state_dict.get('is_on', False)
            velocity = self.SINGLE_LED_ON if is_on else self.SINGLE_LED_OFF

            msg = mido.Message(
                'note_on',
                channel=0,
                note=midi_note,
                velocity=velocity
            )
            messages.append(msg)

        # Handle scene button feedback (single green LED)
        elif control_id.startswith("scene_"):
            try:
                btn_num = int(control_id.split("_")[1])
                midi_note = self.SCENE_BUTTON_START + btn_num - 1
            except (IndexError, ValueError) as e:
                logger.error(f"Invalid scene button control_id format: {control_id} ({e})")
                return []

            is_on = state_dict.get('is_on', False)
            velocity = self.SINGLE_LED_ON if is_on else self.SINGLE_LED_OFF

            msg = mido.Message(
                'note_on',
                channel=0,
                note=midi_note,
                velocity=velocity
            )
            messages.append(msg)

        # Faders and shift button have no feedback capability
        return messages

    def _get_color_velocity(self, color: str) -> int:
        """
        Map color name to velocity value.

        Args:
            color: Color name (e.g., "red", "green", "blue")

        Returns:
            Velocity value (0-127) for the color
        """
        color = color.lower().strip()

        # Check predefined palette
        if color in self.COLOR_PALETTE:
            return self.COLOR_PALETTE[color]

        # Try parsing hex color format
        if color.startswith('#'):
            # For hex colors, we'll map to the closest palette color
            # This is a simplified approach - could be enhanced with color distance calculation
            logger.warning(f"Hex color '{color}' not directly supported, using default")
            return self.COLOR_PALETTE['white']

        # Default to off if color not recognized
        logger.warning(f"Unknown color '{color}', defaulting to off")
        return self.COLOR_PALETTE['off']