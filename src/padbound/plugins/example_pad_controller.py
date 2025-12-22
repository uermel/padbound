"""
Example Pad Controller Plugin.

Reference implementation demonstrating:
- Accurate capability declarations
- LED and color support for pads
- Read-only faders (no motorized feedback)
- Proper initialization and shutdown
"""

import mido

from ..controls import (
    ControlType,
    ControlDefinition,
    ControlCapabilities,
)
from ..plugin import (
    ControllerPlugin,
    MIDIMapping,
    FeedbackMapping,
    MIDIMessageType,
)


class ExamplePadController(ControllerPlugin):
    """
    Example pad controller with:
    - 16 pads (4x4 grid) with LED and color support
    - 8 faders (read-only, no motorized feedback)
    - 4 side buttons with LED (no color)
    """

    @property
    def name(self) -> str:
        """Plugin name."""
        return "Example Pad Controller"

    @property
    def port_patterns(self) -> list[str]:
        """Port name patterns for auto-detection."""
        return ["Example Pad", "ExamplePad"]

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define all controls with accurate capabilities.

        Returns:
            List of control definitions
        """
        controls = []

        # 16 pads (Toggle) - LED + color support
        # Color palette: off, red, green, yellow (velocity-based)
        for i in range(1, 17):
            controls.append(
                ControlDefinition(
                    control_id=f"pad_{i}",
                    control_type=ControlType.TOGGLE,
                    capabilities=ControlCapabilities(
                        supports_feedback=True,
                        requires_feedback=True,  # Device needs LED updates from library
                        supports_led=True,
                        supports_color=True,
                        color_mode="velocity",
                        color_palette=["off", "red", "green", "yellow"],
                        requires_discovery=False,  # Pads start in known off state
                    ),
                    display_name=f"Pad {i}"
                )
            )

        # 8 faders (Continuous) - Read-only, no motorized feedback
        for i in range(1, 9):
            controls.append(
                ControlDefinition(
                    control_id=f"fader_{i}",
                    control_type=ControlType.CONTINUOUS,
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # No motorized faders
                        requires_discovery=True,  # Unknown until moved
                    ),
                    display_name=f"Fader {i}",
                    min_value=0,
                    max_value=127
                )
            )

        # 4 side buttons (Momentary) - LED only, no color
        for i in range(1, 5):
            controls.append(
                ControlDefinition(
                    control_id=f"button_{i}",
                    control_type=ControlType.MOMENTARY,
                    capabilities=ControlCapabilities(
                        supports_feedback=True,
                        requires_feedback=True,  # Device needs LED updates from library
                        supports_led=True,
                        supports_color=False,  # LED on/off only
                        requires_discovery=False,
                    ),
                    display_name=f"Button {i}"
                )
            )

        return controls

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Define MIDI-to-control mappings.

        Pads: Note 36-51 (MIDI notes)
        Faders: CC 1-8 (Control Change)
        Buttons: Note 52-55

        Returns:
            List of input mappings
        """
        mappings = []

        # Pads: Note 36-51
        for i in range(1, 17):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=35 + i,  # 36-51
                    control_id=f"pad_{i}"
                )
            )

        # Faders: CC 1-8
        for i in range(1, 9):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=0,
                    control=i,  # CC 1-8
                    control_id=f"fader_{i}"
                )
            )

        # Buttons: Note 52-55
        for i in range(1, 5):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=51 + i,  # 52-55
                    control_id=f"button_{i}"
                )
            )

        return mappings

    def get_feedback_mappings(self) -> list[FeedbackMapping]:
        """
        Define control-to-MIDI feedback mappings.

        Only for controls that support feedback (pads and buttons).
        Faders have no feedback (not motorized).

        Returns:
            List of feedback mappings
        """
        mappings = []

        # Pads: Note 36-51 with velocity for color
        for i in range(1, 17):
            mappings.append(
                FeedbackMapping(
                    control_id=f"pad_{i}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=35 + i,
                    value_source="color"  # Color mapped via velocity
                )
            )

        # Buttons: Note 52-55 with velocity for on/off
        for i in range(1, 5):
            mappings.append(
                FeedbackMapping(
                    control_id=f"button_{i}",
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=0,
                    note=51 + i,
                    value_source="is_on"  # On/off mapped to velocity
                )
            )

        return mappings

    def init(self, send_message, receive_message=None) -> None:
        """
        Initialize controller to known state.

        Clears all pads and buttons to off state.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages (unused)

        Returns:
            None - no values discovered
        """
        # Clear all 16 pads (velocity=0 = off)
        for i in range(1, 17):
            msg = mido.Message('note_on', channel=0, note=35 + i, velocity=0)
            send_message(msg)

        # Clear all 4 buttons (velocity=0 = off)
        for i in range(1, 5):
            msg = mido.Message('note_on', channel=0, note=51 + i, velocity=0)
            send_message(msg)

        return None

    def shutdown(self, send_message) -> None:
        """
        Clean up on disconnect.

        Same as init - clear all LEDs.
        """
        self.init(send_message)

    def translate_feedback(self, control_id: str, state_dict: dict) -> list[mido.Message]:
        """
        Custom feedback translation with color palette support.

        Maps colors to velocities:
        - off: 0
        - red: 5
        - green: 127
        - yellow: 64

        Args:
            control_id: Control identifier
            state_dict: State dictionary

        Returns:
            List of MIDI messages
        """
        messages = []

        # Color mapping for pads
        color_map = {
            "off": 0,
            "red": 5,
            "green": 127,
            "yellow": 64,
        }

        # Extract control number
        if control_id.startswith("pad_"):
            pad_num = int(control_id.split("_")[1])
            note = 35 + pad_num

            # Get velocity from color or is_on
            if "color" in state_dict:
                velocity = color_map.get(state_dict["color"], 0)
            elif "is_on" in state_dict:
                velocity = 127 if state_dict["is_on"] else 0
            else:
                velocity = 0

            msg = mido.Message('note_on', channel=0, note=note, velocity=velocity)
            messages.append(msg)

        elif control_id.startswith("button_"):
            button_num = int(control_id.split("_")[1])
            note = 51 + button_num

            # Get velocity from is_on
            velocity = 127 if state_dict.get("is_on", False) else 0

            msg = mido.Message('note_on', channel=0, note=note, velocity=velocity)
            messages.append(msg)

        return messages
