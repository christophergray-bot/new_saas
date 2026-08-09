# Family Quest Center Code Cleanup Review — 2026-08-09

## Recommendation

Label this reviewed snapshot **Family Quest Center v1.7.0-rc1**.

`rc1` is appropriate because the application contains substantial functionality
beyond the old 1.6.0 milestone, but production validation and the dependency
security review are not yet complete.

## High-confidence cleanup findings

The uploaded working copy contained several items that should not remain in a
clean source/release package:

- Python `__pycache__` directories and `.pyc` files.
- `.pytest_cache`.
- multiple `.bak` files.
- stale `test_results_hd2.txt`.
- accidental file `tatus --short`.
- runtime `backups/`.
- local `.env` / `.env.bak` secrets.
- Git repository metadata (`.git`) in a distributable archive.
- the legacy `content/default_pack` manifest; pack discovery uses
  `content/packs/*/pack.json` and the canonical starter pack is
  `content/packs/explorer_starter_pack/pack.json`.
- an accidental **full duplicate of the Family Quest Center project** inside
  `content/packs/explorer_starter_pack/characters/`. Only Explorer image assets
  belong there.

The Explorer character directory was reduced to image assets only. Both WEBP
runtime assets and PNG source masters were retained.

## Documentation/comment review

- Existing CSS and SQL files already had leading comments.
- Nearly all production Python modules already had module notes/docstrings.
- Lightweight module/template notes were added to files that supported comments
  but lacked a leading header.
- JSON files were not given comments because standard JSON does not support them.
- README, Known Limitations, release notes, and the Content Pack template were
  refreshed for this release candidate.

## Versioning changes

- `app.py`: `APP_VERSION = "1.7.0-rc1"`
- `README.md` and `README.txt` updated.
- `docs/KNOWN_LIMITATIONS.md` updated.
- `docs/RELEASE_NOTES_1.7.0-RC1.md` added.

## Size impact

- Uploaded copy: 2,195 files, 301.4 MB.
- Reviewed clean tree: 476 files, 20.9 MB.

The largest reduction came from removing embedded Git history, generated Python
files, and the accidental nested copy of the application.

## Items intentionally not deleted

- Historical documentation under `docs/history/` was retained because it
  provides development/security traceability.
- Explorer PNG source masters were retained even though the application serves
  WEBP files; they may be useful for future asset regeneration.
- Existing tests were retained, including focused regression tests from recent
  issue passes.

## Remaining release work

1. Run the complete test suite in the normal configured environment.
2. Review the four open Dependabot findings.
3. Verify the latest Child Session Timeout, Character Workshop, and Quest Book
   Read Aloud changes on desktop/tablet/mobile.
4. Verify Railway deployment, billing, email, backup/restore, and Owner tools.
5. Promote to final `1.7.0` only after those checks are complete.
