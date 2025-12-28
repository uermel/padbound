"""
Debug layout models for TUI visualization.

These Pydantic models define how controller plugins specify their
TUI layout for the debug visualization client.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ControlWidget(str, Enum):
    """Types of control widgets for TUI rendering."""

    PAD = "pad"  # Square/rectangular pad (toggle/momentary)
    FADER = "fader"  # Vertical slider
    KNOB = "knob"  # Rotary control display
    BUTTON = "button"  # Simple button
    ENCODER = "encoder"  # Endless encoder display


class ControlPlacement(BaseModel):
    """Placement of a control in a TUI grid section."""

    control_id: str
    widget_type: ControlWidget
    row: int = Field(ge=0)  # Grid row (0 = top)
    col: int = Field(ge=0)  # Grid column (0 = left)
    row_span: int = Field(ge=1, default=1)
    col_span: int = Field(ge=1, default=1)
    label: Optional[str] = None  # Display label (defaults to control_id)


class LayoutSection(BaseModel):
    """A named section of controls (e.g., 'Pad Grid', 'Faders')."""

    name: str
    controls: list[ControlPlacement]
    rows: int = Field(ge=1)
    cols: int = Field(ge=1)


class DebugLayout(BaseModel):
    """Complete TUI layout definition for a controller."""

    plugin_name: str
    description: Optional[str] = None
    sections: list[LayoutSection]
