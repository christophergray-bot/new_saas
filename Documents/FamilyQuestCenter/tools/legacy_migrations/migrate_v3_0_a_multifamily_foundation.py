"""Family Quest Center developer documentation.

File: tools/legacy_migrations/migrate_v3_0_a_multifamily_foundation.py
Purpose: Supports the migrate v3 0 a multifamily foundation portion of Family Quest Center.

Maintenance notes:
- Preserve tenant and family data isolation when changing queries.
- Keep route, template, and schema changes synchronized.
- Run regression tests before release packaging.
Documentation updated: 2026-07-31.
"""

from config import Config
from services.multifamily_foundation import ensure_multifamily_foundation


if __name__ == "__main__":
    family_id = ensure_multifamily_foundation(Config.DATABASE_PATH)
    print("Multi-family foundation installed successfully.")
    print(f"Existing records were assigned to family ID {family_id}.")
