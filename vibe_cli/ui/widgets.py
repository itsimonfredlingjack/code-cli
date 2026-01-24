from textual.widget import Widget
from textual.widgets import Static
from rich.console import RenderableType
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text
from rich.panel import Panel
from rich.align import Align
from rich.console import Group
from datetime import datetime
from typing import Optional, List
import math
import random
from textual.reactive import reactive
from rich import box
from .theme import COLORS, VibeNeonStyle
import pygments.styles

# Register custom neon theme
pygments.styles.STYLE_MAP["vibe_neon"] = "vibe_cli.ui.theme:VibeNeonStyle"


class StatusBar(Static):
    """Input status indicator"""

    status = reactive("ready")  # ready, typing, processing
    char_count = reactive(0)
    model_name = reactive("phi-4")
    _frame = reactive(0)

    def on_mount(self) -> None:
        self.set_interval(0.3, self._tick)

    def _tick(self) -> None:
        self._frame += 1
        if self.status == "processing":
            self.refresh()

    def render(self) -> RenderableType:
        # Animated spinner for processing
        spinners = ["◐", "◓", "◑", "◒"]
        spinner = spinners[self._frame % len(spinners)]
        model_info = f" [dim]│[/] [dim]Model:[/] [{COLORS['tertiary']}]{self.model_name}[/]"

        if self.status == "processing":
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] "
                f"[{COLORS['secondary']}]{spinner}[/] [{COLORS['secondary']}]Processing...[/]{model_info}"
            )
        elif self.status == "typing":
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] "
                f"[{COLORS['tertiary']}]{self.char_count}[/] [dim]chars[/] [dim]│[/] "
                f"[dim][Enter] Send[/]{model_info}"
            )
        else:  # ready
            return Text.from_markup(
                f"[dim][?] Help[/] [dim]│[/] [{COLORS['success']}]●[/] [{COLORS['text']}]Ready[/]{model_info}"
            )


class SystemBanner(Static):
    """Session info header with ASCII icons"""

    # Reactive properties for live data
    tokens_used = reactive(2400)
    tokens_total = reactive(4000)
    latency_ms = reactive(234)
    git_branch = reactive("main")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._session_start = datetime.now()

    def on_mount(self) -> None:
        self.set_interval(1.0, self.refresh)  # Update every second

    def render(self) -> RenderableType:
        time_str = datetime.now().strftime("%H:%M")

        # Session duration
        elapsed = datetime.now() - self._session_start
        minutes = int(elapsed.total_seconds() // 60)
        seconds = int(elapsed.total_seconds() % 60)
        session_str = f"{minutes}m {seconds:02d}s"

        # Token percentage with color coding
        token_pct = int((self.tokens_used / self.tokens_total) * 100)
        if token_pct < 50:
            token_color = COLORS["success"]
        elif token_pct < 80:
            token_color = COLORS["warning"]
        else:
            token_color = COLORS["error"]

        # Latency color coding
        if self.latency_ms < 500:
            lat_color = COLORS["success"]
        elif self.latency_ms < 1000:
            lat_color = COLORS["warning"]
        else:
            lat_color = COLORS["error"]

        # Build header with ASCII icons (no emojis!)
        content = Text.from_markup(
            f"[bold {COLORS['primary']}]VIBE_OS[/] [dim]│[/] "
            f"[{COLORS['text']}]{time_str}[/] [dim]│[/] "
            f"[{COLORS['secondary']}]◷[/] [{COLORS['text']}]{session_str}[/] [dim]│[/] "
            f"[{token_color}]▣[/] [{COLORS['text']}]{self.tokens_used}/{self.tokens_total}[/] "
            f"[dim]([/][{token_color}]{token_pct}%[/][dim])[/] [dim]│[/] "
            f"[{lat_color}]◈[/] [{COLORS['text']}]{self.latency_ms}ms[/] [dim]│[/] "
            f"[{COLORS['tertiary']}]⌥[/] [{COLORS['secondary']}]{self.git_branch}[/]"
        )
        return Panel(Align.center(content), style=f"on {COLORS['bg']}", border_style=COLORS["primary"])


class AICoreAvatar(Widget):
    """The Impossible ASCII Sphere"""

    state = reactive("idle")
    phase = reactive(0.0)

    def on_mount(self) -> None:
        self.set_interval(0.05, self.tick)  # 20 FPS

    def tick(self) -> None:
        self.phase += 0.1
        self.refresh()

    def render(self) -> RenderableType:
        # Generate a 3D-ish sphere using density characters
        width, height = 16, 8  # Perfect fit for 24-col sidebar
        output_lines = []

        center_x, center_y = width / 2, height / 2

        # State modifiers
        spin_speed = 1.0
        if self.state == "thinking":
            spin_speed = 3.0
        elif self.state == "coding":
            spin_speed = 0.5

        time_offset = self.phase * spin_speed

        for y in range(height):
            line = ""
            for x in range(width):
                # Normalize coords -1 to 1
                nx = (x - center_x) / (width / 2.5)
                ny = (y - center_y) / (height / 2.5)

                # Sphere equation + rotation simulation
                # Z-depth estimation
                dist = math.sqrt(nx * nx + ny * ny)

                if dist > 1.0:
                    char = " "
                    # Random glitch pixels
                    if self.state == "coding" and random.random() < 0.05:
                        char = random.choice([".", ",", "`"])
                else:
                    # 3D rotation effect
                    z = math.sqrt(1.0 - dist * dist)
                    # Simple lighting calculation
                    angle = math.atan2(ny, nx) + time_offset
                    lighting = math.sin(angle * 3) * z

                    # Density mapping
                    if lighting > 0.8:
                        char = "█"
                    elif lighting > 0.5:
                        char = "▓"
                    elif lighting > 0.2:
                        char = "▒"
                    elif lighting > -0.2:
                        char = "░"
                    else:
                        char = "·"

                line += char
            output_lines.append(line)

        # Mood ring color based on state
        ring_color = COLORS["primary"]  # lavender for idle
        ring_style = ""
        if self.state == "thinking":
            ring_color = COLORS["secondary"]  # mint
            ring_style = "bold"
        elif self.state == "coding":
            ring_color = COLORS["tertiary"]  # peach
        elif self.state == "error":
            ring_color = COLORS["error"]  # pink
            ring_style = "bold blink"
        elif self.state == "success":
            ring_color = COLORS["success"]  # sage

        # Animated ring characters
        ring_chars = "░▒▓█▓▒"
        ring_idx = int(self.phase * 2) % len(ring_chars)
        ring_char = ring_chars[ring_idx]

        # Build title with animated ring effect
        if self.state in ("thinking", "coding"):
            title = f"[{ring_style} {ring_color}]{ring_char}[/] CORE [{ring_style} {ring_color}]{ring_char}[/]"
        else:
            title = f"[{ring_color}]●[/] CORE [{ring_color}]●[/]"

        art = "\n".join(output_lines)
        return Panel(
            Align.center(Text(art, style=f"bold {ring_color}")),
            title=title,
            border_style=f"{ring_style} {ring_color}".strip(),
            style=f"on {COLORS['bg']}",
            box=box.ROUNDED,
        )


class PowerGauge(Widget):
    """Vertical retro-grade gauge"""

    level = reactive(0.0)
    label = reactive("")

    def render(self) -> RenderableType:
        height = 10
        filled_height = int(self.level * height)

        lines = []
        for i in range(height):
            # Invert Y (draw from bottom up)
            y = (height - 1) - i

            if y < filled_height:
                # Gradient logic: Low=Green, Mid=Yellow, High=Red
                val = y / height
                if val < 0.5:
                    col = COLORS["success"]
                elif val < 0.8:
                    col = COLORS["warning"]
                else:
                    col = COLORS["error"]

                char = "█" + "▓▒░"[i % 3]  # Texture
                lines.append(f"[{col}]{char * 4}[/]")
            else:
                lines.append(f"[dim]{'░' * 4}[/]")

        return Panel(Align.center("\n".join(lines)), title=self.label, border_style=COLORS["surface_light"])


class HyperChatBubble(Widget):
    """Floating glass interaction bubble"""

    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None):
        super().__init__()
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now()

    def render(self) -> RenderableType:
        time_str = self.timestamp.strftime("%H:%M")

        if self.role == "user":
            header = f"[bold {COLORS['primary']}]➜ COMMAND[/]"
            content_render = Text(self.content, style=COLORS["text"])

            panel = Panel(
                content_render,
                title=header,
                title_align="right",
                subtitle=f"[dim]@{time_str}[/]",
                subtitle_align="right",
                border_style=COLORS["primary"],
                box=box.HEAVY,  # Sharp, command-line feel
                padding=(0, 1),
                style="on default",  # Transparent/default bg
                expand=False,  # Shrink to fit content
            )
            return Align.right(panel)

        elif self.role == "assistant":
            header = f"[bold {COLORS['secondary']}]◈ AI_CORE[/]"
            content_render = Markdown(self.content)

            panel = Panel(
                content_render,
                title=header,
                title_align="left",
                subtitle=f"[dim]@{time_str}[/]",
                subtitle_align="left",
                border_style=COLORS["secondary"],
                box=box.ROUNDED,  # Clean rounded borders
                padding=(0, 1),
                style=f"on {COLORS['surface']}",  # Glassy bg
                width=60,  # Fixed width for readability
            )
            return Align.left(panel)

        elif self.role == "tool":
            header = f"[bold {COLORS['warning']}]⚡ SYS_EXEC[/] [dim]@{time_str}[/]"
            content_render = Syntax(self.content, "bash", theme="vibe_neon")

            # Tool logs take full width (or centered)
            return Panel(
                content_render,
                title=header,
                border_style=COLORS["warning"],
                box=box.ASCII,  # Raw log feel
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
            )

        else:  # Error
            header = f"[bold {COLORS['error']}]⚠ CRITICAL[/] [dim]@{time_str}[/]"
            content_render = Text(self.content, style=COLORS["error"])

            return Panel(
                content_render,
                title=header,
                border_style=COLORS["error"],
                padding=(0, 1),
                style=f"on {COLORS['surface']}",
            )


class CommandHistory(Static):
    """Mini command log for sidebar"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._commands: list[tuple[str, str]] = []  # (name, status)

    def add_command(self, name: str, status: str = "pending") -> None:
        """Add a command. Status: pending, success, error"""
        self._commands.append((name, status))
        # Keep only last 5
        if len(self._commands) > 5:
            self._commands = self._commands[-5:]
        self.refresh()

    def update_last(self, status: str) -> None:
        """Update the status of the last command"""
        if self._commands:
            name, _ = self._commands[-1]
            self._commands[-1] = (name, status)
            self.refresh()

    def render(self) -> RenderableType:
        text = Text()

        if not self._commands:
            text.append("  No commands yet", style="dim")
        else:
            for i, (name, status) in enumerate(self._commands):
                icon, color = self._get_status_icon(status)
                if i > 0:
                    text.append("\n")
                text.append(" ▸ ", style="dim")
                text.append(f"{name[:8]:<8} ")  # Shorter truncation
                text.append(icon, style=color)

        return Panel(
            text,
            title="LOG",
            border_style=COLORS["surface_light"],
            style=f"on {COLORS['surface']}",
        )

    def _get_status_icon(self, status: str) -> tuple[str, str]:
        """Return (icon, color) for status"""
        if status == "success":
            return ("✓", COLORS["success"])
        elif status == "error":
            return ("✗", COLORS["error"])
        else:  # pending
            return ("◌", COLORS["warning"])


class ShortcutsPanel(Static):
    """Keyboard shortcuts overlay"""

    def render(self) -> RenderableType:
        shortcuts = [
            ("[?]", "Toggle Help"),
            ("[Ctrl+C]", "Quit"),
            ("[Ctrl+L]", "Clear Chat"),
            ("[↑/↓]", "History"),
            ("[Enter]", "Send"),
        ]

        lines = []
        for key, desc in shortcuts:
            lines.append(f"  [{COLORS['secondary']}]{key:<10}[/] [{COLORS['text']}]{desc}[/]")

        return Panel(
            Text.from_markup("\n".join(lines)),
            title=f"[bold {COLORS['primary']}]KEYMAP[/]",
            border_style=COLORS["primary"],
            style=f"on {COLORS['surface']}",
        )
