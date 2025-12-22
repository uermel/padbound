"""
Generic MIDI Controller Plugin.

Fallback plugin that works with any MIDI device by:
- Mapping all note_on/note_off to momentary controls
- Mapping all CC messages to continuous controls
- No feedback support (read-only)
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
    MIDIMessageType,
)


class GenericMIDIController(ControllerPlugin):
    """
    Generic MIDI controller plugin.

    Works with any MIDI device as a read-only input controller.
    Automatically discovers controls as MIDI messages arrive.
    """

    @property
    def name(self) -> str:
        """Plugin name."""
        return "Generic MIDI Controller"

    @property
    def port_patterns(self) -> list[str]:
        """
        No specific patterns - matches any port.

        Returns:
            Empty list (matches all ports)
        """
        return []

    def get_control_definitions(self) -> list[ControlDefinition]:
        """
        Define generic controls.

        Creates:
        - 128 note controls (note 0-127) as momentary
        - 128 CC controls (CC 0-127) as continuous

        Returns:
            List of control definitions
        """
        controls = []

        # All MIDI notes (0-127) as momentary controls
        for note in range(128):
            controls.append(
                ControlDefinition(
                    control_id=f"note_{note}",
                    control_type=ControlType.MOMENTARY,
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # Read-only
                        requires_discovery=True,
                    ),
                    display_name=f"Note {note}"
                )
            )

        # All CC controls (0-127) as continuous
        for cc in range(128):
            controls.append(
                ControlDefinition(
                    control_id=f"cc_{cc}",
                    control_type=ControlType.CONTINUOUS,
                    capabilities=ControlCapabilities(
                        supports_feedback=False,  # Read-only
                        requires_discovery=True,
                    ),
                    display_name=f"CC {cc}",
                    min_value=0,
                    max_value=127
                )
            )

        return controls

    def get_input_mappings(self) -> list[MIDIMapping]:
        """
        Define MIDI-to-control mappings.

        Maps all note_on and CC messages to corresponding controls.

        Returns:
            List of input mappings
        """
        mappings = []

        # All notes (note_on)
        for note in range(128):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.NOTE_ON,
                    channel=None,  # Any channel
                    note=note,
                    control_id=f"note_{note}"
                )
            )

        # All CC controls
        for cc in range(128):
            mappings.append(
                MIDIMapping(
                    message_type=MIDIMessageType.CONTROL_CHANGE,
                    channel=None,  # Any channel
                    control=cc,
                    control_id=f"cc_{cc}"
                )
            )

        return mappings

    def get_feedback_mappings(self) -> list:
        """
        No feedback support (read-only controller).

        Returns:
            Empty list
        """
        return []

    def init(self, send_message, receive_message=None) -> None:
        """
        Initialize controller.

        Generic MIDI has no specific initialization - it's read-only.

        Args:
            send_message: Function to send MIDI messages
            receive_message: Function to receive MIDI messages (unused)

        Returns:
            None - no values discovered
        """
        return None

    def shutdown(self, send_message) -> None:
        """
        Shutdown controller.

        Generic MIDI has no specific shutdown sequence.
        """
        pass  # No shutdown needed for generic controller
