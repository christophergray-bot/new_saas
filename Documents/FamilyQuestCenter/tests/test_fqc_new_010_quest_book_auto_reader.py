"""Automated regression/validation coverage.

File: tests/test_fqc_new_010_quest_book_auto_reader.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_quest_book_reader_has_read_aloud_controls():
    template = (ROOT / "templates/quest_books/reader.html").read_text(encoding="utf-8")
    assert 'id="quest-book-read-play"' in template
    assert 'id="quest-book-read-pause"' in template
    assert 'id="quest-book-read-stop"' in template
    assert 'id="quest-book-story-text"' in template
    assert 'id="quest-book-scene-title"' in template

def test_quest_book_reader_uses_browser_speech_api_and_stops_on_navigation():
    template = (ROOT / "templates/quest_books/reader.html").read_text(encoding="utf-8")
    assert '"speechSynthesis" in window' in template
    assert 'new SpeechSynthesisUtterance(text)' in template
    assert 'window.speechSynthesis.pause()' in template
    assert 'window.speechSynthesis.resume()' in template
    assert 'window.speechSynthesis.cancel()' in template
    assert 'window.addEventListener("pagehide"' in template

def test_read_aloud_has_browser_fallback():
    template = (ROOT / "templates/quest_books/reader.html").read_text(encoding="utf-8")
    assert 'Read Aloud is not supported by this browser.' in template
    assert 'status.textContent = "Unavailable"' in template
