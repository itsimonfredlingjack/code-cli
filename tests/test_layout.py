# tests/test_layout.py
"""Tests for layout components."""

import pytest


def test_transcript_pane_has_add_system_message():
    """TranscriptPane should have add_system_message method."""
    from code_cli.ui.layout import TranscriptPane
    from code_cli.ui.cards import SystemCard

    pane = TranscriptPane()
    # Method should exist
    assert hasattr(pane, 'add_system_message')
    assert callable(getattr(pane, 'add_system_message'))
