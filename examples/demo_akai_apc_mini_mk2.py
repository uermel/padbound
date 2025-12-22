#!/usr/bin/env python3
"""
Demo script for AKAI APC mini MK2 MIDI Controller.

This script demonstrates:
- Setting up a configuration with custom colors for the 8x8 pad grid
- Connecting to the controller
- Registering callbacks for pads, faders, and buttons
- Processing and printing MIDI events in real-time
"""

import logging
import time
from padbound.controller import Controller
from padbound.plugins.akai_apc_mini_mk2 import AkaiAPCminiMK2Plugin
from padbound.config import ControllerConfig, ControlConfig
from padbound.controls import ControlType, ControlState
from padbound.logging_config import setup_logging, set_module_level, get_logger

# Set up rich logging to see what's happening
setup_logging(level=logging.INFO)

logger = get_logger(__name__)

# Enable debug logging for specific modules to see MIDI input
set_module_level('padbound.controller', logging.DEBUG)
set_module_level('padbound.midi_io', logging.DEBUG)


def create_example_config() -> ControllerConfig:
    """
    Create an example configuration for the APC mini MK2 with colorful pad grid.

    This configuration demonstrates:
    - Rainbow gradient across the pad grid with dim OFF states
    - Named colors from the APC mini's indexed palette
    - Mix of different color schemes per row
    - ON/OFF color states for visual feedback

    The 8x8 grid layout (row 0 = bottom, row 7 = top):
    - Row 0: Rainbow spectrum (bright when ON, dim when OFF)
    - Row 1: Warm colors (bright on, dim off)
    - Row 2: Cool colors (bright on, black off)
    - Row 3: Earth tones (bright on, dim off)
    - Row 4: Bright colors (on) vs dark (off)
    - Row 5: Monochrome (bright on, dim off)
    - Row 6: Primary colors (bright on, black off)
    - Row 7: Purple/magenta gradient (bright on, dim off)
    """
    controls = {}

    # Row 0 (bottom): Rainbow spectrum with dim off states
    rainbow_on = ['red', 'orange', 'yellow', 'lime', 'green', 'cyan', 'blue', 'purple']
    rainbow_off = ['red_dim', 'orange_dim', 'yellow', 'lime', 'green_dark', 'cyan', 'blue_dark', 'purple']
    for col, (on_color, off_color) in enumerate(zip(rainbow_on, rainbow_off)):
        controls[f"pad_0_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 1: Warm colors with dim off
    warm_on = ['red', 'red', 'orange', 'orange', 'yellow', 'orange', 'pink', 'red']
    warm_off = ['red_dim', 'red_dark', 'orange_dim', 'orange_dark', 'yellow', 'orange_dim', 'pink', 'red_dim']
    for col, (on_color, off_color) in enumerate(zip(warm_on, warm_off)):
        controls[f"pad_1_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 2: Cool colors (bright on, black off)
    cool = ['cyan', 'blue', 'blue_dark', 'purple', 'magenta', 'blue', 'cyan', 'green']
    for col, color in enumerate(cool):
        controls[f"pad_2_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=color,
            off_color='black'  # Completely off when not pressed
        )

    # Row 3: Earth/natural tones with dim off
    earth_on = ['orange', 'orange', 'yellow', 'lime', 'green', 'green', 'orange', 'red']
    earth_off = ['orange_dark', 'orange_dim', 'yellow', 'lime', 'green_dark', 'green_dark', 'orange_dark', 'red_dark']
    for col, (on_color, off_color) in enumerate(zip(earth_on, earth_off)):
        controls[f"pad_3_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 4: Bright colors vs dark off states
    bright_on = ['pink', 'orange', 'yellow', 'lime', 'cyan', 'blue', 'purple', 'magenta']
    bright_off = ['red_dark', 'orange_dark', 'yellow', 'green_dark', 'blue_dark', 'blue_dark', 'purple', 'magenta']
    for col, (on_color, off_color) in enumerate(zip(bright_on, bright_off)):
        controls[f"pad_4_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 5: Monochrome gradient (bright on, dark off)
    mono_on = ['grey', 'grey', 'white', 'white', 'white', 'white', 'white', 'white']
    mono_off = ['black', 'dark_grey', 'grey', 'grey', 'grey', 'grey', 'grey', 'white']
    for col, (on_color, off_color) in enumerate(zip(mono_on, mono_off)):
        controls[f"pad_5_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 6: Primary colors (bright on, black off)
    primary = ['red', 'red', 'green', 'green', 'blue', 'blue', 'yellow', 'yellow']
    for col, color in enumerate(primary):
        controls[f"pad_6_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=color,
            off_color='black'
        )

    # Row 7 (top): Purple/magenta gradient with dim off
    purple_on = ['blue', 'blue', 'purple', 'purple', 'magenta', 'magenta', 'pink', 'pink']
    purple_off = ['blue_dark', 'blue_dark', 'purple', 'purple', 'magenta', 'magenta', 'pink', 'pink']
    for col, (on_color, off_color) in enumerate(zip(purple_on, purple_off)):
        controls[f"pad_7_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    config = ControllerConfig(controls=controls)
    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events."""
    # Extract row and col from control_id
    parts = control_id.split('_')
    row, col = parts[1], parts[2]
    status = "ON " if state.is_on else "off"
    print(f"[PAD] Row {row} Col {col} -> {status} color={state.color}")


def on_fader_change(control_id: str, state: ControlState):
    """Callback for fader events."""
    fader_num = control_id.split('_')[1]
    bar = '█' * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[FADER {fader_num}] {state.value:3d}/127 [{bar:<31s}]")


def on_track_button(control_id: str, state: ControlState):
    """Callback for track button events."""
    btn_num = control_id.split('_')[1]
    status = "PRESSED" if state.is_on else "released"
    print(f"[TRACK {btn_num}] {status}")


def on_scene_button(control_id: str, state: ControlState):
    """Callback for scene button events."""
    btn_num = control_id.split('_')[1]
    status = "PRESSED" if state.is_on else "released"
    print(f"[SCENE {btn_num}] {status}")


def on_shift_button(control_id: str, state: ControlState):
    """Callback for shift button events."""
    status = "PRESSED" if state.is_on else "released"
    print(f"[SHIFT] {status}")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "="*60)
    print("AKAI APC mini MK2 Demo")
    print("="*60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   ✓ Configuration created with colorful 8x8 pad grid:")
    print("      Each row demonstrates ON/OFF color states:")
    print("      - Row 0 (bottom): Rainbow (bright on, dim off)")
    print("      - Row 1: Warm colors (bright on, dim off)")
    print("      - Row 2: Cool colors (bright on, BLACK off)")
    print("      - Row 3: Earth tones (bright on, dim off)")
    print("      - Row 4: Bright colors (bright on, dark off)")
    print("      - Row 5: Monochrome (bright on, dark off)")
    print("      - Row 6: Primary colors (bright on, BLACK off)")
    print("      - Row 7 (top): Purple/magenta (bright on, dim off)")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = AkaiAPCminiMK2Plugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   ✓ Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Type-specific callbacks
    controller.on_type(ControlType.TOGGLE, on_pad_change)
    controller.on_type(ControlType.CONTINUOUS, on_fader_change)
    print("   ✓ Registered callbacks for pads (TOGGLE) and faders (CONTINUOUS)")

    # Control-specific callbacks for buttons
    for i in range(1, 9):
        controller.on_control(f"track_{i}", on_track_button)
        controller.on_control(f"scene_{i}", on_scene_button)
    controller.on_control("shift", on_shift_button)
    print("   ✓ Registered callbacks for track, scene, and shift buttons")

    # Global callback for everything
    controller.on_global(on_any_control)
    print("   ✓ Registered global callback")

    # Connect to controller
    print("\n4. Connecting to controller...")
    try:
        controller.connect()
        print(f"   ✓ Connected successfully!")
    except IOError as e:
        print(f"   ✗ Failed to connect: {e}")
        print("\nMake sure your APC mini MK2 is connected via USB.")
        return

    # Print controller info
    print("\n" + "="*60)
    print("Controller Information:")
    print("="*60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.PAD_COUNT} RGB pads (8x8 grid)")
    print(f"  - {plugin.FADER_COUNT} faders (8 channel + 1 master)")
    print(f"  - {plugin.TRACK_BUTTON_COUNT} track buttons (red LED)")
    print(f"  - {plugin.SCENE_BUTTON_COUNT} scene buttons (green LED)")
    print(f"  - 1 shift button")

    # Print pad grid layout
    print("\n" + "="*60)
    print("Pad Grid Layout (8x8):")
    print("="*60)
    print("Row 7 (top)    → Purple/magenta gradient")
    print("Row 6          → Primary colors")
    print("Row 5          → Monochrome gradient")
    print("Row 4          → Bright colors")
    print("Row 3          → Earth tones")
    print("Row 2          → Cool colors")
    print("Row 1          → Warm colors")
    print("Row 0 (bottom) → Rainbow spectrum")
    print("                 ↑")
    print("              Col 0-7 (left to right)")

    # Main event loop
    print("\n" + "="*60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("="*60)
    print("\nTry:")
    print("  - Press pads to toggle them on/off")
    print("    * Watch the ON/OFF color transitions!")
    print("    * Row 2 and 6: Completely dark when OFF")
    print("    * Row 0, 1, 3, 7: Dim colors when OFF")
    print("    * Row 4, 5: Different dark colors when OFF")
    print("    * Each row demonstrates different ON/OFF color schemes")
    print("  - Move faders to see continuous values (0-127)")
    print("    * Faders 1-8 are channel faders")
    print("    * Fader 9 is the master fader")
    print("  - Press track buttons (1-8) - red LEDs will light up")
    print("  - Press scene buttons (1-8) - green LEDs will light up")
    print("  - Press shift button (no LED feedback)")
    print("")

    try:
        while True:
            # Process any pending MIDI events
            num_events = controller.process_events()

            # Sleep briefly to avoid busy-waiting
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n\nShutting down...")

    finally:
        # Disconnect and cleanup
        controller.disconnect()
        print("✓ Disconnected from controller")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()