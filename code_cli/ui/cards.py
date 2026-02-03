# code_cli/ui/cards.py

from __future__ import annotations

from datetime import datetime
import json

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual import events
from textual.binding import Binding
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static
from textual.containers import Container, Vertical

from .theme import COLORS, HUD, get_icon


class CodeBlockWidget(Widget):
    """Syntax-highlighted code block with copy affordance."""

    can_focus = True

    BINDINGS = [
        Binding("c", "copy_code", "Copy"),
    ]

    def __init__(self, code: str, language: str = "text", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.code = code
        self.language = language

    def render(self) -> RenderableType:
        # Header with language and copy hint
        header = Text()
        header.append(f" {self.language} ", style=f"on {COLORS['panel_raised']} {COLORS['text']}")
        header.append("  ", style=COLORS["text_muted"])
        header.append("[c]", style=f"bold {COLORS['accent_cyan']}")
        header.append("opy", style=COLORS["text_muted"])

        return Panel(
            Syntax(self.code, self.language, theme="monokai", word_wrap=True, background_color=COLORS["panel"]),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 1),
            style=f"on {COLORS['panel']}",
        )

    def action_copy_code(self) -> None:
        """Copy code to clipboard."""
        import subprocess
        import platform
        try:
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=self.code.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=self.code.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")


class BaseCard(Widget):
    """Base card component with common functionality."""

    can_focus = True
    content = reactive("")
    collapsed = reactive(False)

    BINDINGS = [
        Binding("y", "copy_content", "Copy"),
    ]

    def __init__(self, title: str, content: str, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.title = title
        self.content = content
        self.timestamp = datetime.now()

    def _truncate(self, text: str, limit: int = 14) -> str:
        lines = text.splitlines()
        if len(lines) <= limit:
            return text
        return "\n".join(lines[:limit]) + "\n..."

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self.refresh(layout=True)

    def _update_status_class(self, status: str) -> None:
        """Update CSS class based on status."""
        self.remove_class("streaming", "error", "warning", "success")
        if status in ("streaming", "error", "warning", "success"):
            self.add_class(status)

    def action_copy_content(self) -> None:
        """Copy card content to clipboard."""
        import subprocess
        import platform
        try:
            text = self.content
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")

    def on_click(self, event: events.Click) -> None:
        from .widgets import CardSelected
        self.post_message(CardSelected(self))


class UserMessageCard(BaseCard):
    """Card for user messages."""
    
    def __init__(self, content: str, **kwargs: object) -> None:
        super().__init__("USER", content, **kwargs)
        self.role = "user"
    
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        header = f"USER · {time_str}"
        body = self._truncate(self.content) if self.collapsed else self.content
        return Panel(
            Text(body, style=COLORS["text"]),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class AgentMessageCard(Container):
    """Card for agent messages with streaming support and focusable code blocks."""

    can_focus = True
    collapsed = reactive(False)
    content = reactive("")
    _streaming = reactive(False)
    _status = reactive("done")  # streaming, done, error
    _stream_buffer = ""
    _last_render_time = 0.0
    _render_throttle_ms = 33  # ~30 fps
    _content_container = None

    BINDINGS = [
        Binding("y", "copy_content", "Copy"),
    ]

    def __init__(self, content: str = "", **kwargs: object) -> None:
        super().__init__(**kwargs)
        self.role = "assistant"
        self.content = content
        self._streaming = False
        self._status = "done"
        self._stream_buffer = ""
        self._last_render_time = 0.0
        self.timestamp = datetime.now()
        self.title = "AGENT"
        self._content_container = None

    def compose(self):
        """Yield child widgets for text and code blocks."""
        # Header
        yield Static(self._build_header(), classes="agent-card-header", id="agent-header")

        # Content container - will hold dynamically updated children
        content_container = Vertical(classes="agent-card-content", id="agent-content")
        yield content_container

    def on_mount(self) -> None:
        """After mount, populate the content container with parsed content."""
        self._content_container = self.query_one("#agent-content", Vertical)
        self._rebuild_content()

    def _rebuild_content(self) -> None:
        """Rebuild the content container's children."""
        if not self._content_container:
            return

        # Clear existing content children
        self._content_container.remove_children()

        # Parse and mount new children
        body_content = self._truncate(self.content) if self.collapsed else self.content
        parts = self._parse_content_with_code_blocks(body_content)

        if not parts or (len(parts) == 1 and parts[0][0] == "text" and not parts[0][1]):
            # Empty or no content
            if self._status == "streaming":
                self._content_container.mount(Static(Markdown("*Thinking...*"), classes="agent-card-text"))
            else:
                self._content_container.mount(Static("", classes="agent-card-text"))
        else:
            children = []
            for i, part in enumerate(parts):
                if part[0] == "text":
                    if part[1]:
                        children.append(Static(Markdown(part[1]), classes="agent-card-text"))
                elif part[0] == "code":
                    lang, code = part[1], part[2]
                    children.append(CodeBlockWidget(code, lang, classes="agent-card-code"))

            if children:
                self._content_container.mount(*children)

    def _build_header(self) -> Text:
        """Build the header text with status indicator."""
        time_str = self.timestamp.strftime("%H:%M")

        # Status indicator (compact)
        if self._status == "streaming":
            status_icon = get_icon("spinner")
            status_text = f"{status_icon} STREAMING"
            status_color = COLORS["accent_cyan"]
        elif self._status == "error":
            status_icon = get_icon("error")
            status_text = f"{status_icon} ERROR"
            status_color = COLORS["danger"]
        else:
            status_icon = get_icon("done")
            status_text = f"{status_icon} DONE"
            status_color = COLORS["border"]

        header = Text()
        header.append(f"AGENT · {status_text} · {time_str}", style=status_color)
        return header

    def _truncate(self, text: str, limit: int = 14) -> str:
        lines = text.splitlines()
        if len(lines) <= limit:
            return text
        return "\n".join(lines[:limit]) + "\n..."

    def append(self, text: str) -> None:
        """Append text to stream buffer (throttled rendering)."""
        self._stream_buffer += text
        self._throttled_refresh()

    def _throttled_refresh(self) -> None:
        """Refresh only if enough time has passed (throttle to ~30 fps)."""
        import time
        now = time.time()
        elapsed_ms = (now - self._last_render_time) * 1000
        if elapsed_ms >= self._render_throttle_ms:
            self.content += self._stream_buffer
            self._stream_buffer = ""
            self._last_render_time = now
            self._rebuild_content()

    def start_streaming(self) -> None:
        """Mark card as streaming."""
        self._streaming = True
        self._status = "streaming"
        self._update_status_class("streaming")
        self._update_header()

    def stop_streaming(self) -> None:
        """Mark card as done streaming."""
        # Flush any remaining buffer
        if self._stream_buffer:
            self.content += self._stream_buffer
            self._stream_buffer = ""
        self._streaming = False
        self._status = "done"
        self._update_status_class("done")
        self._rebuild_content()

    def mark_error(self) -> None:
        """Mark card as failed."""
        # Flush any remaining buffer
        if self._stream_buffer:
            self.content += self._stream_buffer
            self._stream_buffer = ""
        self._streaming = False
        self._status = "error"
        self._update_status_class("error")
        self._rebuild_content()

    def _update_status_class(self, status: str) -> None:
        """Update CSS class based on status."""
        self.remove_class("streaming", "error", "warning", "success")
        if status in ("streaming", "error", "warning", "success"):
            self.add_class(status)

    def _update_header(self) -> None:
        """Update just the header widget."""
        try:
            header_widget = self.query_one(".agent-card-header", Static)
            if header_widget:
                header_widget.update(self._build_header())
        except Exception:
            # Header not mounted yet
            pass

    def toggle_collapse(self) -> None:
        self.collapsed = not self.collapsed
        self._rebuild_content()

    def _parse_content_with_code_blocks(self, content: str) -> list:
        """Parse content and extract code blocks for special rendering."""
        import re

        parts = []
        code_pattern = r'```(\w*)\n(.*?)```'
        last_end = 0

        for match in re.finditer(code_pattern, content, re.DOTALL):
            # Text before code block
            if match.start() > last_end:
                text_before = content[last_end:match.start()].strip()
                if text_before:
                    parts.append(("text", text_before))

            # Code block
            language = match.group(1) or "text"
            code = match.group(2).strip()
            parts.append(("code", language, code))

            last_end = match.end()

        # Text after last code block
        if last_end < len(content):
            text_after = content[last_end:].strip()
            if text_after:
                parts.append(("text", text_after))

        return parts if parts else [("text", content)]

    def action_copy_content(self) -> None:
        """Copy card content to clipboard."""
        import subprocess
        import platform
        try:
            text = self.content
            if platform.system() == "Darwin":
                subprocess.run(["pbcopy"], input=text.encode(), check=True)
            else:
                subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), check=True)
            self.app.notify("Copied to clipboard", severity="information")
        except Exception:
            self.app.notify("Copy failed - clipboard unavailable", severity="warning")

    def on_click(self, event: events.Click) -> None:
        from .widgets import CardSelected
        self.post_message(CardSelected(self))


class ToolCallCard(BaseCard):
    """Card for tool calls with status and duration."""
    
    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        status: str = "pending",  # pending, approved, running, ok, error
        duration_ms: int | None = None,
        **kwargs: object,
    ) -> None:
        title = f"TOOL {tool_name.upper()}"
        super().__init__(title, "", **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.status = status
        self.duration_ms = duration_ms
    
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        
        # Status badge - color discipline: cyan only for active/streaming
        status_colors = {
            "pending": COLORS["accent_orange"],
            "approved": COLORS["border"],  # Neutral when approved but not running
            "running": COLORS["accent_cyan"],
            "ok": COLORS["success"],
            "error": COLORS["danger"],
        }
        status_color = status_colors.get(self.status, COLORS["text_muted"])
        
        duration_text = f" · {self.duration_ms}ms" if self.duration_ms else ""
        header = f"{self.tool_name.upper()} · {self.status.upper()}{duration_text} · {time_str}"
        
        args_json = json.dumps(self.arguments, indent=2)
        body_text = f"ARGS:\n{args_json}"
        body = self._truncate(body_text, limit=18) if self.collapsed else body_text
        
        return Panel(
            Syntax(body, "json", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class ToolResultCard(BaseCard):
    """Card for tool execution results."""
    
    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        result: str = "",
        is_error: bool = False,
        **kwargs: object,
    ) -> None:
        title = f"RESULT {tool_name.upper()}"
        super().__init__(title, result, **kwargs)
        self.tool_name = tool_name
        self.arguments = arguments or {}
        self.is_error = is_error
    
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        status = "ERROR" if self.is_error else "OK"
        status_color = COLORS["danger"] if self.is_error else COLORS["success"]
        
        header = f"{self.tool_name.upper()} · {status} · {time_str}"
        body = self._truncate(self.content, limit=18) if self.collapsed else self.content

        if self.is_error:
            renderable = Text(body, style=COLORS["danger"])
        else:
            renderable = Syntax(body, "text", theme="code_neon", word_wrap=True)

        return Panel(
            renderable,
            title=header,
            title_align="left",
            border_style=status_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class DiffCard(BaseCard):
    """Card for showing diffs with expand/collapse."""
    
    def __init__(self, diff_text: str, file_path: str = "", **kwargs: object) -> None:
        super().__init__("DIFF", diff_text, **kwargs)
        self.file_path = file_path
        self._full_diff = diff_text
    
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        diff_icon = get_icon("diff")
        
        header = f"{diff_icon} DIFF"
        if self.file_path:
            header += f" · {self.file_path}"
        header += f" · {time_str}"
        
        # Show summary when collapsed
        if self.collapsed:
            lines = self._full_diff.splitlines()
            summary = f"{len(lines)} lines changed"
            if lines:
                # Show first few changed lines
                preview_lines = [l for l in lines[:5] if l.startswith(("+", "-"))]
                summary += "\n" + "\n".join(preview_lines[:3])
                if len(preview_lines) > 3:
                    summary += "\n..."
            body = summary
        else:
            body = self._full_diff
        
        return Panel(
            Syntax(body, "diff", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=COLORS["border"],  # Neutral border - cyan only for active/focus
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class ErrorCard(BaseCard):
    """Card for error messages."""
    
    def __init__(self, error_message: str, details: str = "", **kwargs: object) -> None:
        super().__init__("ERROR", error_message, **kwargs)
        self.details = details
    
    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        error_icon = get_icon("error")
        
        header = f"{error_icon} ERROR · {time_str}"
        
        body = self.content
        if self.details and not self.collapsed:
            body += f"\n\nDETAILS:\n{self.details}"
        elif self.collapsed:
            body = self._truncate(body, limit=10)
        
        return Panel(
            Text(body, style=COLORS["danger"]),
            title=header,
            title_align="left",
            border_style=COLORS["danger"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class SystemCard(BaseCard):
    """Card for system/runtime messages (not streaming)."""

    def __init__(self, content: str, level: str = "info", **kwargs: object) -> None:
        super().__init__("SYSTEM", content, **kwargs)
        self.level = level  # info, warning, error

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")

        if self.level == "warning":
            level_color = COLORS["accent_orange"]
            level_text = "WARNING"
        elif self.level == "error":
            level_color = COLORS["danger"]
            level_text = "ERROR"
        else:
            level_color = COLORS["text_muted"]
            level_text = "INFO"

        header = f"SYSTEM · {level_text} · {time_str}"
        body = self._truncate(self.content) if self.collapsed else self.content

        return Panel(
            Text(body, style=COLORS["text"]),
            title=header,
            title_align="left",
            border_style=level_color,
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class PlanCard(BaseCard):
    """Card for showing plans."""

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")
        header = f"PLAN · {time_str}"
        body = self._truncate(self.content, limit=18) if self.collapsed else self.content
        
        return Panel(
            Markdown(body),
            title=header,
            title_align="left",
            border_style=COLORS["border"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class PendingToolCallCard(ToolCallCard):
    """Card for pending tool calls in SAFE mode with approve/reject buttons."""
    
    def __init__(
        self,
        tool_name: str,
        arguments: dict | None = None,
        on_approve: callable | None = None,
        on_reject: callable | None = None,
        on_approve_all: callable | None = None,
        **kwargs: object,
    ) -> None:
        super().__init__(tool_name, arguments, status="pending", **kwargs)
        self.on_approve = on_approve
        self.on_reject = on_reject
        self.on_approve_all = on_approve_all
    
    def render(self) -> RenderableType:
        """Render with action buttons (buttons are handled via click events)."""
        time_str = self.timestamp.strftime("%H:%M")
        header = f"{self.tool_name.upper()} · PENDING · {time_str}"
        
        args_json = json.dumps(self.arguments, indent=2)
        body_text = f"ARGS:\n{args_json}\n\n[Approve Once] [Approve All Until Idle] [Reject]"
        body = self._truncate(body_text, limit=18) if self.collapsed else body_text
        
        return Panel(
            Syntax(body, "json", theme="code_neon", word_wrap=True),
            title=header,
            title_align="left",
            border_style=COLORS["accent_orange"],
            box=HUD,
            padding=(0, 0),
            style=f"on {COLORS['panel']}",
        )


class EmptyStateCard(BaseCard):
    """Card shown when transcript is empty."""
    
    def __init__(self, **kwargs: object) -> None:
        super().__init__("", "", **kwargs)
        self.examples = [
            "Add a new feature to handle user authentication",
            "Fix the bug in the login function",
            "Refactor the database connection code",
        ]
    
    def render(self) -> RenderableType:
        content = Text()
        content.append("Type a request, or press ", style=COLORS["text_muted"])
        content.append("Ctrl+Shift+P", style=f"bold {COLORS['accent_cyan']}")
        content.append(" for commands\n\n", style=COLORS["text_muted"])
        content.append("Examples:\n", style=COLORS["text"])
        for i, example in enumerate(self.examples, 1):
            content.append(f"  {i}. ", style=COLORS["text_muted"])
            content.append(example, style=COLORS["text"])
            content.append("\n", style=COLORS["text_muted"])
        
        return Panel(
            content,
            border_style=COLORS["border"],
            box=HUD,
            padding=(1, 2),
            style=f"on {COLORS['panel']}",
        )
