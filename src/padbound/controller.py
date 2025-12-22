"""
Main Controller API - User-facing interface for Padbound.

This module provides the primary Controller class that orchestrates all
components and provides a simple API for working with MIDI controllers.
"""

from typing import Optional, Union, Any

import mido

from .callbacks import CallbackManager
from .config import ControllerConfig, ControlConfigResolver
from .controls import (
    Control,
    ControlType,
    ControlState,
    ControlDefinition,
    ControllerCapabilities,
    CapabilityError,
    ToggleControl,
    MomentaryControl,
    ContinuousControl,
)
from .midi_io import MIDIInterface
from .plugin import ControllerPlugin
from .logging_config import get_logger
from .registry import plugin_registry
from .state import ControllerState

logger = get_logger(__name__)


class Controller:
    """
    Main user-facing API for MIDI controller interaction.

    Provides high-level abstraction over MIDI controllers with:
    - Automatic plugin detection and initialization
    - Thread-safe state management
    - Callback system for state changes
    - Capability-aware feedback operations
    - Progressive state discovery
    - Bank management (when supported)
    """

    def __init__(
        self,
        plugin: Optional[Union[str, ControllerPlugin]] = None,
        config: Optional[ControllerConfig] = None,
        strict_mode: bool = True,
        auto_connect: bool = False
    ):
        """
        Initialize controller.

        Args:
            plugin: Plugin name, instance, or 'auto' for auto-detection.
                   If None, must call connect() manually.
            config: Controller configuration (Pydantic model) for control types and colors.
                   Optional - if not provided, uses plugin defaults.
            strict_mode: If True, raise CapabilityError for unsupported operations.
                        If False, log warnings instead.
            auto_connect: If True, automatically connect on initialization
        """
        self._plugin: Optional[ControllerPlugin] = None
        self._strict_mode = strict_mode
        self._connected = False

        # Components (initialized on connect)
        self._state: Optional[ControllerState] = None
        self._callbacks: CallbackManager = CallbackManager()
        self._midi: Optional[MIDIInterface] = None

        # Initialization handshake tracking
        # When True, controller is ready for normal operation
        # When False, first MIDI input is consumed for state detection
        self._initialization_complete: bool = True

        # Configuration system
        self._controller_config = config
        self._config_resolver = ControlConfigResolver(config)

        # Resolve plugin
        if isinstance(plugin, str):
            if plugin == 'auto':
                self._plugin = plugin_registry.detect()
                if not self._plugin:
                    raise ValueError("No controller auto-detected. Please specify plugin explicitly.")
            else:
                self._plugin = plugin_registry.get_plugin(plugin)
                if not self._plugin:
                    raise ValueError(f"Unknown plugin: {plugin}")
        elif isinstance(plugin, ControllerPlugin):
            self._plugin = plugin

        # Validate bank configurations against plugin constraints
        if self._plugin and config and config.banks:
            for bank_id, bank_config in config.banks.items():
                self._plugin.validate_bank_config(
                    bank_id, bank_config, self._strict_mode
                )

        # Auto-connect if requested
        if auto_connect and self._plugin:
            self.connect()

    @property
    def capabilities(self) -> Optional[ControllerCapabilities]:
        """Get controller capabilities."""
        return self._state.capabilities if self._state else None

    @property
    def is_connected(self) -> bool:
        """Check if controller is connected."""
        return self._connected

    @property
    def plugin(self) -> Optional[ControllerPlugin]:
        """Get active plugin."""
        return self._plugin

    def connect(
        self,
        input_port: Optional[str] = None,
        output_port: Optional[str] = None
    ) -> None:
        """
        Connect to MIDI controller and initialize.

        Args:
            input_port: Input port name (auto-detect if None)
            output_port: Output port name (auto-detect if None)

        Raises:
            ValueError: If no plugin configured
            IOError: If connection fails
        """
        if not self._plugin:
            raise ValueError("No plugin configured. Pass plugin to __init__ or call with plugin parameter")

        if self._connected:
            logger.warning("Already connected")
            return

        # Find ports if not specified
        if input_port is None or output_port is None:
            found_input, found_output = plugin_registry.find_ports(self._plugin)

            if input_port is None:
                input_port = found_input
            if output_port is None:
                output_port = found_output

            if not input_port and not output_port:
                raise IOError(f"Could not find MIDI ports for plugin '{self._plugin.name}'")

        # Initialize MIDI interface
        self._midi = MIDIInterface(on_message=self._on_midi_message)
        self._midi.connect(input_port, output_port)

        # Initialize state management
        # Get controller capabilities from plugin
        capabilities = self._plugin.get_capabilities()
        self._state = ControllerState(capabilities)

        # Register all controls from plugin
        for control_def in self._plugin.get_control_definitions():
            control = self._create_control(control_def)
            self._state.register_control(control)

        # Call plugin init to set controller to known state
        logger.info(f"Initializing controller: {self._plugin.name}")
        self._plugin.init(self._send_message, self._midi.receive_message)

        # Program persistent configuration (if plugin supports it)
        if self._controller_config and self._state.capabilities.supports_persistent_configuration:
            logger.info("Programming persistent configuration into device")
            self._plugin.configure_programs(self._send_message, self._controller_config)

            # Give device time to process the configuration before LED updates
            import time
            time.sleep(0.2)

        # Check if plugin requires initialization handshake
        # When True, first MIDI input is consumed to detect bank/state
        if self._state.capabilities.requires_initialization_handshake:
            self._initialization_complete = False
            logger.info(
                f"Plugin '{self._plugin.name}' requires initialization handshake - "
                f"first interaction will be consumed for state detection"
            )
            # Skip initial LED states - they'll be set via _apply_bank_leds() after bank detection
        else:
            self._initialization_complete = True
            # Display initial LED states for controls with configured colors
            # This lights up pads with their off_color to show the configured layout
            logger.debug("Setting initial LED states from configuration")
            for control_def in self._plugin.get_control_definitions():
                control = self._state.get_control(control_def.control_id)
                if not control:
                    continue

                # Only send feedback for controls with color support and configured colors
                if control.definition.capabilities.supports_feedback:
                    # Use off_color for initial state (controls start in OFF state)
                    if control.definition.off_color is not None:
                        state_dict = {
                            'is_on': False,
                            'value': 0,
                            'color': control.definition.off_color,
                            'normalized_value': None
                        }
                        messages = self._plugin.translate_feedback(control.definition.control_id, state_dict)
                        for msg in messages:
                            self._send_message(msg)

        # Set connected flag
        self._connected = True

        logger.info(
            f"Connected to {self._plugin.name} "
            f"(input: {input_port}, output: {output_port})"
        )

    def disconnect(self) -> None:
        """Disconnect from controller and cleanup."""
        if not self._connected:
            return

        # Call plugin shutdown
        if self._plugin and self._midi:
            logger.info(f"Shutting down controller: {self._plugin.name}")
            self._plugin.shutdown(self._send_message)

        # Disconnect MIDI
        if self._midi:
            self._midi.disconnect()
            self._midi = None

        self._connected = False
        logger.info("Controller disconnected")

    def reconfigure(self, config: Optional['ControllerConfig'] = None) -> None:
        """
        Reprogram device memory with new configuration (if supported).

        Updates persistent configuration in device memory. Configuration changes
        persist across program switches and potentially power cycles.

        Useful for:
        - Changing color schemes at runtime
        - Switching control types (toggle ↔ momentary)
        - Adjusting MIDI channels
        - Modifying knob ranges

        Args:
            config: New configuration, or None to reprogram current config

        Raises:
            RuntimeError: If not connected
            NotImplementedError: If plugin doesn't support persistent configuration

        Example:
            # Change all pad colors to blue
            new_config = ControllerConfig(banks={
                "bank_1": BankConfig(controls={
                    f"pad_{i}": ControlConfig(color="blue")
                    for i in range(1, 9)
                })
            })
            controller.reconfigure(new_config)
        """
        from .config import ControllerConfig

        self._ensure_connected()

        if not self._state.capabilities.supports_persistent_configuration:
            raise NotImplementedError(
                f"Plugin '{self._plugin.name}' does not support persistent configuration"
            )

        # Use provided config or current config
        if config:
            # TODO: Consider validating and merging with current config
            # For now, replace entirely
            self._controller_config = config

            # TODO: If control types changed, may need to rebuild Control objects
            # For initial implementation, focus on colors

        config_to_use = config or self._controller_config

        if not config_to_use:
            logger.warning("No configuration available to program")
            return

        # Reprogram device
        logger.info("Reprogramming device with new configuration")
        self._plugin.configure_programs(self._send_message, config_to_use)

        logger.info("Device reconfiguration complete")

    # State query methods

    def get_state(self, control_id: str) -> Optional[ControlState]:
        """
        Get current state for a control.

        Args:
            control_id: Control identifier

        Returns:
            Current state or None if control not found
        """
        self._ensure_connected()
        return self._state.get_state(control_id)

    def get_all_states(self) -> dict[str, ControlState]:
        """
        Get all control states.

        Returns:
            Dictionary mapping control_id to ControlState
        """
        self._ensure_connected()
        return self._state.get_all_states()

    def get_discovered_controls(self) -> list[str]:
        """
        Get list of controls with known state.

        Returns:
            List of control IDs that have been interacted with
        """
        self._ensure_connected()
        return self._state.get_discovered_controls()

    def get_undiscovered_controls(self) -> list[str]:
        """
        Get list of controls with unknown state.

        Returns:
            List of control IDs not yet interacted with
        """
        self._ensure_connected()
        return self._state.get_undiscovered_controls()

    def get_controls(self) -> list[ControlDefinition]:
        """
        Get all control definitions.

        Returns:
            List of control definitions
        """
        self._ensure_connected()
        if not self._plugin:
            return []
        return self._plugin.get_control_definitions()

    # Programmatic state control

    def set_state(self, control_id: str, **kwargs) -> None:
        """
        Set control state programmatically (sends hardware feedback).

        Validates capabilities before attempting. Behavior depends on strict_mode:
        - Strict mode: Raises CapabilityError for unsupported operations
        - Permissive mode: Logs warning and returns without error

        Args:
            control_id: Control identifier
            **kwargs: State parameters (is_on, value, color, etc.)

        Raises:
            ValueError: If control not found
            CapabilityError: If operation unsupported (strict mode only)

        Example:
            controller.set_state('pad_1', is_on=True, color='red')
            controller.set_state('fader_1', value=64)
        """
        self._ensure_connected()

        # Get control
        control = self._state.get_control(control_id)
        if not control:
            raise ValueError(f"Unknown control: {control_id}")

        capabilities = control.definition.capabilities

        # Check if feedback supported at all
        if not capabilities.supports_feedback:
            self._handle_unsupported_operation(
                f"Control '{control_id}' does not support feedback"
            )
            return

        # Validate specific operations
        if 'value' in kwargs and not capabilities.supports_value_setting:
            self._handle_unsupported_operation(
                f"Control '{control_id}' does not support value setting (not motorized)"
            )
            return

        if 'color' in kwargs:
            if not capabilities.supports_color:
                self._handle_unsupported_operation(
                    f"Control '{control_id}' does not support color"
                )
                return

            # Validate color against palette
            if not self._state.validate_color(control_id, kwargs['color']):
                color = kwargs['color']
                palette = capabilities.color_palette
                self._handle_unsupported_operation(
                    f"Color '{color}' not in palette {palette} for control '{control_id}'"
                )
                return

        # All checks passed - translate to MIDI and send
        if self._plugin:
            messages = self._plugin.translate_feedback(control_id, kwargs)
            for msg in messages:
                self._send_message(msg)

    def can_set_state(self, control_id: str, **kwargs) -> bool:
        """
        Check if set_state() would succeed.

        Returns True if operation is supported, False otherwise.
        Does not throw exceptions regardless of strict_mode.

        Args:
            control_id: Control identifier
            **kwargs: State parameters to check

        Returns:
            True if operation supported, False otherwise
        """
        if not self._connected or not self._state:
            return False

        try:
            control = self._state.get_control(control_id)
            if not control:
                return False

            capabilities = control.definition.capabilities

            if not capabilities.supports_feedback:
                return False

            if 'value' in kwargs and not capabilities.supports_value_setting:
                return False

            if 'color' in kwargs:
                if not capabilities.supports_color:
                    return False
                if not self._state.validate_color(control_id, kwargs['color']):
                    return False

            return True

        except Exception:
            return False

    # Bank management

    def get_active_bank(self, control_type: ControlType) -> Optional[str]:
        """
        Get active bank for control type.

        Returns:
            Bank ID if tracking supported and set, None otherwise

        Note:
            Most controllers do NOT support bank feedback. The library will
            still correctly identify controls by their full ID (pad_1@bank_2),
            but cannot tell you which bank is currently active.
        """
        self._ensure_connected()
        return self._state.get_active_bank(control_type)

    def set_active_bank(self, control_type: ControlType, bank_id: str) -> None:
        """
        Set active bank for control type.

        Args:
            control_type: Type of controls
            bank_id: Bank identifier

        Note:
            Silent no-op if bank tracking not supported.
        """
        self._ensure_connected()
        self._state.set_active_bank(control_type, bank_id)

    # Callback registration

    def on_control(self, control_id: str, callback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for specific control with optional signal type filtering.

        Args:
            control_id: Control identifier (e.g., "pad_1@bank_1")
            callback: Function(state: ControlState) -> None
            signal_type: Optional signal type filter:
                        None = fires for all signal types (default)
                        "note" = fires only for NOTE messages
                        "cc" = fires only for CC messages
                        "pc" = fires only for PC messages
        """
        self._callbacks.register_control(control_id, callback, signal_type)

    def on_type(self, control_type: ControlType, callback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for all controls of a type with optional signal filtering.

        Args:
            control_type: Type of controls
            callback: Function(control_id: str, state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        self._callbacks.register_type(control_type, callback, signal_type)

    def on_global(self, callback, signal_type: Optional[str] = None) -> None:
        """
        Register callback for all control changes with optional signal filtering.

        Args:
            callback: Function(control_id: str, state: ControlState) -> None
            signal_type: Optional signal type filter (None = all signals)
        """
        self._callbacks.register_global(callback, signal_type)

    def on_bank_change(self, control_type: ControlType, callback) -> None:
        """
        Register callback for bank changes.

        Args:
            control_type: Type of controls in bank
            callback: Function(bank_id: str) -> None

        Note:
            Only fires if controller supports bank feedback.
        """
        self._callbacks.register_bank(control_type, callback)

    # Processing

    def process_events(self) -> int:
        """
        Process pending MIDI events.

        Call this regularly in your main loop to process incoming MIDI messages
        and dispatch callbacks.

        Returns:
            Number of messages processed
        """
        if not self._midi:
            return 0

        return self._midi.process_pending_messages()

    # Context manager support

    def __enter__(self):
        """Context manager entry."""
        if not self._connected and self._plugin:
            self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - disconnect."""
        self.disconnect()
        return False

    # Internal methods

    def _ensure_connected(self) -> None:
        """Raise error if not connected."""
        if not self._connected:
            raise RuntimeError("Controller not connected. Call connect() first.")

    def _handle_unsupported_operation(self, message: str) -> None:
        """Handle unsupported operation based on strict_mode."""
        if self._strict_mode:
            raise CapabilityError(message)
        else:
            logger.warning(message)

    def _create_control(self, definition: ControlDefinition) -> Control:
        """
        Create Control instance from definition.

        Uses configuration resolver to determine actual control type and colors.

        Args:
            definition: Control definition

        Returns:
            Control instance
        """
        # Resolve type and colors from config
        actual_type, on_color, off_color = self._config_resolver.resolve_config(
            definition.control_id,
            definition
        )

        # Create control with resolved type and colors
        resolved_definition = definition.model_copy(
            update={
                'control_type': actual_type,
                'on_color': on_color,
                'off_color': off_color
            }
        )

        if actual_type == ControlType.TOGGLE:
            control = ToggleControl(resolved_definition)
        elif actual_type == ControlType.MOMENTARY:
            control = MomentaryControl(resolved_definition)
        elif actual_type == ControlType.CONTINUOUS:
            control = ContinuousControl(resolved_definition)
        else:
            raise ValueError(f"Unknown control type: {actual_type}")

        return control

    def _send_message(self, msg: mido.Message) -> None:
        """Send MIDI message (internal)."""
        if self._midi:
            self._midi.send_message(msg)

    def _apply_bank_leds(self, bank_id: str) -> None:
        """
        Apply LED colors for all controls in a bank.

        Sends feedback to update LEDs based on current state and configured colors.
        Used after bank detection/switch to sync visual state with hardware.

        Args:
            bank_id: Bank to apply LED colors for
        """
        if not self._plugin or not self._state:
            return

        for control_def in self._plugin.get_control_definitions():
            # Only process controls in the specified bank
            if control_def.bank_id != bank_id:
                continue

            control = self._state.get_control(control_def.control_id)
            if not control:
                continue

            # Only send feedback for controls with feedback capability
            if not control.definition.capabilities.supports_feedback:
                continue

            # Determine color based on current state
            state = control.state
            if state.is_on:
                color = control.definition.on_color
            else:
                color = control.definition.off_color

            if not color:
                continue

            # Build state dict and send feedback
            state_dict = {
                'is_on': state.is_on if state.is_on is not None else False,
                'value': state.value if state.value is not None else 0,
                'color': color,
                'normalized_value': state.normalized_value
            }

            messages = self._plugin.translate_feedback(control_def.control_id, state_dict)
            for msg in messages:
                self._send_message(msg)

        logger.debug(f"Applied LED colors for bank: {bank_id}")

    def _on_midi_message(self, msg: mido.Message) -> None:
        """
        Handle incoming MIDI message.

        Translates message via plugin, updates state, dispatches callbacks.

        Args:
            msg: Incoming MIDI message
        """
        if not self._plugin or not self._state:
            return

        # Handle initialization handshake (first interaction consumed)
        if not self._initialization_complete:
            bank_id = self._plugin.complete_initialization(msg, self._send_message)
            self._initialization_complete = True

            if bank_id:
                # Update internal bank tracking
                control_type = ControlType.TOGGLE  # Primary type for pads
                self._state.set_active_bank(control_type, bank_id)
                self._callbacks.on_bank_change(control_type, bank_id)

                # Apply LED colors for detected bank
                self._apply_bank_leds(bank_id)

            logger.info(f"Initialization complete (bank: {bank_id or 'default'})")
            return  # Consume message - do not pass to callbacks

        # Check for bank switch
        bank_id = self._plugin.translate_bank_switch(msg)
        if bank_id:
            # Determine control type from message (simplified)
            # In practice, plugin should provide this information
            control_type = ControlType.TOGGLE  # Default
            self._state.set_active_bank(control_type, bank_id)
            self._callbacks.on_bank_change(control_type, bank_id)
            return

        # Translate MIDI to control with signal type
        result = self._plugin.translate_input(msg)
        if not result:
            logger.debug(f"No mapping found for MIDI message: {msg}")
            return

        control_id, value, signal_type = result

        # Update state
        try:
            new_state = self._state.update_state(control_id, value)

            # Get control type for callbacks
            control = self._state.get_control(control_id)
            if control:
                control_type = control.definition.control_type
                self._callbacks.on_control_change(control_id, new_state, control_type, signal_type)

                # Auto-send feedback if control REQUIRES it (hardware doesn't manage LEDs)
                if control.definition.capabilities.requires_feedback:
                    if new_state.color is not None:
                        # Convert ControlState to dict for translate_feedback
                        state_dict = {
                            'is_on': new_state.is_on,
                            'value': new_state.value,
                            'color': new_state.color,
                            'normalized_value': new_state.normalized_value
                        }
                        messages = self._plugin.translate_feedback(control_id, state_dict)
                        for feedback_msg in messages:
                            self._send_message(feedback_msg)

        except ValueError as e:
            logger.error(f"Error updating state: {e}")
