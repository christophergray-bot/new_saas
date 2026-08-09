"""Automated regression/validation coverage.

File: tests/test_fqc_new_014_character_picker.py
Reviewed for v1.7.0-rc1 cleanup.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "templates/child/character.html"

def test_character_picker_uses_four_step_flow():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "Step 1" in text and "Pick Your Profile Character" in text
    assert "Step 2" in text and "Choose Your Skin Tone" in text
    assert "('frame_key', 'Step 3', 'Choose Your Frame'" in text
    assert "('theme_key', 'Step 4', 'Choose Your Theme'" in text
    assert "Choose Your Character Style" not in text
    assert "Pick the kind of explorer you want to be." not in text

def test_picker_labels_only_boy_and_girl_explorer():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert '"Girl Explorer"' in text
    assert '"Boy Explorer"' in text
    assert 'publicCharacterName' in text
    assert 'previewName.textContent = publicName;' in text

def test_legacy_default_adventurers_are_not_presented_as_picker_choices():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert 'const parsed = radios.map(parseAvatar).filter(Boolean);' in text
    assert 'const avatars = parsed.filter(a => a.style === explorerStyle && !a.radio.disabled);' in text
