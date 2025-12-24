"""
Plugin registry for controller discovery and management.

This module provides the global plugin registry for registering and discovering
controller plugins.
"""

from typing import Optional, Type

import mido

from padbound.logging_config import get_logger
from padbound.plugin import ControllerPlugin

logger = get_logger(__name__)


class PluginRegistry:
    """
    Global registry for controller plugins.

    Manages plugin registration, lookup, and auto-detection based on
    MIDI port names.
    """

    def __init__(self):
        """Initialize empty registry."""
        self._plugins: dict[str, Type[ControllerPlugin]] = {}

    def register(self, plugin_class: Type[ControllerPlugin]) -> None:
        """
        Register a plugin class.

        Args:
            plugin_class: Plugin class (not instance) to register

        Raises:
            ValueError: If plugin with same name already registered
        """
        # Create temporary instance to get name
        temp_instance = plugin_class()
        name = temp_instance.name

        if name in self._plugins:
            logger.warning(f"Plugin '{name}' already registered, overwriting")

        self._plugins[name] = plugin_class
        logger.debug(f"Registered plugin: {name}")

    def unregister(self, name: str) -> None:
        """
        Unregister a plugin by name.

        Args:
            name: Plugin name
        """
        if name in self._plugins:
            del self._plugins[name]
            logger.debug(f"Unregistered plugin: {name}")

    def get_plugin(self, name: str) -> Optional[ControllerPlugin]:
        """
        Get plugin instance by name.

        Args:
            name: Plugin name

        Returns:
            Plugin instance or None if not found
        """
        plugin_class = self._plugins.get(name)
        if plugin_class:
            return plugin_class()
        return None

    def list_plugins(self) -> list[str]:
        """
        List all registered plugin names.

        Returns:
            List of plugin names
        """
        return list(self._plugins.keys())

    def detect(self, port_name: Optional[str] = None) -> Optional[ControllerPlugin]:
        """
        Auto-detect controller plugin based on MIDI port names.

        If port_name is provided, matches against that. Otherwise, queries
        available MIDI ports and attempts to match against plugin patterns.

        Args:
            port_name: Specific port name to match, or None to search all

        Returns:
            Plugin instance if detected, None otherwise
        """
        # Get available port names
        if port_name:
            port_names = [port_name]
        else:
            try:
                port_names = mido.get_input_names()
            except Exception as e:
                logger.error(f"Failed to query MIDI ports: {e}")
                return None

        # Try to match against plugin patterns
        for plugin_class in self._plugins.values():
            plugin = plugin_class()
            patterns = plugin.port_patterns

            for pattern in patterns:
                for available_port in port_names:
                    if pattern.lower() in available_port.lower():
                        logger.info(
                            f"Auto-detected controller: {plugin.name} "
                            f"(matched pattern '{pattern}' in port '{available_port}')",
                        )
                        return plugin

        logger.warning("No controller plugin auto-detected")
        return None

    def find_ports(self, plugin: ControllerPlugin) -> tuple[Optional[str], Optional[str]]:
        """
        Find input and output ports for a plugin.

        Args:
            plugin: Plugin to find ports for

        Returns:
            (input_port, output_port) tuple, either may be None
        """
        patterns = plugin.port_patterns
        if not patterns:
            return (None, None)

        input_port = None
        output_port = None

        # Search input ports
        try:
            for port_name in mido.get_input_names():
                for pattern in patterns:
                    if pattern.lower() in port_name.lower():
                        input_port = port_name
                        break
                if input_port:
                    break
        except Exception as e:
            logger.error(f"Failed to query input ports: {e}")

        # Search output ports
        try:
            for port_name in mido.get_output_names():
                for pattern in patterns:
                    if pattern.lower() in port_name.lower():
                        output_port = port_name
                        break
                if output_port:
                    break
        except Exception as e:
            logger.error(f"Failed to query output ports: {e}")

        return (input_port, output_port)

    def validate_plugin(self, plugin: ControllerPlugin) -> list[str]:
        """
        Validate plugin implementation completeness.

        Args:
            plugin: Plugin to validate

        Returns:
            List of validation errors (empty if valid)
        """
        errors = []

        # Check name
        try:
            name = plugin.name
            if not name or not isinstance(name, str):
                errors.append("Plugin name must be a non-empty string")
        except Exception as e:
            errors.append(f"Error getting plugin name: {e}")

        # Check control definitions
        try:
            controls = plugin.get_control_definitions()
            if not isinstance(controls, list):
                errors.append("get_control_definitions() must return a list")
            elif len(controls) == 0:
                errors.append("Plugin must define at least one control")
        except Exception as e:
            errors.append(f"Error getting control definitions: {e}")

        # Check input mappings
        try:
            mappings = plugin.get_input_mappings()
            if not isinstance(mappings, list):
                errors.append("get_input_mappings() must return a list")
            elif len(mappings) == 0:
                errors.append("Plugin must define at least one input mapping")
        except Exception as e:
            errors.append(f"Error getting input mappings: {e}")

        # Check init method (must be implemented)
        try:
            # Check if init is not the default ABC method
            if not hasattr(plugin.init, "__isabstractmethod__"):
                # Try calling with dummy function
                plugin.init(lambda msg: None)
            else:
                errors.append("Plugin must implement init() method")
        except NotImplementedError:
            errors.append("Plugin must implement init() method")
        except Exception:
            # Any other error is OK - method is implemented
            pass

        return errors


# Global plugin registry instance
plugin_registry = PluginRegistry()
