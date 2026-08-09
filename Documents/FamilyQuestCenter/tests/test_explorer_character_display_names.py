"""Automated regression/validation coverage.

File: tests/test_explorer_character_display_names.py
Reviewed for v1.7.0-rc1 cleanup.
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_explorer_avatar_names_do_not_include_skin_tones():
    bad = re.compile(r"(light|medium|dark|deep)", re.I)
    found = []

    for path in ROOT.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        stack = [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                key = str(item.get("key", "")).lower()
                name = item.get("name")
                if isinstance(name, str) and ("girl" in key or "boy" in key) and ("explorer" in key or "adventurer" in key):
                    found.append(name)
                    assert not bad.search(name), f"{path}: {name}"
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)

    assert found

def test_character_workshop_uses_simple_public_names():
    template = (ROOT / "templates/child/character.html").read_text(encoding="utf-8")
    assert '"Girl Explorer"' in template
    assert '"Boy Explorer"' in template
    assert 'previewName.textContent = publicName;' in template
