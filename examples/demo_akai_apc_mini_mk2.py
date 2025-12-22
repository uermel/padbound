#!/usr/bin/env python3
"""
Demo script for AKAI APC mini MK2 MIDI Controller.

This script demonstrates:
- Setting up a configuration with custom colors for the 8x8 pad grid
- Connecting to the controller with automatic fader position discovery
- Registering callbacks for pads, faders, and buttons
- Processing and printing MIDI events in real-time

The APC mini MK2 supports:
- True RGB colors via SysEx (any color, not just indexed palette)
- Fader position discovery via Introduction Message (0x60/0x61)
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
    - True RGB colors via SysEx (any color, not limited to indexed palette)
    - Rainbow gradient across the pad grid with dim OFF states
    - Mix of different color schemes per row
    - ON/OFF color states for visual feedback

    The 8x8 grid layout (row 0 = bottom, row 7 = top):
    - Row 0: Rainbow spectrum (bright when ON, dim when OFF)
    - Row 1: Warm colors (bright on, dim off)
    - Row 2: Cool colors (bright on, black off)
    - Row 3: Earth tones (bright on, dim off)
    - Row 4: Bright colors (on) vs dark (off)
    - Row 5: Monochrome gradient (bright on, dark off)
    - Row 6: Primary colors (bright on, black off)
    - Row 7: Purple/magenta gradient (bright on, dim off)

    Color formats supported:
    - Named: "red", "green", "blue", "cyan", "magenta", "yellow", "white", "black"
    - Hex: "#FF0000", "#00FF00", "#0000FF"
    - RGB: "rgb(255, 0, 0)", "rgb(0, 255, 0)", "rgb(0, 0, 255)"
    """
    controls = {}

    # Row 0 (bottom): Rainbow spectrum with dim off states
    rainbow_on = ['red', 'orange', 'yellow', 'lime', 'green', 'cyan', 'blue', 'purple']
    rainbow_off = ['rgb(64, 0, 0)', 'rgb(64, 32, 0)', 'rgb(64, 64, 0)', 'rgb(32, 64, 0)',
                   'rgb(0, 64, 0)', 'rgb(0, 64, 64)', 'rgb(0, 0, 64)', 'rgb(32, 0, 64)']
    for col, (on_color, off_color) in enumerate(zip(rainbow_on, rainbow_off)):
        controls[f"pad_0_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 1: Warm colors with dim off
    warm_on = ['red', '#FF4400', 'orange', '#FFAA00', 'yellow', 'orange', 'pink', 'red']
    warm_off = ['rgb(64, 0, 0)', 'rgb(64, 16, 0)', 'rgb(64, 32, 0)', 'rgb(64, 48, 0)',
                'rgb(64, 64, 0)', 'rgb(64, 32, 0)', 'rgb(64, 16, 32)', 'rgb(64, 0, 0)']
    for col, (on_color, off_color) in enumerate(zip(warm_on, warm_off)):
        controls[f"pad_1_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 2: Cool colors (bright on, black off)
    cool = ['cyan', 'blue', '#4444FF', 'purple', 'magenta', 'blue', 'cyan', 'green']
    for col, color in enumerate(cool):
        controls[f"pad_2_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=color,
            off_color='black'  # Completely off when not pressed
        )

    # Row 3: Earth/natural tones with dim off
    earth_on = ['#CC6600', 'orange', '#CCCC00', 'lime', 'green', '#00CC00', '#CC6600', 'red']
    earth_off = ['rgb(48, 24, 0)', 'rgb(64, 32, 0)', 'rgb(48, 48, 0)', 'rgb(32, 64, 0)',
                 'rgb(0, 48, 0)', 'rgb(0, 48, 0)', 'rgb(48, 24, 0)', 'rgb(48, 0, 0)']
    for col, (on_color, off_color) in enumerate(zip(earth_on, earth_off)):
        controls[f"pad_3_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 4: Bright colors vs dark off states
    bright_on = ['pink', 'orange', 'yellow', 'lime', 'cyan', 'blue', 'purple', 'magenta']
    bright_off = ['rgb(48, 0, 0)', 'rgb(48, 24, 0)', 'rgb(48, 48, 0)', 'rgb(0, 48, 0)',
                  'rgb(0, 48, 48)', 'rgb(0, 0, 48)', 'rgb(24, 0, 48)', 'rgb(48, 0, 48)']
    for col, (on_color, off_color) in enumerate(zip(bright_on, bright_off)):
        controls[f"pad_4_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color
        )

    # Row 5: Monochrome gradient (bright on, dark off)
    mono_on = ['rgb(128, 128, 128)', 'rgb(160, 160, 160)', 'rgb(192, 192, 192)', 'rgb(224, 224, 224)',
               'white', 'white', 'white', 'white']
    mono_off = ['black', 'rgb(32, 32, 32)', 'rgb(48, 48, 48)', 'rgb(64, 64, 64)',
                'rgb(80, 80, 80)', 'rgb(96, 96, 96)', 'rgb(112, 112, 112)', 'rgb(128, 128, 128)']
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
    purple_on = ['#6666FF', 'blue', '#8800FF', 'purple', '#FF00FF', 'magenta', '#FF4488', 'pink']
    purple_off = ['rgb(24, 24, 64)', 'rgb(0, 0, 64)', 'rgb(32, 0, 64)', 'rgb(32, 0, 64)',
                  'rgb(64, 0, 64)', 'rgb(64, 0, 64)', 'rgb(64, 16, 32)', 'rgb(64, 16, 32)']
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
    print("      Using true RGB colors via SysEx (named, hex, or rgb() formats)")
    print("      Each row demonstrates ON/OFF color states:")
    print("      - Row 0 (bottom): Rainbow (bright on, dim off)")
    print("      - Row 1: Warm colors (bright on, dim off)")
    print("      - Row 2: Cool colors (bright on, BLACK off)")
    print("      - Row 3: Earth tones (bright on, dim off)")
    print("      - Row 4: Bright colors (bright on, dark off)")
    print("      - Row 5: Monochrome gradient (bright on, dark off)")
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

    # Show discovered fader positions
    print("\n" + "="*60)
    print("Discovered Fader Positions:")
    print("="*60)
    print("(Obtained via Introduction Message on startup)")
    for i in range(1, plugin.FADER_COUNT + 1):
        fader_id = f"fader_{i}"
        state = controller.get_state(fader_id)
        label = f"Fader {i}" if i < 9 else "Master "
        if state and state.value is not None:
            bar = '█' * (state.value // 4)
            print(f"  {label}: {state.value:3d}/127 [{bar:<31s}]")
        else:
            print(f"  {label}: (not discovered)")

    # Print pad grid layout
    print("\n" + "="*60)
    print("Pad Grid Layout (8x8) - True RGB Colors:")
    print("="*60)
    print("Row 7 (top)    → Purple/magenta gradient (hex + named)")
    print("Row 6          → Primary colors (named)")
    print("Row 5          → Monochrome gradient (rgb())")
    print("Row 4          → Bright colors (named)")
    print("Row 3          → Earth tones (hex)")
    print("Row 2          → Cool colors (named + hex)")
    print("Row 1          → Warm colors (hex + named)")
    print("Row 0 (bottom) → Rainbow spectrum (named)")
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
    print("    * Initial positions are discovered on startup (shown above)")
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