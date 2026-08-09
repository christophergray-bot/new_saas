"""Automated regression/validation coverage.

File: tests/test_fqc_new_010_quest_book_auto_reader_visible.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_read_aloud_controls_are_inside_story_card_above_story_text():
    template = (ROOT / "templates/quest_books/reader.html").read_text(encoding="utf-8")
    story_card = template.index('quest-book-story-card')
    controls = template.index('id="quest-book-read-aloud"')
    story_text = template.index('id="quest-book-story-text"')
    assert story_card < controls < story_text
    assert "Read This Page" in template

def test_read_aloud_controls_use_existing_family_quest_button_classes():
    template = (ROOT / "templates/quest_books/reader.html").read_text(encoding="utf-8")
    assert 'class="button button-primary quest-book-audio-button"' in template
    assert 'class="button button-secondary quest-book-audio-button"' in template

def test_read_aloud_layout_has_family_quest_theme_styling():
    css = (ROOT / "static/style.css").read_text(encoding="utf-8")
    assert ".quest-book-read-aloud-inline" in css
    assert "border-radius: 16px;" in css
    assert "rgba(111, 78, 171" in css
