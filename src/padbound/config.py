"""
Pydantic configuration models for controller setup.

This module provides type-safe configuration models for defining control types
and colors across banks in multi-bank MIDI controllers.
"""

import re
from typing import Optional
from pydantic import BaseModel, Field, field_validator, model_validator

from .controls import ControlType, ControlDefinition, CapabilityError
from .logging_config import get_logger

logger = get_logger(__name__)


class ConfigurationError(Exception):
    """Raised when configuration is invalid or conflicts with hardware constraints."""
    pass


class ControlConfig(BaseModel):
    """
    Configuration for a single control.

    Specifies control type and optional colors for visual feedback.
    Supports separate colors for ON and OFF states.
    """
    type: ControlType
    color: Optional[str] = None  # ON state color: Named color, hex (#FF0000), or rgb(r,g,b)
    off_color: Optional[str] = None  # OFF state color (defaults to black if not specified)
    led_mode: Optional[str] = None  # LED animation: "solid", "pulse", "blink" (default: solid)

    @field_validator('led_mode')
    @classmethod
    def validate_led_mode(cls, v):
        """Validate led_mode is one of the supported values."""
        if v is not None and v not in ("solid", "pulse", "blink"):
            raise ValueError(f"led_mode must be 'solid', 'pulse', or 'blink', got '{v}'")
        return v

    def __hash__(self):
        """Make hashable for use in dicts/sets."""
        return hash((self.type, self.color, self.off_color, self.led_mode))


class BankConfig(BaseModel):
    """
    Configuration for a bank of controls.

    Maps control IDs (or patterns) to their configuration.
    Supports wildcards: "pad_*" matches "pad_1", "pad_2", etc.

    Attributes:
        controls: Control configurations by ID or pattern
        toggle_mode: Bank-level toggle mode for controllers with global toggle settings.
            None = use plugin default, True = toggle mode, False = momentary mode.
    """
    controls: dict[str, ControlConfig]
    toggle_mode: Optional[bool] = None

    @field_validator('controls')
    @classmethod
    def validate_control_keys(cls, v):
        """Validate control ID patterns."""
        for key in v.keys():
            if not (key.replace('_', '').replace('*', '').isalnum()):
                raise ValueError(f"Invalid control ID pattern: {key}")
        return v


class ControllerConfig(BaseModel):
    """
    Root configuration for a controller.

    Supports two modes:
    1. Bank-aware: `banks` dict for multi-bank controllers
    2. Flat: `controls` dict for single-bank controllers

    Only one mode can be used at a time.
    """
    # Bank-aware mode
    banks: Optional[dict[str, BankConfig]] = None

    # Flat mode (backward compatible)
    controls: Optional[dict[str, ControlConfig]] = None

    @model_validator(mode='after')
    def validate_exclusive_modes(self):
        """Ensure only one mode is used."""
        if self.banks is not None and self.controls is not None:
            raise ValueError("Cannot specify both 'banks' and 'controls'. Use one mode.")
        if self.banks is None and self.controls is None:
            raise ValueError("Must specify either 'banks' or 'controls'.")
        return self

    def is_bank_aware(self) -> bool:
        """Check if configuration uses bank-aware mode."""
        return self.banks is not None


class ControlConfigResolver:
    """
    Resolves control configuration from user config and plugin defaults.

    Resolution priority (bank-aware):
    1. Exact match in bank config (config.banks[bank_id].controls[control_base_id])
    2. Wildcard match in bank config (config.banks[bank_id].controls["pad_*"])
    3. Flat config fallback (if provided)
    4. Plugin default
    """

    def __init__(self, config: Optional[ControllerConfig] = None):
        """Initialize resolver with user configuration."""
        self._config = config

        if config is None:
            self._is_bank_aware = False
            self._flat_config = None
            self._bank_configs = None
        elif config.is_bank_aware():
            self._is_bank_aware = True
            self._flat_config = None
            # Pre-compile wildcard patterns per bank
            self._bank_configs = {}
            for bank_id, bank_config in config.banks.items():
                self._bank_configs[bank_id] = self._compile_config(bank_config.controls)
        else:
            self._is_bank_aware = False
            self._flat_config = self._compile_config(config.controls)
            self._bank_configs = None

    def _compile_config(self, controls: dict[str, ControlConfig]) -> tuple[dict, list]:
        """
        Compile config into exact matches and wildcard patterns.

        Returns:
            (exact_matches dict, wildcard_patterns list)
        """
        exact_matches = {}
        wildcard_patterns = []

        for pattern, control_config in controls.items():
            if '*' in pattern:
                # Convert glob pattern to regex
                regex_pattern = pattern.replace('*', '.*')
                compiled = re.compile(f'^{regex_pattern}$')
                wildcard_patterns.append((compiled, control_config))
            else:
                exact_matches[pattern] = control_config

        return (exact_matches, wildcard_patterns)

    def resolve_config(
        self,
        control_id: str,
        definition: ControlDefinition
    ) -> tuple[ControlType, Optional[str], Optional[str], Optional[str]]:
        """
        Resolve control type and colors for a control.

        Args:
            control_id: Full control identifier (e.g., "pad_1@bank_1")
            definition: Plugin's control definition

        Returns:
            (resolved_type, on_color, off_color, led_mode)

        Raises:
            CapabilityError: If requested type not supported by control
        """
        # Parse control_id to extract base ID and bank
        control_base_id, bank_id = self._parse_control_id(control_id)

        control_config = None

        # Try bank-aware resolution first
        if self._is_bank_aware and bank_id and bank_id in self._bank_configs:
            exact_matches, wildcard_patterns = self._bank_configs[bank_id]

            # Try exact match
            if control_base_id in exact_matches:
                control_config = exact_matches[control_base_id]
                logger.debug(f"Control '{control_id}': exact match in {bank_id}")

            # Try wildcard matches
            if not control_config:
                for pattern, config in wildcard_patterns:
                    if pattern.match(control_base_id):
                        control_config = config
                        logger.debug(f"Control '{control_id}': wildcard match in {bank_id}")
                        break

        # Try flat config fallback
        if not control_config and self._flat_config:
            exact_matches, wildcard_patterns = self._flat_config

            # Try full control_id first, then base ID
            for check_id in [control_id, control_base_id]:
                if check_id in exact_matches:
                    control_config = exact_matches[check_id]
                    break

            # Try wildcard matches
            if not control_config:
                for check_id in [control_id, control_base_id]:
                    for pattern, config in wildcard_patterns:
                        if pattern.match(check_id):
                            control_config = config
                            break
                    if control_config:
                        break

        # Extract type, colors, and LED mode
        if control_config:
            resolved_type = control_config.type
            on_color = control_config.color
            off_color = control_config.off_color
            led_mode = control_config.led_mode
            self._validate_supported(control_id, resolved_type, definition)
        else:
            # Fall back to plugin default
            resolved_type = definition.control_type
            on_color = None
            off_color = None
            led_mode = None
            logger.debug(f"Control '{control_id}': using plugin default")

        return (resolved_type, on_color, off_color, led_mode)

    def _parse_control_id(self, control_id: str) -> tuple[str, Optional[str]]:
        """
        Parse control_id into base ID and bank ID.

        Examples:
            "pad_1" → ("pad_1", None)
            "pad_1@bank_1" → ("pad_1", "bank_1")

        Returns:
            (control_base_id, bank_id or None)
        """
        if '@' in control_id:
            base_id, bank_id = control_id.split('@', 1)
            return (base_id, bank_id)
        else:
            return (control_id, None)

    def _validate_supported(
        self,
        control_id: str,
        requested_type: ControlType,
        definition: ControlDefinition
    ) -> None:
        """
        Validate that requested type is supported by the control.

        Args:
            control_id: Control identifier
            requested_type: Requested control type
            definition: Plugin's control definition

        Raises:
            CapabilityError: If type not supported
        """
        # If no type_modes specified, only the default type is supported
        if definition.type_modes is None:
            if requested_type != definition.control_type:
                raise CapabilityError(
                    f"Control '{control_id}' only supports type "
                    f"{definition.control_type.value}, but {requested_type.value} "
                    f"was requested. This control has fixed hardware behavior."
                )
        else:
            # Check if requested type is in supported types
            if requested_type not in definition.type_modes.supported_types:
                supported_str = ", ".join(
                    t.value for t in definition.type_modes.supported_types
                )
                raise CapabilityError(
                    f"Control '{control_id}' does not support type "
                    f"{requested_type.value}. Supported types: {supported_str}"
                )
