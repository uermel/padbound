"""
Controller plugins for Padbound.

This package contains reference plugin implementations and serves as
a collection point for controller-specific plugins.
"""

# Import plugins and register them
from ..registry import plugin_registry
from .akai_apc_mini_mk2 import AkaiAPCminiMK2Plugin
from .akai_lpd8_mk2 import AkaiLPD8MK2Plugin
from .behringer_x_touch_mini import BehringerXTouchMiniPlugin
from .example_pad_controller import ExamplePadController
from .generic_midi import GenericMIDIController
from .presonus_atom import PreSonusAtomPlugin
from .xjam import XjamPlugin

# Register all plugins
plugin_registry.register(AkaiAPCminiMK2Plugin)
plugin_registry.register(AkaiLPD8MK2Plugin)
plugin_registry.register(BehringerXTouchMiniPlugin)
plugin_registry.register(ExamplePadController)
plugin_registry.register(GenericMIDIController)
plugin_registry.register(PreSonusAtomPlugin)
plugin_registry.register(XjamPlugin)

__all__ = [
    "AkaiAPCminiMK2Plugin",
    "AkaiLPD8MK2Plugin",
    "BehringerXTouchMiniPlugin",
    "ExamplePadController",
    "GenericMIDIController",
    "PreSonusAtomPlugin",
    "XjamPlugin",
]
