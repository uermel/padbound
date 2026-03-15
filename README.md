


<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_light.svg">
    <img alt="Padbound" src="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_light.svg">
  </picture>
</p>

<p align="center">
  <a href="https://pypi.org/project/padbound/"><img alt="PyPI" src="https://img.shields.io/pypi/v/padbound"></a>
  <a href="https://pypi.org/project/padbound/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/padbound"></a>
  <a href="https://github.com/uermel/padbound/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/pypi/l/padbound"></a>
</p>

A stateful Python interface for MIDI controllers that abstracts hardware differences behind a unified API with three fundamental control types: **Toggle**, **Momentary**, and **Continuous**.

## Overview

Padbound lets applications work with MIDI controllers using abstract control IDs (`"pad_1"`, `"knob_3"`) and high-level state (on/off, colors, normalized values) instead of raw MIDI messages. A plugin system handles the translation for each controller, so your application code works across different hardware without changes.

## Features

- **Three Control Types** &mdash; Toggle (on/off switch), Momentary (press-and-release trigger), and Continuous (knobs/faders with 0.0&ndash;1.0 range)
- **Progressive State Discovery** &mdash; Continuous controls start in "unknown" state until first interaction, honestly representing hardware limitations
- **Capability-Based API** &mdash; Validates hardware support before attempting operations; strict mode raises errors, permissive mode logs warnings
- **Thread-Safe** &mdash; Immutable state snapshots (Pydantic frozen models) and lock-protected internals for safe concurrent access
- **Plugin Architecture** &mdash; 7 built-in plugins covering popular controllers, with a straightforward base class for adding more
- **Callback System** &mdash; Five callback levels (global, per-control, per-type, per-category, per-bank) with error isolation and signal-type filtering
- **Bank Support** &mdash; Handles hardware-managed bank switching with per-bank configuration
- **LED Feedback** &mdash; Set pad colors (RGB or named), LED animation modes (solid/pulse/blink), and on/off states from code
- **Configuration Hierarchy** &mdash; Per-bank, per-control settings for types, colors, and LED modes with wildcard pattern matching
- **Debug TUI** &mdash; Real-time terminal visualization of controller state via WebSocket

## Installation

Requires **Python 3.12+**.

```bash
pip install padbound
```

For development and debugging tools:

```bash
pip install padbound[debug]   # Debug TUI + WebSocket server
pip install padbound[dev]     # Linting, formatting, notebooks
pip install padbound[test]    # pytest + coverage
pip install padbound[docs]    # MkDocs documentation
```

## Quick Start

```python
from padbound import Controller, ControlType

# Auto-detect and connect to controller
with Controller(plugin='auto', auto_connect=True) as controller:
    # Register callback for a specific pad
    controller.on_control('pad_1', lambda state: print(f"Pad 1: {state.is_on}"))

    # Register callback for all continuous controls (knobs/faders)
    def on_continuous(control_id, state):
        if state.is_discovered:
            print(f"{control_id}: {state.normalized_value:.2f}")
    controller.on_type(ControlType.CONTINUOUS, on_continuous)

    # Main loop
    while True:
        controller.process_events()
```

## Usage

### Callback Registration

Padbound provides five levels of callback registration, from most specific to broadest:

```python
from padbound import Controller, ControlType

with Controller(plugin='auto', auto_connect=True) as controller:
    # Per-control callback — fires only for pad_1
    controller.on_control('pad_1', lambda state: print(f"Pad 1: {state.is_on}"))

    # Per-type callback — fires for all toggles, all continuous, etc.
    controller.on_type(ControlType.TOGGLE, lambda cid, state: print(f"{cid} toggled"))

    # Per-category callback — fires for all controls in a category (e.g., transport)
    controller.on_category('transport', lambda cid, state: print(f"Transport: {cid}"))

    # Global callback — fires for every control change
    controller.on_global(lambda cid, state: print(f"Any control: {cid}"))

    # Bank change callback — fires when a bank switches
    controller.on_bank_change('pad', lambda bank_id: print(f"Switched to {bank_id}"))

    while True:
        controller.process_events()
```

Callbacks can also filter by MIDI signal type for controllers with multi-signal pads:

```python
# Only fires for note messages, not CC or program change
controller.on_control('pad_1', my_callback, signal_type='note')
```

All callbacks are error-isolated — if one callback raises an exception, other callbacks and the main loop continue unaffected.

### Setting Control State (LED Feedback)

```python
from padbound import Controller, StateUpdate

with Controller(plugin='auto', auto_connect=True) as controller:
    # Set a single pad's LED color and state
    update = StateUpdate(is_on=True, color='red')
    if controller.can_set_state('pad_1', update):
        controller.set_state('pad_1', update)

    # Batch update — plugin can optimize into fewer MIDI messages
    controller.set_states([
        ('pad_1', StateUpdate(is_on=True, color='red')),
        ('pad_2', StateUpdate(is_on=True, color='green')),
        ('pad_3', StateUpdate(is_on=False)),
    ])

    # Query current state
    state = controller.get_state('pad_1')
    if state:
        print(f"Pad 1 is {'on' if state.is_on else 'off'}, color: {state.color}")
```

### Configuration

Configure control types, colors, and LED modes per bank and per control:

```python
from padbound import Controller, ControllerConfig, BankConfig, ControlConfig, ControlType

config = ControllerConfig(banks={
    'bank_1': BankConfig(controls={
        'pad_1': ControlConfig(type=ControlType.TOGGLE, on_color='red', off_color='dim_red'),
        'pad_2': ControlConfig(type=ControlType.MOMENTARY, on_color='green'),
        'pad_*': ControlConfig(on_color='blue'),  # Wildcard — applies to all unmatched pads
    })
})

with Controller(plugin='auto', config=config, auto_connect=True) as controller:
    while True:
        controller.process_events()
```

Configuration can also be updated at runtime with `controller.reconfigure(new_config)`.

### Progressive Discovery

Continuous controls (knobs, faders, encoders) have no way to report their physical position until the user moves them. Padbound makes this explicit:

```python
state = controller.get_state('knob_1')
if state.is_discovered:
    print(f"Knob 1 value: {state.normalized_value:.2f}")
else:
    print("Knob 1: position unknown (not yet moved)")

# Get lists of discovered/undiscovered controls
print("Ready:", controller.get_discovered_controls())
print("Waiting:", controller.get_undiscovered_controls())
```

### Strict vs. Permissive Mode

```python
# Strict mode (default) — raises CapabilityError for unsupported operations
controller = Controller(plugin='auto', strict_mode=True)

# Permissive mode — logs warnings instead of raising
controller = Controller(plugin='auto', strict_mode=False)
```

### Debug TUI

Padbound includes a real-time terminal UI for visualizing controller state. Enable the WebSocket server on the controller, then connect with the TUI client:

```python
# In your application
controller = Controller(plugin='auto', auto_connect=True, debug_server=True)
print(f"Debug URL: {controller.debug_url}")
```

```bash
# In another terminal
padbound-debug --url ws://127.0.0.1:8765
```

The TUI displays a live view of all pads, knobs, faders, and buttons with real-time state updates, colors, and bank information.

## Supported Controllers

| Controller | Pads | Knobs/Encoders | Faders | Buttons | RGB LEDs | LED Modes | Banks | Persistent Config | Special Features |
|---|---|---|---|---|---|---|---|---|---|
| **AKAI LPD8 MK2** | 8 | 8 knobs | — | — | Full | Solid | 4 (HW) | SysEx | Multi-signal pads (NOTE/CC/PC) |
| **AKAI APC mini MK2** | 64 | — | 9 | 17 | Full | Solid/Pulse/Blink | 1 | — | Fader position discovery |
| **AKAI MPD218** | 16 | 6 encoders | — | 6 | — | — | 3+3 (HW) | SysEx | Multi-signal pads, 16 presets, pressure sensing |
| **PreSonus ATOM** | 16 | 4 encoders | — | 20 | Full | Solid/Pulse/Blink | 8 (HW) | — | Native Control mode, encoder acceleration |
| **Synido TempoPad P16** | 16 | 4 encoders | — | 6 | Full | — | 3 (HW) | SysEx | RGB color config via SysEx, dual working modes |
| **Xjam** | 16 | 6 knobs | — | — | — | — | 3 (HW) | SysEx | Multi-signal pads, multiple encoder modes |
| **X-Touch Mini** | 16 | 8 + buttons | 1 | — | Single | Solid | 2 (HW) | — | Auto-reflecting encoder rings |

**Legend:**
- **HW** = Hardware-managed bank switching
- **RGB LEDs**: Full = true RGB color support, Single = on/off only, — = hardware-managed or none
- **LED Modes**: Animation/behavior modes supported from software
- **Persistent Config**: Device stores configuration in non-volatile memory via SysEx

### Detailed Controller Information

<details>
<summary><b>AKAI LPD8 MK2</b></summary>

**Control Surface**: 8 RGB pads + 8 knobs\
**Banks**: 4 banks with hardware-based switching\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via SysEx
- **Pad LED Modes**: Solid
- **Pad Modes**: Toggle or momentary (global per bank)
- **Knob Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx)
</details>

<details>
<summary><b>AKAI APC mini MK2</b></summary>

**Control Surface**: 8x8 RGB pad grid + 9 faders + 17 buttons\
**Banks**: Single layer\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via SysEx
- **Pad LED Modes**: Solid, pulse, blink
- **Pad Modes**: Toggle or momentary (per pad)
- **Fader Feedback**: None (read-only, initial position discovered)
- **Button LED Feedback**: Single-color (red for track, green for scene)
- **Configuration**: Volatile
</details>

<details>
<summary><b>AKAI MPD218</b></summary>

**Control Surface**: 16 velocity/pressure-sensitive pads + 6 encoders + 6 buttons\
**Banks**: 3 pad banks + 3 control banks with hardware switching (48 pads, 18 knobs total)\
**Capabilities**:
- **Pad LED Feedback**: None (red backlit, hardware-managed)
- **Pad Modes**: Toggle or momentary (per pad via SysEx preset)
- **Pad Signals**: NOTE, Program Change, or Bank messages
- **Encoder Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx, 16 presets)
</details>

<details>
<summary><b>PreSonus ATOM</b></summary>

**Control Surface**: 16 RGB pads (4x4) + 4 encoders + 20 buttons\
**Banks**: 8 hardware-managed banks (not software-accessible)\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via Native Control mode
- **Pad LED Modes**: Solid, pulse, breathe
- **Pad Modes**: Toggle or momentary (per pad)
- **Encoder Type**: Relative with acceleration
- **Encoder Feedback**: None (read-only)
- **Button LED Feedback**: Single-color
- **Configuration**: Volatile
</details>

<details>
<summary><b>Synido TempoPad P16</b></summary>

**Control Surface**: 16 RGB pads (4x4) + 4 encoders + 6 transport buttons\
**Banks**: 3 pad/encoder banks with hardware switching\
**Capabilities**:
- **Pad LED Feedback**: RGB colors via SysEx (stored in device memory)
- **Pad LED State**: Hardware-managed (no real-time software control)
- **Pad Modes**: Toggle or momentary (per pad in user-defined mode)
- **Encoder Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx)
- **Working Modes**: Keyboard mode (red LED) and User-Defined mode (green LED)
</details>

<details>
<summary><b>Xjam (ESI/Artesia Pro)</b></summary>

**Control Surface**: 16 pads + 6 knobs per bank\
**Banks**: 3 banks (Green, Yellow, Red) with synchronized pad/knob switching\
**Capabilities**:
- **Pad LED Feedback**: None (hardware-managed)
- **Pad Modes**: Toggle or momentary (global)
- **Knob Type**: Configurable (absolute or 3 relative modes)
- **Knob Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx)
</details>

<details>
<summary><b>Behringer X-Touch Mini</b></summary>

**Control Surface**: 8 encoders with buttons + 16 pads + 1 fader\
**Banks**: 2 layers (A, B) with hardware switching\
**Capabilities**:
- **Pad LED Feedback**: Single-color
- **Pad LED Modes**: Solid
- **Pad Modes**: Toggle or momentary (per pad)
- **Encoder Type**: Absolute
- **Encoder Feedback**: LED ring auto-reflects value
- **Encoder Button Feedback**: Single-color
- **Fader Feedback**: None (read-only)
- **Configuration**: Volatile
</details>

## Writing a Plugin

To add support for a new controller, subclass `ControllerPlugin` and implement the required methods:

```python
from padbound import ControllerPlugin, ControlDefinition, plugin_registry
from padbound.plugin import MIDIMapping

class MyControllerPlugin(ControllerPlugin):
    port_patterns = ["My Controller"]  # For auto-detection from MIDI port names

    @property
    def name(self) -> str:
        return "My Controller"

    def get_control_definitions(self) -> list[ControlDefinition]:
        # Define all pads, knobs, buttons with their capabilities
        ...

    def get_input_mappings(self) -> dict[str, MIDIMapping]:
        # Map MIDI messages to control IDs
        ...

    def init(self, send_message, receive_message):
        # Initialize controller to a known state
        ...

    def translate_feedback_batch(self, updates):
        # Convert state updates to MIDI messages for LED feedback
        ...

# Register the plugin
plugin_registry.register(MyControllerPlugin)
```

See `src/padbound/plugins/example_midi_controller.py` for a complete reference implementation.

## Examples

The `examples/` directory contains runnable demos for each supported controller:

- `demo_akai_lpd8.py` &mdash; AKAI LPD8 MK2
- `demo_akai_apc_mini_mk2.py` &mdash; AKAI APC mini MK2
- `demo_akai_mpd218.py` &mdash; AKAI MPD218
- `demo_presonus_atom.py` &mdash; PreSonus ATOM
- `demo_synido_tempopad.py` &mdash; Synido TempoPad P16
- `demo_xjam.py` &mdash; Xjam
- `demo_x_touch_mini.py` &mdash; Behringer X-Touch Mini

## Acknowledgements

Some protocol information for supported controllers was gathered from:
- **AKAI LPD8 MK2**: [stephensrmmartin/lpd8mk2](https://github.com/stephensrmmartin/lpd8mk2)
- **PreSonus ATOM**: [EMATech/AtomCtrl](https://github.com/EMATech/AtomCtrl)
- **Behringer X-Touch Mini**: [AndreasPantle/X-Touch-Mini-HandsOn](https://github.com/AndreasPantle/X-Touch-Mini-HandsOn)

## License

MIT License
