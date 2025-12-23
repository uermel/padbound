"""
AKAI APC mini MK2 MIDI Controller Plugin.

Hardware specifications:
- 8x8 grid of RGB backlit pads (64 pads, notes 0x00-0x3F)
- 9 faders (8 channel + 1 master, CC 0x30-0x38)
- 8 track buttons with red LEDs (notes 0x64-0x6B)
- 8 scene launch buttons with green LEDs (notes 0x70-0x77)
- 1 shift button (note 0x7A, no LED)
- RGB LED control via SysEx or velocity-indexed palette
- USB MIDI interface

Control features:
- Pads send NOTE messages and support full RGB feedback via SysEx
- Faders send CC messages (read-only, no motorized feedback)
- Track/Scene buttons send NOTE messages with single-color LED feedback
- 3 hardware modes: Session View (CH 0-15), Drum Mode (CH 9), Note Mode (Port 1)

================================================================================
SYSEX PROTOCOL DOCUMENTATION
================================================================================

All SysEx messages use the following header format:
    F0 47 7F 4F <cmd> <len_msb> <len_lsb> [payload...] F7

Where:
    F0          = SysEx start
    47          = Akai manufacturer ID
    7F          = Device ID (all devices)
    4F          = APC mini MK2 product ID
    <cmd>       = Command/message type identifier
    <len_msb>   = Data length MSB (most significant 7 bits)
    <len_lsb>   = Data length LSB (least significant 7 bits)
    [payload]   = Command-specific data
    F7          = SysEx end

--------------------------------------------------------------------------------
COMMAND 0x24: RGB LED COLOR LIGHTING
--------------------------------------------------------------------------------
Sets RGB color for one or more pads using true 8-bit RGB values.
Each color channel (0-255) is split into MSB/LSB for MIDI 7-bit compliance.

Request:
    F0 47 7F 4F 24 <len_msb> <len_lsb> <start_pad> <end_pad> <rgb_data> F7

    24              = RGB LED Color Lighting command
    <len_msb/lsb>   = Number of data bytes (8 for single pad)
    <start_pad>     = First pad to update (0x00-0x3F)
    <end_pad>       = Last pad to update (0x00-0x3F)
    <rgb_data>      = 6 bytes: [R_MSB, R_LSB, G_MSB, G_LSB, B_MSB, B_LSB]

    Color format (MSB/LSB split):
        Each 8-bit color channel is split into two 7-bit bytes:
        MSB = (value >> 7) & 0x7F
        LSB = value & 0x7F
        Example: RGB(255, 128, 64) → [0x01, 0x7F, 0x01, 0x00, 0x00, 0x40]

    For multiple pads with same color, set start_pad < end_pad.
    For single pad, set start_pad = end_pad.

Response: None

Example (set pad 0 to red):
    F0 47 7F 4F 24 00 08 00 00 01 7F 00 00 00 00 F7
    |              |     |  |  |                 |
    |  header      |len  |pads| RGB(255,0,0)     |end

--------------------------------------------------------------------------------
COMMAND 0x60: INTRODUCTION MESSAGE
--------------------------------------------------------------------------------
Sent to initialize the device and inform firmware of application version.
Device responds with current fader positions.

Request:
    F0 47 7F 4F 60 00 04 <app_id> <ver_hi> <ver_lo> <bugfix> F7

    60          = Introduction message
    00 04       = 4 bytes of data
    <app_id>    = Application/configuration identifier (0x00)
    <ver_hi>    = Application version major
    <ver_lo>    = Application version minor
    <bugfix>    = Application bugfix level

Response:
    F0 47 7F 4F 61 00 09 <fader1> <fader2> ... <fader9> F7

    61          = Introduction response
    00 09       = 9 bytes of fader data
    <faderN>    = Current position of fader N (0-127)

================================================================================
LED CONTROL VIA MIDI NOTE ON (Alternative to SysEx)
================================================================================

RGB pads can also be controlled via Note On messages with a 128-color palette.
The MIDI channel determines LED behavior (brightness/blink/pulse).

Message format: 9X nn vv
    X   = MIDI channel (determines behavior, see below)
    nn  = Pad note number (0x00-0x3F)
    vv  = Velocity (color index from 128-color palette)

LED Behavior by MIDI Channel:
    Channel 0  (0x90) = 10% brightness
    Channel 1  (0x91) = 25% brightness
    Channel 2  (0x92) = 50% brightness
    Channel 3  (0x93) = 65% brightness
    Channel 4  (0x94) = 75% brightness
    Channel 5  (0x95) = 90% brightness
    Channel 6  (0x96) = 100% brightness (default)
    Channel 7  (0x97) = Pulsing 1/16 note
    Channel 8  (0x98) = Pulsing 1/8 note
    Channel 9  (0x99) = Pulsing 1/4 note
    Channel 10 (0x9A) = Pulsing 1/2 note
    Channel 11 (0x9B) = Blinking 1/24 note
    Channel 12 (0x9C) = Blinking 1/16 note
    Channel 13 (0x9D) = Blinking 1/8 note
    Channel 14 (0x9E) = Blinking 1/4 note
    Channel 15 (0x9F) = Blinking 1/2 note

Common velocity-to-color mappings:
    0   = Black/Off      21  = Green         45  = Blue
    3   = White          37  = Cyan          49  = Purple
    5   = Red            53  = Magenta       56  = Pink
    9   = Orange         13  = Yellow

--------------------------------------------------------------------------------
SINGLE LED CONTROL (Track/Scene Buttons)
--------------------------------------------------------------------------------
Track and Scene buttons have single-color LEDs (red/green respectively).
Always use MIDI Channel 0 for single LED control.

Message format: 90 nn vv
    nn  = Button note number (0x64-0x6B for track, 0x70-0x77 for scene)
    vv  = LED state:
          0x00 = Off
          0x01 = On (or 0x03-0x7F)
          0x02 = Blink

================================================================================
MIDI INPUT MESSAGE FORMATS
================================================================================

PAD MESSAGES (Session View - Default):
    Note On:  9n pp vv    (n=channel 0-15, pp=pad 0x00-0x3F, vv=velocity)
    Note Off: 8n pp 00    (n=channel 0-15, pp=pad 0x00-0x3F)

PAD MESSAGES (Drum Mode):
    Note On:  99 pp vv    (channel 9, pp=pad 0x00-0x3F, vv=velocity)
    Note Off: 89 pp 00    (channel 9, pp=pad 0x00-0x3F)

FADER MESSAGES:
    CC:       B0 cc vv    (channel 0, cc=0x30-0x38, vv=0-127)

TRACK BUTTON MESSAGES:
    Note On:  90 bb vv    (channel 0, bb=0x64-0x6B, vv=velocity)
    Note Off: 80 bb 00    (channel 0, bb=0x64-0x6B)

SCENE BUTTON MESSAGES:
    Note On:  90 bb vv    (channel 0, bb=0x70-0x77, vv=velocity)
    Note Off: 80 bb 00    (channel 0, bb=0x70-0x77)

SHIFT BUTTON:
    Note On:  90 7A vv    (channel 0, note 0x7A)
    Note Off: 80 7A 00    (channel 0, note 0x7A)

================================================================================
CONTROL MAPPING
================================================================================

Pad Matrix (8x8 grid, bottom-left origin):
    Row 7: 0x38 0x39 0x3A 0x3B 0x3C 0x3D 0x3E 0x3F  (top)
    Row 6: 0x30 0x31 0x32 0x33 0x34 0x35 0x36 0x37
    Row 5: 0x28 0x29 0x2A 0x2B 0x2C 0x2D 0x2E 0x2F
    Row 4: 0x20 0x21 0x22 0x23 0x24 0x25 0x26 0x27
    Row 3: 0x18 0x19 0x1A 0x1B 0x1C 0x1D 0x1E 0x1F
    Row 2: 0x10 0x11 0x12 0x13 0x14 0x15 0x16 0x17
    Row 1: 0x08 0x09 0x0A 0x0B 0x0C 0x0D 0x0E 0x0F
    Row 0: 0x00 0x01 0x02 0x03 0x04 0x05 0x06 0x07  (bottom)

Track Buttons:  0x64 0x65 0x66 0x67 0x68 0x69 0x6A 0x6B (buttons 1-8)
Scene Buttons:  0x70 0x71 0x72 0x73 0x74 0x75 0x76 0x77 (buttons 1-8)
Shift Button:   0x7A

Faders (CC numbers): 0x30 0x31 0x32 0x33 0x34 0x35 0x36 0x37 0x38
                     (faders 1-8)                      (master)

================================================================================
References:
- Protocol documentation: APC mini mk2 - Communication Protocol - v1.0.pdf
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
    ControlCapabilities,
    ControllerCapabilities,
)
from ..logging_config import get_logger
from ..utils import RGBColor

logger = get_logger(__name__)


class APCminiMK2RGBColor(RGBColor):
    """RGB color with APC mini MK2-specific SysEx byte conversion methods.

    Extends base RGBColor with methods for converting to the byte formats
    required by the APC mini MK2's SysEx protocol.
    """

    def to_sysex_bytes_msb_lsb(self) -> list[int]:
        """Convert to MSB/LSB format for SysEx RGB LED command.

        Each 8-bit color channel (0-255) is split into two 7-bit bytes:
        MSB = (value >> 7) & 0x7F
        LSB = value & 0x7F

        Returns 6 bytes: [R_MSB, R_LSB, G_MSB, G_LSB, B_MSB, B_LSB]
        """
        result = []
        for value in (self.r, self.g, self.b):
            msb = (value >> 7) & 0x7F
            lsb = value & 0x7F
            result.extend([msb, lsb])
        return result


class APCminiMK2PadRGBUpdate(BaseModel):
    """RGB LED update for APC mini MK2 pads (0x24 command).

    Can update a single pad or a range of consecutive pads with the same color.
    Uses SysEx command 0x24 (RGB LED Color Lighting) with MSB/LSB color encoding.
    """

    start_pad: int = Field(ge=0, le=0x3F, description="Start pad note (0x00-0x3F)")
    end_pad: int = Field(ge=0, le=0x3F, description="End pad note (0x00-0x3F)")
    color: APCminiMK2RGBColor = Field(description="RGB color to set")

    def to_sysex_message(self) -> mido.Message:
        """Build SysEx message for RGB LED update.

        Format: F0 47 7F 4F 24 <len MSB> <len LSB> <start> <end> <RGB 6 bytes> F7
        """
        rgb_bytes = self.color.to_sysex_bytes_msb_lsb()
        data_bytes = [self.start_pad, self.end_pad] + rgb_bytes
        data_len = len(data_bytes)

        sysex_data = [
            0x47,  # Akai manufacturer
            0x7F,  # All devices
            0x4F,  # APC mini MK2 product ID
            0x24,  # RGB LED command
            (data_len >> 7) & 0x7F,  # Length MSB
            data_len & 0x7F,          # Length LSB
        ] + data_bytes

        return mido.Message('sysex', data=sysex_data)


class APCminiMK2IntroRequest(BaseModel):
    """Introduction message to APC mini MK2 (0x60 command).

    Sent on startup to initialize device and request fader positions.
    """

    app_id: int = Field(default=0x00, ge=0, le=0x7F, description="Application ID")
    version_major: int = Field(default=0x01, ge=0, le=0x7F, description="Version major")
    version_minor: int = Field(default=0x00, ge=0, le=0x7F, description="Version minor")
    version_bugfix: int = Field(default=0x00, ge=0, le=0x7F, description="Version bugfix")

    def to_sysex_message(self) -> mido.Message:
        """Build SysEx message for introduction request.

        Format: F0 47 7F 4F 60 00 04 <app_id> <ver_hi> <ver_lo> <bugfix> F7
        """
        sysex_data = [
            0x47,  # Akai manufacturer
            0x7F,  # All devices
            0x4F,  # APC mini MK2 product ID
            0x60,  # Introduction command
            0x00, 0x04,  # Length: 4 bytes
            self.app_id,
            self.version_major,
            self.version_minor,
            self.version_bugfix,
        ]
        return mido.Message('sysex', data=sysex_data)


class APCminiMK2IntroResponse(BaseModel):
    """Introduction response from APC mini MK2 (0x61 command).

    Contains current positions of all 9 faders.
    """

    fader_positions: list[int] = Field(min_length=9, max_length=9, description="Fader positions (0-127)")

    @classmethod
    def from_sysex_data(cls, data: tuple | list) -> Optional["APCminiMK2IntroResponse"]:
        """Parse introduction response from SysEx data.

        Expected format: 47 7F 4F 61 00 09 <fader1>...<fader9>

        Args:
            data: SysEx data bytes (without F0/F7)

        Returns:
            APCminiMK2IntroResponse if valid, None otherwise
        """
        data = list(data)
        # Validate header: manufacturer (47), device (7F), product (4F), response cmd (61)
        if (len(data) >= 15 and
            data[0] == 0x47 and data[2] == 0x4F and data[3] == 0x61):
            fader_positions = data[6:15]  # 9 fader values after header
            return cls(fader_positions=fader_positions)
        return None


class AkaiAPCminiMK2Plugin(ControllerPlugin):
    """
    AKAI APC mini MK2 plugin with RGB pad grid and faders.

    Features:
    - 8x8 RGB pad grid (64 pads total) with true RGB color support via SysEx
    - 9 faders (continuous controls, read-only)
    - 8 track buttons with red LED feedback
    - 8 scene launch buttons with green LED feedback
    - 1 shift button (no LED)
    - RGB LED control via SysEx command 0x24 (any RGB color)
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

    # SysEx configuration
    SYSEX_MANUFACTURER = 0x47  # Akai
    SYSEX_DEVICE_ID = 0x7F     # All devices
    SYSEX_PRODUCT_ID = 0x4F    # APC mini MK2
    SYSEX_RGB_LED_CMD = 0x24   # RGB LED Color Lighting command
    SYSEX_INTRO_CMD = 0x60     # Introduction message command
    SYSEX_INTRO_RESPONSE = 0x61  # Introduction response command

    # RGB LED behavior - MIDI channel determines mode (for Note On method)
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

    # LED mode channels for Note On method (pad LED control with palette colors)
    # These are MIDI channel numbers (0-indexed) for mido.Message
    LED_CHANNEL_SOLID = 6       # 100% brightness, solid
    LED_CHANNEL_PULSE = 9       # 1/4 note pulse (medium speed)
    LED_CHANNEL_BLINK = 14      # 1/4 note blink (medium speed)

    # 128-color palette for Note On LED control
    # Maps velocity values to approximate RGB colors
    # Based on APC mini MK2 protocol documentation
    COLOR_PALETTE: dict[int, tuple[int, int, int]] = {
        0: (0, 0, 0),           # Off/Black
        1: (30, 30, 30),        # Dark gray
        2: (127, 127, 127),     # Gray
        3: (255, 255, 255),     # White
        4: (255, 76, 76),       # Light red
        5: (255, 0, 0),         # Red
        6: (89, 0, 0),          # Dark red
        7: (25, 0, 0),          # Dim red
        8: (255, 189, 108),     # Peach
        9: (255, 84, 0),        # Orange
        10: (89, 29, 0),        # Dark orange
        11: (39, 27, 0),        # Brown
        12: (255, 255, 76),     # Light yellow
        13: (255, 255, 0),      # Yellow
        14: (89, 89, 0),        # Dark yellow
        15: (25, 25, 0),        # Dim yellow
        16: (136, 255, 76),     # Yellow-green
        17: (84, 255, 0),       # Lime
        18: (29, 89, 0),        # Dark lime
        19: (20, 43, 0),        # Dim lime
        20: (76, 255, 76),      # Light green
        21: (0, 255, 0),        # Green
        22: (0, 89, 0),         # Dark green
        23: (0, 25, 0),         # Dim green
        24: (76, 255, 94),      # Mint
        25: (0, 255, 25),       # Spring green
        26: (0, 89, 13),        # Dark spring
        27: (0, 25, 2),         # Dim spring
        28: (76, 255, 136),     # Light cyan-green
        29: (0, 255, 84),       # Cyan-green
        30: (0, 89, 29),        # Dark cyan-green
        31: (0, 31, 18),        # Dim cyan-green
        32: (76, 255, 183),     # Light aqua
        33: (0, 255, 153),      # Aqua
        34: (0, 89, 53),        # Dark aqua
        35: (0, 25, 18),        # Dim aqua
        36: (76, 195, 255),     # Light sky blue
        37: (0, 255, 255),      # Cyan
        38: (0, 89, 89),        # Dark cyan
        39: (0, 25, 25),        # Dim cyan
        40: (76, 136, 255),     # Light blue
        41: (0, 170, 255),      # Sky blue
        42: (0, 65, 82),        # Dark sky blue
        43: (0, 16, 25),        # Dim sky blue
        44: (76, 76, 255),      # Light indigo
        45: (0, 0, 255),        # Blue
        46: (0, 0, 89),         # Dark blue
        47: (0, 0, 25),         # Dim blue
        48: (135, 76, 255),     # Light purple
        49: (84, 0, 255),       # Purple
        50: (25, 0, 100),       # Dark purple
        51: (15, 0, 48),        # Dim purple
        52: (255, 76, 255),     # Light magenta
        53: (255, 0, 255),      # Magenta
        54: (89, 0, 89),        # Dark magenta
        55: (25, 0, 25),        # Dim magenta
        56: (255, 76, 135),     # Pink
        57: (255, 0, 84),       # Hot pink
        58: (89, 0, 29),        # Dark pink
        59: (48, 0, 24),        # Dim pink
        60: (255, 25, 0),       # Red-orange
        61: (153, 53, 0),       # Rust
        62: (121, 81, 0),       # Gold
        63: (67, 100, 0),       # Olive
        64: (3, 57, 0),         # Forest
        65: (0, 87, 53),        # Teal
        66: (0, 84, 127),       # Ocean
        67: (0, 0, 255),        # Royal blue
        68: (0, 68, 117),       # Navy
        69: (39, 0, 136),       # Indigo
        70: (72, 0, 120),       # Violet
        71: (110, 0, 48),       # Maroon
        # Extended colors (72-127) - variations and blends
        72: (255, 77, 0),
        73: (255, 148, 0),
        74: (165, 255, 0),
        75: (0, 255, 59),
        76: (0, 199, 255),
        77: (0, 84, 255),
        78: (60, 0, 255),
        79: (163, 0, 186),
        80: (255, 0, 59),
        81: (255, 101, 76),
        82: (255, 148, 76),
        83: (210, 255, 76),
        84: (76, 255, 110),
        85: (76, 220, 255),
        86: (76, 130, 255),
        87: (110, 76, 255),
        88: (195, 76, 210),
        89: (255, 76, 110),
        # More variations
        90: (255, 40, 0),
        91: (180, 100, 0),
        92: (140, 140, 0),
        93: (50, 140, 0),
        94: (0, 140, 60),
        95: (0, 100, 140),
        96: (0, 50, 140),
        97: (60, 0, 140),
        98: (120, 0, 100),
        99: (140, 0, 40),
        # High saturation colors
        100: (255, 0, 48),
        101: (255, 128, 0),
        102: (200, 200, 0),
        103: (80, 200, 0),
        104: (0, 200, 80),
        105: (0, 160, 200),
        106: (0, 80, 200),
        107: (80, 0, 200),
        108: (160, 0, 160),
        109: (200, 0, 80),
        # Soft pastels
        110: (255, 180, 180),
        111: (255, 220, 180),
        112: (255, 255, 180),
        113: (200, 255, 180),
        114: (180, 255, 200),
        115: (180, 255, 255),
        116: (180, 200, 255),
        117: (200, 180, 255),
        118: (255, 180, 255),
        119: (255, 180, 220),
        # Final colors
        120: (180, 60, 0),
        121: (100, 80, 0),
        122: (60, 80, 0),
        123: (0, 80, 40),
        124: (0, 60, 80),
        125: (0, 40, 80),
        126: (40, 0, 80),
        127: (80, 0, 60),
    }

    def __init__(self):
        """Initialize plugin."""
        super().__init__()
        # Track current pad colors for state management (RGB tuples)
        self._current_pad_colors: dict[str, tuple[int, int, int]] = {}
        # Track discovered fader positions
        self._fader_positions: dict[str, int] = {}

    def _find_nearest_palette_color(self, r: int, g: int, b: int) -> int:
        """Find velocity value of nearest color in the 128-color palette.

        Uses Euclidean distance in RGB color space to find the closest match.

        Args:
            r: Red component (0-255)
            g: Green component (0-255)
            b: Blue component (0-255)

        Returns:
            Velocity value (0-127) for the nearest palette color
        """
        min_distance = float('inf')
        nearest_velocity = 0
        for velocity, (pr, pg, pb) in self.COLOR_PALETTE.items():
            # Euclidean distance in RGB space
            distance = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
            if distance < min_distance:
                min_distance = distance
                nearest_velocity = velocity
        return nearest_velocity

    def _get_led_mode_channel(self, led_mode: str) -> int:
        """Get MIDI channel for the specified LED mode.

        Args:
            led_mode: LED mode ("solid", "pulse", or "blink")

        Returns:
            MIDI channel number (0-indexed) for Note On message
        """
        if led_mode == 'pulse':
            return self.LED_CHANNEL_PULSE
        elif led_mode == 'blink':
            return self.LED_CHANNEL_BLINK
        else:
            return self.LED_CHANNEL_SOLID

    @property
    def name(self) -> str:
        """Plugin name for display and registration."""
        return "AKAI APC mini MK2"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection.

        Must use 'Control' port for SysEx LED commands to work.
        The 'Notes' port does not process SysEx messages.
        """
        return [
            "APC mini mk2 Control",
        ]

    def get_capabilities(self) -> ControllerCapabilities:
        """Return controller-level capabilities."""
        return ControllerCapabilities(
            supports_bank_feedback=False,  # No automatic bank feedback
            indexing_scheme="2d",          # 8x8 grid indexing
            grid_rows=self.PAD_ROWS,
            grid_cols=self.PAD_COLS,
            supports_persistent_configuration=False,  # No SysEx programming
            post_init_delay=0.5,  # Device needs time after intro message before LED commands
            feedback_message_delay=0.010,  # 10ms between SysEx messages (prevents buffer overflow)
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
                            color_mode="rgb",  # True RGB via SysEx (solid mode)
                            supported_led_modes=["solid", "pulse", "blink"],  # Pulse/blink use palette
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
                        requires_discovery=False,  # Discovered via introduction message
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
    ) -> dict[str, int]:
        """
        Initialize APC mini MK2 to known state.

        Sends introduction message to discover fader positions and reset device.
        The intro message causes the device to clear all LEDs internally.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages with timeout

        Returns:
            Dictionary of discovered control values (fader_id -> position)
        """
        logger.info("Initializing AKAI APC mini MK2")

        discovered_values: dict[str, int] = {}

        # Send introduction message and get fader positions
        if receive_message is not None:
            intro = APCminiMK2IntroRequest()
            send_message(intro.to_sysex_message())

            # Wait for response with timeout
            response_msg = receive_message(1.0)  # 1 second timeout
            if response_msg and response_msg.type == 'sysex':
                response = APCminiMK2IntroResponse.from_sysex_data(response_msg.data)
                if response:
                    for i, pos in enumerate(response.fader_positions, 1):
                        fader_id = f"fader_{i}"
                        self._fader_positions[fader_id] = pos
                        discovered_values[fader_id] = pos
                    logger.info(f"Discovered fader positions: {discovered_values}")
                else:
                    logger.warning("Failed to parse introduction response")
            else:
                logger.warning("No introduction response received from device")

        # NOTE: The 0x60 intro message above clears all LEDs internally and resets
        # the device to SysEx-ready state. Do NOT send Note On clearing here, as
        # that would put all pads into Note On mode and break SysEx for solid pads.
        # NOTE: post_init_delay in get_capabilities() handles the timing for LED updates

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

        return discovered_values

    def shutdown(self, send_message: Callable[[mido.Message], None]) -> None:
        """
        Shutdown sequence - clear all LEDs.

        Sends messages to turn off all pads, track buttons, and scene buttons.
        For pads, we need to:
        1. Send Note Off to stop any blink/pulse animations (all channels)
        2. Send SysEx to set RGB to black
        """
        logger.info("Shutting down AKAI APC mini MK2")

        # Use same delay as initialization to avoid buffer overflow
        message_delay = 0.010  # 10ms between messages

        # Clear all pad LEDs
        black = APCminiMK2RGBColor(r=0, g=0, b=0)
        for row in range(8):
            for col in range(8):
                pad_note = self.PAD_START_NOTE + (row * 8) + col

                # Stop any blink/pulse animations by sending Note Off on all LED channels
                for channel in [self.LED_CHANNEL_SOLID, self.LED_CHANNEL_PULSE, self.LED_CHANNEL_BLINK]:
                    stop_msg = mido.Message(
                        'note_on',
                        channel=channel,
                        note=pad_note,
                        velocity=0
                    )
                    send_message(stop_msg)
                    time.sleep(message_delay)

                # Set RGB to black via SysEx
                sysex_msg = self._build_pad_rgb_sysex(pad_note, black)
                send_message(sysex_msg)
                time.sleep(message_delay)

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
            time.sleep(message_delay)

        # Clear all scene button LEDs
        for btn_num in range(self.SCENE_BUTTON_COUNT):
            midi_note = self.SCENE_BUTTON_START + btn_num
            msg = mido.Message(
                'note_on',
                channel=0,
                note=midi_note,
                velocity=self.SINGLE_LED_OFF
            )
            send_message(msg)
            time.sleep(message_delay)

        # Reset color tracking
        self._current_pad_colors = {}

        # Send Introduction message (0x60) to reset device to clean SysEx-ready state.
        # This should help avoid requiring unplug/replug between sessions.
        intro = APCminiMK2IntroRequest()
        send_message(intro.to_sysex_message())

        logger.info("APC mini MK2 shutdown complete")

    def translate_feedback(
        self,
        control_id: str,
        state_dict: dict,
    ) -> list[mido.Message]:
        """
        Translate control state to LED feedback.

        For APC mini MK2:
        - Pads: RGB LEDs via SysEx command 0x24 (true RGB colors)
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
        # - Solid mode: SysEx for full RGB colors
        # - Pulse/Blink modes: Note On with palette color (hardware limitation)
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

            # Get color and LED mode from state
            # Use 'or' to handle both missing key AND None value
            color = state_dict.get('color') or 'off'
            led_mode = state_dict.get('led_mode') or 'solid'  # Runtime mode
            definition_led_mode = state_dict.get('definition_led_mode') or 'solid'  # Configured mode
            is_on = state_dict.get('is_on', False)

            # Parse color string to RGB
            rgb_color = APCminiMK2RGBColor.from_string(color)

            # Store current color as RGB tuple
            self._current_pad_colors[control_id] = (rgb_color.r, rgb_color.g, rgb_color.b)

            # MODE SEPARATION: SysEx and Note On are mutually exclusive per pad.
            # Once Note On is sent on an animation channel, the pad ignores SysEx
            # until device power cycle. Therefore:
            # - Pulse/blink pads: ALWAYS use Note On (never SysEx)
            # - Solid pads: ALWAYS use SysEx (never Note On)

            if definition_led_mode in ('pulse', 'blink'):
                # PULSE/BLINK PADS: Use Note On ONLY (never SysEx)
                # This pad must stay in Note On mode for its entire lifecycle
                if is_on:
                    # ON: Use animation channel with color velocity
                    velocity = self._find_nearest_palette_color(rgb_color.r, rgb_color.g, rgb_color.b)
                    channel = self._get_led_mode_channel(definition_led_mode)
                else:
                    # OFF: Use channel 6 (solid) with palette-approximated off_color
                    if rgb_color.r == 0 and rgb_color.g == 0 and rgb_color.b == 0:
                        velocity = 0  # True black
                    else:
                        velocity = self._find_nearest_palette_color(rgb_color.r, rgb_color.g, rgb_color.b)
                    channel = self.LED_CHANNEL_SOLID  # Channel 6 for solid off state

                msg = mido.Message(
                    'note_on',
                    channel=channel,
                    note=pad_note,
                    velocity=velocity
                )
                messages.append(msg)
            else:
                # SOLID PADS: Use SysEx RGB (full color fidelity)
                sysex_msg = self._build_pad_rgb_sysex(pad_note, rgb_color)
                messages.append(sysex_msg)

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

    def _build_pad_rgb_sysex(
        self,
        pad_note: int,
        color: APCminiMK2RGBColor
    ) -> mido.Message:
        """
        Build SysEx message to set a single pad's RGB color.

        Args:
            pad_note: Pad note number (0x00-0x3F)
            color: RGB color to set

        Returns:
            SysEx MIDI message
        """
        update = APCminiMK2PadRGBUpdate(
            start_pad=pad_note,
            end_pad=pad_note,
            color=color
        )
        return update.to_sysex_message()