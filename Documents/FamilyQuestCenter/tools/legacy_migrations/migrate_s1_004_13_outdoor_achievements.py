"""Install the outdoor achievement defaults for S1-004.13."""
from pathlib import Path

from services.default_achievements import ensure_outdoor_achievements

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "chorce.db"


def migrate() -> None:
    """Handle the migrate workflow."""
    installed = ensure_outdoor_achievements(DATABASE_PATH)
    if installed:
        print(f"Outdoor achievement defaults installed successfully ({installed} processed).")
    else:
        print("No achievements were installed. Confirm chorce.db and the achievements table exist.")


if __name__ == "__main__":
    migrate()
