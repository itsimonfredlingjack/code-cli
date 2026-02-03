# code_cli/ui/layout.py

from __future__ import annotations

import json
from pathlib import Path

from rich.console import RenderableType
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer, Vertical
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView, Static, TabbedContent, TabPane

from .cards import (
    AgentMessageCard,
    DiffCard,
    EmptyStateCard,
    ErrorCard,
    PlanCard,
    SystemCard,
    ToolCallCard,
    ToolResultCard,
    UserMessageCard,
)
from .theme import COLORS, get_icon


class SectionHeader(Static):
    """Section header for navigation panels."""
    
    def __init__(self, label: str, **kwargs: object) -> None:
        # Don't pass classes to super - add them after initialization
        kwargs.pop("classes", None)  # Remove if present to avoid conflict
        super().__init__(label, **kwargs)
        # Add base class after initialization
        self.add_class("section-header")


class LeftRail(Container):
    """Collapsible left rail: icon-only (4 chars) or expanded (26 chars)."""

    can_focus = True

    BINDINGS = [
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "select_icon", "Select", show=False),
    ]

    _icon_ids = ["icon-files", "icon-sessions", "icon-tools", "icon-search", "icon-settings"]

    def __init__(self, root_path: Path, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.root_path = root_path
        self._expanded = False
        self._active_icon = None  # Track which icon is active
    
    def compose(self) -> ComposeResult:
        from .project_tree import PinnedFilesPanel, ProjectTree
        
        # Always compose all widgets, show/hide based on state
        yield Static(get_icon("files"), id="icon-files", classes="rail-icon")
        yield Static(get_icon("sessions"), id="icon-sessions", classes="rail-icon")
        yield Static(get_icon("tools"), id="icon-tools", classes="rail-icon")
        yield Static(get_icon("search"), id="icon-search", classes="rail-icon")
        yield Static(get_icon("settings"), id="icon-settings", classes="rail-icon")
        
        # Create section headers with merged classes
        nav_header = SectionHeader("NAVIGATOR", id="header-nav")
        nav_header.add_class("rail-expanded")
        yield nav_header
        
        yield ProjectTree(self.root_path, id="project-tree", classes="rail-expanded")
        
        pinned_header = SectionHeader("PINNED", id="header-pinned")
        pinned_header.add_class("rail-expanded")
        yield pinned_header
        
        yield PinnedFilesPanel(id="pinned-files", classes="rail-expanded")
        
        tools_header = SectionHeader("TOOLS", id="header-tools")
        tools_header.add_class("rail-expanded")
        yield tools_header
        
        yield ToolRunList(id="tool-runs", classes="rail-expanded")
        
        sessions_header = SectionHeader("SESSIONS", id="header-sessions")
        sessions_header.add_class("rail-expanded")
        yield sessions_header
        
        yield SessionList(id="sessions", classes="rail-expanded")
    
    def on_mount(self) -> None:
        """Set initial state."""
        self._update_display()
        # Set first icon as active by default
        if not self._expanded:
            first_icon = self.query_one("#icon-files", Static)
            if first_icon:
                first_icon.add_class("active")
                self._active_icon = "icon-files"
    
    def toggle(self) -> None:
        """Toggle between collapsed and expanded (keybinding-only, not via clicks)."""
        # Don't toggle if locked in focus mode
        if self.has_class("focus-locked"):
            return
        self._expanded = not self._expanded
        if self._expanded:
            self.add_class("expanded")
        else:
            self.remove_class("expanded")
        self._update_display()
        self.refresh(layout=True)
    
    def on_click(self, event) -> None:
        """Handle icon clicks for selection (but not expand/collapse)."""
        # Only handle clicks directly on icons, not anywhere else in the rail
        target = event.target
        if target and hasattr(target, "id"):
            icon_id = target.id
            if icon_id and icon_id.startswith("icon-"):
                # Update active icon
                if self._active_icon:
                    old_icon = self.query_one(f"#{self._active_icon}", Static)
                    if old_icon:
                        old_icon.remove_class("active")
                target.add_class("active")
                self._active_icon = icon_id
                self.focus()
                event.stop()
                return
        # For any other click in the rail, stop propagation but don't expand
        event.stop()
    
    def on_mouse_down(self, event) -> None:
        """Prevent any mouse-down from causing expand/collapse."""
        # Only handle clicks directly on icons or within the rail itself
        target = event.target
        # Check if click is on an icon
        if target and hasattr(target, "id") and target.id and target.id.startswith("icon-"):
            # Allow icon clicks to proceed (handled by on_click)
            return
        # Check if click is within the rail container (not outside)
        if target and hasattr(target, "parent") and target.parent == self:
            # Click is within rail, allow it but don't expand
            event.stop()
            return
        # For clicks outside the rail (shouldn't happen, but be safe), stop propagation
        event.stop()
    
    def on_focus(self) -> None:
        """Prevent focus from causing expansion."""
        # Focus should not expand the rail - only Ctrl+B should
        pass
    
    def _update_display(self) -> None:
        """Update visibility of widgets based on expanded state."""
        # Show/hide icon-only widgets
        for widget in self.query(".rail-icon"):
            widget.display = not self._expanded

        # Show/hide expanded widgets
        for widget in self.query(".rail-expanded"):
            widget.display = self._expanded

    def _set_active_icon(self, icon_id: str) -> None:
        """Set the active icon by ID."""
        # Remove active from current
        if self._active_icon:
            try:
                old_icon = self.query_one(f"#{self._active_icon}", Static)
                old_icon.remove_class("active")
            except Exception:
                pass
        # Add active to new
        try:
            new_icon = self.query_one(f"#{icon_id}", Static)
            new_icon.add_class("active")
            self._active_icon = icon_id
        except Exception:
            pass

    def action_move_up(self) -> None:
        """Move selection up in collapsed mode."""
        if self._expanded or not self._active_icon:
            return
        try:
            idx = self._icon_ids.index(self._active_icon)
            new_idx = (idx - 1) % len(self._icon_ids)
            self._set_active_icon(self._icon_ids[new_idx])
        except ValueError:
            pass

    def action_move_down(self) -> None:
        """Move selection down in collapsed mode."""
        if self._expanded or not self._active_icon:
            return
        try:
            idx = self._icon_ids.index(self._active_icon)
            new_idx = (idx + 1) % len(self._icon_ids)
            self._set_active_icon(self._icon_ids[new_idx])
        except ValueError:
            pass

    def action_select_icon(self) -> None:
        """Select/activate the current icon."""
        if not self._active_icon:
            return
        # For now, selecting an icon expands the rail to show details
        # Future: Could trigger specific panel content
        if not self._expanded:
            self.toggle()


class ToolRunList(ListView):
    """List of tool runs."""
    
    def add_run(self, label: str) -> None:
        self.mount(ListItem(Label(label)))
    
    def clear_runs(self) -> None:
        self.remove_children()


class SessionList(ListView):
    """List of sessions."""
    
    def set_sessions(self, sessions: list[str]) -> None:
        self.remove_children()
        for name in sessions:
            self.mount(ListItem(Label(name)))


class PinnedActivityBar(Widget):
    """Compact activity bar (1-2 lines max) showing current agent activity."""

    _active = reactive(False)
    _current_step = reactive("")
    _current_file = reactive("")
    _current_tool = reactive("")
    _elapsed_seconds = reactive(0)
    _start_time = 0.0

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._active = False
        self._start_time = 0.0

    def watch__active(self, active: bool) -> None:
        """Update CSS class when active state changes."""
        if active:
            self.add_class("active")
        else:
            self.remove_class("active")

    def start_activity(self, step: str, file: str = "", tool: str = "") -> None:
        """Start showing activity."""
        import time
        self._active = True
        self._current_step = step
        self._current_file = file
        self._current_tool = tool
        self._elapsed_seconds = 0
        self._start_time = time.time()
        self.refresh()

    def stop_activity(self) -> None:
        """Stop showing activity."""
        self._active = False
        self._start_time = 0.0
        self.refresh()

    def tick_elapsed(self) -> None:
        """Update elapsed time from start_time. Call periodically."""
        import time
        if self._active and self._start_time > 0:
            self._elapsed_seconds = int(time.time() - self._start_time)
            self.refresh()
    
    def update_elapsed(self, seconds: int) -> None:
        """Update elapsed time."""
        self._elapsed_seconds = seconds
        self.refresh()
    
    def render(self) -> RenderableType:
        if not self._active:
            return Text("")
        
        text = Text()
        spinner = get_icon("spinner")
        text.append(f"{spinner} ", style=COLORS["accent_cyan"])
        text.append(self._current_step, style=COLORS["text"])
        
        if self._current_file:
            text.append(" · ", style=COLORS["text_muted"])
            file_icon = get_icon("file")
            text.append(f"{file_icon} {self._current_file}", style=COLORS["text"])
        
        if self._current_tool:
            text.append(" · ", style=COLORS["text_muted"])
            tool_icon = get_icon("tool")
            text.append(f"{tool_icon} {self._current_tool}", style=COLORS["text"])
        
        if self._elapsed_seconds > 0:
            text.append(" · ", style=COLORS["text_muted"])
            text.append(f"{self._elapsed_seconds}s", style=COLORS["text_muted"])
        
        return text


class TranscriptPane(ScrollableContainer):
    """Main transcript pane showing timeline of cards."""
    
    can_focus = True
    _user_at_bottom = reactive(True)
    
    def compose(self) -> ComposeResult:
        with Vertical(id="transcript-list"):
            yield Static(id="transcript-top")

    def _list(self) -> Vertical:
        return self.query_one("#transcript-list", Vertical)

    def _append_card(self, card: Widget) -> Widget:
        """Append a card to the transcript list and autoscroll if at bottom."""
        self._list().mount(card)
        if self._user_at_bottom:
            # Scroll after layout is updated to avoid reflow jumps
            self.call_after_refresh(self.scroll_end, animate=False)
        return card

    def card_children(self) -> list[Widget]:
        """Return list of card widgets in the transcript."""
        return list(self._list().children)

    def has_non_empty_cards(self) -> bool:
        """Check if transcript has any non-empty-state cards."""
        return any(not isinstance(c, EmptyStateCard) for c in self._list().children)
    
    def add_message(self, role: str, content: str) -> UserMessageCard | AgentMessageCard:
        """Add a message card."""
        if role == "user":
            card = UserMessageCard(content, classes="card")
        else:
            card = AgentMessageCard(content, classes="card")
            card.start_streaming()
        return self._append_card(card)

    def add_system_message(self, content: str, level: str = "info") -> SystemCard:
        """Add a system message card (not streaming)."""
        card = SystemCard(content, level=level, classes="card")
        return self._append_card(card)
    
    def add_tool_call(
        self,
        tool_name: str,
        arguments: dict | None = None,
        status: str = "pending",
        duration_ms: int | None = None,
    ) -> ToolCallCard:
        """Add a tool call card."""
        card = ToolCallCard(tool_name, arguments, status, duration_ms, classes="card")
        return self._append_card(card)
    
    def add_tool_result(
        self,
        tool_name: str,
        arguments: dict | None = None,
        result: str = "",
        is_error: bool = False,
    ) -> ToolResultCard:
        """Add a tool result card."""
        card = ToolResultCard(tool_name, arguments, result, is_error, classes="card")
        if len(result.splitlines()) > 18:
            card.collapsed = True
        return self._append_card(card)
    
    def add_diff(self, diff_text: str, file_path: str = "") -> DiffCard:
        """Add a diff card."""
        card = DiffCard(diff_text, file_path, classes="card")
        if len(diff_text.splitlines()) > 10:
            card.collapsed = True
        return self._append_card(card)
    
    def add_error(self, error_message: str, details: str = "") -> ErrorCard:
        """Add an error card."""
        card = ErrorCard(error_message, details, classes="card")
        return self._append_card(card)
    
    def add_plan(self, content: str) -> PlanCard:
        """Add a plan card."""
        card = PlanCard("PLAN", content, classes="card")
        if len(content.splitlines()) > 18:
            card.collapsed = True
        return self._append_card(card)
    
    def show_empty_state(self) -> None:
        """Show empty state card."""
        if not any(isinstance(c, EmptyStateCard) for c in self._list().children):
            card = EmptyStateCard(classes="card")
            self._append_card(card)

    def remove_empty_state(self) -> None:
        """Remove empty state card if present."""
        for child in list(self._list().children):
            if isinstance(child, EmptyStateCard):
                child.remove()

    def clear_cards(self) -> None:
        """Remove all cards while keeping the transcript anchor."""
        for child in list(self._list().children):
            if child.id != "transcript-top":
                child.remove()
    
    def on_scroll(self) -> None:
        """Track if user is at bottom for smart autoscroll."""
        # Check if scroll position is at bottom
        scroll_y = self.scroll_y
        max_scroll_y = self.max_scroll_y
        self._user_at_bottom = scroll_y >= max_scroll_y - 1


class CodeOutputPane(Container):
    """Collapsible code output pane (starts collapsed)."""
    
    can_focus = True
    _collapsed = reactive(True)
    
    def compose(self) -> ComposeResult:
        with ScrollableContainer(id="code-output-scroll"):
            yield SectionHeader("CODE OUTPUT")
            yield Static(id="code-output-content")
    
    def toggle(self) -> None:
        """Toggle collapsed state."""
        self._collapsed = not self._collapsed
        if self._collapsed:
            self.remove_class("expanded")
            self.display = False
        else:
            self.add_class("expanded")
            self.display = True
        self.refresh(layout=True)
    
    def show_code(self, code: str, language: str = "text") -> None:
        """Show code in the pane."""
        try:
            widget = self.query_one("#code-output-content", Static)
        except Exception:
            # Fallback if scroll container structure changed
            widget = self.query_one("#code-output-scroll", Static)
        widget.update(Syntax(code, language, theme="code_neon", word_wrap=True))
        if self._collapsed:
            self.toggle()  # Auto-expand when showing code
    
    def show_diff(self, diff_text: str) -> None:
        """Show diff in the pane."""
        try:
            widget = self.query_one("#code-output-content", Static)
        except Exception:
            # Fallback if scroll container structure changed
            widget = self.query_one("#code-output-scroll", Static)
        widget.update(Syntax(diff_text, "diff", theme="code_neon", word_wrap=True))
        if self._collapsed:
            self.toggle()  # Auto-expand when showing diff


class CenterPane(Vertical):
    """Center pane containing activity bar, transcript, and code output."""
    
    def on_click(self, event) -> None:
        """Handle clicks - only stop if clicking on pane itself, not children."""
        # Only stop if clicking directly on CenterPane, not on child widgets
        target = getattr(event, "widget", None)
        if target == self:
            event.stop()
        # Otherwise let clicks propagate to children (like input)
    
    def on_mouse_down(self, event) -> None:
        """Handle mouse-down - only stop if clicking on pane itself, not children."""
        # Only stop if clicking directly on CenterPane, not on child widgets
        target = getattr(event, "widget", None)
        if target == self:
            event.stop()
        # Otherwise let mouse-down propagate to children (like input)
    
    def compose(self) -> ComposeResult:
        yield PinnedActivityBar(id="pinned-activity")
        yield TranscriptPane(id="transcript")
        yield CodeOutputPane(id="code-output")


class InspectorDrawer(Container):
    """Inspector drawer as overlay (not persistent column)."""
    
    can_focus = True
    _visible = reactive(False)
    _width = reactive(45)
    
    BINDINGS = [
        Binding("escape", "close_drawer", "Close", priority=True),
        Binding("ctrl+i", "close_drawer", "Close", priority=True),
        Binding("ctrl+\\", "close_drawer", "Close", priority=True),
    ]
    
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._visible = False
        self._width = 45
        self._diff_view = Static("No diff yet. Generate a patch to see changes here.", id="diff-view")
        self._tool_view = Static("Select a tool card to see details here.", id="tool-view")
        self._context_view = Static("Pin files to build context.", id="context-view")
        self._logs_view = Static("No logs yet. Tool execution logs will appear here.", id="logs-view")
    
    def compose(self) -> ComposeResult:
        with TabbedContent(id="inspector-tabs"):
            with TabPane("Diff", id="tab-diff"):
                yield self._diff_view
            with TabPane("Tool", id="tab-tool"):
                yield self._tool_view
            with TabPane("Context", id="tab-context"):
                yield self._context_view
            with TabPane("Logs", id="tab-logs"):
                yield self._logs_view
    
    def toggle(self) -> None:
        """Toggle drawer visibility."""
        self._visible = not self._visible
        self._update_display()
        if self._visible:
            self.focus()
        self.refresh(layout=True)
    
    def show(self) -> None:
        """Show drawer."""
        self._visible = True
        self._update_display()
        self.focus()
        self.refresh(layout=True)
    
    def hide(self) -> None:
        """Hide drawer."""
        self._visible = False
        self._update_display()
        self.refresh(layout=True)
    
    def _update_display(self) -> None:
        """Update display and check for small terminal fallback."""
        if not self._visible:
            self.display = False
            self.remove_class("visible")
            self.remove_class("fullscreen")
            self.can_focus = False  # Prevent focus interception when hidden
            # Remove drawer-open class from screen
            if self.app and hasattr(self.app, "screen"):
                self.app.screen.remove_class("drawer-open")
            return
        
        # Check terminal width for small terminal fallback
        if self.app and hasattr(self.app, "screen"):
            terminal_width = self.app.screen.size.width
            # Also check if drawer width would be too large relative to terminal
            if terminal_width < 100 or self._width >= terminal_width * 0.8:
                # Full-screen modal for small terminals or when drawer is too wide
                self.display = True
                self.add_class("visible")
                self.add_class("fullscreen")
                # Update width for fullscreen
                self.styles.width = "100%"
            else:
                # Normal side drawer
                self.display = True
                self.add_class("visible")
                self.remove_class("fullscreen")
                # Restore drawer width
                self.styles.width = self._width
            self.can_focus = True  # Allow focus when visible
            # Add drawer-open class to screen for dimming effect (single source of truth)
            self.app.screen.add_class("drawer-open")
        else:
            # Fallback: normal display
            self.display = True
            self.add_class("visible")
            self.can_focus = True  # Allow focus when visible
            if self.app and hasattr(self.app, "screen"):
                self.app.screen.add_class("drawer-open")
    
    def resize(self, delta: int) -> None:
        """Resize drawer width."""
        self._width = max(30, min(60, self._width + delta))
        # Update width style
        self.styles.width = self._width
        # Call _update_display to check if fullscreen is needed after resize
        self._update_display()
        self.refresh(layout=True)
    
    def show_diff(self, diff_text: str) -> None:
        """Show diff in drawer."""
        if diff_text.strip():
            self._diff_view.update(Syntax(diff_text, "diff", theme="code_neon", word_wrap=True))
        else:
            self._diff_view.update("No diff yet. Generate a patch to see changes here.")
    
    def show_tool(self, tool_name: str, arguments: dict | None = None, result: str = "") -> None:
        """Show tool details in drawer."""
        args_json = json.dumps(arguments or {}, indent=2)
        body = f"TOOL: {tool_name}\n\nARGS:\n{args_json}\n\nRESULT:\n{result}"
        self._tool_view.update(Syntax(body, "text", theme="code_neon", word_wrap=True))
    
    def show_context(self, pinned: list[str], ctx_pct: int) -> None:
        """Show context in drawer."""
        if not pinned:
            body = "Pin files to build context."
        else:
            body = "Pinned Files:\n" + "\n".join(f"- {p}" for p in pinned)
        body += f"\n\nCTX {ctx_pct}%"
        self._context_view.update(Text(body, style=COLORS["text"]))
    
    def append_log(self, log_text: str) -> None:
        """Append to logs view."""
        widget = self.query_one("#logs-view", Static)
        current = widget.renderable
        if isinstance(current, Text):
            current.append(log_text)
            widget.update(current)
        else:
            widget.update(Text(log_text, style=COLORS["text"]))
    
    def action_close_drawer(self) -> None:
        """Close drawer (bound to Esc/Ctrl+I on drawer itself)."""
        self.hide()


class ComposerBar(Container):
    """Bottom composer bar (fixed height, always visible)."""

    _hint_text = "Type a request, or press Ctrl+Shift+P for commands"

    def compose(self) -> ComposeResult:
        with Vertical(id="composer-stack"):
            yield Static(self._hint_text, id="hint-strip", classes="hint")
            yield Input(placeholder="Type a message...", id="composer-input")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Hide hint strip when typing."""
        hint = self.query_one("#hint-strip", Static)
        if event.value:
            hint.update("")
        else:
            hint.update(self._hint_text)

    def on_focus(self, event) -> None:
        """Hide hint when input is focused."""
        hint = self.query_one("#hint-strip", Static)
        hint.update("")

    def on_blur(self, event) -> None:
        """Show hint when input loses focus (if empty)."""
        try:
            input_widget = self.query_one("#composer-input", Input)
            hint = self.query_one("#hint-strip", Static)
            if not input_widget.value:
                hint.update(self._hint_text)
        except Exception:
            pass
