"""
Synido TempoPAD P16 MIDI Controller Plugin.

Hardware specifications:
- 16 velocity-sensing pads with RGB backlit LEDs (4x4 grid)
- 3 pad banks (A, B, C) switchable via PAD BANK button (48 total pads)
- 4 endless rotary encoders × 3 banks (12 total knobs)
- 6 transport control buttons (Back, Stop, Forward, Record, Play/Pause, Loop)
- USB MIDI interface with 3.5mm MIDI OUT

Control features:
- Pads configurable as TOGGLE or MOMENTARY (per-pad in user-defined mode)
- Pads can send NOTE (default), CC, or PC messages
- Knobs can send CC, Channel Aftertouch, or Pitch Bend messages
- RGB LED colors configurable per pad via SysEx (stored in device memory)
- Two working modes: Keyboard mode (red LED) and User-Defined mode (green LED)

IMPORTANT: LED Behavior:
- RGB colors are configured via SysEx and stored in device memory
- Hardware manages LED state based on pad mode and toggle state
- There is NO real-time LED feedback from software to device
- When a pad is pressed, the device shows the configured color
- This is similar to MPD218 but with configurable RGB colors

================================================================================
SYSEX PROTOCOL DOCUMENTATION
================================================================================

All SysEx messages use the following format:
    F0 <command> 00 00 00 20 6F [header bytes] [payload...] F7

Where:
    F0          = SysEx start
    <command>   = Command byte (01, 02, 04)
    00 00 00 20 6F = Fixed header prefix
    [header]    = Additional header bytes
    [payload]   = Command-specific data
    F7          = SysEx end

--------------------------------------------------------------------------------
COMMAND 0x01: WRITE CONFIGURATION
--------------------------------------------------------------------------------
Writes complete device configuration to non-volatile memory.

Format:
    F0 01 00 00 00 20 6F 00 01 01 04 <velocity_type> 7F
       <48 pads × 7 bytes> <12 knobs × 7 bytes> <6 buttons × 4 bytes>
    F7

Header bytes (after 00 00 00 20 6F):
    00          = Unknown (validated by device)
    01          = Unknown (validated by device)
    01          = Unknown (validated by device)
    04          = Number of knobs per bank
    <vel_type>  = Velocity curve (00=fixed/white, 01=soft/blue, 02=medium/green, 03=hard/red)
    7F          = Max velocity / sensitivity

--------------------------------------------------------------------------------
COMMAND 0x02: READ CONFIGURATION
--------------------------------------------------------------------------------
Reads complete device configuration from memory.

Request:
    F0 02 F7

Response:
    F0 02 00 00 00 20 6F [header + full config] F7

Returns same format as command 0x01 but as a response.

--------------------------------------------------------------------------------
COMMAND 0x04: READ GLOBAL STATE
--------------------------------------------------------------------------------
Reads global state (smaller response).

Request:
    F0 04 00 00 00 20 6F F7

Response:
    F0 04 00 00 00 20 6F [24 bytes global state] F7

================================================================================
DATA STRUCTURES
================================================================================

Pad Configuration (7 bytes per pad, 48 pads total):
    Byte 0      = Pad mode (00=Note, 01=CC, 02=PC)
    Byte 1      = MIDI note/CC/PC number (0-127)
    Byte 2      = MIDI channel (1-16)
    Byte 3      = Toggle mode (00=Momentary, 01=Toggle)
    Bytes 4-6   = RGB color (R, G, B each 0-127)

Pad Banks (MIDI note ranges):
    Bank A: Notes 36-51 (0x24-0x33)
    Bank B: Notes 60-75 (0x3C-0x4B)
    Bank C: Notes 84-99 (0x54-0x63)

Knob Configuration (7 bytes per knob, 12 knobs total):
    Byte 0      = Knob mode (00=CC, 01=Channel Aftertouch, 02=Pitch Bend)
    Byte 1      = CC number (0-127)
    Byte 2      = MIDI channel (1-16)
    Byte 3      = Minimum value (0-127)
    Byte 4      = Maximum value (0-127)
    Bytes 5-6   = Reserved (00 7F)

Default Knob CC Assignments:
    Bank A: CC 7, 1, 2, 10 (Knobs 1-4)
    Bank B: CC 14, 15, 12, 13
    Bank C: CC 53, 54, 51, 52

Transport Button Configuration (4 bytes per button, 6 buttons total):
    Byte 0      = Button mode (00=Note)
    Byte 1      = MIDI note number
    Byte 2      = MIDI channel (1)
    Byte 3      = Toggle mode (00=Momentary, 01=Toggle)

Transport Buttons (all on channel 1):
    Back:       Note 21 (0x15), Momentary
    Stop:       Note 22 (0x16), Momentary
    Forward:    Note 23 (0x17), Momentary
    Record:     Note 24 (0x18), Toggle
    Play/Pause: Note 25 (0x19), Toggle
    Loop:       Note 26 (0x1A), Toggle

================================================================================
References:
- Protocol reverse-engineered from Synido Pad16 Editor software captures
- User Guide: Synido TempoPAD P16 User Manual V1.0
================================================================================
"""

import time
from enum import IntEnum
from typing import TYPE_CHECKING, Callable, Optional

import mido
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from padbound.config import ControllerConfig

from padbound.controls import (
    BankDefinition,
    ControlCapabilities,
    ControlDefinition,
    ControllerCapabilities,
    ControlState,
    ControlType,
    ControlTypeModes,
)
from padbound.debug.layout import ControlPlacement, ControlWidget, DebugLayout, LayoutSection
from padbound.logging_config import get_logger
from padbound.plugin import (
    BatchFeedbackResult,
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)
from padbound.utils import RGBColor

logger = get_logger(__name__)


# =============================================================================
# Enums for TempoPAD configuration
# =============================================================================


class PadMode(IntEnum):
    """Pad message type."""

    NOTE = 0
    CC = 1
    PC = 2


class KnobMode(IntEnum):
    """Knob message type."""

    CC = 0
    CHANNEL_AFTERTOUCH = 1
    PITCH_BEND = 2


class VelocityCurve(IntEnum):
    """Velocity curve type (indicated by VELOCITY TYPE button color)."""

    FIXED_WHITE = 0  # Fixed velocity (127)
    SOFT_BLUE = 1  # Soft curve - higher velocity with light taps
    MEDIUM_GREEN = 2  # Linear velocity curve
    HARD_RED = 3  # Hard curve - requires harder taps for high velocity


# =============================================================================
# SysEx Protocol Constants
# =============================================================================


class TempoPADSysEx:
    """SysEx protocol constants for TempoPAD."""

    # Command bytes
    CMD_WRITE = 0x01  # Write configuration to device
    CMD_READ = 0x02  # Read configuration from device
    CMD_READ_GLOBAL = 0x04  # Read global state

    # Fixed header prefix (appears after command byte)
    HEADER_PREFIX = [0x00, 0x00, 0x00, 0x20, 0x6F]

    # Default header suffix (after prefix, before payload)
    # Format: [unknown, unknown, unknown, unknown, unknown, max_velocity]
    # Note: Must use WRITE format [0x00, 0x00, 0x00, 0x00, 0x00, 0x7F], not READ format
    DEFAULT_HEADER_SUFFIX = [0x00, 0x00, 0x00, 0x00, 0x00, 0x7F]


# =============================================================================
# Pydantic Models for SysEx Configuration
# =============================================================================


class TempoPADRGBColor(RGBColor):
    """RGB color for TempoPAD with MIDI-range values (0-127)."""

    def to_sysex_bytes(self) -> list[int]:
        """Convert to 3 bytes for SysEx (MIDI range 0-127)."""
        return list(self.to_midi_range())


class TempoPADPadConfig(BaseModel):
    """Configuration for a single TempoPAD pad (7 bytes in SysEx)."""

    mode: PadMode = Field(default=PadMode.NOTE, description="Pad message mode")
    number: int = Field(default=36, ge=0, le=127, description="MIDI note/CC/PC number")
    channel: int = Field(default=1, ge=1, le=16, description="MIDI channel (1-indexed)")
    toggle: bool = Field(default=False, description="True=Toggle, False=Momentary")
    color: TempoPADRGBColor = Field(
        default_factory=lambda: TempoPADRGBColor(r=90, g=0, b=0),
        description="RGB LED color",
    )

    def to_bytes(self) -> bytes:
        """Convert to 7-byte SysEx format."""
        rgb = self.color.to_sysex_bytes()
        return bytes(
            [
                self.mode,
                self.number,
                self.channel,
                0x01 if self.toggle else 0x00,
                rgb[0],
                rgb[1],
                rgb[2],
            ],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "TempoPADPadConfig":
        """Parse from 7-byte SysEx format."""
        if len(data) < 7:
            raise ValueError(f"Pad config requires 7 bytes, got {len(data)}")
        return cls(
            mode=PadMode(data[0]),
            number=data[1],
            channel=data[2],
            toggle=data[3] == 0x01,
            color=TempoPADRGBColor.from_midi_values(data[4], data[5], data[6]),
        )


class TempoPADKnobConfig(BaseModel):
    """Configuration for a single TempoPAD knob (7 bytes in SysEx)."""

    mode: KnobMode = Field(default=KnobMode.CC, description="Knob message mode")
    cc_number: int = Field(default=7, ge=0, le=127, description="CC number")
    channel: int = Field(default=1, ge=1, le=16, description="MIDI channel (1-indexed)")
    min_value: int = Field(default=0, ge=0, le=127, description="Minimum value")
    max_value: int = Field(default=127, ge=0, le=127, description="Maximum value")

    def to_bytes(self) -> bytes:
        """Convert to 7-byte SysEx format."""
        return bytes(
            [
                self.mode,
                self.cc_number,
                self.channel,
                self.min_value,
                self.max_value,
                0x00,  # Reserved
                0x7F,  # Reserved
            ],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "TempoPADKnobConfig":
        """Parse from 7-byte SysEx format."""
        if len(data) < 7:
            raise ValueError(f"Knob config requires 7 bytes, got {len(data)}")
        return cls(
            mode=KnobMode(data[0]),
            cc_number=data[1],
            channel=data[2],
            min_value=data[3],
            max_value=data[4],
        )


class TempoPADButtonConfig(BaseModel):
    """Configuration for a transport button (4 bytes in SysEx)."""

    mode: int = Field(default=0, ge=0, le=127, description="Button mode (always 0=Note)")
    number: int = Field(default=21, ge=0, le=127, description="MIDI note number")
    channel: int = Field(default=1, ge=1, le=16, description="MIDI channel (1-indexed)")
    toggle: bool = Field(default=False, description="True=Toggle, False=Momentary")

    def to_bytes(self) -> bytes:
        """Convert to 4-byte SysEx format."""
        return bytes(
            [
                self.mode,
                self.number,
                self.channel,
                0x01 if self.toggle else 0x00,
            ],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "TempoPADButtonConfig":
        """Parse from 4-byte SysEx format."""
        if len(data) < 4:
            raise ValueError(f"Button config requires 4 bytes, got {len(data)}")
        return cls(
            mode=data[0],
            number=data[1],
            channel=data[2],
            toggle=data[3] == 0x01,
        )


class TempoPADFullConfig(BaseModel):
    """Complete TempoPAD device configuration."""

    velocity_curve: VelocityCurve = Field(
        default=VelocityCurve.MEDIUM_GREEN,
        description="Velocity curve type",
    )
    pads: list[TempoPADPadConfig] = Field(
        default_factory=lambda: [TempoPADPadConfig() for _ in range(48)],
        min_length=48,
        max_length=48,
        description="48 pad configs (3 banks × 16 pads)",
    )
    knobs: list[TempoPADKnobConfig] = Field(
        default_factory=lambda: [TempoPADKnobConfig() for _ in range(12)],
        min_length=12,
        max_length=12,
        description="12 knob configs (3 banks × 4 knobs)",
    )
    buttons: list[TempoPADButtonConfig] = Field(
        default_factory=lambda: [TempoPADButtonConfig() for _ in range(6)],
        min_length=6,
        max_length=6,
        description="6 transport button configs",
    )

    def to_sysex_message(self) -> mido.Message:
        """Build complete configuration SysEx message.

        Format: F0 01 [header] [48 pads] [12 knobs] [6 buttons] F7
        """
        data = [TempoPADSysEx.CMD_WRITE]
        data.extend(TempoPADSysEx.HEADER_PREFIX)

        # Header suffix with velocity curve
        header_suffix = list(TempoPADSysEx.DEFAULT_HEADER_SUFFIX)
        header_suffix[4] = self.velocity_curve  # Update velocity type
        data.extend(header_suffix)

        # Pad configurations (48 × 7 = 336 bytes)
        for pad in self.pads:
            data.extend(pad.to_bytes())

        # Knob configurations (12 × 7 = 84 bytes)
        for knob in self.knobs:
            data.extend(knob.to_bytes())

        # Button configurations (6 × 4 = 24 bytes)
        for button in self.buttons:
            data.extend(button.to_bytes())

        return mido.Message("sysex", data=data)

    @classmethod
    def from_sysex_data(cls, data: tuple | list) -> Optional["TempoPADFullConfig"]:
        """Parse configuration from SysEx response.

        Expected format: 02 00 00 00 20 6F [header] [pads] [knobs] [buttons]
        """
        data = list(data)

        # Validate minimum length
        # Header: 1 (cmd) + 5 (prefix) + 6 (suffix) = 12 bytes
        # Pads: 48 × 7 = 336 bytes
        # Knobs: 12 × 7 = 84 bytes
        # Buttons: 6 × 4 = 24 bytes
        # Total: 12 + 336 + 84 + 24 = 456 bytes
        if len(data) < 456:
            logger.warning(f"Config data too short: {len(data)} bytes (expected ~456)")
            return None

        # Validate header
        if data[0] != TempoPADSysEx.CMD_READ:
            logger.warning(f"Unexpected command byte: {data[0]:02X}")
            return None

        # Parse header
        offset = 12  # Skip command + header prefix + suffix
        velocity_curve = VelocityCurve(data[10])

        # Parse pads (48 × 7 bytes starting at offset 12)
        pads = []
        for i in range(48):
            pad_data = data[offset + i * 7 : offset + i * 7 + 7]
            pads.append(TempoPADPadConfig.from_bytes(bytes(pad_data)))

        # Parse knobs (12 × 7 bytes)
        knob_offset = offset + 48 * 7
        knobs = []
        for i in range(12):
            knob_data = data[knob_offset + i * 7 : knob_offset + i * 7 + 7]
            knobs.append(TempoPADKnobConfig.from_bytes(bytes(knob_data)))

        # Parse buttons (6 × 4 bytes)
        button_offset = knob_offset + 12 * 7
        buttons = []
        for i in range(6):
            button_data = data[button_offset + i * 4 : button_offset + i * 4 + 4]
            buttons.append(TempoPADButtonConfig.from_bytes(bytes(button_data)))

        return cls(
            velocity_curve=velocity_curve,
            pads=pads,
            knobs=knobs,
            buttons=buttons,
        )


# =============================================================================
# Plugin Implementation
# =============================================================================


class SynidoTempoPADPlugin(ControllerPlugin):
    """
    Synido TempoPAD P16 plugin with multi-bank pad and knob support.

    Features:
    - 16 velocity-sensitive pads × 3 banks (48 total) with configurable RGB colors
    - 4 endless rotary knobs × 3 banks (12 total)
    - 6 transport buttons (Back, Stop, Forward, Record, Play/Pause, Loop)
    - RGB LED colors stored in device memory via SysEx
    - NO real-time LED feedback (hardware manages LED state)
    - Pads configurable as TOGGLE or MOMENTARY

    This controller is unique because:
    - It has RGB LEDs that can be configured via SysEx (like LPD8 MK2)
    - But there's no real-time feedback capability (like MPD218)
    - Colors are "baked in" at configuration time, then hardware manages them
    """

    # Hardware configuration
    PAD_COUNT = 16
    PAD_BANKS = 3
    PAD_TOTAL = PAD_COUNT * PAD_BANKS  # 48

    KNOB_COUNT = 4
    KNOB_BANKS = 3
    KNOB_TOTAL = KNOB_COUNT * KNOB_BANKS  # 12

    BUTTON_COUNT = 6

    # Bank identifiers
    BANK_IDS = ["bank_a", "bank_b", "bank_c"]

    # Pad note ranges per bank (factory defaults)
    BANK_NOTE_RANGES: dict[str, tuple[int, int]] = {
        "bank_a": (36, 51),  # Notes 0x24-0x33
        "bank_b": (60, 75),  # Notes 0x3C-0x4B
        "bank_c": (84, 99),  # Notes 0x54-0x63
    }

    # Default knob CC assignments per bank
    DEFAULT_KNOB_CCS: dict[str, list[int]] = {
        "bank_a": [7, 1, 2, 10],
        "bank_b": [14, 15, 12, 13],
        "bank_c": [53, 54, 51, 52],
    }

    # Transport button definitions (note, name, default_toggle)
    TRANSPORT_BUTTONS = [
        (21, "back", False),
        (22, "stop", False),
        (23, "forward", False),
        (24, "record", True),
        (25, "play", True),
        (26, "loop", True),
    ]

    # Default MIDI channel (1-indexed)
    DEFAULT_CHANNEL = 1

    def __init__(self):
        """Initialize plugin with bank tracking."""
        super().__init__()
        self._last_active_bank: str = "bank_a"
        self._current_config: Optional[TempoPADFullConfig] = None
        # Store callbacks for runtime queries
        self._send_message: Optional[Callable[[mido.Message], None]] = None
        self._receive_message: Optional[Callable[[float], Optional[mido.Message]]] = None

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "Synido TempoPAD P16"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "Synido Pad16",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # No automatic bank LED feedback
            indexing_scheme="1d",  # Linear pad/knob numbering per bank
            supports_persistent_configuration=True,  # SysEx programming supported
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 3 pad/knob banks.

        Banks are detected by note range since pads send different notes per bank.
        """
        return [
            BankDefinition(
                bank_id="bank_a",
                control_type=ControlType.TOGGLE,
                display_name="Bank A",
            ),
            BankDefinition(
                bank_id="bank_b",
                control_type=ControlType.TOGGLE,
                display_name="Bank B",
            ),
            BankDefinition(
                bank_id="bank_c",
                control_type=ControlType.TOGGLE,
                display_name="Bank C",
            ),
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across 3 banks plus transport buttons.

        Creates:
        - 3 banks × 16 pads = 48 pads
        - 3 banks × 4 knobs = 12 knobs
        - 6 transport buttons (not banked)
        """
        definitions = []

        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            start_note, _ = self.BANK_NOTE_RANGES[bank_id]

            # 16 pads per bank
            for pad_num in range(1, self.PAD_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{pad_num}@{bank_id}",
                        control_type=ControlType.TOGGLE,  # Default, can be MOMENTARY
                        category="pad",
                        type_modes=ControlTypeModes(
                            supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                            default_type=ControlType.TOGGLE,
                            requires_hardware_sync=True,  # Mode stored in device
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # No real-time LED control
                            requires_feedback=False,
                            supports_led=False,  # Can't control at runtime
                            supports_color=True,  # Can configure via SysEx
                            color_mode="rgb",
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        bank_id=bank_id,
                        display_name=f"B{chr(65 + bank_idx)} Pad {pad_num}",
                        signal_types=["note", "cc", "pc"],
                    ),
                )

            # 4 knobs per bank
            for knob_num in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{knob_num}@{bank_id}",
                        control_type=ControlType.CONTINUOUS,
                        category="knob",
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Not motorized
                            requires_feedback=False,
                            requires_discovery=True,  # Initial position unknown
                        ),
                        bank_id=bank_id,
                        min_value=0,
                        max_value=127,
                        display_name=f"B{chr(65 + bank_idx)} Knob {knob_num}",
                    ),
                )

        # Transport buttons (not banked)
        for _note, button_name, is_toggle in self.TRANSPORT_BUTTONS:
            control_type = ControlType.TOGGLE if is_toggle else ControlType.MOMENTARY
            definitions.append(
                ControlDefinition(
                    control_id=f"button_{button_name}",
                    control_type=control_type,
                    category="button",
                    type_modes=ControlTypeModes(
                        supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                        default_type=control_type,
                        requires_hardware_sync=True,
                    ),
                    capabilities=ControlCapabilities(
                        supports_feedback=False,
                        requires_feedback=False,
                        requires_discovery=False,
                    ),
                    display_name=button_name.title(),
                ),
            )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        All controls use the same MIDI channel (default 1).
        Banks are distinguished by note range for pads.
        """
        mappings = []

        for bank_id in self.BANK_IDS:
            start_note, end_note = self.BANK_NOTE_RANGES[bank_id]
            knob_ccs = self.DEFAULT_KNOB_CCS[bank_id]

            # Pad mappings - Note On/Off
            for pad_num in range(1, self.PAD_COUNT + 1):
                midi_note = start_note + pad_num - 1
                control_id = f"pad_{pad_num}@{bank_id}"

                mappings.extend(
                    [
                        MIDIMapping(
                            message_type=MIDIMessageType.NOTE_ON,
                            channel=self.DEFAULT_CHANNEL - 1,  # 0-indexed
                            note=midi_note,
                            control_id=control_id,
                            signal_type="note",
                        ),
                        MIDIMapping(
                            message_type=MIDIMessageType.NOTE_OFF,
                            channel=self.DEFAULT_CHANNEL - 1,
                            note=midi_note,
                            control_id=control_id,
                            signal_type="note",
                        ),
                    ],
                )

            # Knob mappings - CC
            for knob_num in range(1, self.KNOB_COUNT + 1):
                midi_cc = knob_ccs[knob_num - 1]
                control_id = f"knob_{knob_num}@{bank_id}"

                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.CONTROL_CHANGE,
                        channel=self.DEFAULT_CHANNEL - 1,
                        control=midi_cc,
                        control_id=control_id,
                        signal_type="default",
                    ),
                )

        # Transport button mappings
        for note, button_name, _ in self.TRANSPORT_BUTTONS:
            control_id = f"button_{button_name}"
            mappings.extend(
                [
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=self.DEFAULT_CHANNEL - 1,
                        note=note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=self.DEFAULT_CHANNEL - 1,
                        note=note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                ],
            )

        return mappings

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with bank detection from note range.

        Since all banks share the same MIDI channel, we detect the active
        bank from the note number for pad messages.

        Returns:
            (control_id, value, signal_type) or None
        """
        # Handle note messages (pads and transport buttons)
        if msg.type in ("note_on", "note_off"):
            note = msg.note

            # Check if it's a transport button
            for btn_note, btn_name, _ in self.TRANSPORT_BUTTONS:
                if note == btn_note:
                    control_id = f"button_{btn_name}"
                    value = msg.velocity
                    return (control_id, value, "note")

            # Check which pad bank this note belongs to
            for bank_id, (start_note, end_note) in self.BANK_NOTE_RANGES.items():
                if start_note <= note <= end_note:
                    # Update active bank tracking
                    if bank_id != self._last_active_bank:
                        logger.debug(f"TempoPAD bank switch: {self._last_active_bank} -> {bank_id}")
                        self._last_active_bank = bank_id

                    pad_num = note - start_note + 1
                    control_id = f"pad_{pad_num}@{bank_id}"
                    value = msg.velocity
                    return (control_id, value, "note")

        # Handle CC messages (knobs)
        elif msg.type == "control_change":
            cc = msg.control

            # Find which bank and knob this CC belongs to
            for bank_id in self.BANK_IDS:
                knob_ccs = self.DEFAULT_KNOB_CCS[bank_id]
                if cc in knob_ccs:
                    knob_num = knob_ccs.index(cc) + 1
                    control_id = f"knob_{knob_num}@{bank_id}"
                    return (control_id, msg.value, "default")

        return None

    def compute_control_state(
        self,
        control_id: str,
        value: int,
        signal_type: str,
        current_state: ControlState,
        control_definition: ControlDefinition,
    ) -> tuple[Optional[ControlState], bool]:
        """
        Handle state for pads when hardware manages toggle mode.

        When hardware is in TOGGLE mode:
        - Hardware tracks toggle state and manages LED
        - Software just reports press/release events
        - is_on=True on note_on (pressed), is_on=False on note_off (released)

        Args:
            control_id: Control identifier
            value: MIDI value (velocity for notes)
            signal_type: Signal type ("note", "cc", etc.)
            current_state: Current control state
            control_definition: Control definition with type info

        Returns:
            (state, trigger_callback) tuple
        """
        is_pad = control_id.startswith("pad_")
        is_button = control_id.startswith("button_")
        is_toggle = control_definition.control_type == ControlType.TOGGLE
        is_note = signal_type == "note"

        if (is_pad or is_button) and is_toggle and is_note:
            # Hardware manages toggle state - just report press/release
            is_pressed = value > 0
            return (
                ControlState(
                    control_id=control_id,
                    timestamp=current_state.timestamp,
                    is_discovered=True,
                    is_on=is_pressed,
                    value=value,
                ),
                True,  # Always fire callback
            )

        # Default behavior for MOMENTARY pads and knobs
        return (None, True)

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]],
    ) -> Optional[dict[str, int]]:
        """
        Initialize TempoPAD to known state.

        Queries the device for current configuration to understand
        the pad/knob setup.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            None - no values to discover
        """
        logger.info("Initializing Synido TempoPAD P16")

        # Store callbacks for runtime use
        self._send_message = send_message
        self._receive_message = receive_message

        # Query current configuration
        config = self._query_config(send_message, receive_message)
        if config:
            self._current_config = config
            logger.info(
                f"TempoPAD config loaded: velocity_curve={config.velocity_curve.name}, "
                f"{len(config.pads)} pads, {len(config.knobs)} knobs",
            )
        else:
            logger.warning("Could not query TempoPAD config, using defaults")
            self._current_config = None

        # Default to bank A
        self._last_active_bank = "bank_a"

        logger.info("TempoPAD initialization complete")
        return None

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence for TempoPAD.

        The TempoPAD doesn't need special cleanup since LEDs are hardware-managed.
        """
        logger.info("Shutting down Synido TempoPAD P16")
        # No cleanup needed - LEDs are hardware-managed
        logger.info("TempoPAD shutdown complete")

    def translate_feedback(
        self,
        control_id: str,
        state: ControlState,
        definition: ControlDefinition,
    ) -> list[mido.Message]:
        """
        Translate control state to MIDI feedback.

        For TempoPAD, this always returns an empty list since:
        - Pad LEDs are hardware-managed (no real-time software control)
        - Knobs are not motorized (no feedback capability)
        - LED colors are configured via SysEx at init time only

        Args:
            control_id: Control being updated
            state: Current control state
            definition: Control definition

        Returns:
            Empty list (no feedback support)
        """
        # TempoPAD has no real-time LED feedback from software
        return []

    def translate_feedback_batch(
        self,
        updates: list[tuple[str, ControlState, ControlDefinition]],
    ) -> BatchFeedbackResult:
        """
        Translate multiple control states to MIDI feedback.

        For TempoPAD, this always returns an empty result since there
        is no real-time LED feedback capability.

        Args:
            updates: List of (control_id, state, definition) tuples

        Returns:
            Empty BatchFeedbackResult
        """
        # TempoPAD has no real-time LED feedback from software
        return BatchFeedbackResult(messages=[])

    def configure_programs(
        self,
        send_message: Callable[[mido.Message], None],
        config: "ControllerConfig",
    ) -> None:
        """
        Program TempoPAD with persistent configuration.

        Writes user configuration (RGB colors, toggle modes) to device
        non-volatile memory via SysEx. These settings persist across
        power cycles.

        Args:
            send_message: Function to send MIDI messages
            config: Full controller configuration with resolved settings
        """
        if not config or not config.banks:
            logger.debug("No configuration provided, skipping programming")
            return

        logger.info("Programming TempoPAD device memory with configuration")

        # Build device configuration from user config
        device_config = self._build_config_from_user_config(config)

        # Send configuration to device
        sysex_msg = device_config.to_sysex_message()
        logger.debug(f"Sending config SysEx ({len(sysex_msg.data)} bytes)")
        send_message(sysex_msg)

        # Allow device to process
        time.sleep(0.2)

        logger.info("TempoPAD program configuration complete")

    def _query_config(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]],
    ) -> Optional[TempoPADFullConfig]:
        """
        Query current configuration from device.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            TempoPADFullConfig if successful, None otherwise
        """
        # Build query: F0 02 F7
        query = mido.Message("sysex", data=[TempoPADSysEx.CMD_READ])

        logger.debug("Querying TempoPAD configuration...")
        send_message(query)

        # Wait for response
        response = receive_message(1.0)  # 1 second timeout

        if response and response.type == "sysex":
            config = TempoPADFullConfig.from_sysex_data(response.data)
            if config:
                logger.debug(f"Received config with {len(config.pads)} pads")
                return config
            else:
                logger.warning("Failed to parse config response")
        else:
            logger.warning("No config response received from device")

        return None

    def _build_config_from_user_config(
        self,
        config: "ControllerConfig",
    ) -> TempoPADFullConfig:
        """
        Build a TempoPADFullConfig from user configuration.

        Maps padbound config to TempoPAD device format:
        - Control types (TOGGLE/MOMENTARY) -> pad toggle mode
        - Colors -> pad RGB values
        - Bank configurations -> appropriate pad/knob slots

        Args:
            config: User configuration

        Returns:
            TempoPADFullConfig ready to upload
        """
        # Start with defaults
        device_config = TempoPADFullConfig()

        # Configure pads for each bank
        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            start_note, _ = self.BANK_NOTE_RANGES[bank_id]
            bank_config = config.banks.get(bank_id) if config.banks else None

            for pad_num in range(1, self.PAD_COUNT + 1):
                pad_idx = bank_idx * self.PAD_COUNT + pad_num - 1
                midi_note = start_note + pad_num - 1

                # Get pad-specific config if available
                pad_id = f"pad_{pad_num}"
                control_config = None
                if bank_config and bank_config.controls:
                    control_config = bank_config.controls.get(pad_id)

                # Determine toggle mode
                toggle = True  # Default to toggle
                if control_config and control_config.type == ControlType.MOMENTARY:
                    toggle = False
                elif bank_config and bank_config.toggle_mode is not None:
                    toggle = bank_config.toggle_mode

                # Determine color
                color = TempoPADRGBColor(r=90, g=0, b=0)  # Default red
                if control_config and control_config.on_color:
                    color = TempoPADRGBColor.from_string(control_config.on_color)

                # Update pad config
                device_config.pads[pad_idx] = TempoPADPadConfig(
                    mode=PadMode.NOTE,
                    number=midi_note,
                    channel=self.DEFAULT_CHANNEL,
                    toggle=toggle,
                    color=color,
                )

        # Configure knobs for each bank
        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            knob_ccs = self.DEFAULT_KNOB_CCS[bank_id]

            for knob_num in range(1, self.KNOB_COUNT + 1):
                knob_idx = bank_idx * self.KNOB_COUNT + knob_num - 1
                midi_cc = knob_ccs[knob_num - 1]

                device_config.knobs[knob_idx] = TempoPADKnobConfig(
                    mode=KnobMode.CC,
                    cc_number=midi_cc,
                    channel=self.DEFAULT_CHANNEL,
                    min_value=0,
                    max_value=127,
                )

        # Configure transport buttons
        for btn_idx, (note, _, is_toggle) in enumerate(self.TRANSPORT_BUTTONS):
            device_config.buttons[btn_idx] = TempoPADButtonConfig(
                mode=0,
                number=note,
                channel=self.DEFAULT_CHANNEL,
                toggle=is_toggle,
            )

        return device_config

    def get_debug_layout(self) -> DebugLayout:
        """Return TUI debug layout for Synido TempoPAD P16."""
        controls = []
        bank_id = self._last_active_bank or "bank_a"

        # 4 knobs (row 0, cols 0-3)
        for i in range(1, 5):
            controls.append(
                ControlPlacement(
                    control_id=f"knob_{i}@{bank_id}",
                    widget_type=ControlWidget.KNOB,
                    row=0,
                    col=i - 1,
                    label=f"K{i}",
                ),
            )

        # Transport buttons (row 0, cols 4-5)
        controls.append(
            ControlPlacement(
                control_id="button_record",
                widget_type=ControlWidget.BUTTON,
                row=0,
                col=4,
                label="Rec",
            ),
        )
        controls.append(
            ControlPlacement(
                control_id="button_play",
                widget_type=ControlWidget.BUTTON,
                row=0,
                col=5,
                label="Play",
            ),
        )

        # 4×4 pad grid (rows 1-4)
        for pad_num in range(1, 17):
            row = 1 + (pad_num - 1) // 4
            col = (pad_num - 1) % 4
            controls.append(
                ControlPlacement(
                    control_id=f"pad_{pad_num}@{bank_id}",
                    widget_type=ControlWidget.PAD,
                    row=row,
                    col=col,
                ),
            )

        # More transport buttons (row 5)
        controls.append(
            ControlPlacement(
                control_id="button_back",
                widget_type=ControlWidget.BUTTON,
                row=5,
                col=0,
                label="Back",
            ),
        )
        controls.append(
            ControlPlacement(
                control_id="button_stop",
                widget_type=ControlWidget.BUTTON,
                row=5,
                col=1,
                label="Stop",
            ),
        )
        controls.append(
            ControlPlacement(
                control_id="button_forward",
                widget_type=ControlWidget.BUTTON,
                row=5,
                col=2,
                label="Fwd",
            ),
        )
        controls.append(
            ControlPlacement(
                control_id="button_loop",
                widget_type=ControlWidget.BUTTON,
                row=5,
                col=3,
                label="Loop",
            ),
        )

        return DebugLayout(
            plugin_name=self.name,
            description=f"Synido TempoPAD P16 - {bank_id}",
            sections=[
                LayoutSection(
                    name=f"TempoPAD [{bank_id}]",
                    controls=controls,
                    rows=6,
                    cols=6,
                ),
            ],
        )
