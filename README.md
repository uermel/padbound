

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_light.svg">
    <img alt="Padbound" src="https://raw.githubusercontent.com/uermel/padbound/refs/heads/main/assets/logo_light.svg">
  </picture>
</p>


A general, stateful python interface for MIDI controllers that abstracts hardware differences behind a simple API.

## Overview

Padbound provides a high-level abstraction over MIDI controllers, allowing applications to work with three fundamental
control types (toggles, momentary triggers, continuous controls) and RGB colors without dealing with raw MIDI messages.

## Features

- **Three Control Types**: Toggle, Momentary, and Continuous controls with unified API
- **Progressive State Discovery**: Honest representation of hardware limitations (knobs/faders start in "unknown" state)
- **Capability-Based API**: Validates hardware support before attempting operations
- **Thread-Safe**: Safe concurrent access from callbacks and main thread
- **Plugin Architecture**: Extensible system for supporting different controllers
- **Callback System**: Global, per-control, and type-based callbacks with error isolation
- **Bank Support**: Handles controllers with bank switching (when supported)
- **Strict/Permissive Modes**: Choose between errors or warnings for unsupported operations

## Installation

```bash
pip install padbound
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

## Examples

See the `examples/` directory for controller-specific demos:
- `demo_akai_lpd8.py` - AKAI LPD8 MK2
- `demo_akai_apc_mini_mk2.py` - AKAI APC mini MK2
- `demo_presonus_atom.py` - PreSonus ATOM
- `demo_xjam.py` - Xjam
- `demo_x_touch_mini.py` - Behringer X-Touch Mini

### Callback Registration

```python
from padbound import Controller, ControlType

with Controller(plugin='auto', auto_connect=True) as controller:
    # Per-control callback
    controller.on_control('pad_1', lambda state: print(f"Pad 1: {state.is_on}"))

    # Per-type callback (all toggles, all continuous, etc.)
    controller.on_type(ControlType.TOGGLE, lambda cid, state: print(f"{cid} toggled"))

    # Per-category callback (e.g., all transport buttons)
    controller.on_category('transport', lambda cid, state: print(f"Transport: {cid}"))

    # Global callback (all controls)
    controller.on_global(lambda cid, state: print(f"Any control: {cid}"))

    while True:
        controller.process_events()
```

### Setting Control State

```python
from padbound import Controller, StateUpdate

with Controller(plugin='auto', auto_connect=True) as controller:
    # Set pad LED color and state
    update = StateUpdate(is_on=True, color='red')
    if controller.can_set_state('pad_1', update):
        controller.set_state('pad_1', update)

    # Query control state
    state = controller.get_state('pad_1')
    if state:
        print(f"Pad 1 is {'on' if state.is_on else 'off'}")
```

### Using Configuration

```python
from padbound import Controller, ControllerConfig, BankConfig, ControlConfig, ControlType

# Configure pad colors and types
config = ControllerConfig(banks={
    'bank_1': BankConfig(controls={
        'pad_1': ControlConfig(type=ControlType.TOGGLE, color='red', off_color='dim_red'),
        'pad_2': ControlConfig(type=ControlType.MOMENTARY, color='green'),
    })
})

with Controller(plugin='auto', config=config, auto_connect=True) as controller:
    while True:
        controller.process_events()
```

## Supported Controllers

### Capability Comparison

| Controller | Pads | Knobs/Encoders | Faders | Buttons | RGB LEDs | LED Modes | Banks | Persistent Config | Special Features |
|------------|----|---------------|--------|---------|----------|-----------|-------|-------------------|------------------|
| **AKAI LPD8 MK2** | 8 | 8 knobs | — | — | ✓ Full | Solid | 4 (HW) | ✓ SysEx | Multi-signal pads (NOTE/CC/PC) |
| **AKAI APC mini MK2** | 64 | — | 9 | 17 | ✓ Full | Solid/Pulse/Blink | 1 | — | Fader position discovery |
| **PreSonus ATOM** | 16 | 4 | — | 20 | ✓ Full | Solid/Pulse/Blink | 8 (HW) | — | Native Control mode, encoder acceleration |
| **Xjam** | 16 | 6 | — | — | — | — | 3 (HW) | ✓ SysEx | Multi-signal pads, multiple encoder modes |
| **X-Touch Mini** | 16 | 8 + buttons | 1 | — | Single | Solid | 2 (HW) | — | Deferred LED feedback, auto-reflecting encoder rings |

**Legend:**
- **HW** = Hardware-managed bank switching
- **RGB LEDs**: Full = True RGB color support, Single = On/off only
- **LED Modes**: Animation/behavior modes supported
- **Persistent Config**: Device stores configuration in non-volatile memory

### Detailed Controller Information

#### AKAI LPD8 MK2
**Control Surface**: 8 RGB pads + 8 knobs\
**Banks**: 4 banks with hardware-based switching\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via SysEx
- **Pad LED Modes**: Solid
- **Pad Modes**: Toggle or momentary (global per bank)
- **Knob Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx)

#### AKAI APC mini MK2
**Control Surface**: 8×8 RGB pad grid + 9 faders + 17 buttons\
**Banks**: Single layer\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via SysEx
- **Pad LED Modes**: Solid, pulse, blink
- **Pad Modes**: Toggle or momentary (per pad)
- **Fader Feedback**: None (read-only, initial position discovered)
- **Button LED Feedback**: Single-color (red for track, green for scene)
- **Configuration**: Volatile

#### PreSonus ATOM
**Control Surface**: 16 RGB pads (4×4) + 4 encoders + 20 buttons\
**Banks**: 8 hardware-managed banks (not software-accessible)\
**Capabilities**:
- **Pad LED Feedback**: Full RGB via Native Control mode
- **Pad LED Modes**: Solid, pulse, breathe
- **Pad Modes**: Toggle or momentary (per pad)
- **Encoder Type**: Relative with acceleration
- **Encoder Feedback**: None (read-only)
- **Button LED Feedback**: Single-color
- **Configuration**: Volatile

#### Xjam (ESI/Artesia Pro)
**Control Surface**: 16 pads + 6 knobs per bank\
**Banks**: 3 banks (Green, Yellow, Red) with synchronized pad/knob switching\
**Capabilities**:
- **Pad LED Feedback**: None (hardware-managed)
- **Pad Modes**: Toggle or momentary (global)
- **Knob Type**: Configurable (absolute or 3 relative modes)
- **Knob Feedback**: None (read-only)
- **Configuration**: Persistent (SysEx)

#### Behringer X-Touch Mini
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

## Documentation

TBD

## Acknowledgements

Some protocol information for supported controllers was gathered from:
- **AKAI LPD8 MK2**: [stephensrmmartin/lpd8mk2](https://github.com/stephensrmmartin/lpd8mk2)
- **PreSonus ATOM**: [EMATech/AtomCtrl](https://github.com/EMATech/AtomCtrl)
- **Behringer X-Touch Mini**: [AndreasPantle/X-Touch-Mini-HandsOn](https://github.com/AndreasPantle/X-Touch-Mini-HandsOn)

## License

MIT License
