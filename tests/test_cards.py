# tests/test_cards.py
"""Tests for card components."""

import pytest
from rich.console import Console
from io import StringIO
from code_cli.ui.cards import SystemCard, CodeBlockWidget


def _render_to_text(renderable) -> str:
    """Render a Rich renderable to plain text."""
    console = Console(file=StringIO(), force_terminal=True, width=80)
    console.print(renderable)
    return console.file.getvalue()


def test_system_card_renders_without_streaming():
    """SystemCard should never show STREAMING status."""
    card = SystemCard("Test warning", level="warning")
    rendered = card.render()
    # Render to text for assertion
    rendered_str = _render_to_text(rendered)
    assert "STREAMING" not in rendered_str
    assert "SYSTEM" in rendered_str
    # Expanded rendering shows WARNING level
    card.collapsed = False
    expanded_str = _render_to_text(card.render())
    assert "WARNING" in expanded_str


def test_system_card_levels():
    """SystemCard supports info, warning, error levels."""
    info_card = SystemCard("Info message", level="info")
    warn_card = SystemCard("Warning message", level="warning")
    error_card = SystemCard("Error message", level="error")

    assert info_card.level == "info"
    assert warn_card.level == "warning"
    assert error_card.level == "error"


def test_system_card_default_level():
    """SystemCard defaults to info level."""
    card = SystemCard("Default level message")
    assert card.level == "info"


def test_system_card_content():
    """SystemCard stores content correctly."""
    card = SystemCard("Test content", level="warning")
    assert card.content == "Test content"
    assert card.title == "SYSTEM"


def test_code_block_widget_stores_code_and_language():
    """CodeBlockWidget stores code and language correctly."""
    widget = CodeBlockWidget("print('hello')", language="python")
    assert widget.language == "python"
    assert widget.code == "print('hello')"


def test_code_block_widget_default_language():
    """CodeBlockWidget defaults to text language."""
    widget = CodeBlockWidget("some code")
    assert widget.language == "text"


def test_code_block_widget_renders_with_language():
    """CodeBlockWidget renders with language label."""
    widget = CodeBlockWidget("print('hello')", language="python")
    rendered = widget.render()
    rendered_str = _render_to_text(rendered)
    assert "python" in rendered_str.lower()


def test_agent_message_card_parses_code_blocks():
    """AgentMessageCard parses code blocks from content."""
    from code_cli.ui.cards import AgentMessageCard

    card = AgentMessageCard()
    content = """Here is some code:

```python
print('hello')
```

And some more text."""

    parts = card._parse_content_with_code_blocks(content)

    # Should have 3 parts: text, code, text
    assert len(parts) == 3
    assert parts[0][0] == "text"
    assert "Here is some code" in parts[0][1]
    assert parts[1][0] == "code"
    assert parts[1][1] == "python"
    assert "print('hello')" in parts[1][2]
    assert parts[2][0] == "text"
    assert "And some more text" in parts[2][1]
