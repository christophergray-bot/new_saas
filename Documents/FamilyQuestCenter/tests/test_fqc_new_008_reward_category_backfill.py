"""Automated regression/validation coverage.

File: tests/test_fqc_new_008_reward_category_backfill.py
Reviewed for v1.7.0-rc1 cleanup.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_starter_pack_version_for_category_backfill():
    pack = json.loads((ROOT / "content/packs/explorer_starter_pack/pack.json").read_text(encoding="utf-8"))
    assert pack["version"] == "2.1.1"
    assert [c["name"] for c in pack["reward_categories"]] == [
        "Treats & Snacks",
        "Screen & Game Time",
        "Activities & Adventures",
        "Special Privileges",
    ]

def test_update_path_backfills_each_missing_category():
    text = (ROOT / "services/content_packs.py").read_text(encoding="utf-8")
    assert 'for category in pack.get("reward_categories", [])' in text
    assert 'if category_id not in tracked_category_ids:' in text
    assert 'tracked_category_ids.add(category_id)' in text
