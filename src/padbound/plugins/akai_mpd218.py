"""
AKAI MPD218 MIDI Controller Plugin.
Firmware 1.12.0

Hardware specifications:
- 16 velocity- and pressure-sensitive pads with red backlit LEDs
- 3 pad banks (A, B, C) accessible via Pad Bank button (48 total pads)
- 6 360-degree endless rotary potentiometers (knobs)
- 3 control banks (A, B, C) accessible via Control Bank button (18 total knobs)
- 6 function buttons (Ctrl Bank, Prog, Pad Bank, Full Level, NR Config, Note Repeat)
- 16 presets stored in device non-volatile memory
- USB MIDI interface (USB bus powered)

Control features:
- Pads configurable as MOMENTARY (default) or TOGGLE (per-pad in preset)
- Pads can send NOTE (default), PROG, or BANK messages
- Pads support velocity and pressure (channel/poly aftertouch)
- Knobs send CC messages (read-only, not motorized)
- Red backlit LEDs are hardware-managed (no software control)

================================================================================
SYSEX PROTOCOL DOCUMENTATION
================================================================================

All SysEx messages use the following header format:
    F0 47 00 34 <cmd> [payload...] F7

Where:
    F0          = SysEx start
    47          = Akai manufacturer ID
    00          = Device ID (specific device, not 0x7F broadcast)
    34          = MPD218 product ID
    <cmd>       = Command byte
    [payload]   = Command-specific data
    F7          = SysEx end

--------------------------------------------------------------------------------
COMMAND 0x10: PRESET DUMP/LOAD
--------------------------------------------------------------------------------
Used to upload a complete preset configuration to device memory.
The preset will be stored in the slot specified by the preset number in the data.

Request (Upload):
    F0 47 00 34 10 04 1d <preset_data 541 bytes> F7

    10          = Preset Dump/Load command
    04 1d       = Length (541 bytes, 7-bit stuffed: 0x04<<7 | 0x1d = 541)

Response: None (preset is stored immediately)

--------------------------------------------------------------------------------
COMMAND 0x12: PRESET REQUEST
--------------------------------------------------------------------------------
Request a preset configuration from device memory.

Request:
    F0 47 00 34 12 00 01 <preset_num> F7

    12          = Preset Request command
    00 01       = Length (1 byte)
    <preset_num> = Preset to read (0x01-0x10 for presets 1-16)

Response:
    F0 47 00 34 10 04 1d <preset_data 541 bytes> F7

    Returns a Preset Dump message with the requested preset data.

================================================================================
PRESET DATA STRUCTURE (541 bytes)
================================================================================

Header (13 bytes):
    Byte 0      = Preset number (1-16)
    Bytes 1-8   = Name (8 ASCII characters, space-padded)
    Bytes 9-10  = Tempo (7-bit stuffed, see below)
    Byte 11     = Division (0-7, see TIME_DIVISION enum)
    Byte 12     = Swing (50, 54, 56, 58, 60, 62)

Tempo encoding (7-bit stuffing):
    The tempo value (30-300 BPM) is split across two bytes:
    Byte 9  = (tempo & 0x7F)          # Low 7 bits
    Byte 10 = (tempo >> 7) & 0x7F     # High bits

Pad Configurations (384 bytes = 48 pads x 8 bytes):
    Organized as 3 banks of 16 pads each.
    Order: Bank A (pads 1-16), Bank B (pads 1-16), Bank C (pads 1-16)

    For each pad (8 bytes):
        Byte 0      = Type (0=NOTE, 1=PROG, 2=BANK)
        Byte 1      = MIDI channel (1-16, stored as 1-indexed)
        Byte 2      = Note number (0-127, NOTE mode only)
        Byte 3      = Trigger (0=MOMENTARY, 1=TOGGLE, NOTE mode only)
        Byte 4      = Aftertouch (0=OFF, 1=CHANNEL, 2=POLY, NOTE mode only)
        Byte 5      = Program number (0-127, PROG mode only)
        Byte 6      = Bank MSB (0-127, BANK mode only)
        Byte 7      = Bank LSB (0-127, BANK mode only)

Knob Configurations (144 bytes = 18 knobs x 8 bytes):
    Organized as 3 banks of 6 knobs each.
    Order: Bank A (knobs 1-6), Bank B (knobs 1-6), Bank C (knobs 1-6)

    For each knob (8 bytes):
        Byte 0      = Type (0=CC, 1=AFTERTOUCH, 2=INC_DEC_1, 3=INC_DEC_2)
        Byte 1      = MIDI channel (1-16, stored as 1-indexed)
        Byte 2      = CC number (0-127, CC and INC_DEC_2 modes)
        Byte 3      = Minimum value (0-127, CC and AFTERTOUCH modes)
        Byte 4      = Maximum value (0-127, CC and AFTERTOUCH modes)
        Byte 5      = MSB (0-127, INC_DEC_1 mode only)
        Byte 6      = LSB (0-127, INC_DEC_1 mode only)
        Byte 7      = Value (0-127, INC_DEC_1 mode only)

Total: 13 (header) + 384 (pads) + 144 (knobs) = 541 bytes

================================================================================
MIDI MESSAGE FORMATS (Standard MIDI, not SysEx)
================================================================================

PAD MESSAGES (NOTE mode - Default):
    Note On:  9n kk vv    (n=channel, kk=note, vv=velocity)
    Note Off: 8n kk 00    (n=channel, kk=note)

PAD MESSAGES (PROG mode):
    PC:       Cn pp       (n=channel, pp=program)

PAD MESSAGES (BANK mode):
    CC:       Bn 00 mm    (Bank Select MSB: n=channel, mm=msb)
    CC:       Bn 20 ll    (Bank Select LSB: n=channel, ll=lsb)

KNOB MESSAGES (CC mode - Default):
    CC:       Bn cc vv    (n=channel, cc=CC number, vv=value)

AFTERTOUCH:
    Channel:  Dn vv       (n=channel, vv=pressure)
    Poly:     An kk vv    (n=channel, kk=note, vv=pressure)

================================================================================
DEFAULT MIDI MAPPINGS
================================================================================

Pad Banks (default channel 10):
    Bank A: Notes 36-51 (C2 to D#3)
    Bank B: Notes 52-67 (E3 to G4)
    Bank C: Notes 68-83 (G#4 to B5)

Knob Banks (example CCs, varies by preset):
    Bank A: CCs 3, 9, 12, 13, 14, 15
    Bank B: CCs 16, 17, 18, 19, 20, 21
    Bank C: CCs 22, 23, 24, 25, 26, 27

================================================================================
LED BEHAVIOR
================================================================================

IMPORTANT: The MPD218 does NOT support software-controlled LED colors.

The red backlit LEDs are managed entirely by the device firmware:
- LEDs light up when a pad is pressed (velocity-sensitive brightness)
- In TOGGLE mode, LED stays on when pad is "on" and off when "off"
- There is NO SysEx command to control LED state or color

This means:
- supports_feedback = False for all pads
- No translate_feedback() messages for LEDs
- LED state reflects hardware state, not software state

================================================================================
References:
- User Guide: MPD218-UserGuide-v1.0.pdf
- Protocol: github.com/simonwood/mpd-utils
================================================================================
"""

import time
from enum import IntEnum
from typing import TYPE_CHECKING, Callable, Optional, Tuple

import mido
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from padbound.config import ControllerConfig

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
    BatchFeedbackResult,
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)
from padbound.state import ControlState

logger = get_logger(__name__)


# =============================================================================
# Enums for MPD218 configuration
# =============================================================================


class PadType(IntEnum):
    """Pad message type."""

    NOTE = 0
    PROG = 1
    BANK = 2


class PadTrigger(IntEnum):
    """Pad trigger mode."""

    MOMENTARY = 0
    TOGGLE = 1


class PadAftertouch(IntEnum):
    """Pad aftertouch mode."""

    OFF = 0
    CHANNEL = 1
    POLY = 2


class KnobType(IntEnum):
    """Knob message type."""

    CC = 0
    AFTERTOUCH = 1
    INC_DEC_1 = 2
    INC_DEC_2 = 3


class TimeDivision(IntEnum):
    """Note repeat time division."""

    DIV_1_4 = 0
    DIV_1_4T = 1
    DIV_1_8 = 2
    DIV_1_8T = 3
    DIV_1_16 = 4
    DIV_1_16T = 5
    DIV_1_32 = 6
    DIV_1_32T = 7


class Swing(IntEnum):
    """Swing amount."""

    OFF = 50
    SWING_54 = 54
    SWING_56 = 56
    SWING_58 = 58
    SWING_60 = 60
    SWING_62 = 62


# =============================================================================
# Pydantic models for SysEx preset parsing
# =============================================================================


class MPD218PadConfig(BaseModel):
    """Configuration for a single MPD218 pad (8 bytes in SysEx)."""

    type: PadType = Field(default=PadType.NOTE, description="Message type")
    channel: int = Field(default=10, ge=1, le=16, description="MIDI channel (1-16)")
    note: int = Field(default=36, ge=0, le=127, description="Note number (NOTE mode)")
    trigger: PadTrigger = Field(default=PadTrigger.MOMENTARY, description="Trigger mode")
    aftertouch: PadAftertouch = Field(default=PadAftertouch.CHANNEL, description="Aftertouch mode")
    program: int = Field(default=0, ge=0, le=127, description="Program number (PROG mode)")
    msb: int = Field(default=0, ge=0, le=127, description="Bank MSB (BANK mode)")
    lsb: int = Field(default=0, ge=0, le=127, description="Bank LSB (BANK mode)")

    def to_bytes(self) -> bytes:
        """Convert to 8-byte SysEx format."""
        return bytes(
            [
                self.type,
                self.channel,  # 1-indexed in protocol
                self.note,
                self.trigger,
                self.aftertouch,
                self.program,
                self.msb,
                self.lsb,
            ],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "MPD218PadConfig":
        """Parse from 8-byte SysEx format."""
        if len(data) < 8:
            raise ValueError(f"Pad config requires 8 bytes, got {len(data)}")
        return cls(
            type=PadType(data[0]),
            channel=data[1],
            note=data[2],
            trigger=PadTrigger(data[3]),
            aftertouch=PadAftertouch(data[4]),
            program=data[5],
            msb=data[6],
            lsb=data[7],
        )


class MPD218KnobConfig(BaseModel):
    """Configuration for a single MPD218 knob (8 bytes in SysEx)."""

    type: KnobType = Field(default=KnobType.CC, description="Message type")
    channel: int = Field(default=1, ge=1, le=16, description="MIDI channel (1-16)")
    midicc: int = Field(default=3, ge=0, le=127, description="CC number")
    min_value: int = Field(default=0, ge=0, le=127, description="Minimum value")
    max_value: int = Field(default=127, ge=0, le=127, description="Maximum value")
    msb: int = Field(default=0, ge=0, le=127, description="MSB (INC_DEC_1 mode)")
    lsb: int = Field(default=0, ge=0, le=127, description="LSB (INC_DEC_1 mode)")
    value: int = Field(default=0, ge=0, le=127, description="Value (INC_DEC_1 mode)")

    def to_bytes(self) -> bytes:
        """Convert to 8-byte SysEx format."""
        return bytes(
            [
                self.type,
                self.channel,
                self.midicc,
                self.min_value,
                self.max_value,
                self.msb,
                self.lsb,
                self.value,
            ],
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> "MPD218KnobConfig":
        """Parse from 8-byte SysEx format."""
        if len(data) < 8:
            raise ValueError(f"Knob config requires 8 bytes, got {len(data)}")
        return cls(
            type=KnobType(data[0]),
            channel=data[1],
            midicc=data[2],
            min_value=data[3],
            max_value=data[4],
            msb=data[5],
            lsb=data[6],
            value=data[7],
        )


class MPD218PresetConfig(BaseModel):
    """Complete MPD218 preset configuration (541 bytes in SysEx)."""

    preset_num: int = Field(default=1, ge=1, le=16, description="Preset number (1-16)")
    name: str = Field(default="Padbound", max_length=8, description="Preset name (8 chars)")
    tempo: int = Field(default=120, ge=0, le=300, description="Tempo BPM (0 = use device default)")
    division: TimeDivision = Field(default=TimeDivision.DIV_1_16, description="Time division")
    swing: Swing = Field(default=Swing.OFF, description="Swing amount")
    pads: list[MPD218PadConfig] = Field(
        default_factory=lambda: [MPD218PadConfig() for _ in range(48)],
        min_length=48,
        max_length=48,
        description="48 pad configs (3 banks x 16 pads)",
    )
    knobs: list[MPD218KnobConfig] = Field(
        default_factory=lambda: [MPD218KnobConfig() for _ in range(18)],
        min_length=18,
        max_length=18,
        description="18 knob configs (3 banks x 6 knobs)",
    )

    def to_sysex_message(self) -> mido.Message:
        """Build complete preset upload SysEx message.

        Format: F0 47 00 34 10 04 1d <541 bytes preset data> F7
        """
        # Build preset data
        data = []

        # Header
        data.append(self.preset_num)

        # Name (8 chars, space-padded)
        name_bytes = (self.name + " " * 8)[:8].encode("ascii")
        data.extend(name_bytes)

        # Tempo (7-bit stuffed, big-endian: high byte first)
        data.append((self.tempo >> 7) & 0x7F)  # High bits
        data.append(self.tempo & 0x7F)  # Low 7 bits

        # Division and Swing
        data.append(self.division)
        data.append(self.swing)

        # Pad configs (48 x 8 = 384 bytes)
        for pad in self.pads:
            data.extend(pad.to_bytes())

        # Knob configs (18 x 8 = 144 bytes)
        for knob in self.knobs:
            data.extend(knob.to_bytes())

        # Build SysEx message
        # Header: 47 00 34 10 04 1d (Akai, device 0, MPD218, preset dump, length)
        sysex_data = [
            0x47,  # Akai manufacturer
            0x00,  # Device ID
            0x34,  # MPD218 product ID
            0x10,  # Preset dump command
            0x04,  # Length MSB (541 >> 7 = 4)
            0x1D,  # Length LSB (541 & 0x7F = 29)
        ] + data

        return mido.Message("sysex", data=sysex_data)

    @classmethod
    def from_sysex_data(cls, data: tuple | list) -> Optional["MPD218PresetConfig"]:
        """Parse preset from SysEx response data.

        Expected format: 47 00 34 10 04 1d <541 bytes>

        Args:
            data: SysEx data bytes (without F0/F7)

        Returns:
            MPD218PresetConfig if valid, None otherwise
        """
        data = list(data)

        # Validate header
        if len(data) < 547:  # 6 header + 541 data
            logger.warning(f"Preset data too short: {len(data)} bytes (expected 547)")
            return None

        if data[0] != 0x47 or data[2] != 0x34 or data[3] != 0x10:
            logger.warning(f"Invalid preset header: {data[:6]}")
            return None

        # Skip header (6 bytes)
        payload = data[6:]

        # Parse header
        preset_num = payload[0]
        name = bytes(payload[1:9]).decode("ascii", errors="replace").rstrip()
        # Tempo (7-bit stuffed, big-endian: high byte at [9], low byte at [10])
        tempo = (payload[10] & 0x7F) | ((payload[9] & 0x7F) << 7)
        division = TimeDivision(payload[11])
        swing = Swing(payload[12])

        # Parse pads (starting at byte 13)
        pads = []
        pad_offset = 13
        for i in range(48):
            pad_data = payload[pad_offset + i * 8 : pad_offset + i * 8 + 8]
            pads.append(MPD218PadConfig.from_bytes(bytes(pad_data)))

        # Parse knobs (starting after pads: 13 + 384 = 397)
        knobs = []
        knob_offset = 397
        for i in range(18):
            knob_data = payload[knob_offset + i * 8 : knob_offset + i * 8 + 8]
            knobs.append(MPD218KnobConfig.from_bytes(bytes(knob_data)))

        return cls(
            preset_num=preset_num,
            name=name,
            tempo=tempo,
            division=division,
            swing=swing,
            pads=pads,
            knobs=knobs,
        )


# =============================================================================
# Plugin Implementation
# =============================================================================


class AkaiMPD218Plugin(ControllerPlugin):
    """
    AKAI MPD218 plugin with multi-bank pad and knob support.

    Features:
    - 16 velocity-sensitive pads per bank (3 banks = 48 total pads)
    - 6 endless rotary knobs per bank (3 banks = 18 total knobs)
    - Bank detection via note range (same MIDI channel for all banks)
    - Pads configurable as TOGGLE or MOMENTARY
    - Red backlit LEDs (hardware-managed, no software control)
    - 16 presets stored in device memory via SysEx
    """

    # Hardware configuration
    PAD_COUNT = 16
    PAD_BANKS = 3
    PAD_TOTAL = PAD_COUNT * PAD_BANKS  # 48

    KNOB_COUNT = 6
    KNOB_BANKS = 3
    KNOB_TOTAL = KNOB_COUNT * KNOB_BANKS  # 18

    # Bank identifiers
    BANK_IDS = ["bank_a", "bank_b", "bank_c"]

    # Note ranges per bank (factory defaults)
    BANK_NOTE_RANGES: dict[str, tuple[int, int]] = {
        "bank_a": (36, 51),  # C2 to D#3
        "bank_b": (52, 67),  # E3 to G4
        "bank_c": (68, 83),  # G#4 to B5
    }

    # Default knob CC assignments per bank
    DEFAULT_KNOB_CCS: dict[str, list[int]] = {
        "bank_a": [3, 9, 12, 13, 14, 15],
        "bank_b": [16, 17, 18, 19, 20, 21],
        "bank_c": [22, 23, 24, 25, 26, 27],
    }

    # Default MIDI channel (0-indexed, channel 10 = 9)
    DEFAULT_CHANNEL = 9

    # SysEx constants
    SYSEX_MANUFACTURER = 0x47  # Akai
    SYSEX_DEVICE_ID = 0x00
    SYSEX_PRODUCT_ID = 0x34  # MPD218
    SYSEX_PRESET_DUMP = 0x10
    SYSEX_PRESET_REQUEST = 0x12

    def __init__(self):
        """Initialize plugin with separate pad/knob bank tracking."""
        super().__init__()
        self._last_pad_bank: str = "bank_a"
        self._last_knob_bank: str = "bank_a"
        self._current_preset: Optional[MPD218PresetConfig] = None
        # Store callbacks for runtime queries
        self._send_message: Optional[Callable[[mido.Message], None]] = None
        self._receive_message: Optional[Callable[[float], Optional[mido.Message]]] = None

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "AKAI MPD218"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "MPD218",
            "MPD218 MIDI 1",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # No bank LEDs to control
            indexing_scheme="1d",  # Linear pad/knob numbering per bank
            supports_persistent_configuration=True,  # Supports SysEx programming
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 3 pad banks and 3 knob banks (independent).

        Banks are detected by note range (pads) and CC range (knobs)
        since all use the same MIDI channel.
        """
        return [
            BankDefinition(bank_id="bank_a", category="pad", display_name="Bank A"),
            BankDefinition(bank_id="bank_b", category="pad", display_name="Bank B"),
            BankDefinition(bank_id="bank_c", category="pad", display_name="Bank C"),
            BankDefinition(bank_id="bank_a", category="knob", display_name="Bank A"),
            BankDefinition(bank_id="bank_b", category="knob", display_name="Bank B"),
            BankDefinition(bank_id="bank_c", category="knob", display_name="Bank C"),
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across 3 banks.

        Creates 3 banks x (16 pads + 6 knobs) = 66 controls total.
        """
        definitions = []

        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            start_note, _ = self.BANK_NOTE_RANGES[bank_id]
            self.DEFAULT_KNOB_CCS[bank_id]

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
                            requires_hardware_sync=True,  # Mode stored in preset
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Hardware manages LEDs
                            requires_feedback=False,
                            supports_led=False,  # Cannot control via software
                            supports_color=False,  # Red only, not controllable
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        bank_id=bank_id,
                        display_name=f"B{chr(65 + bank_idx)} Pad {pad_num}",
                    ),
                )

            # 6 knobs per bank
            for knob_num in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{knob_num}@{bank_id}",
                        control_type=ControlType.CONTINUOUS,
                        category="knob",
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Not motorized
                            requires_discovery=True,  # Initial position unknown
                        ),
                        bank_id=bank_id,
                        min_value=0,
                        max_value=127,
                        display_name=f"B{chr(65 + bank_idx)} Knob {knob_num}",
                    ),
                )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        All banks use the same MIDI channel (default 10).
        Banks are distinguished by note range for pads.
        """
        mappings = []

        for _bank_idx, bank_id in enumerate(self.BANK_IDS):
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
                            channel=self.DEFAULT_CHANNEL,
                            note=midi_note,
                            control_id=control_id,
                            signal_type="note",
                        ),
                        MIDIMapping(
                            message_type=MIDIMessageType.NOTE_OFF,
                            channel=self.DEFAULT_CHANNEL,
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
                        channel=self.DEFAULT_CHANNEL,
                        control=midi_cc,
                        control_id=control_id,
                        signal_type="default",
                    ),
                )

        return mappings

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with bank detection from note range.

        Since all banks share the same MIDI channel, we detect the active
        bank from the note number for pads and CC number for knobs.
        Pad and knob banks are tracked independently.

        Returns:
            (control_id, value, signal_type) or None
        """
        # Handle note messages (pads)
        if msg.type in ("note_on", "note_off"):
            note = msg.note

            # Find which bank this note belongs to
            for bank_id, (start_note, end_note) in self.BANK_NOTE_RANGES.items():
                if start_note <= note <= end_note:
                    # Update pad bank tracking
                    if bank_id != self._last_pad_bank:
                        logger.debug(f"MPD218 pad bank switch: {self._last_pad_bank} -> {bank_id}")
                        self._last_pad_bank = bank_id

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
                    # Update knob bank tracking
                    if bank_id != self._last_knob_bank:
                        logger.debug(f"MPD218 knob bank switch: {self._last_knob_bank} -> {bank_id}")
                        self._last_knob_bank = bank_id

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
    ) -> Tuple[Optional[ControlState], bool]:
        """
        Handle state for pads when hardware manages toggle mode.

        When hardware is in TOGGLE mode:
        - Hardware tracks toggle state and manages LED
        - Software just reports press/release events
        - is_on=True on note_on (pressed), is_on=False on note_off (released)

        This avoids software/hardware state getting out of sync.

        Args:
            control_id: Control identifier (e.g., "pad_1@bank_a")
            value: MIDI value (velocity for notes, 0-127 for CC)
            signal_type: Signal type ("note", "cc", etc.)
            current_state: Current control state
            control_definition: Control definition with type info

        Returns:
            (state, trigger_callback) tuple:
            - state: New ControlState or None for default behavior
            - trigger_callback: Whether to fire user callbacks
        """
        is_pad = "pad_" in control_id
        is_toggle = control_definition.control_type == ControlType.TOGGLE
        is_note = signal_type == "note"

        if is_pad and is_toggle and is_note:
            # Don't software-toggle - just report press/release
            # Hardware handles actual toggle state and LED
            is_pressed = value > 0
            return (
                ControlState(
                    control_id=control_id,
                    timestamp=current_state.timestamp,
                    is_discovered=True,
                    is_on=is_pressed,  # True=pressed, False=released
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
        Initialize MPD218 to known state.

        Queries the device for the currently active preset and parses
        the pad/knob configuration.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            None - pads don't report state, knobs need physical movement
        """
        logger.info("Initializing AKAI MPD218")

        # Store callbacks for runtime use
        self._send_message = send_message
        self._receive_message = receive_message

        # Query preset 1 to verify communication
        preset = self._query_preset(send_message, receive_message, preset_num=1)
        if preset:
            self._current_preset = preset
            logger.info(f"MPD218 preset 1 loaded: '{preset.name}' tempo={preset.tempo}")
        else:
            logger.warning("Could not query MPD218 preset, using defaults")
            self._current_preset = None

        # Default to bank A
        self._last_pad_bank = "bank_a"
        self._last_knob_bank = "bank_a"

        logger.info("MPD218 initialization complete")
        return None

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence for MPD218.

        The MPD218 doesn't need special cleanup since LEDs are hardware-managed.
        """
        logger.info("Shutting down AKAI MPD218")
        # No cleanup needed - LEDs are hardware-managed
        logger.info("MPD218 shutdown complete")

    def translate_feedback(
        self,
        control_id: str,
        state: ControlState,
        definition: ControlDefinition,
    ) -> list[mido.Message]:
        """
        Translate control state to MIDI feedback.

        For MPD218, this always returns an empty list since:
        - Pad LEDs are hardware-managed (no software control)
        - Knobs are not motorized (no feedback capability)

        Args:
            control_id: Control being updated
            state: Current control state
            definition: Control definition

        Returns:
            Empty list (no feedback support)
        """
        # MPD218 has no software-controllable feedback
        return []

    def translate_feedback_batch(
        self,
        updates: list[tuple[str, ControlState, ControlDefinition]],
    ) -> BatchFeedbackResult:
        """
        Translate multiple control states to MIDI feedback.

        For MPD218, this always returns an empty result since there
        is no software-controllable LED feedback.

        Args:
            updates: List of (control_id, state, definition) tuples

        Returns:
            Empty BatchFeedbackResult
        """
        # MPD218 has no software-controllable feedback
        return BatchFeedbackResult(messages=[])

    def configure_programs(
        self,
        send_message: Callable[[mido.Message], None],
        config: "ControllerConfig",
    ) -> None:
        """
        Program preset configuration into device memory.

        Writes user configuration (toggle/momentary modes, note assignments)
        to MPD218 preset memory via SysEx.

        Note: This writes to preset 1 by default. The MPD218 stores the
        configuration persistently and applies it when the preset is loaded.

        Args:
            send_message: Function to send MIDI messages
            config: Full controller configuration with resolved settings
        """
        if not config or not config.banks:
            logger.debug("No configuration provided, skipping preset programming")
            return

        logger.info("Programming MPD218 preset with configuration")

        # Build preset configuration from user config
        preset = self._build_preset_from_config(config)

        # Send preset to device
        sysex_msg = preset.to_sysex_message()
        logger.debug(f"Sending preset SysEx ({len(sysex_msg.data)} bytes)")
        send_message(sysex_msg)

        # Allow device to process
        time.sleep(0.2)

        logger.info("MPD218 preset programming complete")

    def _query_preset(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]],
        preset_num: int = 1,
    ) -> Optional[MPD218PresetConfig]:
        """
        Query a preset from device memory.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout
            preset_num: Preset number to query (1-16)

        Returns:
            MPD218PresetConfig if successful, None otherwise
        """
        # Build query: F0 47 00 34 12 00 01 <preset_num> F7
        query = mido.Message(
            "sysex",
            data=[
                self.SYSEX_MANUFACTURER,
                self.SYSEX_DEVICE_ID,
                self.SYSEX_PRODUCT_ID,
                self.SYSEX_PRESET_REQUEST,
                0x00,
                0x01,
                preset_num,
            ],
        )

        logger.debug(f"Querying MPD218 preset {preset_num}...")
        send_message(query)

        # Wait for response
        response = receive_message(1.0)  # 1 second timeout

        if response and response.type == "sysex":
            preset = MPD218PresetConfig.from_sysex_data(response.data)
            if preset:
                logger.debug(f"Received preset {preset.preset_num}: '{preset.name}'")
                return preset
            else:
                logger.warning("Failed to parse preset response")
        else:
            logger.warning("No preset response received from device")

        return None

    def _build_preset_from_config(
        self,
        config: "ControllerConfig",
        preset_num: int = 1,
    ) -> MPD218PresetConfig:
        """
        Build an MPD218PresetConfig from user configuration.

        Maps padbound config to MPD218 preset format:
        - Control types (TOGGLE/MOMENTARY) -> pad trigger mode
        - Bank configurations -> appropriate pad/knob slots

        Args:
            config: User configuration
            preset_num: Preset number to write (1-16)

        Returns:
            MPD218PresetConfig ready to upload
        """
        # Start with default preset
        preset = MPD218PresetConfig(preset_num=preset_num, name="Padbound")

        # Configure pads for each bank
        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            start_note, _ = self.BANK_NOTE_RANGES[bank_id]
            bank_config = config.banks.get(bank_id) if config.banks else None

            for pad_num in range(1, self.PAD_COUNT + 1):
                pad_idx = bank_idx * self.PAD_COUNT + pad_num - 1
                midi_note = start_note + pad_num - 1

                # Get pad config from user config
                control_id = f"pad_{pad_num}"
                control_config = None
                if bank_config and bank_config.controls:
                    control_config = bank_config.controls.get(control_id)

                # Determine trigger mode from control type
                trigger = PadTrigger.MOMENTARY  # Default
                if (control_config and control_config.type == ControlType.TOGGLE) or (
                    bank_config and bank_config.toggle_mode
                ):
                    trigger = PadTrigger.TOGGLE

                # Build pad config
                preset.pads[pad_idx] = MPD218PadConfig(
                    type=PadType.NOTE,
                    channel=self.DEFAULT_CHANNEL + 1,  # 1-indexed in preset
                    note=midi_note,
                    trigger=trigger,
                    aftertouch=PadAftertouch.CHANNEL,
                )

        # Configure knobs for each bank
        for bank_idx, bank_id in enumerate(self.BANK_IDS):
            knob_ccs = self.DEFAULT_KNOB_CCS[bank_id]

            for knob_num in range(1, self.KNOB_COUNT + 1):
                knob_idx = bank_idx * self.KNOB_COUNT + knob_num - 1
                midi_cc = knob_ccs[knob_num - 1]

                preset.knobs[knob_idx] = MPD218KnobConfig(
                    type=KnobType.CC,
                    channel=self.DEFAULT_CHANNEL + 1,  # 1-indexed in preset
                    midicc=midi_cc,
                    min_value=0,
                    max_value=127,
                )

        return preset

    def get_debug_layout(self):
        """
        Define TUI layout matching physical MPD218 layout.

        Physical layout (6 cols × 4 rows):
        - Cols 0-1: 6 knobs in 3 rows of 2
        - Cols 2-5: 4x4 pad grid

        Knobs:   Pads:
        K1  K2   13 14 15 16
        K3  K4    9 10 11 12
        K5  K6    5  6  7  8
         .   .    1  2  3  4

        Returns:
            DebugLayout for the state debug TUI
        """
        from padbound.debug.layout import ControlPlacement, ControlWidget, DebugLayout, LayoutSection

        controls = []
        pad_bank = self._last_pad_bank
        knob_bank = self._last_knob_bank

        # Knobs (cols 0-1, rows 0-2)
        knob_layout = [
            [1, 2],  # row 0
            [3, 4],  # row 1
            [5, 6],  # row 2
        ]
        for row, knob_row in enumerate(knob_layout):
            for col, knob_num in enumerate(knob_row):
                controls.append(
                    ControlPlacement(
                        control_id=f"knob_{knob_num}@{knob_bank}",
                        widget_type=ControlWidget.KNOB,
                        row=row,
                        col=col,
                        label=f"K{knob_num}",
                    ),
                )

        # Pads (cols 2-5, rows 0-3)
        # Row 0: pads 13-16, Row 1: pads 9-12, Row 2: pads 5-8, Row 3: pads 1-4
        pad_layout = [
            [13, 14, 15, 16],  # row 0
            [9, 10, 11, 12],  # row 1
            [5, 6, 7, 8],  # row 2
            [1, 2, 3, 4],  # row 3
        ]
        for row, pad_row in enumerate(pad_layout):
            for col_offset, pad_num in enumerate(pad_row):
                controls.append(
                    ControlPlacement(
                        control_id=f"pad_{pad_num}@{pad_bank}",
                        widget_type=ControlWidget.PAD,
                        row=row,
                        col=2 + col_offset,
                    ),
                )

        bank_desc = f"pads: {pad_bank} | knobs: {knob_bank}" if pad_bank != knob_bank else pad_bank
        return DebugLayout(
            plugin_name=self.name,
            description=f"AKAI MPD218 - {bank_desc}",
            sections=[
                LayoutSection(
                    name=f"MPD218 - {bank_desc}",
                    controls=controls,
                    rows=4,
                    cols=6,
                ),
            ],
        )
