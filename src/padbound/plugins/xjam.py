"""
Xjam MIDI Controller Plugin.

ESI Audiotechnik / Artesia Pro Xjam MIDI Performance Controller

Hardware specifications:
- 16 pressure-sensitive drum pads × 3 banks (48 total)
- 6 endless rotary encoders × 3 banks (18 total)
- Separate pad/knob bank switching (synchronized in this plugin)
- Global toggle/momentary mode for all pads
- SysEx-based configuration
- No LED feedback capability (controller manages its own LEDs)
- USB MIDI interface

Control features:
- Pads configurable as TOGGLE or MOMENTARY (global per device)
- Pads can send NOTE (default), CC, PC, or MMC messages
- Knobs can send CC, Pitch Bend, PC, or Aftertouch messages
- Encoder modes: Absolute, Relative 2s Comp, Relative Bin Offset, Relative Signed Bit
- 3 banks for both pads and knobs (Green, Yellow, Red)

================================================================================
SYSEX PROTOCOL DOCUMENTATION
================================================================================

All SysEx messages use the following header format:
    F0 00 20 54 30 <cmd> [payload...] F7

Where:
    F0          = SysEx start
    00 20 54    = ESI/Artesia manufacturer ID
    30          = Device ID (Xjam)
    <cmd>       = Command byte
    [payload]   = Command-specific data
    F7          = SysEx end

--------------------------------------------------------------------------------
COMMAND 0x10: WRITE CONFIGURATION
--------------------------------------------------------------------------------
Writes configuration to an element (pad, knob, or global setting).

Pad Configuration (Type 07):
    F0 00 20 54 30 10 <pad_id> 07 <mode> <note> <channel> 00 00 00 00 F7

    pad_id      = Element ID (01-30 across 3 banks)
    mode        = 00=note, 01=CC, 02=PC, 03=MMC
    note        = MIDI note/CC/PC/MMC number (0-127)
    channel     = 00=global, 01-10=channel 1-16

Knob Configuration (Type 03):
    F0 00 20 54 30 10 <knob_id> 03 <msg_type> <cc_num> <mode_ch> F7

    knob_id     = Element ID (31-42 across 3 banks)
    msg_type    = 04=CC, 05=Pitch, 06=PC, 07=Aftertouch
    cc_num      = CC number (for CC mode)
    mode_ch     = Encoder mode (bits 5-6) + channel (bits 0-4)

Boolean Flag (Type 01):
    F0 00 20 54 30 10 <element> 01 <value> F7

    element 43  = Aftertouch mode (00=off, 01=channel, 02=poly)
    element 44  = Note toggle mode (00=momentary, 01=toggle)

--------------------------------------------------------------------------------
GLOBAL COMMANDS
--------------------------------------------------------------------------------

Set Active Pad Bank:
    F0 00 20 54 30 00 09 <bank> F7
    bank = 00 (Green), 01 (Yellow), 02 (Red)

Set Active Ctrl Bank:
    F0 00 20 54 30 00 0A <bank> F7

Global Commit (apply changes):
    F0 00 20 54 30 00 70 07 01 40 00 00 00 00 00 F7

--------------------------------------------------------------------------------
CONFIG MODE
--------------------------------------------------------------------------------

Enter Config Mode:
    F0 00 20 54 30 7B 01 F7
    F0 00 20 54 02 01 F7

Exit Config Mode:
    F0 00 20 54 30 7B 00 F7
    F0 00 20 54 02 01 F7

Acknowledgment (device response):
    F0 00 20 54 30 7C F7

================================================================================
ELEMENT ID MAPPING
================================================================================

Pads (48 total across 3 banks):
    Bank 1 (Green):  01-10 (hex) = Pads 1-16
    Bank 2 (Yellow): 11-20 (hex) = Pads 1-16
    Bank 3 (Red):    21-30 (hex) = Pads 1-16

Knobs (18 total across 3 banks):
    Bank 1 (Green):  31-36 (hex) = Knobs 1-6
    Bank 2 (Yellow): 37-3C (hex) = Knobs 1-6
    Bank 3 (Red):    3D-42 (hex) = Knobs 1-6

Global Settings:
    43 = Aftertouch mode
    44 = Toggle mode (global for all pads)
    70 = Global commit

================================================================================
DEFAULT MIDI MAPPINGS (Factory)
================================================================================

Bank 1 Pads (notes, non-sequential drum layout):
    Pad 1-8:  35, 37, 39, 40, 42, 44, 46, 48
    Pad 9-16: 36, 38, 41, 43, 45, 47, 49, 51

Bank 1 Knobs:
    Knob 1-6: CC 28-33, Channel 4

================================================================================
References:
- Protocol reverse-engineered from Xjam Editor software captures
================================================================================
"""

import time
from typing import Callable, Optional

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
    ControlTypeModes,
    ControlCapabilities,
    ControllerCapabilities,
    BankDefinition,
)
from ..logging_config import get_logger

logger = get_logger(__name__)


# =============================================================================
# SysEx Protocol Constants
# =============================================================================

class XjamSysEx:
    """SysEx protocol constants for Xjam."""

    # Manufacturer and device IDs
    MANUFACTURER_ID = [0x00, 0x20, 0x54]
    DEVICE_ID = 0x30
    HEADER = MANUFACTURER_ID + [DEVICE_ID]

    # Command bytes
    CMD_WRITE = 0x10           # Write configuration to element
    CMD_GLOBAL = 0x00          # Global commands (bank selection, commit)
    CMD_CONFIG_MODE = 0x7B     # Enter/exit config mode
    CMD_HANDSHAKE = 0x02       # Handshake for config mode
    CMD_ACK = 0x7C             # Acknowledgment from device

    # Message types
    TYPE_PAD = 0x07            # Pad configuration (7 data bytes)
    TYPE_KNOB = 0x03           # Knob configuration (3 data bytes)
    TYPE_BOOL = 0x01           # Boolean flag (1 data byte)

    # Global command sub-IDs
    GLOBAL_PAD_BANK = 0x09     # Set active pad bank
    GLOBAL_CTRL_BANK = 0x0A    # Set active ctrl/knob bank
    GLOBAL_COMMIT = 0x70       # Apply configuration changes

    # Element IDs
    ELEMENT_AFTERTOUCH = 0x43  # Aftertouch mode setting
    ELEMENT_TOGGLE = 0x44      # Toggle mode setting (global)

    # Pad modes
    PAD_MODE_NOTE = 0x00
    PAD_MODE_CC = 0x01
    PAD_MODE_PC = 0x02
    PAD_MODE_MMC = 0x03

    # Knob message types
    KNOB_MSG_CC = 0x04
    KNOB_MSG_PITCH = 0x05
    KNOB_MSG_PC = 0x06
    KNOB_MSG_AFTERTOUCH = 0x07

    # Encoder modes (encoded in bits 5-6 of mode_channel byte)
    ENCODER_ABSOLUTE = 0x00        # Direct value mapping
    ENCODER_REL_2S_COMP = 0x20     # Relative 2s complement
    ENCODER_REL_BIN_OFFSET = 0x40  # Relative binary offset
    ENCODER_REL_SIGNED_BIT = 0x60  # Relative signed bit

    # Aftertouch modes
    AFTERTOUCH_OFF = 0x00
    AFTERTOUCH_CHANNEL = 0x01
    AFTERTOUCH_POLY = 0x02


# =============================================================================
# Pydantic Models for SysEx Messages
# =============================================================================

class XjamPadConfig(BaseModel):
    """Configuration for a single Xjam pad.

    Generates SysEx message for pad configuration (element 01-30).
    """

    element_id: int = Field(ge=0x01, le=0x30, description="Pad element ID")
    mode: int = Field(ge=0, le=3, default=0, description="Pad mode: 0=note, 1=CC, 2=PC, 3=MMC")
    note: int = Field(ge=0, le=127, default=36, description="MIDI note/CC/PC/MMC number")
    channel: int = Field(ge=0, le=16, default=0, description="MIDI channel: 0=global, 1-16=specific")

    def to_sysex_message(self) -> mido.Message:
        """Build SysEx message for pad configuration.

        Format: F0 00 20 54 30 10 <element> 07 <mode> <note> <channel> 00 00 00 00 F7
        """
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_WRITE,
            self.element_id,
            XjamSysEx.TYPE_PAD,
            self.mode,
            self.note,
            self.channel,
            0x00, 0x00, 0x00, 0x00,  # Reserved padding
        ]
        return mido.Message('sysex', data=data)


class XjamKnobConfig(BaseModel):
    """Configuration for a single Xjam knob/encoder.

    Generates SysEx message for knob configuration (element 31-42).
    """

    element_id: int = Field(ge=0x31, le=0x42, description="Knob element ID")
    msg_type: int = Field(ge=4, le=7, default=4, description="Message type: 4=CC, 5=Pitch, 6=PC, 7=AT")
    cc_num: int = Field(ge=0, le=127, default=0, description="CC number (for CC mode)")
    encoder_mode: int = Field(ge=0, le=3, default=0, description="Encoder mode: 0=abs, 1=rel2s, 2=relbin, 3=relsig")
    channel: int = Field(ge=0, le=15, default=0, description="MIDI channel (0-indexed)")

    def to_sysex_message(self) -> mido.Message:
        """Build SysEx message for knob configuration.

        Format: F0 00 20 54 30 10 <element> 03 <msg_type> <cc_num> <mode_ch> F7

        mode_ch encodes both encoder mode (bits 5-6) and channel (bits 0-4).
        """
        # Encode mode and channel into single byte
        mode_channel = (self.encoder_mode << 5) | (self.channel & 0x0F)

        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_WRITE,
            self.element_id,
            XjamSysEx.TYPE_KNOB,
            self.msg_type,
            self.cc_num,
            mode_channel,
        ]
        return mido.Message('sysex', data=data)


class XjamGlobalConfig(BaseModel):
    """Global configuration settings for Xjam.

    Handles aftertouch mode and toggle mode settings.
    """

    aftertouch_mode: int = Field(ge=0, le=2, default=0, description="0=off, 1=channel, 2=poly")
    toggle_mode: bool = Field(default=True, description="True=toggle, False=momentary")

    def to_sysex_messages(self) -> list[mido.Message]:
        """Build SysEx messages for global settings.

        Returns list of messages for aftertouch and toggle mode.
        """
        messages = []

        # Aftertouch setting
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_WRITE,
            XjamSysEx.ELEMENT_AFTERTOUCH,
            XjamSysEx.TYPE_BOOL,
            self.aftertouch_mode,
        ]
        messages.append(mido.Message('sysex', data=data))

        # Toggle mode setting
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_WRITE,
            XjamSysEx.ELEMENT_TOGGLE,
            XjamSysEx.TYPE_BOOL,
            0x01 if self.toggle_mode else 0x00,
        ]
        messages.append(mido.Message('sysex', data=data))

        return messages


class XjamBankSelect(BaseModel):
    """Bank selection command for Xjam."""

    bank: int = Field(ge=0, le=2, description="Bank number: 0=Green, 1=Yellow, 2=Red")

    def to_pad_bank_message(self) -> mido.Message:
        """Build SysEx message to set active pad bank."""
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_GLOBAL,
            XjamSysEx.GLOBAL_PAD_BANK,
            self.bank,
        ]
        return mido.Message('sysex', data=data)

    def to_ctrl_bank_message(self) -> mido.Message:
        """Build SysEx message to set active ctrl/knob bank."""
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_GLOBAL,
            XjamSysEx.GLOBAL_CTRL_BANK,
            self.bank,
        ]
        return mido.Message('sysex', data=data)


class XjamConfigMode(BaseModel):
    """Config mode control for Xjam."""

    enter: bool = Field(description="True to enter config mode, False to exit")

    def to_sysex_messages(self) -> list[mido.Message]:
        """Build SysEx messages to enter/exit config mode.

        Config mode requires two messages: mode switch and handshake.
        """
        messages = []

        # Config mode switch
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_CONFIG_MODE,
            0x01 if self.enter else 0x00,
        ]
        messages.append(mido.Message('sysex', data=data))

        # Handshake (same for enter and exit)
        data = XjamSysEx.MANUFACTURER_ID + [
            XjamSysEx.CMD_HANDSHAKE,
            0x01,
        ]
        messages.append(mido.Message('sysex', data=data))

        return messages


class XjamGlobalCommit(BaseModel):
    """Global commit command to apply configuration changes."""

    def to_sysex_message(self) -> mido.Message:
        """Build SysEx message for global commit.

        Format: F0 00 20 54 30 00 70 07 01 40 00 00 00 00 00 F7
        """
        data = XjamSysEx.HEADER + [
            XjamSysEx.CMD_GLOBAL,
            XjamSysEx.GLOBAL_COMMIT,
            0x07, 0x01, 0x40, 0x00, 0x00, 0x00, 0x00, 0x00,
        ]
        return mido.Message('sysex', data=data)


# =============================================================================
# Plugin Implementation
# =============================================================================

class XjamPlugin(ControllerPlugin):
    """
    Xjam MIDI Controller plugin.

    Features:
    - 16 pads × 3 banks (48 total) with configurable modes
    - 6 knobs × 3 banks (18 total) with multiple encoder modes
    - Synchronized pad/knob bank switching
    - Global toggle/momentary mode for all pads
    - SysEx-based persistent configuration
    - No LED feedback (controller manages its own LEDs)
    """

    # Hardware configuration
    PAD_COUNT = 16
    KNOB_COUNT = 6
    BANK_COUNT = 3

    # Element ID ranges for each bank (pad and knob)
    # Bank index: (pad_start, pad_end, knob_start, knob_end)
    BANK_ELEMENTS = {
        0: (0x01, 0x10, 0x31, 0x36),  # Bank 1 (Green)
        1: (0x11, 0x20, 0x37, 0x3C),  # Bank 2 (Yellow)
        2: (0x21, 0x30, 0x3D, 0x42),  # Bank 3 (Red)
    }

    # Bank to MIDI channel mapping (0-indexed)
    # We configure each bank to use a different channel for automatic detection
    BANK_CHANNELS = {
        "bank_1": 0,  # Channel 1
        "bank_2": 1,  # Channel 2
        "bank_3": 2,  # Channel 3
    }

    # Default pad note assignments (factory default - non-sequential drum layout)
    # Pad numbers 1-16 map to these MIDI notes
    DEFAULT_PAD_NOTES = [
        35, 37, 39, 40, 42, 44, 46, 48,  # Pads 1-8
        36, 38, 41, 43, 45, 47, 49, 51,  # Pads 9-16
    ]

    # Default knob CC assignments (factory default)
    # Knobs 1-6 map to CCs 28-33
    DEFAULT_KNOB_CCS = [28, 29, 30, 31, 32, 33]

    def __init__(self):
        """Initialize plugin with bank tracking."""
        super().__init__()
        self._last_active_bank: Optional[str] = None
        # Track callbacks for runtime queries
        self._send_message: Optional[Callable[[mido.Message], None]] = None
        self._receive_message: Optional[Callable[[float], Optional[mido.Message]]] = None

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "Xjam"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return [
            "ESI Xjam",
            "Xjam",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # No automatic bank feedback
            indexing_scheme="1d",          # Linear pad/knob numbering
            supports_persistent_configuration=True,  # SysEx programming supported
            requires_initialization_handshake=False,  # We configure channels for detection
        )

    def get_bank_definitions(self) -> list[BankDefinition]:
        """
        Define 3 banks (synchronized pad and knob banks).

        Banks are color-coded matching the hardware:
        - Bank 1: Green
        - Bank 2: Yellow
        - Bank 3: Red
        """
        return [
            BankDefinition(
                bank_id="bank_1",
                control_type=ControlType.TOGGLE,
                display_name="Bank 1 (Green)"
            ),
            BankDefinition(
                bank_id="bank_2",
                control_type=ControlType.TOGGLE,
                display_name="Bank 2 (Yellow)"
            ),
            BankDefinition(
                bank_id="bank_3",
                control_type=ControlType.TOGGLE,
                display_name="Bank 3 (Red)"
            ),
        ]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls across 3 banks.

        Creates 3 banks × (16 pads + 6 knobs) = 66 controls total.
        """
        definitions = []

        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"

            # 16 pads per bank (configurable as TOGGLE or MOMENTARY)
            for pad_num in range(1, self.PAD_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"pad_{pad_num}@{bank_id}",
                        control_type=ControlType.TOGGLE,  # Default to TOGGLE
                        category="pad",
                        type_modes=ControlTypeModes(
                            supported_types=[ControlType.TOGGLE, ControlType.MOMENTARY],
                            default_type=ControlType.TOGGLE,
                            requires_hardware_sync=True,  # Global toggle requires SysEx
                        ),
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # No LED control from software
                            requires_feedback=False,
                            supports_led=False,
                            supports_color=False,
                            requires_discovery=False,  # Pads report state immediately
                        ),
                        bank_id=bank_id,
                        display_name=f"B{bank_num} Pad {pad_num}",
                        signal_types=["note", "cc", "pc"],  # Note, CC, PC modes
                    )
                )

            # 6 knobs per bank (continuous, read-only)
            for knob_num in range(1, self.KNOB_COUNT + 1):
                definitions.append(
                    ControlDefinition(
                        control_id=f"knob_{knob_num}@{bank_id}",
                        control_type=ControlType.CONTINUOUS,
                        category="knob",
                        capabilities=ControlCapabilities(
                            supports_feedback=False,  # Knobs are read-only
                            requires_feedback=False,
                            requires_discovery=True,  # Initial position unknown
                        ),
                        bank_id=bank_id,
                        min_value=0,
                        max_value=127,
                        display_name=f"B{bank_num} Knob {knob_num}",
                        signal_types=["cc", "pitch", "pc", "aftertouch"],
                    )
                )

        return definitions

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Map MIDI input to controls.

        Each bank uses a different MIDI channel for automatic bank detection:
        - Bank 1: Channel 1 (index 0)
        - Bank 2: Channel 2 (index 1)
        - Bank 3: Channel 3 (index 2)

        Pads can send NOTE, CC, or PC messages.
        Knobs can send CC, Pitch Bend, PC, or Aftertouch messages.
        """
        mappings = []

        for bank_num in range(1, self.BANK_COUNT + 1):
            bank_id = f"bank_{bank_num}"
            channel = self.BANK_CHANNELS[bank_id]

            # Pad mappings - NOTE mode (default)
            for pad_num in range(1, self.PAD_COUNT + 1):
                control_id = f"pad_{pad_num}@{bank_id}"
                midi_note = self.DEFAULT_PAD_NOTES[pad_num - 1]

                # Note On/Off mappings
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

                # CC mode mapping (if pads configured for CC)
                # Use same note number as CC number for CC mode
                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.CONTROL_CHANGE,
                        channel=channel,
                        control=midi_note,  # CC number matches note in CC mode
                        control_id=control_id,
                        signal_type="cc",
                    )
                )

                # PC mode mapping
                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.PROGRAM_CHANGE,
                        channel=channel,
                        control_id=control_id,
                        signal_type="pc",
                    )
                )

            # Knob mappings - CC mode (default)
            for knob_num in range(1, self.KNOB_COUNT + 1):
                control_id = f"knob_{knob_num}@{bank_id}"
                knob_cc = self.DEFAULT_KNOB_CCS[knob_num - 1]

                # CC mode (default)
                mappings.append(
                    MIDIMapping(
                        message_type=MIDIMessageType.CONTROL_CHANGE,
                        channel=channel,
                        control=knob_cc,
                        control_id=control_id,
                        signal_type="cc",
                    )
                )

            # Pitch bend mapping for all knobs (when configured for pitch)
            # Note: Pitch bend is channel-wide, so we map to knob_1 by default
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.PITCHWHEEL,
                    channel=channel,
                    control_id=f"knob_1@{bank_id}",
                    signal_type="pitch",
                )
            )

            # Aftertouch mapping (when configured)
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.AFTERTOUCH,
                    channel=channel,
                    control_id=f"knob_1@{bank_id}",
                    signal_type="aftertouch",
                )
            )

        return mappings

    def init(
        self,
        send_message: Callable[[mido.Message], None],
        receive_message: Callable[[float], Optional[mido.Message]] = None
    ) -> dict[str, int]:
        """
        Initialize Xjam to known state.

        Configures all 3 banks to use different MIDI channels (1-3) for
        automatic bank detection via channel monitoring.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            Empty dict (no values to discover - no LED state to read)
        """
        logger.info("Initializing Xjam")

        # Store callbacks for runtime queries
        self._send_message = send_message
        self._receive_message = receive_message

        # Enter config mode
        config_mode = XjamConfigMode(enter=True)
        for msg in config_mode.to_sysex_messages():
            send_message(msg)
            time.sleep(0.05)  # 50ms delay for device processing

        # Set both banks to bank 1 (synchronized)
        bank_select = XjamBankSelect(bank=0)
        send_message(bank_select.to_pad_bank_message())
        time.sleep(0.05)
        send_message(bank_select.to_ctrl_bank_message())
        time.sleep(0.05)

        # Configure all pads across all banks to use bank-specific channels
        for bank_idx in range(self.BANK_COUNT):
            bank_id = f"bank_{bank_idx + 1}"
            channel = self.BANK_CHANNELS[bank_id]
            pad_start, pad_end, knob_start, knob_end = self.BANK_ELEMENTS[bank_idx]

            logger.debug(f"Configuring {bank_id} pads to channel {channel + 1}")

            # Configure pads for this bank
            for pad_idx in range(self.PAD_COUNT):
                element_id = pad_start + pad_idx
                midi_note = self.DEFAULT_PAD_NOTES[pad_idx]

                pad_config = XjamPadConfig(
                    element_id=element_id,
                    mode=XjamSysEx.PAD_MODE_NOTE,
                    note=midi_note,
                    channel=channel + 1,  # Protocol uses 1-indexed channels
                )
                send_message(pad_config.to_sysex_message())
                time.sleep(0.02)  # 20ms between messages

            logger.debug(f"Configuring {bank_id} knobs to channel {channel + 1}")

            # Configure knobs for this bank
            for knob_idx in range(self.KNOB_COUNT):
                element_id = knob_start + knob_idx
                knob_cc = self.DEFAULT_KNOB_CCS[knob_idx]

                knob_config = XjamKnobConfig(
                    element_id=element_id,
                    msg_type=XjamSysEx.KNOB_MSG_CC,
                    cc_num=knob_cc,
                    encoder_mode=0,  # Absolute mode
                    channel=channel,  # Protocol uses 0-indexed channels here
                )
                send_message(knob_config.to_sysex_message())
                time.sleep(0.02)

        # Set global settings (toggle mode enabled by default)
        global_config = XjamGlobalConfig(
            aftertouch_mode=XjamSysEx.AFTERTOUCH_OFF,
            toggle_mode=True,
        )
        for msg in global_config.to_sysex_messages():
            send_message(msg)
            time.sleep(0.02)

        # Commit all changes
        commit = XjamGlobalCommit()
        send_message(commit.to_sysex_message())
        time.sleep(0.1)  # 100ms for commit processing

        # Exit config mode
        config_mode = XjamConfigMode(enter=False)
        for msg in config_mode.to_sysex_messages():
            send_message(msg)
            time.sleep(0.05)

        # Set initial active bank
        self._last_active_bank = "bank_1"

        logger.info("Xjam initialization complete")
        return {}

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence for Xjam.

        Exits config mode if active (safety measure).
        """
        logger.info("Shutting down Xjam")

        # Exit config mode (in case it was left active)
        config_mode = XjamConfigMode(enter=False)
        for msg in config_mode.to_sysex_messages():
            send_message(msg)
            time.sleep(0.05)

        logger.info("Xjam shutdown complete")

    def validate_bank_config(
        self,
        bank_id: str,
        bank_config: 'BankConfig',
        strict_mode: bool = True
    ) -> None:
        """
        Validate toggle_mode consistency for Xjam.

        The Xjam applies toggle mode globally to ALL pads across ALL banks.
        If the user specifies toggle_mode in one bank config, it will affect
        all banks. This validator warns/errors on conflicting settings.

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
                    f"Xjam applies toggle mode globally to ALL pads - "
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
        Program Xjam with persistent configuration.

        Writes user configuration (toggle mode, control settings) to
        device non-volatile memory via SysEx.

        Args:
            send_message: Function to send MIDI messages
            config: Full controller configuration with resolved settings
        """
        from ..config import ControllerConfig

        if not config or not config.banks:
            logger.debug("No configuration provided, using defaults")
            return

        logger.info("Programming Xjam device memory with configuration")

        # Enter config mode
        config_mode = XjamConfigMode(enter=True)
        for msg in config_mode.to_sysex_messages():
            send_message(msg)
            time.sleep(0.05)

        # Determine global toggle mode from config
        # Since it's global, we take the setting from any bank that has it defined
        toggle_mode = True  # Default
        for bank_id, bank_config in config.banks.items():
            if bank_config.toggle_mode is not None:
                toggle_mode = bank_config.toggle_mode
                logger.info(f"Using toggle_mode={toggle_mode} from {bank_id} (applies globally)")
                break

        # Configure pads for each bank
        for bank_idx in range(self.BANK_COUNT):
            bank_id = f"bank_{bank_idx + 1}"
            bank_config = config.banks.get(bank_id)
            channel = self.BANK_CHANNELS[bank_id]
            pad_start, pad_end, knob_start, knob_end = self.BANK_ELEMENTS[bank_idx]

            logger.info(f"Configuring {bank_id} pads")

            for pad_idx in range(self.PAD_COUNT):
                element_id = pad_start + pad_idx
                pad_id = f"pad_{pad_idx + 1}"
                midi_note = self.DEFAULT_PAD_NOTES[pad_idx]

                # Get pad-specific config if available
                if bank_config and pad_id in bank_config.controls:
                    control_cfg = bank_config.controls[pad_id]
                    # Could extract note/mode overrides here if supported
                else:
                    control_cfg = None

                pad_config = XjamPadConfig(
                    element_id=element_id,
                    mode=XjamSysEx.PAD_MODE_NOTE,
                    note=midi_note,
                    channel=channel + 1,
                )
                send_message(pad_config.to_sysex_message())
                time.sleep(0.02)

            logger.info(f"Configuring {bank_id} knobs")

            for knob_idx in range(self.KNOB_COUNT):
                element_id = knob_start + knob_idx
                knob_cc = self.DEFAULT_KNOB_CCS[knob_idx]

                knob_config = XjamKnobConfig(
                    element_id=element_id,
                    msg_type=XjamSysEx.KNOB_MSG_CC,
                    cc_num=knob_cc,
                    encoder_mode=0,
                    channel=channel,
                )
                send_message(knob_config.to_sysex_message())
                time.sleep(0.02)

        # Set global settings
        global_config = XjamGlobalConfig(
            aftertouch_mode=XjamSysEx.AFTERTOUCH_OFF,
            toggle_mode=toggle_mode,
        )
        for msg in global_config.to_sysex_messages():
            send_message(msg)
            time.sleep(0.02)

        # Commit all changes
        commit = XjamGlobalCommit()
        send_message(commit.to_sysex_message())
        time.sleep(0.1)

        # Exit config mode
        config_mode = XjamConfigMode(enter=False)
        for msg in config_mode.to_sysex_messages():
            send_message(msg)
            time.sleep(0.05)

        logger.info("Xjam program configuration complete")

    def translate_feedback(
        self,
        control_id: str,
        state_dict: dict,
    ) -> list[mido.Message]:
        """
        Translate control state to LED feedback.

        The Xjam does not support LED control from software - the controller
        manages its own LEDs based on pad mode (Note/CC/PC/MMC).

        Args:
            control_id: Control being updated
            state_dict: New state (is_on, value, color, etc.)

        Returns:
            Empty list (no feedback supported)
        """
        # Xjam does not support LED feedback from software
        return []

    def compute_control_state(
        self,
        control_id: str,
        value: int,
        signal_type: str,
        current_state: 'ControlState',
        control_definition: 'ControlDefinition',
    ) -> Optional['ControlState']:
        """
        Custom state computation for Xjam.

        The Xjam in toggle mode manages toggle state in hardware.
        MIDI velocity directly indicates current state:
        - velocity > 0: pad is ON
        - velocity = 0: pad is OFF

        This differs from standard toggle behavior where velocity > 0
        triggers a state flip. The Xjam reports state, not triggers.

        Args:
            control_id: Control identifier
            value: Raw MIDI velocity (0-127)
            signal_type: Signal type ("note", "cc", etc.)
            current_state: Current control state
            control_definition: Control definition

        Returns:
            ControlState for pads (hardware manages toggle state),
            None for other controls (use default behavior).
        """
        from ..controls import ControlState, ControlType
        from datetime import datetime

        # Only handle pads with toggle type
        if not control_id.startswith("pad_"):
            return None
        if control_definition.control_type != ControlType.TOGGLE:
            return None

        # Xjam reports state directly via velocity:
        # velocity > 0 means pad is ON, velocity = 0 means pad is OFF
        is_on = value > 0

        # Determine color based on state
        color = control_definition.on_color if is_on else control_definition.off_color

        # LED mode only applies when ON
        led_mode = control_definition.led_mode if is_on else None

        return ControlState(
            control_id=control_id,
            timestamp=datetime.now(),
            is_discovered=True,
            is_on=is_on,
            value=value,
            color=color,
            led_mode=led_mode,
        )

    def translate_input(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Translate MIDI input with bank detection via channel.

        Since we configure each bank to use a different MIDI channel (1-3),
        we can detect bank switches by monitoring the channel of incoming messages.

        Args:
            msg: MIDI message to translate

        Returns:
            (control_id, value, signal_type) or None
        """
        # Ignore Xjam SysEx ACK messages (sent in response to configuration commands)
        # These have the format: F0 00 20 54 30 7C [optional data...] F7
        if msg.type == 'sysex':
            data = msg.data
            # Check if this is an ACK message (manufacturer ID + device ID + ACK command)
            # data=(0,32,84,48,124) = (0x00,0x20,0x54,0x30,0x7C)
            if (len(data) >= 5 and
                data[0] == 0x00 and data[1] == 0x20 and data[2] == 0x54 and  # Manufacturer ID
                data[3] == 0x30 and  # Device ID
                data[4] == 0x7C):    # ACK command
                # Silently ignore ACK messages
                return None

        # Detect bank from channel
        if hasattr(msg, 'channel'):
            channel = msg.channel
            for bank_id, ch in self.BANK_CHANNELS.items():
                if ch == channel:
                    if bank_id != self._last_active_bank:
                        logger.info(f"Xjam bank switch: {self._last_active_bank} → {bank_id}")
                        self._last_active_bank = bank_id

                        # Sync both pad and ctrl banks to same value
                        # (Xjam has separate pad/ctrl banks - keep them synchronized)
                        if self._send_message:
                            bank_num = int(bank_id.split('_')[1]) - 1  # "bank_1" -> 0
                            bank_select = XjamBankSelect(bank=bank_num)
                            self._send_message(bank_select.to_pad_bank_message())
                            self._send_message(bank_select.to_ctrl_bank_message())
                    break

        # Route message to active bank
        return self._route_to_active_bank(msg)

    def _route_to_active_bank(self, msg: mido.Message) -> Optional[tuple[str, int, str]]:
        """
        Route message to control in the active bank.

        Args:
            msg: MIDI message to route

        Returns:
            (control_id, value, signal_type) or None if not a recognized control
        """
        if not self._last_active_bank:
            return None

        bank_id = self._last_active_bank

        # Handle note messages (pads in Note mode)
        if msg.type in ('note_on', 'note_off'):
            note = msg.note
            # Find pad by note number
            if note in self.DEFAULT_PAD_NOTES:
                pad_num = self.DEFAULT_PAD_NOTES.index(note) + 1
                control_id = f"pad_{pad_num}@{bank_id}"
                value = msg.velocity
                return (control_id, value, "note")

        # Handle CC messages (knobs or pads in CC mode)
        elif msg.type == 'control_change':
            cc = msg.control

            # Check if it's a knob CC
            if cc in self.DEFAULT_KNOB_CCS:
                knob_num = self.DEFAULT_KNOB_CCS.index(cc) + 1
                control_id = f"knob_{knob_num}@{bank_id}"
                return (control_id, msg.value, "cc")

            # Check if it's a pad CC (pad note numbers used as CC in CC mode)
            if cc in self.DEFAULT_PAD_NOTES:
                pad_num = self.DEFAULT_PAD_NOTES.index(cc) + 1
                control_id = f"pad_{pad_num}@{bank_id}"
                return (control_id, msg.value, "cc")

        # Handle program change (pads in PC mode)
        elif msg.type == 'program_change':
            # PC messages route to pad based on program number
            # This is a simplification - actual behavior depends on pad config
            program = msg.program
            if 0 <= program < self.PAD_COUNT:
                control_id = f"pad_{program + 1}@{bank_id}"
                return (control_id, 127, "pc")

        # Handle pitch bend (knobs in Pitch mode)
        elif msg.type == 'pitchwheel':
            # Pitch bend is channel-wide, route to knob_1
            control_id = f"knob_1@{bank_id}"
            # Convert pitch (-8192 to 8191) to 0-127
            value = int((msg.pitch + 8192) / 16383 * 127)
            return (control_id, value, "pitch")

        # Handle aftertouch (knobs in Aftertouch mode)
        elif msg.type == 'aftertouch':
            control_id = f"knob_1@{bank_id}"
            return (control_id, msg.value, "aftertouch")

        return None
