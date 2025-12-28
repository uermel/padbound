"""
Padbound: MIDI Controller Abstraction Library

A unified, stateful interface for MIDI controllers that abstracts hardware
differences behind a simple API. Applications interact with three control types
(toggles, momentary triggers, continuous controls) without knowing the
underlying MIDI implementation.
"""

__version__ = "0.3.0"

# Main API
# Configuration models
from padbound.config import (
    BankConfig,
    ControlConfig,
    ControllerConfig,
)
from padbound.controller import Controller

# Control types and models
from padbound.controls import (
    BankDefinition,
    CapabilityError,
    ControlCapabilities,
    ControlDefinition,
    ControllerCapabilities,
    ControlState,
    ControlType,
    ControlTypeModes,
)

# Logging configuration
from padbound.logging_config import (
    get_logger,
    set_module_level,
    setup_logging,
)

# Plugin development
from padbound.plugin import BatchFeedbackResult, ControllerPlugin

# Plugins
from padbound.plugins.akai_lpd8_mk2 import AkaiLPD8MK2Plugin
from padbound.registry import plugin_registry

__all__ = [
    # Version
    "__version__",
    # Main API
    "Controller",
    # Control types and enums
    "ControlType",
    # State and definitions
    "ControlState",
    "ControlDefinition",
    "ControlCapabilities",
    "ControllerCapabilities",
    "ControlTypeModes",
    "BankDefinition",
    # Configuration models
    "ControlConfig",
    "BankConfig",
    "ControllerConfig",
    # Logging configuration
    "setup_logging",
    "get_logger",
    "set_module_level",
    # Exceptions
    "CapabilityError",
    # Plugin development
    "ControllerPlugin",
    "BatchFeedbackResult",
    "plugin_registry",
    # Plugins
    "AkaiLPD8MK2Plugin",
]
