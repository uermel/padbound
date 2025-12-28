"""
Pydantic models for WebSocket messages between debug server and TUI client.

These models define the protocol for real-time state communication.
"""

from datetime import datetime
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, Field

from padbound.controls import ControlDefinition, ControlState
from padbound.debug.layout import DebugLayout


class FullStateMessage(BaseModel):
    """Message sent on client connection with complete controller state."""

    type: Literal["full_state"] = "full_state"
    timestamp: datetime
    plugin_name: str
    layout: Optional[DebugLayout] = None
    states: dict[str, ControlState]
    definitions: dict[str, ControlDefinition]


class StateChangeMessage(BaseModel):
    """Message sent when a single control's state changes."""

    type: Literal["state_change"] = "state_change"
    timestamp: datetime
    control_id: str
    state: ControlState


# Discriminated union for parsing any incoming message
DebugMessage = Annotated[
    Union[FullStateMessage, StateChangeMessage],
    Field(discriminator="type"),
]
