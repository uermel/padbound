#!/usr/bin/env python3
"""
Demo script for Xjam MIDI Controller.

This script demonstrates:
- Setting up a configuration for the 3 banks
- Connecting to the controller (auto-configures channels for bank detection)
- Registering callbacks for pads, knobs, and bank changes
- Processing and printing MIDI events in real-time

The Xjam supports:
- 16 velocity-sensitive pads per bank (3 banks = 48 pads total)
- 6 endless rotary encoders per bank (3 banks = 18 knobs total)
- Global toggle/momentary mode for all pads
- Automatic bank detection via MIDI channel

IMPORTANT: The Xjam does NOT support LED control from software.
LED colors are determined by pad mode:
  - Green: Note mode (default)
  - Yellow: CC mode
  - Red: Program Change mode
  - Off: MMC mode
"""

import logging
import time

from padbound.config import BankConfig, ControllerConfig
from padbound.controller import Controller
from padbound.controls import ControlState, ControlType
from padbound.logging_config import get_logger, set_module_level, setup_logging
from padbound.plugins.xjam import XjamPlugin

# Set up rich logging to see what's happening
setup_logging(level=logging.INFO)

logger = get_logger(__name__)

# Enable debug logging for specific modules to see MIDI input
set_module_level("padbound.controller", logging.DEBUG)
set_module_level("padbound.midi_io", logging.DEBUG)


def create_example_config() -> ControllerConfig:
    """
    Create an example configuration for the Xjam.

    The Xjam has unique characteristics:
    - NO LED control from software (controller manages LEDs internally)
    - Global toggle_mode affects ALL pads across ALL banks
    - 3 banks (Green, Yellow, Red) with 16 pads + 6 knobs each

    Since we can't control LEDs, the config is simpler than other controllers.
    We only need to set the global toggle_mode.

    Note: The plugin configures each bank to use a different MIDI channel
    (1, 2, 3) for automatic bank detection.
    """
    config = ControllerConfig(
        banks={
            # Bank 1 (Green) - Toggle mode enabled
            "bank_1": BankConfig(
                controls={},  # No per-control config needed (no LED control)
                toggle_mode=True,  # Pads toggle on/off
            ),
            # Bank 2 (Yellow) - Toggle mode enabled
            "bank_2": BankConfig(
                controls={},
                toggle_mode=True,
            ),
            # Bank 3 (Red) - Toggle mode enabled
            "bank_3": BankConfig(
                controls={},
                toggle_mode=True,
            ),
        },
    )

    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events."""
    # Extract pad number and bank from control_id (e.g., "pad_5@bank_2")
    parts = control_id.split("@")
    pad_part = parts[0]  # "pad_5"
    bank_part = parts[1] if len(parts) > 1 else "?"  # "bank_2"

    pad_num = pad_part.split("_")[1]
    bank_num = bank_part.split("_")[1] if "_" in bank_part else "?"

    status = "ON " if state.is_on else "off"
    print(f"[PAD {pad_num:>2s}] Bank {bank_num} -> {status} velocity={state.value:3d}")


def on_knob_change(control_id: str, state: ControlState):
    """Callback for knob events."""
    # Extract knob number and bank from control_id (e.g., "knob_3@bank_1")
    parts = control_id.split("@")
    knob_part = parts[0]  # "knob_3"
    bank_part = parts[1] if len(parts) > 1 else "?"  # "bank_1"

    knob_num = knob_part.split("_")[1]
    bank_num = bank_part.split("_")[1] if "_" in bank_part else "?"

    bar = "█" * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[KNOB {knob_num}] Bank {bank_num} {state.value:3d}/127 [{bar:<31s}]")


def on_bank_change(bank_id: str):
    """Callback for bank changes."""
    bank_num = bank_id.split("_")[1] if "_" in bank_id else "?"
    bank_colors = {"1": "Green", "2": "Yellow", "3": "Red"}
    color = bank_colors.get(bank_num, "Unknown")

    print(f"\n{'='*60}")
    print(f"[BANK SWITCH] Switched to {bank_id} ({color})")
    print(f"{'='*60}\n")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "=" * 60)
    print("Xjam MIDI Controller Demo")
    print("=" * 60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   Configuration created for all 3 banks:")
    print("      - Bank 1 (Green):  Toggle mode, Channel 1")
    print("      - Bank 2 (Yellow): Toggle mode, Channel 2")
    print("      - Bank 3 (Red):    Toggle mode, Channel 3")
    print("")
    print("   NOTE: LED colors are controlled by the hardware, not software!")
    print("         Green=Note, Yellow=CC, Red=PC, Off=MMC")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = XjamPlugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Type-specific callbacks (for all pads and knobs)
    controller.on_type(ControlType.TOGGLE, on_pad_change)
    controller.on_type(ControlType.MOMENTARY, on_pad_change)
    controller.on_type(ControlType.CONTINUOUS, on_knob_change)
    print("   Registered callbacks for pads (TOGGLE/MOMENTARY) and knobs (CONTINUOUS)")

    # Bank change callback
    controller.on_bank_change(ControlType.TOGGLE, on_bank_change)
    print("   Registered bank change callback")

    # Global callback for everything
    controller.on_global(on_any_control)
    print("   Registered global callback")

    # Connect to controller
    print("\n4. Connecting to controller...")
    print("   (This will configure all banks to use different MIDI channels)")
    try:
        controller.connect()
        print("   Connected successfully!")
    except IOError as e:
        print(f"   Failed to connect: {e}")
        print("\nMake sure your Xjam is connected via USB.")
        return

    # Print controller info
    print("\n" + "=" * 60)
    print("Controller Information:")
    print("=" * 60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.PAD_COUNT} pads x {plugin.BANK_COUNT} banks = {plugin.PAD_COUNT * plugin.BANK_COUNT} pads")
    print(f"  - {plugin.KNOB_COUNT} knobs x {plugin.BANK_COUNT} banks = {plugin.KNOB_COUNT * plugin.BANK_COUNT} knobs")

    # Print pad layout
    print("\n" + "=" * 60)
    print("Pad Layout (16 pads per bank):")
    print("=" * 60)
    print("Default Note Assignments (Bank 1):")
    print("  Pad 1-8:  35, 37, 39, 40, 42, 44, 46, 48")
    print("  Pad 9-16: 36, 38, 41, 43, 45, 47, 49, 51")
    print("")
    print("Bank Colors (hardware-controlled):")
    print("  Bank 1: Green LEDs  (Note mode)")
    print("  Bank 2: Yellow LEDs (CC mode)")
    print("  Bank 3: Red LEDs    (PC mode)")

    # Main event loop
    print("\n" + "=" * 60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("=" * 60)
    print("\nTry:")
    print("  - Press pads to trigger notes (toggle on/off)")
    print("    * Velocity is reported based on strike force")
    print("    * LED colors indicate pad mode (hardware-managed):")
    print("      Green=Note, Yellow=CC, Red=PC, Off=MMC")
    print("  - Turn knobs to see continuous values (0-127)")
    print("    * Knobs 1-6 send CC 28-33 by default")
    print("  - Switch banks on the hardware:")
    print("    * Bank 1 (Green)  -> MIDI Channel 1")
    print("    * Bank 2 (Yellow) -> MIDI Channel 2")
    print("    * Bank 3 (Red)    -> MIDI Channel 3")
    print("")
    print("NOTE: This controller does NOT support LED control from software.")
    print("      LEDs are managed internally based on the pad's mode setting.")
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
