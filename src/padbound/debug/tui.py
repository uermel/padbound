"""
Textual TUI application for padbound state debugging.

This module provides a terminal-based visualization of controller state,
receiving real-time updates via WebSocket from a padbound Controller
with debug_server enabled.
"""

import argparse
import asyncio
from typing import Optional

from pydantic import TypeAdapter
from rich.text import Text
from textual import log
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, Static

from padbound.controls import ControlDefinition, ControlState
from padbound.debug.layout import ControlWidget, DebugLayout, LayoutSection
from padbound.debug.messages import DebugMessage, FullStateMessage, StateChangeMessage
from padbound.logging_config import get_logger
from padbound.utils import RGBColor

logger = get_logger(__name__)

# Constants for widget sizing
PAD_WIDTH = 5
PAD_HEIGHT = 2
BUTTON_WIDTH = 8
BUTTON_HEIGHT = 2
FADER_WIDTH = 5
FADER_HEIGHT = 14  # Tall vertical fader (includes border)
INDEX_LABEL_WIDTH = 3  # Width for row/column index labels


class PadWidget(Static):
    """Widget representing a pad control with RGB color support."""

    is_on = reactive(False)
    color = reactive("black")

    def __init__(self, control_id: str, **kwargs):
        super().__init__(**kwargs)
        self.control_id = control_id

    def compose(self) -> ComposeResult:
        # control_id format: pad_{physical_row}_{col}
        # Compute linear index: physical_row * 8 + col (0 = bottom-left)
        parts = self.control_id.split("_")
        if len(parts) == 3 and parts[0] == "pad":
            physical_row = int(parts[1])
            col = int(parts[2])
            linear_index = physical_row * 8 + col
            yield Label(str(linear_index), id="pad-label")
        else:
            yield Label(self.control_id.split("_")[-1], id="pad-label")

    def watch_is_on(self, value: bool) -> None:
        self._update_style()

    def watch_color(self, value: str) -> None:
        log("watch_color", value)
        self._update_style()

    def _update_style(self) -> None:
        """Update widget style based on state.

        The color property is always set to the correct display color
        by _update_control() based on the is_on state, so we just use it directly.
        """
        self.styles.background = self._parse_color(self.color)

    def _parse_color(self, color: str) -> str:
        """Parse color string to CSS hex color using padbound's RGBColor.

        Uses the same color parsing as padbound to ensure consistency
        between hardware LED colors and TUI display.
        """
        # Use padbound's RGBColor for consistent color parsing
        try:
            rgb = RGBColor.from_string(color)
            return f"#{rgb.r:02x}{rgb.g:02x}{rgb.b:02x}"
        except Exception:
            # Fallback to gray if parsing fails
            return "#888888"


class FaderWidget(Static):
    """Widget representing a fader/slider control as a vertical bar."""

    value = reactive(0)

    def __init__(self, control_id: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self.control_id = control_id
        self.label_text = label or control_id
        self._bar_height = FADER_HEIGHT - 4  # Minus border (2), label (1), and value (1)

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, id="fader-label")
        yield Static("", id="fader-bar")
        yield Label("0", id="fader-value")

    def watch_value(self, new_value: int) -> None:
        self._update_bar()

    def on_mount(self) -> None:
        """Update bar when mounted."""
        self._update_bar()

    def _update_bar(self) -> None:
        """Update the vertical bar display."""
        try:
            bar = self.query_one("#fader-bar", Static)
            value_label = self.query_one("#fader-value", Label)
            value_label.update(str(self.value))

            # Calculate filled portion (value 0-127)
            fill_ratio = self.value / 127.0
            filled_rows = int(fill_ratio * self._bar_height)

            # Build vertical bar from bottom to top
            # Use block characters for the bar
            lines = []
            for i in range(self._bar_height):
                row_from_bottom = self._bar_height - 1 - i
                if row_from_bottom < filled_rows:
                    lines.append("████")  # Filled
                else:
                    lines.append("░░░░")  # Empty
            bar.update("\n".join(lines))
        except Exception:
            pass  # Widget not mounted yet


class ButtonWidget(Static):
    """Widget representing a button control."""

    is_on = reactive(False)

    def __init__(self, control_id: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self.control_id = control_id
        self.label_text = label or control_id

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, id="btn-label")

    def watch_is_on(self, value: bool) -> None:
        if value:
            self.add_class("active")
        else:
            self.remove_class("active")


class KnobWidget(Static):
    """Widget representing an encoder/knob control."""

    value = reactive(64)

    def __init__(self, control_id: str, label: str = "", **kwargs):
        super().__init__(**kwargs)
        self.control_id = control_id
        self.label_text = label or control_id

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, id="knob-label")
        yield Label("64", id="knob-value")

    def watch_value(self, new_value: int) -> None:
        try:
            value_label = self.query_one("#knob-value", Label)
            value_label.update(str(new_value))
        except Exception:
            pass


class SectionContainer(Container):
    """Container for a layout section."""

    def __init__(self, section: LayoutSection, **kwargs):
        super().__init__(**kwargs)
        self.section = section


class ControllerStateApp(App):
    """Main TUI application for controller state visualization."""

    CSS = """
    Screen {
        layout: vertical;
    }

    #main {
        layout: vertical;
        height: 100%;
        padding: 1;
    }

    #status {
        height: 3;
        background: $surface;
        padding: 0 1;
    }

    #sections {
        height: 1fr;
        overflow-y: auto;
        overflow-x: auto;
    }

    .section {
        border: solid $primary;
        margin: 1;
        padding: 1;
        height: auto;
        width: auto;
    }

    .section-title {
        text-style: bold;
        margin-bottom: 1;
        height: 1;
    }

    .controller-grid {
        height: auto;
        width: auto;
    }

    .grid-row {
        height: auto;
        width: auto;
    }

    PadWidget {
        width: 6;
        height: 2;
        min-width: 6;
        min-height: 2;
        content-align: center middle;
        background: #333333;
    }

    PadWidget #pad-label {
        text-align: center;
        width: 100%;
    }

    FaderWidget {
        width: 6;
        height: 14;
        min-width: 6;
        min-height: 14;
        background: #222222;
        border: solid #444444;
    }

    FaderWidget #fader-label {
        text-align: center;
        height: 1;
        width: 100%;
    }

    FaderWidget #fader-bar {
        height: 10;
        width: 100%;
        text-align: center;
        color: #00ff00;
    }

    FaderWidget #fader-value {
        text-align: center;
        height: 1;
        width: 100%;
    }

    ButtonWidget {
        width: 6;
        height: 2;
        min-width: 6;
        min-height: 2;
        content-align: center middle;
        background: #333333;
    }

    ButtonWidget.active {
        background: $success;
    }

    ButtonWidget #btn-label {
        text-align: center;
        width: 100%;
    }

    /* Wider buttons for scene/track controls (col 8) */
    .wide-button {
        width: 8;
        min-width: 8;
    }

    /* Placeholder for empty cells in regular rows */
    .cell-placeholder {
        width: 6;
        height: 2;
        min-width: 6;
        min-height: 2;
    }

    /* Placeholder for empty cells in fader rows */
    .fader-placeholder {
        width: 6;
        height: 14;
        min-width: 6;
        min-height: 14;
    }

    KnobWidget {
        width: 6;
        height: 2;
        min-width: 6;
        min-height: 2;
        content-align: center middle;
        background: #444444;
    }

    KnobWidget #knob-label {
        text-align: center;
    }

    KnobWidget #knob-value {
        text-align: center;
        text-style: bold;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "reconnect", "Reconnect"),
    ]

    def __init__(self, ws_url: str = "ws://127.0.0.1:8765"):
        super().__init__()
        self.ws_url = ws_url
        self._ws = None
        self._layout: Optional[DebugLayout] = None
        self._widgets: dict[str, Static] = {}
        self._definitions: dict[str, ControlDefinition] = {}
        self._connected = False
        self._plugin_name = "Unknown"

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Connecting...", id="status"),
            ScrollableContainer(id="sections"),
            id="main",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Connect to WebSocket server on mount."""
        self.run_worker(self._connect_and_listen(), exclusive=True)

    async def _connect_and_listen(self) -> None:
        """Connect to WebSocket and process incoming messages."""
        import traceback

        import websockets

        status = self.query_one("#status", Static)

        while True:
            try:
                status.update(Text(f"Connecting to {self.ws_url}...", style="yellow"))

                async with websockets.connect(self.ws_url) as ws:
                    self._ws = ws
                    self._connected = True
                    status.update(Text(f"Connected to {self._plugin_name}", style="green"))

                    async for message in ws:
                        try:
                            await self._process_message(message)
                        except Exception as e:
                            logger.error(f"Error processing message: {e}\n{traceback.format_exc()}")
                            # Don't disconnect on message processing errors
                            continue

            except asyncio.CancelledError:
                # Worker was cancelled, exit cleanly
                break
            except Exception as e:
                self._connected = False
                error_msg = f"Disconnected: {e}"
                logger.error(f"{error_msg}\n{traceback.format_exc()}")
                status.update(Text(f"{error_msg}. Retrying...", style="red"))
                await asyncio.sleep(2.0)  # Retry after 2 seconds

    async def _process_message(self, message: str) -> None:
        """Process incoming WebSocket message."""
        # Parse message using discriminated union
        msg_adapter: TypeAdapter[DebugMessage] = TypeAdapter(DebugMessage)
        msg = msg_adapter.validate_json(message)

        if isinstance(msg, FullStateMessage):
            # Initial state with layout
            self._plugin_name = msg.plugin_name
            status = self.query_one("#status", Static)
            status.update(Text(f"Connected to {self._plugin_name}", style="green"))

            self.notify(
                f"Received full_state: layout={msg.layout is not None}, "
                f"states={len(msg.states)}, definitions={len(msg.definitions)}",
            )

            # Store definitions for off_color lookup
            if msg.definitions:
                self._definitions = msg.definitions

                # Debug: show sample off_color from definitions
                sample_def = next((v for k, v in self._definitions.items() if k.startswith("pad_")), None)
                if sample_def:
                    self.notify(f"Sample pad definition off_color: {sample_def.off_color}")

            if msg.layout:
                await self._build_layout(msg.layout)
            else:
                self.notify("No layout in full_state message!", severity="warning")

            if msg.states:
                # Debug: show fader values
                fader_states = {k: v.value for k, v in msg.states.items() if k.startswith("fader_")}
                if fader_states:
                    self.notify(f"Fader values: {fader_states}")
                await self._apply_full_state(msg.states)

        elif isinstance(msg, StateChangeMessage):
            # Single control update
            await self._update_control(msg.control_id, msg.state)

    async def _build_layout(self, layout: DebugLayout) -> None:
        """Build TUI layout from plugin definition."""
        self._layout = layout
        self.notify(f"Building layout with {len(self._layout.sections)} sections")

        sections_container = self.query_one("#sections", ScrollableContainer)
        await sections_container.remove_children()

        # Build each section
        for section in self._layout.sections:
            self.notify(f"Building section: {section.name} ({len(section.controls)} controls)")
            try:
                section_widget = await self._build_section(section)
                await sections_container.mount(section_widget)
            except Exception as e:
                import traceback

                self.notify(f"Error building {section.name}: {e}", severity="error")
                logger.error(f"Error building section {section.name}: {traceback.format_exc()}")

        self.notify(f"Layout complete: {len(self._widgets)} widgets")
        self.refresh()

    async def _build_section(self, section: LayoutSection) -> Container:
        """Build a layout section with controls and index labels."""
        # Group controls by row
        rows_dict: dict[int, list] = {}
        for placement in section.controls:
            if placement.row not in rows_dict:
                rows_dict[placement.row] = []
            rows_dict[placement.row].append(placement)

        # Sort each row by column
        for row in rows_dict:
            rows_dict[row].sort(key=lambda p: p.col)

        # Determine the number of columns (find max column used)
        max_col = max(p.col for p in section.controls) if section.controls else 0
        num_cols = max_col + 1

        # Build data rows as Horizontal containers
        row_containers = []
        for row_idx in sorted(rows_dict.keys()):
            # Check if this is a fader row (any fader widget in the row)
            is_fader_row = any(p.widget_type == ControlWidget.FADER for p in rows_dict[row_idx])

            row_widgets = []

            # Build widget lookup for this row by column
            col_to_placement = {p.col: p for p in rows_dict[row_idx]}

            # Add widgets for each column (including empty placeholders)
            for col in range(num_cols):
                if col in col_to_placement:
                    placement = col_to_placement[col]
                    widget = self._create_widget(placement, is_last_col=(col == max_col))
                    self._widgets[placement.control_id] = widget
                    row_widgets.append(widget)
                else:
                    # Empty placeholder with appropriate size
                    if is_fader_row:
                        row_widgets.append(Static("", classes="fader-placeholder"))
                    else:
                        row_widgets.append(Static("", classes="cell-placeholder"))

            row_container = Horizontal(*row_widgets, classes="grid-row")
            row_containers.append(row_container)

        # Stack rows vertically
        grid = Vertical(*row_containers, classes="controller-grid")

        # Create section container with title and grid
        container = Vertical(
            Static(section.name, classes="section-title"),
            grid,
            classes="section",
            id=f"section-{section.name.lower().replace(' ', '-')}",
        )

        return container

    def _create_widget(self, placement, is_last_col: bool = False) -> Static:
        """Create appropriate widget for control placement.

        Args:
            placement: Control placement data
            is_last_col: Whether this widget is in the last column (for wider buttons)
        """
        if placement.widget_type == ControlWidget.PAD:
            return PadWidget(placement.control_id, classes="pad")
        elif placement.widget_type == ControlWidget.FADER:
            return FaderWidget(
                placement.control_id,
                label=placement.label or placement.control_id,
                classes="fader",
            )
        elif placement.widget_type == ControlWidget.BUTTON:
            # Use wider buttons for the last column (typically scene buttons)
            btn_classes = "button wide-button" if is_last_col else "button"
            return ButtonWidget(
                placement.control_id,
                label=placement.label or placement.control_id,
                classes=btn_classes,
            )
        elif placement.widget_type in (ControlWidget.KNOB, ControlWidget.ENCODER):
            return KnobWidget(
                placement.control_id,
                label=placement.label or placement.control_id,
                classes="knob",
            )
        else:
            return Static(placement.control_id)

    async def _apply_full_state(self, states: dict[str, ControlState]) -> None:
        """Apply full state to all widgets."""
        for control_id, state in states.items():
            await self._update_control(control_id, state)

    async def _update_control(self, control_id: str, state: ControlState) -> None:
        """Update a single control widget."""
        widget = self._widgets.get(control_id)
        if not widget:
            return

        if isinstance(widget, PadWidget):
            log(state)
            widget.is_on = state.is_on if state.is_on is not None else False

            # Get colors from state
            widget.color = state.color

            widget._update_style()
            log(widget.color)

        elif isinstance(widget, FaderWidget):
            # Handle None value explicitly (fader not yet moved)
            widget.value = state.value if state.value is not None else 0
        elif isinstance(widget, ButtonWidget):
            widget.is_on = state.is_on if state.is_on is not None else False
        elif isinstance(widget, KnobWidget):
            widget.value = state.value if state.value is not None else 64

        widget.update()

    def action_reconnect(self) -> None:
        """Reconnect to WebSocket server."""
        self.notify("Reconnecting...")
        self.run_worker(self._connect_and_listen(), exclusive=True)


def run_tui(ws_url: str = "ws://127.0.0.1:8765") -> None:
    """
    Run the TUI application.

    Args:
        ws_url: WebSocket URL to connect to
    """
    app = ControllerStateApp(ws_url=ws_url)
    app.run()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Padbound State Debug TUI")
    parser.add_argument(
        "--url",
        default="ws://127.0.0.1:8765",
        help="WebSocket URL to connect to (default: ws://127.0.0.1:8765)",
    )
    args = parser.parse_args()

    run_tui(args.url)


if __name__ == "__main__":
    main()
