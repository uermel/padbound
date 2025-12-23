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
    - LED animation modes: solid (default), pulse, and blink

    The 8x8 grid layout (row 0 = bottom, row 7 = top):
    - Row 0: Rainbow spectrum (bright when ON, dim when OFF) - SOLID
    - Row 1: Warm colors (bright on, dim off) - SOLID
    - Row 2: Cool colors (bright on, black off) - SOLID
    - Row 3: Earth tones (bright on, dim off) - SOLID
    - Row 4: Bright colors - MOMENTARY mode (lit while pressed only)
    - Row 5: Monochrome gradient (bright on, dark off) - SOLID
    - Row 6: Primary colors - PULSE mode (pulsing when ON)
    - Row 7: Purple/magenta gradient - BLINK mode (blinking when ON)

    Color formats supported:
    - Named: "red", "green", "blue", "cyan", "magenta", "yellow", "white", "black"
    - Hex: "#FF0000", "#00FF00", "#0000FF"
    - RGB: "rgb(255, 0, 0)", "rgb(0, 255, 0)", "rgb(0, 0, 255)"

    LED modes:
    - "solid": Full RGB colors via SysEx (default)
    - "pulse": Pulsing animation via Note On (uses 128-color palette approximation)
    - "blink": Blinking animation via Note On (uses 128-color palette approximation)

    Control types:
    - TOGGLE: Press toggles pad on/off, state persists (default)
    - MOMENTARY: Pad lights while pressed, turns off when released

    HARDWARE NOTES:
    The APC mini MK2 has two LED control modes:
    - SysEx RGB mode: Full 24-bit colors
    - Note On mode: 128-color palette with animations (pulse/blink)

    Behavior by LED mode:
    - Solid pads: True RGB colors for both ON and OFF states
    - Pulse/blink pads ON: 128-color palette approximation (hardware limitation)
    - Pulse/blink pads OFF: True RGB colors (via solid→SysEx transition)
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

    # Row 4: Bright colors - MOMENTARY mode (lights while pressed, off when released)
    bright_on = ['pink', 'orange', 'yellow', 'lime', 'cyan', 'blue', 'purple', 'magenta']
    bright_off = ['rgb(48, 0, 0)', 'rgb(48, 24, 0)', 'rgb(48, 48, 0)', 'rgb(0, 48, 0)',
                  'rgb(0, 48, 48)', 'rgb(0, 0, 48)', 'rgb(24, 0, 48)', 'rgb(48, 0, 48)']
    for col, (on_color, off_color) in enumerate(zip(bright_on, bright_off)):
        controls[f"pad_4_{col}"] = ControlConfig(
            type=ControlType.MOMENTARY,  # Lights only while pressed
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

    # Row 6: Primary colors with PULSE mode (pulsing animation when ON)
    # Note: Pulse mode uses 128-color palette, so colors are approximated
    primary = ['red', 'red', 'green', 'green', 'blue', 'blue', 'yellow', 'yellow']
    for col, color in enumerate(primary):
        controls[f"pad_6_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=color,
            off_color='black',
            led_mode='pulse'  # Pulsing animation when ON
        )

    # Row 7 (top): Purple/magenta gradient with BLINK mode (blinking when ON)
    # Note: Blink mode uses 128-color palette, so colors are approximated
    purple_on = ['blue', 'blue', 'purple', 'purple', 'magenta', 'magenta', 'pink', 'pink']
    purple_off = ['rgb(24, 24, 64)', 'rgb(0, 0, 64)', 'rgb(32, 0, 64)', 'rgb(32, 0, 64)',
                  'rgb(64, 0, 64)', 'rgb(64, 0, 64)', 'rgb(64, 16, 32)', 'rgb(64, 16, 32)']
    for col, (on_color, off_color) in enumerate(zip(purple_on, purple_off)):
        controls[f"pad_7_{col}"] = ControlConfig(
            type=ControlType.TOGGLE,
            color=on_color,
            off_color=off_color,
            led_mode='blink'  # Blinking animation when ON
        )

    config = ControllerConfig(controls=controls)
    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events (called via on_type)."""
    # Filter: only handle pads (not buttons which are also MOMENTARY)
    if not control_id.startswith("pad_"):
        return
    # Extract row and col from control_id (format: pad_row_col)
    parts = control_id.split('_')
    row, col = parts[1], parts[2]
    status = "ON " if state.is_on else "off"
    print(f"[PAD] Row {row} Col {col} -> {status} color={state.color}")


def on_fader_change(control_id: str, state: ControlState):
    """Callback for fader events."""
    fader_num = control_id.split('_')[1]
    bar = '█' * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[FADER {fader_num}] {state.value:3d}/127 [{bar:<31s}]")


def make_fader_ctrl_callback(btn_name: str):
    """Create a callback for a fader control / navigation button."""
    def callback(state: ControlState):
        status = "PRESSED" if state.is_on else "released"
        print(f"[{btn_name.upper()}] {status}")
    return callback


def make_scene_callback(btn_name: str):
    """Create a callback for a scene button."""
    def callback(state: ControlState):
        status = "PRESSED" if state.is_on else "released"
        print(f"[{btn_name.upper()}] {status}")
    return callback


def on_shift_button(state: ControlState):
    """Callback for shift button events (on_control passes only state)."""
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
    print("      Each row demonstrates ON/OFF color states, LED modes, and control types:")
    print("      - Row 0 (bottom): Rainbow (bright on, dim off) - SOLID TOGGLE")
    print("      - Row 1: Warm colors (bright on, dim off) - SOLID TOGGLE")
    print("      - Row 2: Cool colors (bright on, BLACK off) - SOLID TOGGLE")
    print("      - Row 3: Earth tones (bright on, dim off) - SOLID TOGGLE")
    print("      - Row 4: Bright colors - MOMENTARY (lights while pressed)")
    print("      - Row 5: Monochrome gradient (bright on, dark off) - SOLID TOGGLE")
    print("      - Row 6: Primary colors (BLACK off) - PULSE TOGGLE")
    print("      - Row 7 (top): Purple/magenta (dim off) - BLINK TOGGLE")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = AkaiAPCminiMK2Plugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   ✓ Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Type-specific callbacks
    controller.on_type(ControlType.TOGGLE, on_pad_change)
    controller.on_type(ControlType.MOMENTARY, on_pad_change)
    controller.on_type(ControlType.CONTINUOUS, on_fader_change)
    print("   ✓ Registered callbacks for pads (TOGGLE/MOMENTARY) and faders (CONTINUOUS)")

    # Control-specific callbacks for buttons (using closures to capture button names)
    # Fader control / navigation buttons (bottom row, red LEDs)
    fader_ctrl_buttons = ["volume", "pan", "send", "device", "up", "down", "left", "right"]
    for btn_name in fader_ctrl_buttons:
        controller.on_control(btn_name, make_fader_ctrl_callback(btn_name))

    # Scene buttons (right column, green LEDs)
    scene_buttons = ["clip", "solo", "mute", "rec", "select", "drum", "note", "stop_all"]
    for btn_name in scene_buttons:
        controller.on_control(btn_name, make_scene_callback(btn_name))

    controller.on_control("shift", on_shift_button)
    print("   ✓ Registered callbacks for fader control, navigation, scene, and shift buttons")

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
    print(f"  - 8 fader control buttons (volume, pan, send, device) + navigation (up, down, left, right)")
    print(f"  - 8 scene buttons (clip, solo, mute, rec, select, drum, note, stop_all)")
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
    print("    * Row 4: MOMENTARY mode - lights only while pressed!")
    print("    * Row 5: Different dark colors when OFF")
    print("    * Each row demonstrates different control types and LED modes")
    print("  - Move faders to see continuous values (0-127)")
    print("    * Initial positions are discovered on startup (shown above)")
    print("    * Faders 1-8 are channel faders")
    print("    * Fader 9 is the master fader")
    print("  - Press fader control buttons (volume, pan, send, device) - red LEDs")
    print("  - Press navigation buttons (up, down, left, right) - red LEDs")
    print("  - Press scene buttons (clip, solo, mute, rec, select, drum, note, stop_all) - green LEDs")
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