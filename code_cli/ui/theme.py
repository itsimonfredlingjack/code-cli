# code_cli/ui/theme.py

from pygments.style import Style as PygmentsStyle
from pygments.token import Comment, Error, Generic, Keyword, Name, Number, Operator, String
from rich.box import ROUNDED

# Semantic Color Tokens (CODENTIC Theme)
COLORS = {
    # Backgrounds
    "bg": "#0B0F13",  # Background base
    "panel": "#121824",  # Panel surface
    "panel_raised": "#18202D",  # Panel raised
    "border": "#2B3646",  # Border
    # Text
    "text": "#E8EEF6",  # Text primary
    "text_muted": "#9AA7B5",  # Text muted
    # Accents
    "accent_orange": "#EE9405",  # Orange accent (current vibe)
    "accent_cyan": "#46C8FF",  # Cyan (activity/streaming)
    "success": "#31D158",  # Green (success/apply)
    "danger": "#FF453A",  # Red (error/danger)
    # Legacy compatibility (mapped to new tokens)
    "surface": "#121824",  # Alias for panel
    "surface_light": "#2B3646",  # Alias for border
    "surface_glow": "#18202D",  # Alias for panel_raised
    "primary": "#46C8FF",  # Alias for accent_cyan
    "secondary": "#EE9405",  # Alias for accent_orange
    "tertiary": "#31D158",  # Alias for success
    "error": "#FF453A",  # Alias for danger
    "warning": "#EE9405",  # Alias for accent_orange
    "text_dim": "#9AA7B5",  # Alias for text_muted
    "text_bright": "#E8EEF6",  # Alias for text
    "focus_ring": "#46C8FF",  # Alias for accent_cyan
    "card_border": "#2B3646",  # Alias for border
    "card_shadow": "#0B0F13",  # Alias for bg
}

# Color Discipline Rules:
# - accent_cyan: ONLY for active streaming/focus
# - accent_orange: warnings, pending
# - danger: errors
# - success: completed successfully
# - border: default/neutral

STATUS_COLORS = {
    "streaming": COLORS["accent_cyan"],
    "pending": COLORS["accent_orange"],
    "running": COLORS["accent_cyan"],
    "done": COLORS["border"],
    "ok": COLORS["success"],
    "error": COLORS["danger"],
    "warning": COLORS["accent_orange"],
    "info": COLORS["text_muted"],
}

# Badge colors for timeline cards
BADGE_COLORS = {
    "user": COLORS["text_muted"],
    "think": COLORS["accent_cyan"],
    "think_done": COLORS["text_muted"],
    "action": COLORS["accent_orange"],
    "action_ok": COLORS["success"],
    "action_error": COLORS["danger"],
    "plan": COLORS["accent_cyan"],
    "diff": COLORS["text_muted"],
    "error": COLORS["danger"],
    "verify_pass": COLORS["success"],
    "verify_fail": COLORS["danger"],
    "decision": COLORS["accent_orange"],
    "decision_approved": COLORS["success"],
    "decision_denied": COLORS["danger"],
    "system": COLORS["text_muted"],
}

# Tool secondary color for dimmed tool output
TOOL_SECONDARY = COLORS["text_muted"]

# Typography variants for consistent text styling
TYPOGRAPHY = {
    "title": f"bold {COLORS['text']}",
    "subtitle": COLORS["text"],
    "body": COLORS["text"],
    "muted": COLORS["text_muted"],
    "timestamp": f"dim {COLORS['text_muted']}",
}

CSS_VARS = f"""
    /* Semantic tokens */
    $bg: {COLORS["bg"]};
    $panel: {COLORS["panel"]};
    $panel_raised: {COLORS["panel_raised"]};
    $border: {COLORS["border"]};
    
    $text: {COLORS["text"]};
    $text_muted: {COLORS["text_muted"]};
    
    $accent_orange: {COLORS["accent_orange"]};
    $accent_cyan: {COLORS["accent_cyan"]};
    $success: {COLORS["success"]};
    $danger: {COLORS["danger"]};
    
    /* Legacy compatibility */
    $surface: {COLORS["surface"]};
    $surface_light: {COLORS["surface_light"]};
    $surface_glow: {COLORS["surface_glow"]};
    $primary: {COLORS["primary"]};
    $secondary: {COLORS["secondary"]};
    $tertiary: {COLORS["tertiary"]};
    $error: {COLORS["error"]};
    $warning: {COLORS["warning"]};
    $text_dim: {COLORS["text_dim"]};
    $text_bright: {COLORS["text_bright"]};
    $focus_ring: {COLORS["focus_ring"]};
    $card_border: {COLORS["card_border"]};
    $card_shadow: {COLORS["card_shadow"]};
"""

# --- STRUCTURAL ASSETS ---

HUD = ROUNDED

# --- ICONOGRAPHY (Nerd Font + ASCII fallbacks) ---

ICONS = {
    # Branch/Git
    "branch": ("󰘬", "BR"),
    "git": ("󰊢", "GIT"),
    # Model/LLM
    "model": ("󰒼", "MODEL"),
    "tokens": ("󰑲", "tks"),
    # Status
    "queue": ("󰃃", "Q"),
    "spinner": ("󰔚", "..."),
    "done": ("󰄬", "[DONE]"),
    "error": ("󰅖", "ERR"),
    # Tools
    "tool": ("󰆍", "TOOL"),
    "diff": ("󰀀", "DIFF"),
    "file": ("󰈔", "FILE"),
    # Navigation (single-char ASCII for narrow rail)
    "search": ("󰍉", "/"),
    "files": ("󰉋", "F"),
    "sessions": ("󰨞", "S"),
    "settings": ("󰒓", "*"),
    "tools": ("󰆍", "T"),
    # Actions
    "approve": ("󰄬", "OK"),
    "reject": ("󰜺", "X"),
    "expand": ("󰁔", "▶"),
    "collapse": ("󰁍", "▼"),
    # Badge icons for timeline cards
    "badge_user": ("󰀄", "USR"),
    "badge_think": ("󰔚", "THK"),
    "badge_action": ("󰆍", "ACT"),
    "badge_plan": ("󰙅", "PLN"),
    "badge_diff": ("󰀀", "DIF"),
    "badge_error": ("󰅖", "ERR"),
    "badge_verify": ("󰐥", "VRF"),
    "badge_decision": ("󰌑", "DEC"),
    "badge_system": ("󰒓", "SYS"),
    # Agent status
    "status_idle": ("󰒲", "IDLE"),
    "status_thinking": ("󰔚", "..."),
    "status_acting": ("󰆍", "ACT"),
    "status_verifying": ("󰐥", "VRF"),
}


def get_icon(name: str) -> str:
    """
    Get icon with Nerd Font fallback to ASCII.

    Returns Nerd Font icon (index 0) if use_nerd_fonts=True in config,
    otherwise returns ASCII fallback (index 1).
    """
    icon_pair = ICONS.get(name, ("?", "?"))

    # Try to load config and check use_nerd_fonts setting
    try:
        from code_cli.config import Config

        config = Config.load()
        use_nerd_fonts = config.ui.use_nerd_fonts
    except Exception:
        # If config isn't available or loading fails, default to ASCII
        use_nerd_fonts = False

    return icon_pair[0] if use_nerd_fonts else icon_pair[1]


class CodeNeonStyle(PygmentsStyle):
    """Neon HUD Syntax Highlighting"""

    background_color = COLORS["surface"]
    highlight_color = COLORS["surface_glow"]

    styles = {
        Keyword: f"bold {COLORS['primary']}",
        Keyword.Constant: f"bold {COLORS['tertiary']}",
        Keyword.Namespace: f"bold {COLORS['primary']}",
        Name: COLORS["text"],
        Name.Function: f"bold {COLORS['primary']}",
        Name.Class: f"bold {COLORS['tertiary']}",
        Name.Builtin: COLORS["primary"],
        String: COLORS["success"],
        String.Doc: f"italic {COLORS['text_dim']}",
        Number: COLORS["secondary"],
        Operator: COLORS["primary"],
        Comment: f"italic {COLORS['text_dim']}",
        Error: f"bold {COLORS['error']}",
        Generic.Prompt: f"bold {COLORS['primary']}",
        Generic.Output: COLORS["text"],
        Generic.Traceback: COLORS["error"],
    }
