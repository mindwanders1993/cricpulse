from typing import Any


def normalize_season(season: Any) -> str:
    """Normalize polymorphic season values (integer or string) to a canonical string format.

    Examples:
        2023 -> '2023'
        '2011/12' -> '2011/12'
        2007 -> '2007'
    """
    if season is None:
        return "Unknown"
    return str(season).strip()


def compute_phase(match_type: str, over_number: int) -> str:
    """Determine match phase based on match format and 1-indexed over number.

    White-ball T20/IT20 (20 overs):
        Overs 1..6   -> 'powerplay'
        Overs 7..15  -> 'middle'
        Overs 16..20 -> 'death'

    White-ball ODI/ODM (50 overs):
        Overs 1..10  -> 'powerplay'
        Overs 11..40 -> 'middle'
        Overs 41..50 -> 'death'

    Test/MDM/Other:
        -> 'regular'
    """
    fmt = (match_type or "").upper().strip()

    if fmt in ("T20", "IT20"):
        if over_number <= 6:
            return "powerplay"
        elif over_number <= 15:
            return "middle"
        else:
            return "death"
    elif fmt in ("ODI", "ODM"):
        if over_number <= 10:
            return "powerplay"
        elif over_number <= 40:
            return "middle"
        else:
            return "death"
    elif fmt == "100":  # The Hundred
        if over_number <= 5:
            return "powerplay"
        elif over_number <= 15:
            return "middle"
        else:
            return "death"
    else:
        return "regular"
