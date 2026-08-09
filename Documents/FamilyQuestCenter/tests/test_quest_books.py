"""Quest Books v1 static content validation."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_explorer_starter_manifest_includes_ember():
    pack = json.loads((ROOT / "content/packs/explorer_starter/pack.json").read_text(encoding="utf-8"))
    book = next(item for item in pack.get("books", []) if item["id"] == "ember_baby_dragon")
    assert book["xp_reward"] == 5
    assert book["file"] == "books/ember_baby_dragon.json"


def test_ember_story_has_valid_explicit_ending():
    story = json.loads((ROOT / "content/packs/explorer_starter/books/ember_baby_dragon.json").read_text(encoding="utf-8"))
    assert story["start_node"] == "start"
    nodes = story["nodes"]
    assert nodes["reunion"]["ending"] is True
    assert not nodes["reunion"].get("choices")
    for node_id, node in nodes.items():
        assert node.get("title"), node_id
        if node.get("ending"):
            continue
        assert node.get("choices"), node_id
        for choice in node["choices"]:
            assert choice["next"] in nodes


def test_active_reader_uses_character_image_with_initial_fallback():
    template = (ROOT / "templates/quest_books/library.html").read_text(encoding="utf-8")
    route = (ROOT / "routes/child.py").read_text(encoding="utf-8")
    assert "child.avatar_image" in template
    assert "character.avatar.image" in template
    assert "child.initial" in template
    assert "character=get_character_profile(child)" in route
