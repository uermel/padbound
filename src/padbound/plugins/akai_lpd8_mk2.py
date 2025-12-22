"""
AKAI LPD8 MK2 MIDI Controller Plugin.
Firmware: 2.49

Hardware specifications:
- 8 RGB backlit drum pads (notes 36-43)
- 8 endless knobs (CC 1-8)
- 4 banks (programs) with customizable MIDI mappings
- RGB LED control via SysEx
- USB MIDI interface

Control features:
- Pads configurable as TOGGLE or MOMENTARY (global per program)
- Pads can send NOTE (default), CC, or PC messages (hardware configurable)
- Knobs send CC messages (read-only, no motorized feedback)
- Multi-bank support via different MIDI channels per bank

================================================================================
SYSEX PROTOCOL DOCUMENTATION
================================================================================

All SysEx messages use the following header format:
    F0 47 7F 4C <cmd> [payload...] F7

Where:
    F0          = SysEx start
    47          = Akai manufacturer ID
    7F          = Device ID (all devices)
    4C          = LPD8 MK2 product ID
    <cmd>       = Command byte
    [payload]   = Command-specific data
    F7          = SysEx end

--------------------------------------------------------------------------------
COMMAND 0x01: SEND PROGRAM (Write Configuration)
--------------------------------------------------------------------------------
Writes a complete program configuration to device non-volatile memory.

Request:
    F0 47 7F 4C 01 01 29 <program_data> F7

    Header (6 bytes):
        01          = Send Program command
        01          = Sub-ID 1
        29          = Sub-ID 2 (program data marker, 41 decimal)

    Program Settings (5 bytes):
        Byte 0      = Program number (1-4)
        Byte 1      = MIDI channel (0-15, where 0 = channel 1)
        Byte 2      = Pressure mode (0=off, 1=channel aftertouch, 2=poly aftertouch)
        Byte 3      = Full level (0=ON fixed 127, 1=OFF velocity sensitive)
        Byte 4      = Toggle mode (0=momentary, 1=toggle)

    Pad Configurations (128 bytes = 8 pads × 16 bytes each):
        For each pad (16 bytes):
            Byte 0      = MIDI note number (0-127)
            Byte 1      = CC number (0-127)
            Byte 2      = Program Change number (0-127)
            Byte 3      = MIDI channel (0-15)
            Bytes 4-9   = OFF color RGB (6 bytes, split format)
            Bytes 10-15 = ON color RGB (6 bytes, split format)

        Color format (split):
            Each color channel (0-255) is split into two 7-bit bytes:
            [R_hi, R_lo, G_hi, G_lo, B_hi, B_lo]
            Where: hi = value // 128, lo = value % 128
            Example: RGB(255, 128, 64) → [1, 127, 1, 0, 0, 64]

    Knob Configurations (32 bytes = 8 knobs × 4 bytes each):
        For each knob (4 bytes):
            Byte 0      = CC number (0-127)
            Byte 1      = MIDI channel (0-15)
            Byte 2      = Minimum value (0-127)
            Byte 3      = Maximum value (0-127)

    Total message size: 6 (header) + 5 (settings) + 128 (pads) + 32 (knobs) = 171 bytes

Response: None

--------------------------------------------------------------------------------
COMMAND 0x03: GET PROGRAM (Read Configuration)
--------------------------------------------------------------------------------
Reads a program configuration from device memory.

Request:
    F0 47 7F 4C 03 00 01 <program_num> F7

    03          = Get Program command
    00 01       = Sub-IDs
    <program_num> = Program to read (1-4)

Response:
    F0 47 7F 4C 03 01 29 <program_data> F7

    Same format as Send Program (0x01), with program data in response.

--------------------------------------------------------------------------------
COMMAND 0x04: GET ACTIVE PROGRAM
--------------------------------------------------------------------------------
Queries which program (1-4) is currently active on the device.

Request:
    F0 47 7F 4C 04 00 00 F7

    04          = Get Active Program command
    00 00       = Required payload

Response:
    F0 47 7F 4C 04 00 01 <program_num> F7

    04          = Get Active Program command
    00 01       = Response marker
    <program_num> = Currently active program (1-4)

Example:
    Request:  F0 47 7F 4C 04 00 00 F7
    Response: F0 47 7F 4C 04 00 01 01 F7  (Program 1 is active)

--------------------------------------------------------------------------------
COMMAND 0x05: GET LED STATE
--------------------------------------------------------------------------------
Reads the current LED colors for all 8 pads.

Request:
    F0 47 7F 4C 05 00 00 F7

    05          = Get LED State command
    00 00       = Required payload

Response:
    F0 47 7F 4C 05 00 30 <rgb_data> F7

    05          = Get LED State command
    00 30       = Response marker (0x30 = 48 decimal = 8 pads × 6 bytes)
    <rgb_data>  = 48 bytes of RGB data (8 pads × 6 bytes each)

    RGB format (MIDI range, split):
        Each pad: [R_hi, R_lo, G_hi, G_lo, B_hi, B_lo]
        Values are in MIDI range (0-127), split into hi/lo 7-bit bytes.
        Since max is 127, hi byte is always 0 or 1.

--------------------------------------------------------------------------------
COMMAND 0x06: LED UPDATE (Temporary)
--------------------------------------------------------------------------------
Directly updates LED colors for all 8 pads. This is a temporary update
that takes effect immediately but does not persist across program switches.

Request:
    F0 47 7F 4C 06 00 30 <rgb_data> F7

    06          = LED Update command
    00 30       = Sub-IDs (0x30 = 48 bytes of RGB data)
    <rgb_data>  = 48 bytes of RGB data (8 pads × 6 bytes each)

    RGB format (MIDI range, split):
        Each pad: [R_hi, R_lo, G_hi, G_lo, B_hi, B_lo]
        Values should be in MIDI range (0-127).
        hi = (value >> 7) & 0x7F
        lo = value & 0x7F

    Pad order: Pad 1, Pad 2, ..., Pad 8

Response: None

Example (set all pads to red at half brightness):
    RGB(64, 0, 0) for each pad:
    hi=0, lo=64 for R; hi=0, lo=0 for G and B
    F0 47 7F 4C 06 00 30
       00 40 00 00 00 00  (Pad 1: R=64, G=0, B=0)
       00 40 00 00 00 00  (Pad 2)
       ... (repeat for all 8 pads)
    F7

--------------------------------------------------------------------------------
COMMAND 0x5A: DEVICE INFO (Speculative)
--------------------------------------------------------------------------------
Returns device/firmware information.

Request:
    F0 47 7F 4C 5A F7

    5A          = Device Info command (no payload required)

Response:
    F0 47 7F 4C 5A 00 20 <device_info> F7

    5A          = Device Info command
    00 20       = Response marker (0x20 = 32 bytes of info)
    <device_info> = Device information bytes (format partially known)

    Known fields in response:
        Byte 4-5    = Firmware version (e.g., 03 02 = v3.2 or similar)
        Other bytes = Hardware identifiers, serial info (undocumented)

================================================================================
MIDI MESSAGE FORMATS (Standard MIDI, not SysEx)
================================================================================

PAD MESSAGES (Note Mode - Default):
    Note On:  9n kk vv    (n=channel, kk=note 36-43, vv=velocity)
    Note Off: 8n kk 00    (n=channel, kk=note 36-43)

PAD MESSAGES (CC Mode - Hardware Configurable):
    CC:       Bn cc vv    (n=channel, cc=36-43, vv=value)

PAD MESSAGES (PC Mode - Hardware Configurable):
    PC:       Cn pp       (n=channel, pp=program 0-7 for pads 1-8)

KNOB MESSAGES:
    CC:       Bn cc vv    (n=channel, cc=1-8, vv=0-127)

================================================================================
DEFAULTS
================================================================================

All 4 programs ship with:
    - MIDI Channel: 10 (index 9)
    - Toggle Mode: Program 1-3 = Momentary, Program 4 = Toggle
    - Pad Notes: 36-43
    - Knob CCs: 1-8
    - Pressure: Off
    - Full Level: Off (velocity sensitive)

Default colors (per program):
    Program 1: OFF=Red,    ON=Blue
    Program 2: OFF=Green,  ON=Blue
    Program 3: OFF=Cyan,   ON=Magenta
    Program 4: OFF=Black,  ON=White

================================================================================
References:
- Partial protocol documentation: https://github.com/stephensrmmartin/lpd8mk2
- Commands 0x04, 0x05, 0x5A discovered via SysEx probing (December 2025)
================================================================================
"""

import time
from typing import Optional, Callable

import mido
from pydantic import BaseModel, Field

from ..plugin import (
    ControllerPlugin,
    MIDIMapping,
    MIDIMessageType,
)
from ..controls import (
    ControlDefinition,
    ControlType,
    ControlCapabilities,
    ControlTypeModes,
    ControllerCapabilities,
    BankDefinition,
)
from ..logging_config import get_logger
from ..utils import RGBColor

logger = get_logger(__name__)


class LPD8MK2RGBColor(RGBColor):
    """RGB color with LPD8 MK2-specific SysEx byte conversion methods.

    Extends base RGBColor with methods for converting to the byte formats
    required by the LPD8 MK2's SysEx protocol.
    """

    def to_sysex_bytes_split(self) -> list[int]:
        """Split each channel (0-255) into hi/lo 7-bit bytes for program config.

        Used in the Send Program command (0x01) for storing pad colors.
        Returns 6 bytes: [R_hi, R_lo, G_hi, G_lo, B_hi, B_lo]
        """
        result = []
        for value in (self.r, self.g, self.b):
            hi = value // 128
            lo = value % 128
            result.extend([hi, lo])
        return result

    def to_sysex_bytes_midi(self) -> list[int]:
        """Convert to MIDI range (0-127) and split into hi/lo bytes for LED control.

        Used in the LED update command (0x06) for real-time pad color changes.
        Returns 6 bytes with hi bytes always 0 (since max value is 127).
        """
        result = []
        for value in self.to_midi_range():
            result.extend([(value >> 7) & 0x7F, value & 0x7F])
        return result


class LPD8MK2PadConfig(BaseModel):
    """Configuration for a single LPD8 MK2 pad (16 bytes in SysEx)."""
    note: int = Field(ge=0, le=127, description="MIDI note number")
    cc: int = Field(ge=0, le=127, description="CC number")
    pcn: int = Field(ge=0, le=127, description="Program change number")
    channel: int = Field(ge=0, le=15, description="MIDI channel (0-indexed)")
    off_color: LPD8MK2RGBColor = Field(description="Color when pad is off")
    on_color: LPD8MK2RGBColor = Field(description="Color when pad is on")

    def to_sysex_bytes(self) -> list[int]:
        """Generate 16-byte pad configuration for program SysEx.
        Format: [note, cc, pcn, channel, OFF_rgb(6), ON_rgb(6)]
        """
        data = [self.note, self.cc, self.pcn, self.channel]
        data.extend(self.off_color.to_sysex_bytes_split())
        data.extend(self.on_color.to_sysex_bytes_split())
        return data


class LPD8MK2KnobConfig(BaseModel):
    """Configuration for a single LPD8 MK2 knob (4 bytes in SysEx)."""
    cc: int = Field(ge=0, le=127, description="CC number")
    channel: int = Field(ge=0, le=15, description="MIDI channel (0-indexed)")
    min_value: int = Field(ge=0, le=127, default=0, description="Minimum value")
    max_value: int = Field(ge=0, le=127, default=127, description="Maximum value")

    def to_sysex_bytes(self) -> list[int]:
        """Generate 4-byte knob configuration for program SysEx.
        Format: [cc, channel, min, max]
        """
        return [self.cc, self.channel, self.min_value, self.max_value]


class LPD8MK2ProgramConfig(BaseModel):
    """Complete LPD8 MK2 program configuration (program 1-4)."""
    program_num: int = Field(ge=1, le=4, description="Program number (1-4)")
    channel: int = Field(ge=0, le=15, description="Global MIDI channel (0-indexed)")
    pressure_mode: int = Field(ge=0, le=2, default=0, description="0=off, 1=channel, 2=poly")
    full_level: int = Field(ge=0, le=1, default=1, description="0=ON(127), 1=OFF(velocity)")
    toggle_mode: bool = Field(default=True, description="True=toggle, False=momentary")
    pads: list[LPD8MK2PadConfig] = Field(min_length=8, max_length=8, description="8 pad configs")
    knobs: list[LPD8MK2KnobConfig] = Field(min_length=8, max_length=8, description="8 knob configs")

    def to_sysex_message(self) -> mido.Message:
        """Build complete Send Program SysEx message (0x01 command).
        Total: 7 (header) + 5 (settings) + 128 (pads) + 32 (knobs) = 172 bytes
        """
        # Header
        data = [
            0x47,  # Akai manufacturer
            0x7F,  # All devices
            0x4C,  # LPD8 MK2 product ID
            0x01,  # Send Program command
            0x01,  # Sub-ID 1
            0x29,  # Sub-ID 2 (program data marker)
        ]

        # Program configuration (5 bytes)
        data.extend([
            self.program_num,
            self.channel,
            self.pressure_mode,
            self.full_level,
            0x01 if self.toggle_mode else 0x00,
        ])

        # 8 pads (16 bytes each)
        for pad in self.pads:
            data.extend(pad.to_sysex_bytes())

        # 8 knobs (4 bytes each)
        for knob in self.knobs:
            data.extend(knob.to_sysex_bytes())

        return mido.Message('sysex', data=data)


class LPD8MK2LEDUpdate(BaseModel):
    """RGB LED update for all 8 pads (0x06 command)."""
    pad_colors: list[LPD8MK2RGBColor] = Field(min_length=8, max_length=8, description="8 pad colors")

    def to_sysex_message(self) -> mido.Message:
        """Build LED color update SysEx message.
        Format: F0 47 7F 4C 06 00 30 [48 bytes RGB] F7
        """
        # Header
        data = [
            0x47,  # Akai manufacturer
            0x7F,  # All devices
            0x4C,  # LPD8 MK2 product ID
            0x06,  # LED command
            0x00,  # Sub-ID 1
            0x30,  # Sub-ID 2
        ]

        # 8 pad colors (6 bytes each, MIDI range 0-127)
        for color in self.pad_colors:
            data.extend(color.to_sysex_bytes_midi())

        return mido.Message('sysex', data=data)


class AkaiLPD8MK2Plugin(ControllerPlugin):
    """
    AKAI LPD8 MK2 plugin with multi-bank and multi-signal support.

    Features:
    - 4 banks on different MIDI channels for automatic bank detection
    - 8 RGB pads per bank (configurable as TOGGLE or MOMENTARY)
    - 3 signal modes per pad: NOTE, CC, PC (hardware configurable)
    - 8 knobs per bank (continuous, read-only)
    - RGB LED feedback via SysEx
    - Automatic bank switch detection via channel monitoring
    """

    # Hardware configuration
    PAD_COUNT = 8
    KNOB_COUNT = 8
    BANK_COUNT = 4

    # MIDI configuration (factory defaults)
    PAD_START_NOTE = 36  # Note mode: Pad 1 = MIDI note 36
    PAD_CC_START = 36    # CC mode: Pad 1 = CC 36 (if configured on hardware)
    KNOB_START_CC = 1    # Knob 1 = CC 1

    # SysEx configuration
    SYSEX_MANUFACTURER = 0x47  # Akai
    SYSEX_DEVICE_ID = 0x7F     # All devices
    SYSEX_PRODUCT_ID = 0x4C    # LPD8 MK2

    # SysEx commands
    SYSEX_SEND_PROGRAM_CMD = 0x01    # Send program configuration (write)
    SYSEX_GET_PROGRAM_CMD = 0x03     # Get program configuration (read)
    SYSEX_GET_ACTIVE_PROGRAM = 0x04  # Get currently active program number
    SYSEX_GET_LED_STATE = 0x05       # Get current LED colors
    SYSEX_LED_CMD = 0x06             # Pad LED color update (write)
    SYSEX_LED_SUBID = [0x00, 0x30]

    # Bank to MIDI channel mapping (0-indexed: channel 1 = 0)
    # Programs are configured to use different channels for MIDI routing
    BANK_CHANNELS = {
        "bank_1": 0,   # Program 1 → MIDI Channel 1
        "bank_2": 1,   # Program 2 → MIDI Channel 2
        "bank_3": 2,   # Program 3 → MIDI Channel 3
        "bank_4": 3,   # Program 4 → MIDI Channel 4
    }

    def __init__(self):
        """Initialize plugin with bank tracking and LED state."""
        super().__init__()
        self._last_active_bank: Optional[str] = None
        # Track current LED colors for all 8 physical pads (R, G, B) in MIDI range 0-127
        self._current_led_colors: list[tuple[int, int, int]] = [(0, 0, 0)] * self.PAD_COUNT
        # Store callbacks for runtime queries (set in init())
        self._send_message: Optional[Callable[[mido.Message], None]] = None
        self._receive_message: Optional[Callable[[float], Optional[mido.Message]]] = None

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "AKAI LPD8 MK2"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "LPD8 mk2",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=True,            # Via active program query
            indexing_scheme="1d",                   # Linear pad/knob numbering
            supports_persistent_configuration=True, # Supports SysEx programming
            requires_initialization_handshake=False # Can query current program directly!
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 4 program banks.

        Each bank corresponds to one of the LPD8 MK2's 4 programs.
        Banks are distinguished by MIDI channel.
        """
        return [
            BankDefinition(
                bank_id=f"bank_{i}",
                control_type=ControlType.TOGGLE,  # Primary control type (pads)
                display_name=f"Bank {i}"
            )
            for i in range(1, self.BANK_COUNT + 1)
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across 4 banks.

        Creates 4 banks × (8 pads + 8 knobs) = 64 controls total.
        Pads support 3 signal modes (NOTE/CC/PC) but behavior is determined
        by control type configuration.
        """
        definitions = []

        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"

            # 8 RGB pads (configurable as TOGGLE or MOMENTARY)
            for pad_num in range(1, self.PAD_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{pad_num}@{bank_id}",
                        control_type=ControlType.TOGGLE,  # Default to TOGGLE
                        type_modes=ControlTypeModes(
                            supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                            default_type=ControlType.TOGGLE,
                            requires_hardware_sync=False,
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=True,  # CAN receive LED commands (for API use)
                            requires_feedback=False,  # Hardware manages LED state internally
                            supports_led=True,
                            supports_color=True,
                            color_mode="rgb",
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        bank_id=bank_id,
                        display_name=f"B{bank_num} Pad {pad_num}",
                        signal_types=["note", "cc", "pc"],  # Supports all 3 signal modes
                    )
                )

            # 8 knobs (continuous, read-only)
            for knob_num in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{knob_num}@{bank_id}",
                        control_type=ControlType.CONTINUOUS,
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Knobs are read-only (not motorized)
                            requires_discovery=True,  # Initial position unknown
                        ),
                        bank_id=bank_id,
                        min_value=0,
                        max_value=127,
                        display_name=f"B{bank_num} Knob {knob_num}",
                    )
                )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls with signal type routing.

        Each bank uses a different MIDI channel for distinction.
        Pads can send NOTE, CC, or PC messages depending on hardware configuration.
        All three signal types map to the same control ID but with different signal_types.

        Also includes factory default channel (9) mappings as fallback for bank_1
        in case SysEx configuration doesn't work.
        """
        mappings = []

        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"
            channel = self.BANK_CHANNELS[bank_id]

            # Pad mappings - 3 signal types per pad
            for pad_num in range(1, self.PAD_COUNT + 1):
                control_id = f"pad_{pad_num}@{bank_id}"
                midi_note = self.PAD_START_NOTE + pad_num - 1  # Notes 36-43
                midi_cc = self.PAD_CC_START + pad_num - 1       # CCs 36-43 (if configured)

                # NOTE mode (default hardware configuration)
                mappings.extend([
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_ON,
                        channel=channel,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                    MIDIMapping(
                        message_type=MIDIMessageType.NOTE_OFF,
                        channel=channel,
                        note=midi_note,
                        control_id=control_id,
                        signal_type="note",
                    ),
                ])

                # CC mode (if hardware configured to send CCs)
                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.CONTROL_CHANGE,
                        channel=channel,
                        control=midi_cc,
                        control_id=control_id,
                        signal_type="cc",
                    )
                )

                # PC mode (if hardware configured to send Program Changes)
                # Note: PC messages don't have a specific note/CC number in the mapping
                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.PROGRAM_CHANGE,
                        channel=channel,
                        control_id=control_id,
                        signal_type="pc",
                    )
                )

            # Knob mappings (always CC mode)
            for knob_num in range(1, self.KNOB_COUNT + 1):
                knob_cc = self.KNOB_START_CC + knob_num - 1  # CCs 1-8
                control_id = f"knob_{knob_num}@{bank_id}"

                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.CONTROL_CHANGE,
                        channel=channel,
                        control=knob_cc,
                        control_id=control_id,
                        signal_type="default",  # Knobs only have one signal mode
                    )
                )

        return mappings

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with robust bank detection.

        - Expected channels (0-3): Use channel for bank tracking (fast path)
        - Unexpected channels: Query 0x04 to detect bank (fallback)
        - Route all messages to _last_active_bank via custom routing

        Returns:
            (control_id, value, signal_type) or None
        """
        if hasattr(msg, 'channel'):
            channel = msg.channel
            known_channels = set(self.BANK_CHANNELS.values())

            if channel in known_channels:
                # Channel matches configured channels - use for bank tracking
                for bank_id, ch in self.BANK_CHANNELS.items():
                    if ch == channel:
                        if bank_id != self._last_active_bank:
                            logger.info(f"LPD8 MK2 bank switch: {self._last_active_bank} → {bank_id}")
                            self._last_active_bank = bank_id
                        break
            else:
                # Unexpected channel - query device for active program
                logger.debug(f"Unexpected channel {channel}, querying active program")
                if self._send_message and self._receive_message:
                    program = self._query_active_program(
                        self._send_message, self._receive_message
                    )
                    new_bank = f"bank_{program}"
                    if new_bank != self._last_active_bank:
                        logger.info(f"LPD8 MK2 bank detected via 0x04: {new_bank}")
                        self._last_active_bank = new_bank

        # Route message to active bank (custom routing, not channel-dependent)
        return self._route_to_active_bank(msg)

    def _route_to_active_bank(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Route message to control in the active bank.

        Unlike channel-based mappings, this routes based on _last_active_bank,
        making it work regardless of which channel the message arrived on.

        Args:
            msg: MIDI message to route

        Returns:
            (control_id, value, signal_type) or None if not a recognized control
        """
        if not self._last_active_bank:
            return None

        bank_id = self._last_active_bank

        # Handle note messages (pads)
        if msg.type in ('note_on', 'note_off'):
            note = msg.note
            # Check if it's a pad note (36-43)
            if self.PAD_START_NOTE <= note < self.PAD_START_NOTE + self.PAD_COUNT:
                pad_num = note - self.PAD_START_NOTE + 1
                control_id = f"pad_{pad_num}@{bank_id}"
                value = msg.velocity
                return (control_id, value, "note")

        # Handle CC messages (knobs or pads in CC mode)
        elif msg.type == 'control_change':
            cc = msg.control

            # Check if it's a knob CC (1-8)
            if self.KNOB_START_CC <= cc < self.KNOB_START_CC + self.KNOB_COUNT:
                knob_num = cc - self.KNOB_START_CC + 1
                control_id = f"knob_{knob_num}@{bank_id}"
                return (control_id, msg.value, "default")

            # Check if it's a pad CC (36-43)
            elif self.PAD_CC_START <= cc < self.PAD_CC_START + self.PAD_COUNT:
                pad_num = cc - self.PAD_CC_START + 1
                control_id = f"pad_{pad_num}@{bank_id}"
                return (control_id, msg.value, "cc")

        # Handle program change messages (pads in PC mode)
        elif msg.type == 'program_change':
            # PC messages from pads - route to active bank
            # Note: PC mode sends program numbers 0-7 for pads 1-8
            program = msg.program
            if 0 <= program < self.PAD_COUNT:
                pad_num = program + 1
                control_id = f"pad_{pad_num}@{bank_id}"
                return (control_id, 127, "pc")  # PC has no velocity, use 127

        return None

    def _query_active_program(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]]
    ) -> int:
        """
        Query device for currently active program number.

        Sends SysEx command 0x04 and parses response to determine which
        program (1-4) is currently selected on the hardware.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            Program number (1-4), defaults to 1 if query fails
        """
        # Build query: F0 47 7F 4C 04 00 00 F7
        query = mido.Message('sysex', data=[
            self.SYSEX_MANUFACTURER,
            self.SYSEX_DEVICE_ID,
            self.SYSEX_PRODUCT_ID,
            self.SYSEX_GET_ACTIVE_PROGRAM,
            0x00,
            0x00,
        ])

        logger.debug("Querying LPD8 MK2 for active program...")
        send_message(query)

        # Wait for response: F0 47 7F 4C 04 00 01 <prog> F7
        response = receive_message(0.5)  # 500ms timeout

        if response and response.type == 'sysex':
            data = list(response.data)
            # Expected: [47, 7F, 4C, 04, 00, 01, <prog>]
            if (len(data) >= 7 and
                data[0] == self.SYSEX_MANUFACTURER and
                data[2] == self.SYSEX_PRODUCT_ID and
                data[3] == self.SYSEX_GET_ACTIVE_PROGRAM):
                program = data[6]
                if 1 <= program <= 4:
                    logger.debug(f"LPD8 MK2 active program: {program}")
                    return program
                else:
                    logger.warning(f"Invalid program number in response: {program}")
            else:
                logger.warning(f"Unexpected SysEx response format: {data}")
        else:
            logger.warning("No response to active program query, defaulting to program 1")

        return 1  # Default to program 1

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]]
    ) -> None:
        """
        Initialize LPD8 MK2 to known state.

        Queries the device for the currently active program, then configures
        each of the 4 programs to use different MIDI channels via SysEx.

        Bank/Channel mapping:
        - Bank 1 (Program 1) → MIDI Channel 1
        - Bank 2 (Program 2) → MIDI Channel 2
        - Bank 3 (Program 3) → MIDI Channel 3
        - Bank 4 (Program 4) → MIDI Channel 4

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout
        """
        logger.info("Initializing AKAI LPD8 MK2")

        # Store callbacks for runtime queries in translate_input()
        self._send_message = send_message
        self._receive_message = receive_message

        # Query current program FIRST (before reconfiguration)
        program = self._query_active_program(send_message, receive_message)
        self._last_active_bank = f"bank_{program}"
        logger.info(f"LPD8 MK2 active program: {program} ({self._last_active_bank})")

        # Configure each program to use a different MIDI channel
        # This allows automatic bank detection based on the channel of incoming messages
        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"
            channel = self.BANK_CHANNELS[bank_id]

            logger.debug(f"Configuring {bank_id} to MIDI channel {channel + 1} via SysEx")

            # Build program configuration SysEx with defaults
            # Actual config colors will be programmed by configure_programs() after init
            program_sysex = self._build_program_config_sysex(
                program_num=bank_num,
                channel=channel,
                bank_config=None  # Use defaults during init
            )
            send_message(program_sysex)

            # Give device time to process the configuration
            time.sleep(0.1)  # 100ms delay

        logger.info("LPD8 MK2 initialization complete")

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence for LPD8 MK2.

        Restores factory default configuration to all 4 programs,
        ensuring device is in a known state for next connection.
        """
        logger.info("Shutting down AKAI LPD8 MK2 - restoring factory defaults")

        for program in self._get_factory_defaults():
            logger.debug(
                f"Restoring Program {program.program_num} to factory defaults: "
                f"channel {program.channel + 1}, "
                f"{'TOGGLE' if program.toggle_mode else 'MOMENTARY'} mode"
            )
            send_message(program.to_sysex_message())
            time.sleep(0.1)

        logger.info("LPD8 MK2 shutdown complete: factory defaults restored")

    def validate_bank_config(
        self,
        bank_id: str,
        bank_config: 'BankConfig',
        strict_mode: bool = True
    ) -> None:
        """
        Validate toggle_mode consistency for LPD8 MK2.

        The LPD8 MK2 applies toggle mode globally per bank (all 8 pads share the same
        toggle/momentary setting). If the user specifies bank-level toggle_mode,
        any pad-level type configs that conflict will be warned about (permissive)
        or rejected (strict).

        Args:
            bank_id: Bank identifier
            bank_config: Bank configuration to validate
            strict_mode: If True, raise on conflicts. If False, warn only.

        Raises:
            ConfigurationError: In strict mode, if pad types conflict with toggle_mode
        """
        from ..config import ConfigurationError

        if bank_config.toggle_mode is None:
            return  # No explicit setting, skip validation

        expected_type = ControlType.TOGGLE if bank_config.toggle_mode else ControlType.MOMENTARY

        for control_id, control_config in bank_config.controls.items():
            if not control_id.startswith("pad_"):
                continue
            if control_config.type and control_config.type != expected_type:
                msg = (
                    f"Bank '{bank_id}' has toggle_mode={bank_config.toggle_mode} "
                    f"but '{control_id}' is configured as {control_config.type.value}. "
                    f"LPD8 MK2 applies toggle mode globally per bank - "
                    f"pad type setting will be ignored."
                )
                if strict_mode:
                    raise ConfigurationError(msg)
                else:
                    logger.warning(msg)

    def configure_programs(
        self,
        send_message: Callable[[mido.Message], None],
        config: 'ControllerConfig'
    ) -> None:
        """
        Program all 4 LPD8 MK2 programs with persistent configuration.

        Writes user configuration (colors, control types, channels, etc.) to
        device non-volatile memory. Configuration persists across program switches
        and potentially power cycles.

        This method is called after init() to write actual config values, allowing
        init() to focus on hardware setup (clearing, resetting).

        Args:
            send_message: Function to send MIDI messages
            config: Full controller configuration with resolved settings
        """
        from ..config import ControllerConfig

        if not config or not config.banks:
            logger.debug("No configuration provided, using defaults")
            return

        logger.info("Programming LPD8 MK2 device memory with configuration")

        # Configure each of the 4 programs
        for program_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{program_num}"
            channel = self.BANK_CHANNELS[bank_id]

            # Get bank config if available
            bank_config = config.banks.get(bank_id) if config.banks else None

            # Log what we're configuring
            if bank_config:
                color_count = sum(
                    1 for ctrl_id, ctrl_cfg in bank_config.controls.items()
                    if ctrl_id.startswith("pad_") and ctrl_cfg.color
                )
                logger.info(
                    f"Configuring Program {program_num}: "
                    f"channel {channel + 1}, {color_count} pad colors"
                )
            else:
                logger.info(f"Configuring Program {program_num}: channel {channel + 1} (defaults)")

            # Build and send program configuration with config data
            program_sysex = self._build_program_config_sysex(
                program_num=program_num,
                channel=channel,
                bank_config=bank_config
            )
            send_message(program_sysex)

            # Give device time to process (100ms per program)
            time.sleep(0.1)

        # Immediately apply LED colors for the active program using direct update
        # (otherwise user has to switch programs for changes to be visible)
        if self._last_active_bank:
            active_bank_config = config.banks.get(self._last_active_bank) if config.banks else None
            self._apply_led_colors_directly(send_message, active_bank_config)

        logger.info("LPD8 MK2 program configuration complete")

    def translate_feedback(
        self,
        control_id: str,
        state_dict: dict,
    ) -> list[mido.Message]:
        """
        Translate control state to RGB LED feedback.

        For LPD8 MK2, only pads support visual feedback via RGB LEDs.
        Knobs are read-only with no feedback capability.

        Maintains internal state of all pad colors to ensure that updating
        one pad doesn't turn off the others (since SysEx updates all 8 pads).

        Args:
            control_id: Control being updated
            state_dict: New state (is_on, value, color, etc.)

        Returns:
            List of MIDI messages (SysEx for RGB LEDs)
        """
        # Only handle pad feedback (knobs don't support feedback)
        if not control_id.startswith("pad_"):
            return []

        # Extract pad number from control_id (e.g., "pad_3@bank_1" → 3)
        try:
            pad_str = control_id.split("_")[1].split("@")[0]
            pad_num = int(pad_str)
        except (IndexError, ValueError) as e:
            logger.error(f"Invalid control_id format: {control_id} ({e})")
            return []

        if not (1 <= pad_num <= self.PAD_COUNT):
            logger.warning(f"Pad number {pad_num} out of range (1-{self.PAD_COUNT})")
            return []

        # Start with current LED state (preserves other pads' colors)
        rgb_values = list(self._current_led_colors)

        # Determine new color for this pad based on state
        is_on = state_dict.get('is_on', False)
        color = state_dict.get('color')

        if is_on and color:
            rgb_color = LPD8MK2RGBColor.from_string(color)
        elif color:
            # Color is set but pad is off - still update stored color for when it turns on
            rgb_color = LPD8MK2RGBColor.from_string(color)
        else:
            rgb_color = LPD8MK2RGBColor(r=0, g=0, b=0)  # Off (black)

        # Convert to MIDI range (0-127) for internal state tracking
        rgb_midi = rgb_color.to_midi_range()

        # Update this pad's color in our state
        rgb_values[pad_num - 1] = rgb_midi
        self._current_led_colors[pad_num - 1] = rgb_midi

        # Build and return SysEx message with all 8 pad colors
        return [self._build_rgb_sysex(rgb_values)]

    def _build_rgb_sysex(self, rgb_data: list[tuple[int, int, int]]) -> mido.Message:
        """
        Build SysEx message for RGB LED control using Pydantic models.

        Args:
            rgb_data: List of 8 (R, G, B) tuples, values 0-127 (MIDI range)

        Returns:
            SysEx MIDI message
        """
        # Convert MIDI range tuples to LPD8MK2RGBColor objects
        colors = [
            LPD8MK2RGBColor.from_midi_values(r, g, b)
            for r, g, b in rgb_data
        ]

        led_update = LPD8MK2LEDUpdate(pad_colors=colors)
        return led_update.to_sysex_message()

    def _get_pad_colors_for_bank(
        self,
        bank_config: Optional['BankConfig']
    ) -> list[tuple[LPD8MK2RGBColor, LPD8MK2RGBColor]]:
        """
        Extract 8 pad colors from bank config with defaults.

        For each pad (1-8):
        - Look up control config for pad_N
        - Extract ON color (or use default)
        - Derive OFF color (black by default, per user requirement)
        - Return as LPD8MK2RGBColor objects (0-255 range)

        Args:
            bank_config: Bank configuration, or None for defaults

        Returns:
            List of 8 (off_color, on_color) tuples as LPD8MK2RGBColor objects
        """
        colors = []

        for pad_num in range(1, self.PAD_COUNT + 1):
            pad_id = f"pad_{pad_num}"

            # Default colors
            off_color = LPD8MK2RGBColor(r=0, g=0, b=0)  # Black (OFF state)
            on_color = LPD8MK2RGBColor(r=0, g=128, b=255)  # Bright blue (ON state)

            # Extract colors from config if available
            if bank_config and bank_config.controls:
                control_config = bank_config.controls.get(pad_id)
                if control_config and control_config.color:
                    # Parse ON color from config
                    on_color = LPD8MK2RGBColor.from_string(control_config.color)

                    # OFF color: use dimmed version of ON color (25% brightness)
                    off_color = LPD8MK2RGBColor(r=on_color.r // 4, g=on_color.g // 4, b=on_color.b // 4)

            colors.append((off_color, on_color))

        return colors

    def _get_control_types_for_bank(
        self,
        bank_config: Optional['BankConfig']
    ) -> bool:
        """
        Get toggle mode for bank.

        Returns the bank-level toggle_mode setting if explicitly set,
        otherwise defaults to True (toggle mode).

        Note: LPD8 MK2 applies toggle mode globally per bank (all 8 pads).
        Use BankConfig.toggle_mode to set this explicitly.

        Args:
            bank_config: Bank configuration, or None for defaults

        Returns:
            True for toggle mode, False for momentary mode
        """
        if bank_config and bank_config.toggle_mode is not None:
            return bank_config.toggle_mode
        return True  # Default: toggle mode

    def _apply_led_colors_directly(
        self,
        send_message: Callable[[mido.Message], None],
        bank_config: Optional['BankConfig']
    ) -> None:
        """
        Send direct LED update to immediately show colors for a bank.

        Uses command 0x06 to update LEDs without requiring program switch.
        Pads start in OFF state, so we apply OFF colors initially.

        Args:
            send_message: Function to send MIDI messages
            bank_config: Bank configuration to get colors from
        """
        # Get pad colors (off_color, on_color tuples)
        pad_colors = self._get_pad_colors_for_bank(bank_config)

        # Use OFF colors since pads start in off state
        off_colors = [off_color for off_color, on_color in pad_colors]

        # Build and send direct LED update
        led_update = LPD8MK2LEDUpdate(pad_colors=off_colors)
        send_message(led_update.to_sysex_message())

        # Update internal LED state tracking
        self._current_led_colors = [
            color.to_midi_range() for color in off_colors
        ]

        logger.debug("Applied LED colors directly via command 0x06")

    def _get_factory_defaults(self) -> list[LPD8MK2ProgramConfig]:
        """
        Get factory default program configurations.

        Returns:
            List of 4 LPD8MK2ProgramConfig objects for programs 1-4
        """
        factory_channel = 9  # Channel 10

        def make_program(
            num: int,
            toggle: bool,
            off: tuple[int, int, int],
            on: tuple[int, int, int]
        ) -> LPD8MK2ProgramConfig:
            pads = [
                LPD8MK2PadConfig(
                    note=self.PAD_START_NOTE + i,
                    cc=self.PAD_CC_START + i,
                    pcn=i,
                    channel=factory_channel,
                    off_color=LPD8MK2RGBColor(r=off[0], g=off[1], b=off[2]),
                    on_color=LPD8MK2RGBColor(r=on[0], g=on[1], b=on[2]),
                )
                for i in range(self.PAD_COUNT)
            ]
            knobs = [
                LPD8MK2KnobConfig(
                    cc=self.KNOB_START_CC + i,
                    channel=factory_channel,
                )
                for i in range(self.KNOB_COUNT)
            ]
            return LPD8MK2ProgramConfig(
                program_num=num,
                channel=factory_channel,
                toggle_mode=toggle,
                pads=pads,
                knobs=knobs,
            )

        return [
            make_program(1, False, (255, 0, 0), (0, 0, 255)),      # red/blue, MOMENTARY
            make_program(2, False, (0, 255, 0), (0, 0, 255)),      # green/blue, MOMENTARY
            make_program(3, False, (0, 255, 255), (255, 0, 255)),  # cyan/magenta, MOMENTARY
            make_program(4, True, (0, 0, 0), (255, 255, 255)),     # black/white, TOGGLE
        ]

    def _build_program_config_sysex(
        self,
        program_num: int,
        channel: int,
        bank_config: Optional['BankConfig'] = None
    ) -> mido.Message:
        """
        Build SysEx message to configure a program using Pydantic models.

        This configures a specific program (1-4) with pads and knobs set to use
        the given MIDI channel, along with colors and control settings.

        Args:
            program_num: Program number (1-4)
            channel: MIDI channel (0-15, where 0 = channel 1)
            bank_config: Optional bank configuration to extract colors and settings from

        Returns:
            SysEx message
        """
        # Extract colors and settings from config
        pad_colors = self._get_pad_colors_for_bank(bank_config)
        toggle_mode = self._get_control_types_for_bank(bank_config)

        # Build pad configs
        pads = []
        for pad_idx in range(self.PAD_COUNT):
            off_color, on_color = pad_colors[pad_idx]
            pads.append(LPD8MK2PadConfig(
                note=self.PAD_START_NOTE + pad_idx,
                cc=self.PAD_CC_START + pad_idx,
                pcn=pad_idx,
                channel=channel,
                off_color=off_color,
                on_color=on_color,
            ))

        # Build knob configs
        knobs = []
        for knob_idx in range(self.KNOB_COUNT):
            knobs.append(LPD8MK2KnobConfig(
                cc=self.KNOB_START_CC + knob_idx,
                channel=channel,
                min_value=0,
                max_value=127,
            ))

        # Create program config and serialize
        program = LPD8MK2ProgramConfig(
            program_num=program_num,
            channel=channel,
            toggle_mode=toggle_mode,
            pads=pads,
            knobs=knobs,
        )

        return program.to_sysex_message()
