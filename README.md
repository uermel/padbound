

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo_dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo_light.svg">
    <img alt="Description" src="assets/logo_light.svg">
  </picture>
</p>


A unified, stateful python interface for MIDI controllers that abstracts hardware differences behind a simple API.

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
pip install -e .
```

## Quick Start

```python
from padbound import Controller, ControlType

# Auto-detect and connect to controller
with Controller(plugin='auto', auto_connect=True) as controller:
    # Register callbacks
    controller.on_control('pad_1', lambda state: print(f"Pad 1: {state.is_on}"))
    controller.on_type(ControlType.CONTINUOUS, lambda cid, state:
        print(f"{cid}: {state.normalized_value:.2f}") if state.is_discovered else None
    )

    # Main loop
    while True:
        controller.process_events()  # Process incoming MIDI
        # Your application logic here
```

## Key Concepts

### Control Types

1. **TOGGLE**: Binary on/off state (e.g., pads acting as switches)
2. **MOMENTARY**: Trigger-based actions with no persistent state (e.g., tap to trigger)
3. **CONTINUOUS**: Range-based values (e.g., knobs, faders, 0-127 or custom ranges)

### Progressive State Discovery

Controls start in "unknown" state until first interaction:
- Knobs and faders don't report their initial position until moved
- Applications can check `state.is_discovered` before using values
- Honest representation of hardware limitations

### Capability System

Every control declares what operations it supports:
- `supports_feedback`: Can receive state updates from library (capability exists)
- `requires_feedback`: Device needs automatic LED updates on input (hardware doesn't manage LEDs)
- `supports_led`: Can control LED on/off
- `supports_color`: Can control LED color
- `supports_value_setting`: Can set position (rare, for motorized faders)

The API validates capabilities before attempting operations:

```python
# Check before setting
if controller.can_set_state('pad_1', is_on=True, color='red'):
    controller.set_state('pad_1', is_on=True, color='red')

# Or handle with strict mode
controller = Controller(plugin='auto', strict_mode=False)
controller.set_state('fader_1', value=64)  # Logs warning if not supported
```

## Examples

See `example_usage.py` for comprehensive examples.

### Basic Usage

```python
from padbound import Controller, ControlType

controller = Controller(plugin='auto')
controller.connect()

# Register callbacks
controller.on_control('pad_1', lambda s: print(f"Pad pressed: {s.is_on}"))
controller.on_type(ControlType.CONTINUOUS, handle_fader_change)

# Process events
while running:
    controller.process_events()
```

## Included Plugins

- AKAI LPD8 MK2
- AKAI APC mini MK2

## Testing

```bash
python test_basic.py      # Run basic tests
python example_usage.py   # Run usage example
```

## Dependencies

- **mido** (>=1.3.3): MIDI I/O
- **pydantic** (>=2.12.5): Type-safe models
- Python 3.12+

## Documentation

TBD

## License

MIT License