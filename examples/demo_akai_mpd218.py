#!/usr/bin/env python3
"""
Demo script for AKAI MPD218 MIDI Pad Controller.

This script demonstrates:
- Setting up a configuration for the 4x4 pad grid with 3 banks
- Connecting to the controller
- Registering callbacks for pads (by category) and knobs (by type)
- Processing and printing MIDI events in real-time
- Bank-aware control handling (pad_1@bank_a, etc.)

The AKAI MPD218 features:
- 16 velocity- and pressure-sensitive pads with red backlit LEDs
- 3 pad banks (A, B, C) accessible via Pad Bank button (48 total pads)
- 6 360-degree endless rotary knobs
- 3 control banks (A, B, C) accessible via Control Bank button (18 total knobs)
- 16 presets stored in device memory

Important: The MPD218 has RED LEDs only (not RGB), and they are hardware-managed.
Software cannot control LED state or color - the LEDs respond to pad presses
automatically based on device firmware.
"""

import logging
import time

from padbound.config import BankConfig, ControlConfig, ControllerConfig
from padbound.controller import Controller
from padbound.controls import ControlType
from padbound.logging_config import get_logger, set_module_level, setup_logging
from padbound.plugins.akai_mpd218 import AkaiMPD218Plugin

# Import ControlState from the correct location
try:
    from padbound.state import ControlState
except ImportError:
    from padbound.controls import ControlState

# Set up rich logging to see what's happening
setup_logging(level=logging.INFO)

logger = get_logger(__name__)

# Enable debug logging for specific modules to see MIDI input
set_module_level("padbound.controller", logging.DEBUG)
set_module_level("padbound.midi_io", logging.DEBUG)


def create_example_config() -> ControllerConfig:
    """
    Create an example configuration for the MPD218.

    Note: Since the MPD218 has hardware-managed red LEDs (no software control),
    color settings have no visual effect. However, we can configure pad behavior
    (TOGGLE vs MOMENTARY) which affects state tracking and is programmed into
    the device via SysEx.

    The 4x4 grid layout (pad numbering, same for all banks):
        13  14  15  16   (top row)
         9  10  11  12
         5   6   7   8
         1   2   3   4   (bottom row)

    This config sets:
    - Bank A: All pads as TOGGLE (press to turn on, press again to turn off)
    - Bank B: All pads as MOMENTARY (on while pressed, off when released)
    - Bank C: Mixed - bottom rows TOGGLE, top row MOMENTARY
    """
    # Build Bank C controls - mixed TOGGLE/MOMENTARY
    bank_c_controls = {}
    # Pads 1-12 (rows 1-3): TOGGLE
    for pad_num in range(1, 13):
        bank_c_controls[f"pad_{pad_num}"] = ControlConfig(type=ControlType.TOGGLE)
    # Pads 13-16 (row 4, top): MOMENTARY
    for pad_num in range(13, 17):
        bank_c_controls[f"pad_{pad_num}"] = ControlConfig(type=ControlType.MOMENTARY)

    return ControllerConfig(
        banks={
            # Bank A: All pads TOGGLE (using toggle_mode for entire bank)
            "bank_a": BankConfig(
                toggle_mode=True,
                controls={},
            ),
            # Bank B: All pads MOMENTARY (toggle_mode=False is default)
            "bank_b": BankConfig(
                toggle_mode=False,
                controls={},
            ),
            # Bank C: Mixed - per-pad control config
            "bank_c": BankConfig(
                controls=bank_c_controls,
            ),
        },
    )


def on_pad_change(control_id: str, state: ControlState):
    """Callback for pad events (both TOGGLE and MOMENTARY)."""
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
    """Callback for knob events (CONTINUOUS)."""
    # Parse control_id: "knob_1@bank_a" -> knob_num=1, bank="bank_a"
    parts = control_id.split("@")
    knob_part = parts[0]  # "knob_1"
    bank_part = parts[1] if len(parts) > 1 else "unknown"  # "bank_a"

    knob_num = int(knob_part.split("_")[1])
    bank_letter = bank_part.replace("bank_", "").upper()

    value = state.value if state.value is not None else 0
    bar = "█" * (value // 4)  # Visual bar (0-31 chars)
    print(f"[KNOB {bank_letter}-{knob_num}] {value:3d}/127 [{bar:<31s}]")


def on_pad_bank_change(bank_id: str):
    """Callback for pad bank changes."""
    bank_letter = bank_id.replace("bank_", "").upper()
    print(f"\n{'='*60}")
    print(f"[PAD BANK SWITCH] Switched to {bank_id} (Bank {bank_letter})")
    print(f"{'='*60}\n")


def on_knob_bank_change(bank_id: str):
    """Callback for knob bank changes."""
    bank_letter = bank_id.replace("bank_", "").upper()
    print(f"\n{'='*60}")
    print(f"[KNOB BANK SWITCH] Switched to {bank_id} (Bank {bank_letter})")
    print(f"{'='*60}\n")


def on_any_control(control_id: str, state: ControlState):
    """Callback for any control change (for debugging)."""
    logger.debug(f"[ANY] {control_id} changed: {state}")


def main():
    """Main demo function."""
    print("\n" + "=" * 60)
    print("AKAI MPD218 Demo")
    print("=" * 60)

    # Create configuration
    print("\n1. Creating configuration...")
    config = create_example_config()
    print("   Configuration created with 3-bank pad/knob layout:")
    print("   - Bank A: All 16 pads as TOGGLE")
    print("   - Bank B: All 16 pads as MOMENTARY")
    print("   - Bank C: Pads 1-12 TOGGLE, Pads 13-16 MOMENTARY")
    print("")
    print("   Pad layout (same for all banks):")
    print("       13  14  15  16   (top row)")
    print("        9  10  11  12")
    print("        5   6   7   8")
    print("        1   2   3   4   (bottom row)")
    print("")
    print("   Note: LED colors are red-only and hardware-managed")

    # Create controller instance
    print("\n2. Creating controller instance...")
    plugin = AkaiMPD218Plugin()
    controller = Controller(plugin=plugin, config=config, debug_server=True)
    print(f"   Controller created: {plugin.name}")

    # Register callbacks
    print("\n3. Registering callbacks...")

    # Category-based callback for all pads
    controller.on_category("pad", on_pad_change)
    print("   Registered callback for pads (category='pad')")

    # Type-based callback for knobs
    controller.on_type(ControlType.CONTINUOUS, on_knob_change)
    print("   Registered callback for knobs (type=CONTINUOUS)")

    # Bank change callbacks (separate for pads and knobs)
    controller.on_bank_change("pad", on_pad_bank_change)
    controller.on_bank_change("knob", on_knob_bank_change)
    print("   Registered pad and knob bank change callbacks")

    # Global callback for debugging
    controller.on_global(on_any_control)
    print("   Registered global callback for debugging")

    # Connect to controller
    print("\n4. Connecting to controller...")
    try:
        controller.connect()
        print("   Connected successfully!")
    except IOError as e:
        print(f"   Failed to connect: {e}")
        print("\nMake sure your AKAI MPD218 is connected via USB.")
        return

    # Print controller info
    print("\n" + "=" * 60)
    print("Controller Information:")
    print("=" * 60)
    print(f"Plugin: {controller.plugin.name}")
    print(f"Controls: {len(controller.get_controls())} total")
    print(f"  - {plugin.PAD_TOTAL} pads ({plugin.PAD_COUNT} per bank x {plugin.PAD_BANKS} banks)")
    print(f"  - {plugin.KNOB_TOTAL} knobs ({plugin.KNOB_COUNT} per bank x {plugin.KNOB_BANKS} banks)")

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

    # Main event loop
    print("\n" + "=" * 60)
    print("Listening for events... (Press Ctrl+C to exit)")
    print("=" * 60)
    print("\nTry:")
    print("  - Press pads to see note events")
    print("    * Bank A: Notes 36-51 (C2-D#3) - all TOGGLE")
    print("    * Bank B: Notes 52-67 (E3-G4) - all MOMENTARY")
    print("    * Bank C: Notes 68-83 (G#4-B5) - mixed")
    print("  - Turn knobs to see CC values (0-127)")
    print("    * Bank A: CCs 3, 9, 12-15")
    print("    * Bank B: CCs 16-21")
    print("    * Bank C: CCs 22-27")
    print("  - Use Pad Bank/Ctrl Bank buttons to switch banks")
    print("    * Bank switching is physical (on device)")
    print("    * Software detects bank from note/CC range")
    print("")
    print("Note: Red backlit LEDs are hardware-managed.")
    print("      Software cannot control LED state or color.")
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
