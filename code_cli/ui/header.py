# code_cli/ui/header.py

from rich.align import Align
from rich.console import RenderableType
from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget

from .theme import COLORS, get_icon
from .widgets import SafeArmState


class CodenticHeader(Widget):
    """Two-line header for CODENTIC with branch, model, CTX bar, queue, latency."""

    model = reactive("unknown")
    branch = reactive("main")
    mode = reactive(SafeArmState.SAFE.value)
    ctx_pct = reactive(0)
    ctx_used = reactive(0)
    ctx_max = reactive(0)
    queue_count = reactive(0)
    tokens_per_sec = reactive(0.0)
    latency_ms = reactive(0)
    is_active = reactive(False)

    def render(self) -> RenderableType:
        # Line 1: CODENTIC title + version + activity spinner
        line1 = Text()
        line1.append("CODENTIC", style=f"bold {COLORS['text']}")
        line1.append(" v0.7.0", style=COLORS["text_muted"])
        if self.is_active:
            spinner = get_icon("spinner")
            line1.append(f" {spinner}", style=COLORS["accent_cyan"])
        
        # Line 2: Mode pill | Branch | Model | CTX bar | Queue | Latency
        line2 = Text()
        
        # Mode pill
        if self.mode == SafeArmState.SAFE.value:
            mode_bg = COLORS["accent_orange"]
            mode_text = "SAFE"
        elif self.mode == SafeArmState.ARMED.value:
            mode_bg = COLORS["success"]
            mode_text = "ARMED"
        else:
            mode_bg = COLORS["accent_cyan"]
            mode_text = "ARMED*"
        
        line2.append(f" {mode_text} ", style=f"on {mode_bg} {COLORS['bg']}")
        line2.append(" | ", style=COLORS["text_muted"])
        
        # Branch
        branch_icon = get_icon("branch")
        line2.append(f"{branch_icon} {self.branch}", style=COLORS["text"])
        line2.append(" | ", style=COLORS["text_muted"])
        
        # Model
        model_icon = get_icon("model")
        line2.append(f"{model_icon} {self.model}", style=COLORS["text"])
        line2.append(" | ", style=COLORS["text_muted"])
        
        # CTX bar (visual bar, not percentage)
        ctx_bar_width = 8
        ctx_filled = int((self.ctx_pct / 100) * ctx_bar_width) if self.ctx_max > 0 else 0
        ctx_bar = "█" * ctx_filled + "░" * (ctx_bar_width - ctx_filled)
        ctx_color = COLORS["accent_cyan"] if self.ctx_pct < 70 else COLORS["accent_orange"] if self.ctx_pct < 90 else COLORS["danger"]
        line2.append(f"CTX ", style=COLORS["text_muted"])
        line2.append(ctx_bar, style=ctx_color)
        line2.append(f" {self.ctx_pct}%", style=COLORS["text_muted"])
        line2.append(" | ", style=COLORS["text_muted"])
        
        # Queue count (always show, even if 0)
        queue_icon = get_icon("queue")
        queue_style = COLORS["accent_orange"] if self.queue_count > 0 else COLORS["text_muted"]
        line2.append(f"{queue_icon} {self.queue_count}", style=queue_style)
        line2.append(" | ", style=COLORS["text_muted"])
        
        # Latency (always show if available)
        if self.latency_ms > 0:
            line2.append(f"{self.latency_ms}ms", style=COLORS["text_muted"])
            line2.append(" | ", style=COLORS["text_muted"])
        
        # Tokens/sec (show if streaming)
        if self.tokens_per_sec > 0:
            tokens_icon = get_icon("tokens")
            line2.append(f"{tokens_icon} {self.tokens_per_sec:.1f}/s", style=COLORS["accent_cyan"])
        
        content = Text()
        content.append(line1)
        content.append("\n")
        content.append(line2)
        
        return Align.left(content)
