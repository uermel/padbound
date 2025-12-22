#!/usr/bin/env python3
"""
Demo script for AKAI LPD8 MK2 MIDI Controller.

This script demonstrates:
- Setting up a configuration with custom control types and colors
- Connecting to the controller
- Registering callbacks for different event types
- Processing and printing MIDI events in real-time
"""

import logging
import time
from padbound.controller import Controller
from padbound.plugins.akai_lpd8_mk2 import AkaiLPD8MK2Plugin
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
    Create an example configuration for the LPD8 with all 4 banks configured.

    This configuration demonstrates:
    - Bank 1: Rainbow gradient (TOGGLE mode) - for triggering samples
    - Bank 2: Warm colors (TOGGLE mode) - for effects/parameters
    - Bank 3: Cool colors (MOMENTARY mode) - for momentary triggers
    - Bank 4: Monochrome levels (TOGGLE mode) - for mixing/levels

    Each bank has different LED colors that are programmed into device memory.
    When you switch programs on the LPD8, the colors change to match the bank.

    Note: LPD8 applies toggle_mode globally per bank (all 8 pads share the same
    toggle/momentary behavior). Use BankConfig.toggle_mode to set this.
    """
    config = ControllerConfig(
        banks={
            # Bank 1 - Rainbow spectrum (TOGGLE mode - default)
            "bank_1": BankConfig(
                toggle_mode=True,  # All pads toggle on/off
                controls={
                    "pad_1": ControlConfig(type=ControlType.TOGGLE, color="red"),
                    "pad_2": ControlConfig(type=ControlType.TOGGLE, color="orange"),
                    "pad_3": ControlConfig(type=ControlType.TOGGLE, color="yellow"),
                    "pad_4": ControlConfig(type=ControlType.TOGGLE, color="green"),
                    "pad_5": ControlConfig(type=ControlType.TOGGLE, color="cyan"),
                    "pad_6": ControlConfig(type=ControlType.TOGGLE, color="blue"),
                    "pad_7": ControlConfig(type=ControlType.TOGGLE, color="purple"),
                    "pad_8": ControlConfig(type=ControlType.TOGGLE, color="magenta"),
                }
            ),

            # Bank 2 - Warm colors (TOGGLE mode)
            "bank_2": BankConfig(
                toggle_mode=True,
                controls={
                    "pad_1": ControlConfig(type=ControlType.TOGGLE, color="red"),
                    "pad_2": ControlConfig(type=ControlType.TOGGLE, color="red"),
                    "pad_3": ControlConfig(type=ControlType.TOGGLE, color="orange"),
                    "pad_4": ControlConfig(type=ControlType.TOGGLE, color="orange"),
                    "pad_5": ControlConfig(type=ControlType.TOGGLE, color="yellow"),
                    "pad_6": ControlConfig(type=ControlType.TOGGLE, color="yellow"),
                    "pad_7": ControlConfig(type=ControlType.TOGGLE, color="pink"),
                    "pad_8": ControlConfig(type=ControlType.TOGGLE, color="pink"),
                }
            ),

            # Bank 3 - Cool colors (MOMENTARY mode - pads only light while held)
            "bank_3": BankConfig(
                toggle_mode=False,  # Momentary: ON while pressed, OFF when released
                controls={
                    "pad_1": ControlConfig(type=ControlType.MOMENTARY, color="cyan"),
                    "pad_2": ControlConfig(type=ControlType.MOMENTARY, color="cyan"),
                    "pad_3": ControlConfig(type=ControlType.MOMENTARY, color="blue"),
                    "pad_4": ControlConfig(type=ControlType.MOMENTARY, color="blue"),
                    "pad_5": ControlConfig(type=ControlType.MOMENTARY, color="teal"),
                    "pad_6": ControlConfig(type=ControlType.MOMENTARY, color="teal"),
                    "pad_7": ControlConfig(type=ControlType.MOMENTARY, color="green"),
                    "pad_8": ControlConfig(type=ControlType.MOMENTARY, color="green"),
                }
            ),

            # Bank 4 - Monochrome intensity levels (TOGGLE mode)
            "bank_4": BankConfig(
                toggle_mode=True,
                controls={
                    "pad_1": ControlConfig(type=ControlType.TOGGLE, color="rgb(32, 32, 32)"),
                    "pad_2": ControlConfig(type=ControlType.TOGGLE, color="rgb(64, 64, 64)"),
                    "pad_3": ControlConfig(type=ControlType.TOGGLE, color="rgb(96, 96, 96)"),
                    "pad_4": ControlConfig(type=ControlType.TOGGLE, color="rgb(128, 128, 128)"),
                    "pad_5": ControlConfig(type=ControlType.TOGGLE, color="rgb(160, 160, 160)"),
                    "pad_6": ControlConfig(type=ControlType.TOGGLE, color="rgb(192, 192, 192)"),
                    "pad_7": ControlConfig(type=ControlType.TOGGLE, color="rgb(224, 224, 224)"),
                    "pad_8": ControlConfig(type=ControlType.TOGGLE, color="white"),
                }
            ),
        }
    )

    return config


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events."""
    mode = "TOGGLE" if state.is_on else "toggle"
    if "@bank_3" in control_id:
        mode = "MOMENTARY" if state.is_on else "momentary"
    print(f"[PAD] {control_id:20s} -> {mode:10s} is_on={state.is_on}, color={state.color}")


def on_knob_change(control_id: str, state: ControlState):
    """Callback for knob events."""
    bar = '█' * (state.value // 4)  # Visual bar (0-31 chars)
    print(f"[KNOB] {control_id:20s} {state.value:3d}/127 [{bar:<31s}]")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def on_bank_change(bank_id: str):
    """Callback for bank changes."""
    print(f"\n{'='*60}")
    print(f"[BANK SWITCH] Switched to {bank_id}")
    print(f"{'='*60}\n")


def on_note_signal(control_id: str, state: ControlState):
    """Callback specifically for NOTE signal type."""
    print(f"[SIGNAL:NOTE] {control_id} -> velocity={state.value}")


def on_cc_signal(control_id: str, state: ControlState):
    """Callback specifically for CC signal type."""
    print(f"[SIGNAL:CC] {control_id} -> value={state.value}")


def main():
    """Main demo function."""
    print("\n" + "="*60)
    print("AKAI LPD8 MK2 Demo")
    print("="*60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   ✓ Configuration created for all 4 banks:")
    print("      - Bank 1: Rainbow spectrum (TOGGLE)")
    print("      - Bank 2: Warm colors (TOGGLE)")
    print("      - Bank 3: Cool colors (MOMENTARY)")
    print("      - Bank 4: White gradient (TOGGLE)")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = AkaiLPD8MK2Plugin()
    controller = Controller(plugin=plugin, config=config)
    print(f"   ✓ Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Type-specific callbacks (for all pads and knobs)
    controller.on_type(ControlType.TOGGLE, on_pad_change)
    controller.on_type(ControlType.MOMENTARY, on_pad_change)
    controller.on_type(ControlType.CONTINUOUS, on_knob_change)
    print("   ✓ Registered callbacks for pads (TOGGLE/MOMENTARY) and knobs (CONTINUOUS)")

    # Signal-type specific callbacks (for pads only, to demonstrate signal routing)
    controller.on_type(ControlType.TOGGLE, on_note_signal, signal_type="note")
    controller.on_type(ControlType.TOGGLE, on_cc_signal, signal_type="cc")
    controller.on_type(ControlType.MOMENTARY, on_note_signal, signal_type="note")
    controller.on_type(ControlType.MOMENTARY, on_cc_signal, signal_type="cc")
    print("   ✓ Registered signal-specific callbacks (NOTE and CC for all pad types)")

    # Global callback for everything
    controller.on_global(on_any_control)
    print("   ✓ Registered global callback")

    # Bank change callback
    controller.on_bank_change(ControlType.TOGGLE, on_bank_change)
    print("   ✓ Registered bank change callback")

    # Connect to controller
    print("\n4. Connecting to controller...")
    try:
        controller.connect()
        print(f"   ✓ Connected successfully!")
    except IOError as e:
        print(f"   ✗ Failed to connect: {e}")
        print("\nMake sure your LPD8 is connected via USB.")
        return

    # Print controller info
    print("\n" + "="*60)
    print("Controller Information:")
    print("="*60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {AkaiLPD8MK2Plugin.PAD_COUNT} pads × {AkaiLPD8MK2Plugin.BANK_COUNT} banks = {AkaiLPD8MK2Plugin.PAD_COUNT * AkaiLPD8MK2Plugin.BANK_COUNT} pads")
    print(f"  - {AkaiLPD8MK2Plugin.KNOB_COUNT} knobs × {AkaiLPD8MK2Plugin.BANK_COUNT} banks = {AkaiLPD8MK2Plugin.KNOB_COUNT * AkaiLPD8MK2Plugin.BANK_COUNT} knobs")

    # Main event loop
    print("\n" + "="*60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("="*60)
    print("\nTry:")
    print("  - Press pads to toggle them on/off (they light up with configured colors)")
    print("  - Turn knobs to see continuous values (0-127)")
    print("  - Press PROG button to switch banks - watch the colors change!")
    print("    * Bank 1 (Prog 1): Rainbow spectrum")
    print("    * Bank 2 (Prog 2): Warm reds/oranges/yellows")
    print("    * Bank 3 (Prog 3): Cool blues/cyans (MOMENTARY - only lights while held)")
    print("    * Bank 4 (Prog 4): White intensity gradient")
    print("  - Try NOTE, CC, or PC modes (if configured on hardware)")
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