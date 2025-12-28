#!/usr/bin/env python3
"""
Demo script for PreSonus Atom MIDI Controller.

This script demonstrates:
- Setting up a configuration with custom colors for the 4x4 pad grid
- Connecting to the controller (automatically switches to Native mode)
- Registering callbacks for pads, encoders, and buttons
- Processing and printing MIDI events in real-time

The PreSonus Atom supports:
- True RGB colors via Native Control mode
- 16 velocity-sensitive pads with RGB LEDs
- 4 endless rotary encoders (relative mode)
- 20 function/transport buttons with LED feedback
"""

import logging
import time

from padbound.config import ControlConfig, ControllerConfig
from padbound.controller import Controller
from padbound.controls import ControlState, ControlType
from padbound.logging_config import get_logger, set_module_level, setup_logging
from padbound.plugins.presonus_atom import PreSonusAtomPlugin

# Set up rich logging to see what's happening
setup_logging(level=logging.INFO)

logger = get_logger(__name__)

# Enable debug logging for specific modules to see MIDI input
set_module_level("padbound.controller", logging.DEBUG)
set_module_level("padbound.midi_io", logging.DEBUG)


def create_example_config() -> ControllerConfig:
    """
    Create an example configuration for the Atom with colorful pad grid.

    This configuration demonstrates:
    - True RGB colors via Native mode (any color, not limited to palette)
    - Rainbow gradient across the pad grid
    - ON/OFF color states for visual feedback

    The 4x4 grid layout (pad numbering):
        13  14  15  16   (top row)
         9  10  11  12
         5   6   7   8
         1   2   3   4   (bottom row)

    Color scheme and LED modes:
    - Row 1 (pads 1-4): Warm colors - TOGGLE, SOLID (steady light when ON)
    - Row 2 (pads 5-8): Cool colors - TOGGLE, PULSE (breathing effect when ON)
    - Row 3 (pads 9-12): Mixed colors - TOGGLE, BLINK (flashing effect when ON)
    - Row 4 (pads 13-16): Bright primaries - MOMENTARY (lights only while pressed)

    Color formats supported:
    - Named: "red", "green", "blue", "cyan", "magenta", "yellow", "white", "black"
    - Hex: "#FF0000", "#00FF00", "#0000FF"
    - RGB: "rgb(255, 0, 0)", "rgb(0, 255, 0)", "rgb(0, 0, 255)"
    """
    controls = {}

    # Row 1 (bottom): Warm colors with dim off states - SOLID mode (default, steady light)
    warm_colors = [
        ("red", "rgb(64, 0, 0)"),
        ("orange", "rgb(64, 32, 0)"),
        ("yellow", "rgb(64, 64, 0)"),
        ("green", "rgb(0, 64, 0)"),
    ]
    for i, (on_color, off_color) in enumerate(warm_colors, start=1):
        controls[f"pad_{i}"] = ControlConfig(type=ControlType.TOGGLE, color=on_color, off_color=off_color)

    # Row 2: Cool colors with dim off states - PULSE mode (breathing effect when ON)
    cool_colors = [
        ("cyan", "rgb(0, 64, 64)"),
        ("blue", "rgb(0, 0, 64)"),
        ("purple", "rgb(32, 0, 64)"),
        ("magenta", "rgb(64, 0, 64)"),
    ]
    for i, (on_color, off_color) in enumerate(cool_colors, start=5):
        controls[f"pad_{i}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color,
            on_led_mode="pulse",  # Breathing effect when ON
        )

    # Row 3: Mixed colors with dim off states - BLINK mode (flashing effect when ON)
    mixed_colors = [
        ("pink", "rgb(64, 16, 32)"),
        ("lime", "rgb(32, 64, 0)"),
        ("#00CCCC", "rgb(0, 48, 48)"),  # Teal (hex format)
        ("white", "rgb(48, 48, 48)"),
    ]
    for i, (on_color, off_color) in enumerate(mixed_colors, start=9):
        controls[f"pad_{i}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color,
            on_led_mode="blink",  # Flashing effect when ON
        )

    # Row 4 (top): MOMENTARY mode - lights up only while pressed
    momentary_colors = [
        ("rgb(255, 64, 64)", "black"),  # Bright red
        ("rgb(64, 255, 64)", "black"),  # Bright green
        ("rgb(64, 64, 255)", "black"),  # Bright blue
        ("rgb(255, 255, 255)", "black"),  # White
    ]
    for i, (on_color, off_color) in enumerate(momentary_colors, start=13):
        controls[f"pad_{i}"] = ControlConfig(
            type=ControlType.MOMENTARY,
            color=on_color,
            off_color=off_color,  # Only lights while pressed
        )

    config = ControllerConfig(controls=controls)
    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events (both TOGGLE and MOMENTARY)."""
    pad_num = int(control_id.split("_")[1])
    status = "ON " if state.is_on else "off"
    # Pads 13-16 (top row) are MOMENTARY, others are TOGGLE
    mode = "MOMENTARY" if pad_num >= 13 else "TOGGLE"
    print(f"[PAD {pad_num:>2d}] {status} ({mode}) color={state.color}")


# Track previous encoder values for direction display (plugin handles accumulation internally)
_prev_encoder_values: dict[str, int] = {}


def on_encoder_change(control_id: str, state: ControlState):
    """Callback for encoder events (now returns accumulated 0-127 values)."""
    enc_num = control_id.split("_")[1]
    value = state.value

    # Determine direction from previous value (for display only)
    prev_value = _prev_encoder_values.get(control_id, 64)
    delta = value - prev_value
    _prev_encoder_values[control_id] = value

    direction = "CW " if delta > 0 else "CCW" if delta < 0 else "   "
    bar = "█" * (value // 4)  # Visual bar (0-31 chars)
    print(f"[ENCODER {enc_num}] {direction} {value:3d}/127 [{bar:<31s}]")


def on_transport_button(control_id: str, state: ControlState):
    """Callback for transport button events."""
    btn_name = control_id.replace("_", " ").upper()
    status = "PRESSED" if state.is_on else "released"
    print(f"[{btn_name}] {status}")


def on_nav_button(control_id: str, state: ControlState):
    """Callback for navigation button events."""
    # Extract button name: "nav_up" -> "UP"
    btn_name = control_id.replace("nav_", "").upper()
    status = "PRESSED" if state.is_on else "released"
    print(f"[NAV {btn_name}] {status}")


def on_mode_button(control_id: str, state: ControlState):
    """Callback for mode/function button events."""
    btn_name = control_id.replace("_", " ").title()
    status = "PRESSED" if state.is_on else "released"
    print(f"[{btn_name}] {status}")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "=" * 60)
    print("PreSonus Atom Demo")
    print("=" * 60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   Configuration created with colorful 4x4 pad grid:")
    print("   Using true RGB colors via Native mode")
    print("   Pad layout (numbering) with LED modes:")
    print("       13  14  15  16   (top row - MOMENTARY, lights while pressed)")
    print("        9  10  11  12   (mixed colors - TOGGLE, BLINK)")
    print("        5   6   7   8   (cool colors - TOGGLE, PULSE)")
    print("        1   2   3   4   (bottom row - warm colors - TOGGLE, SOLID)")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = PreSonusAtomPlugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Category-based callback for all pads (works for both TOGGLE and MOMENTARY)
    controller.on_category("pad", on_pad_change)
    controller.on_type(ControlType.CONTINUOUS, on_encoder_change)
    print("   Registered callbacks for pads (all types) and encoders (CONTINUOUS)")

    # Category-based callbacks for button groups
    controller.on_category("transport", on_transport_button)
    print("   Registered callback for transport buttons (Click, Record, Play, Stop)")

    controller.on_category("navigation", on_nav_button)
    print("   Registered callback for navigation buttons")

    controller.on_category("mode", on_mode_button)
    print("   Registered callback for mode/function buttons")

    # Global callback for everything
    controller.on_global(on_any_control)
    print("   Registered global callback")

    # Connect to controller
    print("\n4. Connecting to controller...")
    print("   (This will switch the Atom to Native Control mode for LED control)")
    try:
        controller.connect()
        print("   Connected successfully!")
    except IOError as e:
        print(f"   Failed to connect: {e}")
        print("\nMake sure your PreSonus Atom is connected via USB.")
        return

    # Print controller info
    print("\n" + "=" * 60)
    print("Controller Information:")
    print("=" * 60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.PAD_COUNT} RGB pads (4x4 grid)")
    print(f"  - {plugin.ENCODER_COUNT} endless encoders (relative mode)")
    print(f"  - {len(plugin.BUTTON_CCS)} buttons (various functions)")

    # Print pad grid with colors and LED modes
    print("\n" + "=" * 60)
    print("Pad Grid Layout (4x4) - True RGB Colors + LED Modes:")
    print("=" * 60)
    print("Row 4 (top):    MOMENTARY - bright while pressed, black when released")
    print("Row 3:          TOGGLE + BLINK - flashing when ON, dim when OFF")
    print("Row 2:          TOGGLE + PULSE - breathing when ON, dim when OFF")
    print("Row 1 (bottom): TOGGLE + SOLID - steady light when ON, dim when OFF")

    # Main event loop
    print("\n" + "=" * 60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("=" * 60)
    print("\nTry:")
    print("  - Press pads (rows 1-3) to toggle them on/off")
    print("    * Row 1: SOLID - steady light when ON")
    print("    * Row 2: PULSE - breathing/pulsing effect when ON")
    print("    * Row 3: BLINK - flashing effect when ON")
    print("    * All rows show dim colors when OFF")
    print("  - Press pads (row 4, top) for momentary behavior")
    print("    * Lights up bright ONLY while pressed")
    print("    * Goes dark immediately when released")
    print("  - Turn encoders to see accumulated values (0-127)")
    print("    * Clockwise: increases value")
    print("    * Counter-clockwise: decreases value")
    print("  - Press transport buttons:")
    print("    * Click, Record, Play, Stop")
    print("    * LEDs light up while pressed (momentary)")
    print("  - Press navigation buttons:")
    print("    * Up, Down, Left, Right, Select, Zoom")
    print("    * LEDs light up while pressed (momentary)")
    print("  - Press mode/function buttons:")
    print("    * Note Repeat, Full Level, Shift")
    print("    * Inst Bank, Preset Up/Down, Show/Hide")
    print("    * Event Nudge, Event Editor")
    print("    * Set Loop, Setup")
    print("    * LEDs light up while pressed (momentary)")
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
        # Disconnect and cleanup (restores MIDI mode)
        controller.disconnect()
        print("Disconnected from controller (restored to MIDI mode)")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()
