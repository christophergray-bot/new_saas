
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class CharacterWorkshopManifestVariantTests(unittest.TestCase):
    def test_explorer_starter_exposes_twelve_variant_avatars(self):
        path = ROOT / "content" / "packs" / "explorer_starter_pack" / "pack.json"
        pack = json.loads(path.read_text(encoding="utf-8"))
        variants = [
            a for a in pack.get("avatars", [])
            if a["key"].startswith("explorer_girl_") or a["key"].startswith("explorer_boy_")
        ]
        self.assertEqual(len(variants), 12)
        for avatar in variants:
            self.assertIn("/explorer_starter_pack/characters/", avatar["image"])

    def test_workshop_has_hierarchical_controls(self):
        text = (ROOT / "templates" / "child" / "character.html").read_text(encoding="utf-8")
        self.assertIn("Pick Your Profile Character", text)
        self.assertIn("Choose Your Skin Tone", text)
        self.assertIn("Choose Your Frame", text)
        self.assertIn("Choose Your Theme", text)
        self.assertNotIn("Choose Your Character Style", text)
        self.assertNotIn("Choose Your Explorer", text)
        self.assertIn("skin-tone-swatch", text)

    def test_cosmetics_reads_active_pack_manifests(self):
        text = (ROOT / "models" / "cosmetics.py").read_text(encoding="utf-8")
        self.assertIn("_active_pack_manifest_cosmetics", text)
        self.assertIn("family_content_packs", text)
        self.assertIn("status='active'", text)

if __name__ == "__main__":
    unittest.main()
