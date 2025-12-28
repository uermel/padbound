"""
Debug module for padbound state visualization.

This module provides tools for real-time debugging of MIDI controller state
through a WebSocket server and Textual TUI client.

Usage:
    # Enable debug server in Controller
    controller = Controller(
        plugin="AKAI APC mini MK2",
        auto_connect=True,
        debug_server=True,
        debug_port=8765,
    )
    print(f"Debug TUI: padbound-debug --url {controller.debug_url}")

    # In another terminal, run the TUI
    $ padbound-debug --url ws://127.0.0.1:8765

    # Or via Python
    $ python -m padbound.debug.tui --url ws://127.0.0.1:8765
"""

from padbound.debug.layout import (
    ControlPlacement,
    ControlWidget,
    DebugLayout,
    LayoutSection,
)

__all__ = [
    # Layout models
    "ControlPlacement",
    "ControlWidget",
    "DebugLayout",
    "LayoutSection",
]

# Conditionally export server and TUI components
# These require websockets and textual dependencies
try:
    from padbound.debug.server import StateBroadcaster  # noqa: F401
    from padbound.debug.tui import ControllerStateApp, run_tui  # noqa: F401

    __all__.extend(
        [
            "StateBroadcaster",
            "ControllerStateApp",
            "run_tui",
        ],
    )
except ImportError:
    # websockets or textual not installed
    pass
