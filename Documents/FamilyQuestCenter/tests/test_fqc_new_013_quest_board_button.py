"""Automated regression/validation coverage.

File: tests/test_fqc_new_013_quest_board_button.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_family_quest_board_button_is_compact_and_right_aligned():
    template = (ROOT / "templates/family_dashboard.html").read_text(encoding="utf-8")
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")

    assert 'family-quest-board-action' in template
    assert '.profile-selector-card .family-quest-board-action' in css
    assert 'justify-self: end;' in css
    assert 'width: auto;' in css
    assert 'min-height: 34px;' in css
