"""Shared utilities for padbound."""

import logging

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# Named color palette mapping color names to RGB tuples (0-255 range)
NAMED_COLORS: dict[str, tuple[int, int, int]] = {
    "off": (0, 0, 0),
    "black": (0, 0, 0),
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "orange": (255, 128, 0),
    "purple": (128, 0, 255),
    "pink": (255, 64, 128),
    "lime": (128, 255, 0),
    "teal": (0, 255, 128),
    "violet": (128, 0, 255),
}


class RGBColor(BaseModel):
    """RGB color with full range (0-255) and parsing from various formats.

    This base class provides:
    - Storage of RGB values in 0-255 range
    - Factory methods to construct from various formats (hex, named, rgb())
    - Conversion to MIDI range (0-127)

    Subclass this for device-specific byte conversion methods.
    """

    r: int = Field(ge=0, le=255, description="Red channel (0-255)")
    g: int = Field(ge=0, le=255, description="Green channel (0-255)")
    b: int = Field(ge=0, le=255, description="Blue channel (0-255)")

    @classmethod
    def from_string(cls, color: str) -> "RGBColor":
        """Parse color from hex (#RRGGBB), named color, or rgb(r,g,b) format.

        Args:
            color: Color string in one of these formats:
                - Named: "red", "green", "blue", etc.
                - Hex: "#FF0000", "#00FF00", etc.
                - RGB: "rgb(255, 0, 0)", "rgb(128, 64, 32)", etc.

        Returns:
            RGBColor instance with parsed values (0-255 range)
        """
        color = color.lower().strip()

        # Named colors
        if color in NAMED_COLORS:
            r, g, b = NAMED_COLORS[color]
            return cls(r=r, g=g, b=b)

        # Hex: #RRGGBB
        if color.startswith("#") and len(color) == 7:
            try:
                r = int(color[1:3], 16)
                g = int(color[3:5], 16)
                b = int(color[5:7], 16)
                return cls(r=r, g=g, b=b)
            except ValueError:
                logger.warning(f"Invalid hex color format: {color}")

        # RGB: rgb(r, g, b)
        if color.startswith("rgb(") and color.endswith(")"):
            try:
                values = color[4:-1].split(",")
                r, g, b = [max(0, min(255, int(v.strip()))) for v in values]
                return cls(r=r, g=g, b=b)
            except (ValueError, IndexError):
                logger.warning(f"Invalid RGB format: {color}")

        # Default: white
        logger.warning(f"Could not parse color '{color}', defaulting to white")
        return cls(r=255, g=255, b=255)

    @classmethod
    def from_midi_values(cls, r: int, g: int, b: int) -> "RGBColor":
        """Create from MIDI range (0-127) values, scaling to full range.

        Args:
            r: Red channel (0-127)
            g: Green channel (0-127)
            b: Blue channel (0-127)

        Returns:
            RGBColor instance with scaled values (0-255 range)
        """
        return cls(r=r * 2, g=g * 2, b=b * 2)

    def to_midi_range(self) -> tuple[int, int, int]:
        """Convert to MIDI range (0-127) by dividing by 2.

        Returns:
            Tuple of (r, g, b) values in 0-127 range
        """
        return (self.r // 2, self.g // 2, self.b // 2)
