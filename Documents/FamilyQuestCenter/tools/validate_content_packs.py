"""Validate bundled Family Quest Center content-pack manifests."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = sorted((ROOT / "content" / "packs").glob("*/pack.json"))
REQUIRED = ("id", "name", "version", "category", "description")
LIST_SECTIONS = ("quests", "adventures", "challenges", "rewards", "achievements", "avatars", "frames", "themes")


def main() -> int:
    errors: list[str] = []
    seen: dict[str, Path] = {}
    for path in MANIFESTS:
        try:
            pack = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.relative_to(ROOT)}: invalid JSON: {exc}")
            continue
        for field in REQUIRED:
            if not pack.get(field):
                errors.append(f"{path.relative_to(ROOT)}: missing required field '{field}'")
        pack_id = pack.get("id")
        if pack_id in seen:
            errors.append(
                f"{path.relative_to(ROOT)}: duplicate id '{pack_id}' also used by {seen[pack_id].relative_to(ROOT)}"
            )
        elif pack_id:
            seen[pack_id] = path
        for section in LIST_SECTIONS:
            if section in pack and not isinstance(pack[section], list):
                errors.append(f"{path.relative_to(ROOT)}: '{section}' must be a list")
        if pack.get("pack_type") == "core" and pack.get("archive_allowed", False):
            errors.append(f"{path.relative_to(ROOT)}: core packs cannot allow whole-pack archiving")

    if errors:
        print("Content Pack validation FAILED")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Content Pack validation OK: {len(seen)} unique packs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
