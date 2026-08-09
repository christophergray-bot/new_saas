"""Automated regression/validation coverage.

File: tests/test_stale_pack_cosmetics_hidden.py
Reviewed for v1.7.0-rc1 cleanup.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class StalePackCosmeticsTests(unittest.TestCase):
    def test_family_cosmetics_filters_missing_or_inactive_pack_sources(self):
        text = (ROOT / "models" / "cosmetics.py").read_text(encoding="utf-8")
        self.assertIn("manifest_cosmetic_keys", text)
        self.assertIn('row["pack_status"] != "active"', text)
        self.assertIn("current_keys = manifest_cosmetic_keys.get(pack_key)", text)
        self.assertIn('(row["category"], row["item_key"]) not in current_keys', text)

    def test_explorer_starter_assets_exist(self):
        pack_root = ROOT / "content" / "packs" / "explorer_starter_pack"
        self.assertTrue((pack_root / "pack.json").is_file())
        self.assertTrue((pack_root / "characters" / "explorer_girl_medium_v1.webp").is_file())

if __name__ == "__main__":
    unittest.main()

