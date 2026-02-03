# code_cli/ui/widgets.py
# Shared primitives: modals, command palette, enums, messages

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json

import pygments.styles
from rich.syntax import Syntax
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ListItem, ListView

from .theme import COLORS

pygments.styles.STYLE_MAP["code_neon"] = "code_cli.ui.theme:CodeNeonStyle"


class SafeArmState(str, Enum):
    SAFE = "SAFE"
    ARMED = "ARMED"
    ARMED_PENDING = "ARMED_PENDING"


@dataclass(frozen=True)
class PaletteCommand:
    command_id: str
    title: str
    description: str


from textual.message import Message


class CardSelected(Message):
    """Message sent when a card is selected."""
    
    def __init__(self, card) -> None:
        super().__init__()
        self.card = card


class CommandItem(ListItem):
    def __init__(self, command: PaletteCommand) -> None:
        self.command_id = command.command_id
        label = Label(f"{command.title} — {command.description}")
        super().__init__(label)


class CommandPalette(ModalScreen[str | None]):
    CSS = f"""
    CommandPalette {{
        align: center middle;
        background: rgba(0, 0, 0, 0.7);
    }}

    #palette {{
        width: 80;
        height: auto;
        padding: 1 2;
        border: solid {COLORS['primary']};
        background: {COLORS['surface']};
    }}

    #palette-input {{
        height: 3;
        border: solid {COLORS['surface_light']};
        background: {COLORS['surface_glow']};
    }}
    """

    def __init__(self, commands: list[PaletteCommand]) -> None:
        super().__init__()
        self._commands = commands
        self._filtered = commands

    def compose(self) -> ComposeResult:
        with Container(id="palette"):
            yield Input(placeholder="Search commands", id="palette-input")
            yield ListView(id="palette-list")

    def on_mount(self) -> None:
        self._render_list(self._commands)
        self.query_one("#palette-input", Input).focus()

    def _render_list(self, commands: list[PaletteCommand]) -> None:
        list_view = self.query_one("#palette-list", ListView)
        list_view.remove_children()
        for command in commands:
            list_view.mount(CommandItem(command))

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip().lower()
        if not query:
            self._filtered = self._commands
        else:
            self._filtered = [
                cmd
                for cmd in self._commands
                if query in cmd.title.lower() or query in cmd.description.lower()
            ]
        self._render_list(self._filtered)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._filtered:
            self.dismiss(self._filtered[0].command_id)
        else:
            self.dismiss(None)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item = event.item
        if isinstance(item, CommandItem):
            self.dismiss(item.command_id)


class ApprovalModal(ModalScreen[bool]):
    CSS = f"""
    ApprovalModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 4 4 1;
        padding: 1 2;
        width: 84;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def __init__(self, tool_name: str, arguments: dict, diff_text: str, reason: str, risk: str) -> None:
        super().__init__()
        self.tool_name = tool_name
        self.arguments = arguments
        self.diff_text = diff_text
        self.reason = reason
        self.risk = risk

    def compose(self) -> ComposeResult:
        args_json = json.dumps(self.arguments, indent=2)
        reason_line = f"Reason: {self.reason} | Risk: {self.risk}"

        yield Container(
            Label(f"CONFIRM TOOL: {self.tool_name}", id="title"),
            Label(reason_line, id="reason"),
            Syntax(
                self.diff_text or "No diff available",
                "diff",
                theme="code_neon",
                line_numbers=False,
                word_wrap=True,
                id="diff",
            ),
            Syntax(
                args_json,
                "json",
                theme="code_neon",
                line_numbers=False,
                word_wrap=True,
                id="details",
            ),
            Button("REJECT", variant="error", id="reject"),
            Button("APPROVE", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ArmConfirmModal(ModalScreen[bool]):
    CSS = f"""
    ArmConfirmModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Label("ENABLE ARMED MODE", id="title"),
            Label("Tools can write files or run commands.", id="details"),
            Button("CANCEL", variant="error", id="reject"),
            Button("ARM", variant="success", id="approve"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "approve":
            self.dismiss(True)
        else:
            self.dismiss(False)


class ArmRequiredModal(ModalScreen[bool]):
    CSS = f"""
    ArmRequiredModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 1;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Label("ARMED REQUIRED", id="title"),
            Label("Switch to ARMED to approve tool execution.", id="details"),
            Button("OK", variant="primary", id="ok"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(False)


class ClearTranscriptModal(ModalScreen[bool]):
    """Modal for confirming transcript clear operation"""

    CSS = f"""
    ClearTranscriptModal {{
        align: center middle;
        background: rgba(0, 0, 0, 0.85);
    }}

    #dialog {{
        grid-size: 2;
        grid-gutter: 1 2;
        grid-rows: 1fr 2 1;
        padding: 1 2;
        width: 70;
        height: auto;
        border: solid {COLORS['warning']};
        background: {COLORS['surface']};
    }}

    #title {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        text-style: bold;
        color: {COLORS['warning']};
    }}

    #details {{
        column-span: 2;
        height: 2;
        width: 100%;
        content-align: center middle;
        color: {COLORS['text']};
    }}

    #shortcuts {{
        column-span: 2;
        height: 1;
        width: 100%;
        content-align: center middle;
        color: {COLORS['text_dim']};
        text-style: italic;
    }}

    Button {{
        width: 100%;
    }}
    """

    def __init__(self, message_count: int):
        super().__init__()
        self.message_count = message_count

    def compose(self) -> ComposeResult:
        count_text = f"Delete {self.message_count} message{'s' if self.message_count != 1 else ''}"
        yield Container(
            Label("CLEAR CONVERSATION HISTORY", id="title"),
            Label(count_text + " from transcript?", id="details"),
            Label("ESC=Cancel  Enter=Confirm", id="shortcuts"),
            Button("CANCEL", variant="error", id="cancel"),
            Button("CLEAR", variant="warning", id="confirm"),
            id="dialog",
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm":
            self.dismiss(True)
        else:
            self.dismiss(False)

    def on_key(self, event) -> None:
        if event.key == "escape":
            self.dismiss(False)
        elif event.key == "enter":
            self.dismiss(True)
