#!/usr/bin/env python3
"""
Demo script for Synido TempoPAD P16 MIDI Controller.

This script demonstrates:
- Setting up a configuration with custom pad colors for all 3 banks
- Connecting to the controller (programs RGB colors via SysEx)
- Registering callbacks for pads, knobs, and transport buttons
- Processing and printing MIDI events in real-time

The Synido TempoPAD P16 features:
- 16 velocity-sensitive pads with RGB backlit LEDs (4x4 grid)
- 3 pad banks (A, B, C) accessible via PAD BANK button (48 total pads)
- 4 endless rotary encoders per bank (12 total knobs)
- 6 transport control buttons (Back, Stop, Forward, Record, Play/Pause, Loop)

IMPORTANT: LED Behavior
The TempoPAD has RGB LEDs, but they work differently from most controllers:
- RGB colors are configured via SysEx and stored in device memory
- When you press a pad, the device shows the configured color
- There is NO real-time LED control from software
- Colors are "baked in" during configuration, then hardware manages them

This is a unique combination: RGB colors (like LPD8 MK2) but no feedback (like MPD218).
"""

import logging
import time

from padbound.config import BankConfig, ControlConfig, ControllerConfig
from padbound.controller import Controller
from padbound.controls import ControlState, ControlType
from padbound.logging_config import get_logger, set_module_level, setup_logging
from padbound.plugins.synido_tempopad import SynidoTempoPADPlugin

# Set up rich logging to see what's happening
setup_logging(level=logging.INFO)

logger = get_logger(__name__)

# Enable debug logging for specific modules to see MIDI input
set_module_level("padbound.controller", logging.DEBUG)
set_module_level("padbound.midi_io", logging.DEBUG)


def create_example_config() -> ControllerConfig:
    """
    Create an example configuration for the TempoPAD.

    Since the TempoPAD stores RGB colors in device memory (not real-time),
    we configure the colors here and they get programmed into the device
    when connect() is called.

    The 4x4 grid layout (pad numbering, same for all banks):
        13  14  15  16   (top row)
         9  10  11  12
         5   6   7   8
         1   2   3   4   (bottom row)

    This config sets:
    - Bank A: Rainbow gradient (Red -> Violet)
    - Bank B: Warm colors (Reds, Oranges, Yellows)
    - Bank C: Cool colors (Blues, Greens, Cyans)
    """
    # Bank A - Rainbow gradient
    bank_a_colors = [
        "red",  # Pad 1
        "orange",  # Pad 2
        "yellow",  # Pad 3
        "lime",  # Pad 4
        "green",  # Pad 5
        "teal",  # Pad 6
        "cyan",  # Pad 7
        "sky",  # Pad 8
        "blue",  # Pad 9
        "purple",  # Pad 10
        "magenta",  # Pad 11
        "pink",  # Pad 12
        "white",  # Pad 13
        "red",  # Pad 14
        "green",  # Pad 15
        "blue",  # Pad 16
    ]

    # Bank B - Warm colors
    bank_b_colors = [
        "rgb(127, 0, 0)",  # Dark red
        "rgb(127, 32, 0)",  # Red-orange
        "rgb(127, 64, 0)",  # Orange
        "rgb(127, 96, 0)",  # Orange-yellow
        "rgb(127, 127, 0)",  # Yellow
        "rgb(96, 127, 0)",  # Yellow-green
        "rgb(127, 64, 32)",  # Tan
        "rgb(127, 32, 32)",  # Salmon
        "rgb(90, 0, 0)",  # Deep red
        "rgb(90, 45, 0)",  # Brown
        "rgb(90, 90, 0)",  # Olive
        "rgb(127, 80, 0)",  # Gold
        "rgb(127, 100, 50)",  # Peach
        "rgb(127, 60, 30)",  # Coral
        "rgb(100, 50, 25)",  # Rust
        "rgb(80, 40, 20)",  # Bronze
    ]

    # Bank C - Cool colors
    bank_c_colors = [
        "rgb(0, 0, 127)",  # Deep blue
        "rgb(0, 32, 127)",  # Blue
        "rgb(0, 64, 127)",  # Cyan-blue
        "rgb(0, 96, 127)",  # Cyan
        "rgb(0, 127, 127)",  # Cyan
        "rgb(0, 127, 96)",  # Cyan-green
        "rgb(0, 127, 64)",  # Teal
        "rgb(0, 127, 32)",  # Green-cyan
        "rgb(0, 127, 0)",  # Green
        "rgb(32, 127, 64)",  # Sea green
        "rgb(64, 127, 127)",  # Light cyan
        "rgb(32, 64, 127)",  # Steel blue
        "rgb(64, 32, 127)",  # Indigo
        "rgb(96, 0, 127)",  # Violet
        "rgb(64, 64, 127)",  # Periwinkle
        "rgb(32, 96, 127)",  # Sky blue
    ]

    # Build bank configurations
    bank_a_controls = {
        f"pad_{i+1}": ControlConfig(
            type=ControlType.TOGGLE,
            on_color=bank_a_colors[i],
        )
        for i in range(16)
    }

    bank_b_controls = {
        f"pad_{i+1}": ControlConfig(
            type=ControlType.TOGGLE,
            on_color=bank_b_colors[i],
        )
        for i in range(16)
    }

    bank_c_controls = {
        f"pad_{i+1}": ControlConfig(
            type=ControlType.MOMENTARY,  # Bank C uses momentary mode
            on_color=bank_c_colors[i],
        )
        for i in range(16)
    }

    return ControllerConfig(
        banks={
            "bank_a": BankConfig(
                toggle_mode=True,
                controls=bank_a_controls,
            ),
            "bank_b": BankConfig(
                toggle_mode=True,
                controls=bank_b_controls,
            ),
            "bank_c": BankConfig(
                toggle_mode=False,  # Momentary mode
                controls=bank_c_controls,
            ),
        },
    )


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events."""
    # Parse control_id: "pad_1@bank_a" -> pad_num=1, bank="bank_a"
    parts = control_id.split("@")
    pad_part = parts[0]  # "pad_1"
    bank_part = parts[1] if len(parts) > 1 else "unknown"  # "bank_a"

    pad_num = int(pad_part.split("_")[1])
    bank_letter = bank_part.replace("bank_", "").upper()

    status = "ON " if state.is_on else "off"
    velocity = state.value if state.value is not None else 0

    print(f"[PAD {bank_letter}-{pad_num:>2d}] {status} velocity={velocity}")


def on_knob_change(control_id: str, state: ControlState):
    """Callback for knob events."""
    # Parse control_id: "knob_1@bank_a" -> knob_num=1, bank="bank_a"
    parts = control_id.split("@")
    knob_part = parts[0]  # "knob_1"
    bank_part = parts[1] if len(parts) > 1 else "unknown"  # "bank_a"

    knob_num = int(knob_part.split("_")[1])
    bank_letter = bank_part.replace("bank_", "").upper()

    value = state.value if state.value is not None else 0
    bar = "█" * (value // 4)  # Visual bar (0-31 chars)
    print(f"[KNOB {bank_letter}-{knob_num}] {value:3d}/127 [{bar:<31s}]")


def on_button_change(control_id: str, state: ControlState):
    """Callback for transport button events."""
    # Parse control_id: "button_play" -> button_name="play"
    button_name = control_id.replace("button_", "").upper()

    status = "ON " if state.is_on else "off"
    print(f"[BUTTON] {button_name:>10s} {status}")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change (for debugging)."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "=" * 60)
    print("Synido TempoPAD P16 Demo")
    print("=" * 60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   Configuration created with 3-bank layout:")
    print("   - Bank A: Rainbow gradient (TOGGLE mode)")
    print("   - Bank B: Warm colors (TOGGLE mode)")
    print("   - Bank C: Cool colors (MOMENTARY mode)")
    print("")
    print("   Pad layout (same for all banks):")
    print("       13  14  15  16   (top row)")
    print("        9  10  11  12")
    print("        5   6   7   8")
    print("        1   2   3   4   (bottom row)")
    print("")
    print("   NOTE: RGB colors are programmed into device memory.")
    print("         There is NO real-time LED feedback from software.")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = SynidoTempoPADPlugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Category-based callback for pads
    controller.on_category("pad", on_pad_change)
    print("   Registered callback for pads (category='pad')")

    # Type-based callback for knobs
    controller.on_type(ControlType.CONTINUOUS, on_knob_change)
    print("   Registered callback for knobs (type=CONTINUOUS)")

    # Category-based callback for transport buttons
    controller.on_category("button", on_button_change)
    print("   Registered callback for transport buttons (category='button')")

    # Global callback for debugging
    controller.on_global(on_any_control)
    print("   Registered global callback for debugging")

    # Connect to controller
    print("\n4. Connecting to controller...")
    print("   (This will program RGB colors into device memory)")
    try:
        controller.connect()
        print("   Connected successfully!")
    except IOError as e:
        print(f"   Failed to connect: {e}")
        print("\nMake sure your Synido TempoPAD P16 is connected via USB.")
        print("The device should appear as 'TempoPAD' in your MIDI devices.")
        return

    # Print controller info
    print("\n" + "=" * 60)
    print("Controller Information:")
    print("=" * 60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.PAD_TOTAL} pads ({plugin.PAD_COUNT} per bank x {plugin.PAD_BANKS} banks)")
    print(f"  - {plugin.KNOB_TOTAL} knobs ({plugin.KNOB_COUNT} per bank x {plugin.KNOB_BANKS} banks)")
    print(f"  - {plugin.BUTTON_COUNT} transport buttons")

    # Print bank info
    print("\n" + "=" * 60)
    print("Bank Configuration:")
    print("=" * 60)
    print("Pad Banks (detected by note range):")
    for bank_id, (start, end) in plugin.BANK_NOTE_RANGES.items():
        bank_letter = bank_id.replace("bank_", "").upper()
        print(f"  Bank {bank_letter}: Notes {start}-{end}")
    print("\nKnob Banks (default CC assignments):")
    for bank_id, ccs in plugin.DEFAULT_KNOB_CCS.items():
        bank_letter = bank_id.replace("bank_", "").upper()
        print(f"  Bank {bank_letter}: CCs {ccs}")
    print("\nTransport Buttons (all on channel 1):")
    for note, name, is_toggle in plugin.TRANSPORT_BUTTONS:
        mode = "Toggle" if is_toggle else "Momentary"
        print(f"  {name.title():12s}: Note {note} ({mode})")

    # Main event loop
    print("\n" + "=" * 60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("=" * 60)
    print("\nTry:")
    print("  - Press pads to see note events and RGB colors")
    print("    * Bank A: Notes 36-51 (rainbow colors, TOGGLE)")
    print("    * Bank B: Notes 60-75 (warm colors, TOGGLE)")
    print("    * Bank C: Notes 84-99 (cool colors, MOMENTARY)")
    print("  - Turn knobs to see CC values (0-127)")
    print("    * Bank A: CCs 7, 1, 2, 10")
    print("    * Bank B: CCs 14, 15, 12, 13")
    print("    * Bank C: CCs 53, 54, 51, 52")
    print("  - Press transport buttons (Back, Stop, Forward, Record, Play, Loop)")
    print("  - Use PAD BANK/KNOB BANK buttons to switch banks")
    print("")
    print("IMPORTANT: RGB LED colors are stored in device memory.")
    print("           Software cannot change LED colors in real-time.")
    print("           The hardware manages LED state based on your presses.")
    print("")

    try:
        while True:
            # Process any pending MIDI events
            controller.process_events()

            # Sleep briefly to avoid busy-waiting
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n\nShutting down...")

    finally:
        # Disconnect and cleanup
        controller.disconnect()
        print("Disconnected from controller")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()
