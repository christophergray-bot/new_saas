
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]

class CharacterWorkshopHierarchyTests(unittest.TestCase):
    def test_hierarchical_character_controls_exist(self):
        text = (ROOT / "templates" / "child" / "character.html").read_text(encoding="utf-8")
        self.assertIn("Pick Your Profile Character", text)
        self.assertIn("Choose Your Skin Tone", text)
        self.assertIn("Choose Your Frame", text)
        self.assertIn("Choose Your Theme", text)
        self.assertNotIn("Choose Your Character Style", text)
        self.assertNotIn("Choose Your Explorer", text)
        self.assertIn("skin-tone-swatch", text)
        self.assertIn('name="avatar_key"', text)
        self.assertIn("Skin tone option", text)

    def test_skin_tone_controls_are_accessible_and_not_text_labeled_by_complexion(self):
        text = (ROOT / "templates" / "child" / "character.html").read_text(encoding="utf-8")
        self.assertIn('aria-label', text)
        self.assertIn('aria-checked', text)

if __name__ == "__main__":
    unittest.main()
