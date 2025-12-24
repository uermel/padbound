"""
Controller plugins for Padbound.

This package contains reference plugin implementations and serves as
a collection point for controller-specific plugins.
"""

# Import plugins and register them
from padbound.plugins.akai_apc_mini_mk2 import AkaiAPCminiMK2Plugin
from padbound.plugins.akai_lpd8_mk2 import AkaiLPD8MK2Plugin
from padbound.plugins.behringer_x_touch_mini import BehringerXTouchMiniPlugin
from padbound.plugins.presonus_atom import PreSonusAtomPlugin
from padbound.plugins.xjam import XjamPlugin
from padbound.registry import plugin_registry

# Register all plugins
plugin_registry.register(AkaiAPCminiMK2Plugin)
plugin_registry.register(AkaiLPD8MK2Plugin)
plugin_registry.register(BehringerXTouchMiniPlugin)
plugin_registry.register(PreSonusAtomPlugin)
plugin_registry.register(XjamPlugin)

__all__ = [
    "AkaiAPCminiMK2Plugin",
    "AkaiLPD8MK2Plugin",
    "BehringerXTouchMiniPlugin",
    "PreSonusAtomPlugin",
    "XjamPlugin",
]
