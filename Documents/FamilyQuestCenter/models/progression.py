"""Character progression helpers for Family Quest Center."""

XP_PER_STAR = 10
XP_PER_LEVEL = 100


def calculate_level(total_xp: int) -> int:
    """Return the character level for a lifetime XP total."""

    safe_xp = max(int(total_xp or 0), 0)
    return (safe_xp // XP_PER_LEVEL) + 1


def get_rank_title(level: int) -> str:
    """Return the rank title associated with a character level."""

    if level >= 20:
        return "Legendary Guardian"
    if level >= 15:
        return "Hero of the Realm"
    if level >= 11:
        return "Quest Champion"
    if level >= 8:
        return "Skilled Adventurer"
    if level >= 5:
        return "Brave Explorer"
    if level >= 3:
        return "Quest Scout"
    return "Young Adventurer"


def build_progression(total_xp: int) -> dict:
    """Build level, rank, and progress values for a template."""

    safe_xp = max(int(total_xp or 0), 0)
    level = calculate_level(safe_xp)
    current_level_xp = safe_xp % XP_PER_LEVEL

    return {
        "total_xp": safe_xp,
        "level": level,
        "rank_title": get_rank_title(level),
        "current_level_xp": current_level_xp,
        "xp_per_level": XP_PER_LEVEL,
        "xp_to_next_level": XP_PER_LEVEL - current_level_xp,
        "progress_percent": current_level_xp,
    }
