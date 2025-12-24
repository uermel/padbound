#!/usr/bin/env python3
"""
Demo script for Behringer X-Touch Mini MIDI Controller.

This script demonstrates:
- Setting up a configuration for the 2 banks (Layer A, Layer B)
- Connecting to the controller (initializes knobs to center, clears LEDs)
- Registering callbacks for pads, knob-buttons, knobs, fader, and bank changes
- Processing and printing MIDI events in real-time

The X-Touch Mini supports:
- 16 velocity-sensitive pads per bank (2 banks = 32 pads total)
- 8 rotary encoders per bank (2 banks = 16 knobs total)
- 8 knob-buttons (push encoders) per bank (2 banks = 16 knob-buttons total)
- 1 fader per bank (2 banks = 2 faders total)
- LED feedback for pads and knob-buttons
- Automatic bank detection via note/CC range

LED Feedback:
- Pads: Toggle on/off with LED reflecting state
- Knob-buttons: LED lights while pressed (momentary)
- Knobs: LED rings auto-reflect encoder position
"""

import logging
import time
from padbound.controller import Controller
from padbound.plugins.behringer_x_touch_mini import BehringerXTouchMiniPlugin
from padbound.config import ControllerConfig, BankConfig, ControlConfig
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
    Create an example configuration for the X-Touch Mini.

    The X-Touch Mini has:
    - 2 banks (Layer A, Layer B)
    - LED feedback for pads (software-managed toggle or momentary)
    - LED feedback for knob-buttons (momentary, lights while pressed)

    Layer A configuration:
    - Row 1 (pads 1-8): TOGGLE mode - press to turn on, press again to turn off
    - Row 2 (pads 9-16): MOMENTARY mode - LED lights only while pressed

    Layer B: All default (TOGGLE mode)
    """
    # Build Layer A controls - mix of toggle and momentary
    layer_a_controls = {}

    # Row 1 (pads 1-8): TOGGLE mode (default, but explicit for clarity)
    for i in range(1, 9):
        layer_a_controls[f"pad_{i}"] = ControlConfig(
            type=ControlType.TOGGLE,
        )

    # Row 2 (pads 9-16): MOMENTARY mode - lights only while pressed
    for i in range(9, 17):
        layer_a_controls[f"pad_{i}"] = ControlConfig(
            type=ControlType.MOMENTARY,
        )

    config = ControllerConfig(
        banks={
            # Layer A - mix of toggle and momentary pads
            "layer_a": BankConfig(
                controls=layer_a_controls,
            ),

            # Layer B - default toggle mode for all pads
            "layer_b": BankConfig(
                controls={},  # Use defaults
            ),
        }
    )

    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events (TOGGLE mode)."""
    # Extract pad number and bank from control_id (e.g., "pad_5@layer_a")
    parts = control_id.split('@')
    pad_part = parts[0]  # "pad_5"
    layer_part = parts[1] if len(parts) > 1 else "?"  # "layer_a"

    pad_num = pad_part.split('_')[1]
    layer = layer_part.replace('layer_', '').upper()  # "A" or "B"

    status = "ON " if state.is_on else "off"
    print(f"[PAD {pad_num:>2s}] Layer {layer} -> {status}")


def on_knob_button_change(control_id: str, state: ControlState):
    """Callback for knob-button events (MOMENTARY mode)."""
    # Extract knob-button number and bank from control_id (e.g., "knob_button_3@layer_a")
    parts = control_id.split('@')
    btn_part = parts[0]  # "knob_button_3"
    layer_part = parts[1] if len(parts) > 1 else "?"  # "layer_a"

    btn_num = btn_part.split('_')[2]  # "3"
    layer = layer_part.replace('layer_', '').upper()  # "A" or "B"

    status = "PRESSED" if state.is_on else "released"
    print(f"[KNOB BTN {btn_num}] Layer {layer} -> {status}")


def on_knob_change(control_id: str, state: ControlState):
    """Callback for knob events (CONTINUOUS mode)."""
    # Extract knob number and bank from control_id (e.g., "knob_3@layer_a")
    parts = control_id.split('@')
    knob_part = parts[0]  # "knob_3"
    layer_part = parts[1] if len(parts) > 1 else "?"  # "layer_a"

    knob_num = knob_part.split('_')[1]
    layer = layer_part.replace('layer_', '').upper()  # "A" or "B"

    bar = '█' * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[KNOB {knob_num}] Layer {layer} {state.value:3d}/127 [{bar:<31s}]")


def on_fader_change(control_id: str, state: ControlState):
    """Callback for fader events (CONTINUOUS mode)."""
    # Extract bank from control_id (e.g., "fader@layer_a")
    parts = control_id.split('@')
    layer_part = parts[1] if len(parts) > 1 else "?"  # "layer_a"

    layer = layer_part.replace('layer_', '').upper()  # "A" or "B"

    bar = '█' * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[FADER] Layer {layer} {state.value:3d}/127 [{bar:<31s}]")


def on_bank_change(bank_id: str):
    """Callback for bank changes."""
    layer = bank_id.replace('layer_', '').upper()  # "A" or "B"

    print(f"\n{'='*60}")
    print(f"[BANK SWITCH] Switched to Layer {layer}")
    print(f"{'='*60}\n")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "="*60)
    print("Behringer X-Touch Mini Demo")
    print("="*60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   Configuration created for 2 banks:")
    print("      - Layer A:")
    print("          Row 1 (pads 1-8): TOGGLE mode")
    print("          Row 2 (pads 9-16): MOMENTARY mode")
    print("      - Layer B: All pads TOGGLE mode")
    print("")
    print("   LED Feedback:")
    print("      - Toggle pads: LED reflects state (ON/OFF)")
    print("      - Momentary pads: LED lights while pressed")
    print("      - Knob-buttons: LED lights while pressed")
    print("      - Knobs: LED rings auto-reflect encoder position")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = BehringerXTouchMiniPlugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Category-based callbacks
    controller.on_category("pad", on_pad_change)
    print("   Registered callback for pads (TOGGLE)")

    controller.on_category("knob_button", on_knob_button_change)
    print("   Registered callback for knob-buttons (MOMENTARY)")

    controller.on_category("knob", on_knob_change)
    print("   Registered callback for knobs (CONTINUOUS)")

    controller.on_category("fader", on_fader_change)
    print("   Registered callback for fader (CONTINUOUS)")

    # Bank change callback
    controller.on_bank_change(ControlType.TOGGLE, on_bank_change)
    print("   Registered bank change callback")

    # Global callback for everything
    controller.on_global(on_any_control)
    print("   Registered global callback")

    # Connect to controller
    print("\n4. Connecting to controller...")
    print("   (This will initialize knobs to center and clear all LEDs)")
    try:
        controller.connect()
        print(f"   Connected successfully!")
    except IOError as e:
        print(f"   Failed to connect: {e}")
        print("\nMake sure your X-Touch Mini is connected via USB.")
        return

    # Print controller info
    print("\n" + "="*60)
    print("Controller Information:")
    print("="*60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.KNOB_BUTTON_COUNT} knob-buttons x {plugin.BANK_COUNT} banks = {plugin.KNOB_BUTTON_COUNT * plugin.BANK_COUNT} knob-buttons")
    print(f"  - {plugin.PAD_COUNT} pads x {plugin.BANK_COUNT} banks = {plugin.PAD_COUNT * plugin.BANK_COUNT} pads")
    print(f"  - {plugin.KNOB_COUNT} knobs x {plugin.BANK_COUNT} banks = {plugin.KNOB_COUNT * plugin.BANK_COUNT} knobs")
    print(f"  - 1 fader x {plugin.BANK_COUNT} banks = {plugin.BANK_COUNT} faders")

    # Print layout
    print("\n" + "="*60)
    print("Control Layout:")
    print("="*60)
    print("")
    print("  Top row: 8 Rotary Encoders with push-buttons")
    print("           [1] [2] [3] [4] [5] [6] [7] [8]")
    print("           Press = Knob Button (momentary)")
    print("           Turn = Knob (continuous)")
    print("")
    print("  Middle:  16 Pads (2 rows of 8)")
    print("           Row 1: [1] [2] [3] [4] [5] [6] [7] [8]  - TOGGLE")
    print("           Row 2: [9] [10] [11] [12] [13] [14] [15] [16]  - MOMENTARY (Layer A)")
    print("           Toggle = Press to turn on, press again to turn off")
    print("           Momentary = LED lights only while pressed")
    print("")
    print("  Bottom:  Fader (continuous, not motorized)")
    print("")
    print("  Banks:   Layer A / Layer B (hardware button)")
    print("           Bank is auto-detected from MIDI note/CC range")

    # Main event loop
    print("\n" + "="*60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("="*60)
    print("\nTry:")
    print("  - Press row 1 pads (1-8) to toggle on/off (LED stays lit)")
    print("  - Press row 2 pads (9-16) for momentary triggers (LED only while pressed)")
    print("  - Press encoder knobs for momentary triggers")
    print("  - Turn encoders to see continuous values (0-127)")
    print("  - Move the fader to see continuous values")
    print("  - Press Layer A/B button to switch banks")
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
        print("Disconnected from controller")
        print("\nDemo complete!")


if __name__ == "__main__":
    main()
