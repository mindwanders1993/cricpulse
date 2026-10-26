from typing import Any

import duckdb

from src.semantic.models import GoldenQuery
from src.utils import setup_logging

logger = setup_logging()

MATCH_FORMAT_MAP: dict[str, str] = {
    "T20": "T20",
    "IT20": "IT20",
    "ODI": "ODI",
    "ODM": "ODM",
    "TEST": "Test",
    "MDM": "MDM",
}


def normalize_match_format(format_name: str | None) -> str:
    """Normalize user or caller-supplied format string to canonical gold.dim_match casing."""
    if not format_name:
        return "T20"
    cleaned = format_name.strip()
    return MATCH_FORMAT_MAP.get(cleaned.upper(), cleaned)


# ==========================================
# CURATED FEW-SHOT GOLDEN SQL QUERIES
# ==========================================

GOLDEN_QUERIES: list[GoldenQuery] = [
    # 1. Death Overs Batting
    GoldenQuery(
        title="Top Death Overs Batsmen in T20s",
        category="batting",
        question="Who has the highest death overs strike rate in T20 matches with a minimum of 100 balls?",
        sql="""
SELECT 
    p.full_name,
    SUM(fd.runs_batter) AS death_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS death_balls_faced,
    ROUND((SUM(fd.runs_batter)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END)) * 100, 2) AS death_strike_rate,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS death_sixes
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE fd.phase = 'death'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) >= 100
ORDER BY death_strike_rate DESC
LIMIT 5;
        """.strip(),
        keywords=["death", "strike rate", "t20", "sixes", "finisher"],
    ),
    # 2. Powerplay Bowling Economy
    GoldenQuery(
        title="Best Powerplay Economy Bowlers in T20s",
        category="bowling",
        question="Which bowlers have the lowest economy rate in the Powerplay (overs 1-6) in T20s with at least 150 balls bowled?",
        sql="""
SELECT 
    p.full_name,
    COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS pp_legal_balls,
    ROUND(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 1) AS pp_overs,
    SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END) AS pp_runs_conceded,
    COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS pp_wickets,
    ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / (COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0)), 2) AS pp_economy
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.bowler_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE fd.phase = 'powerplay'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) >= 150
ORDER BY pp_economy ASC
LIMIT 5;
        """.strip(),
        keywords=["powerplay", "economy", "bowling", "t20", "dot balls"],
    ),
    # 3. Head-to-Head Batter vs Bowler Matchup
    GoldenQuery(
        title="Head to Head Batter vs Bowler Record",
        category="matchup",
        question="What is Virat Kohli's record against Adam Zampa in all formats?",
        sql="""
SELECT 
    fd.batter_name,
    fd.bowler_name,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    SUM(fd.runs_batter) AS runs_scored,
    COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS times_dismissed,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0)), 2) AS batting_average,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls
FROM gold.fact_delivery fd
WHERE LOWER(fd.batter_name) LIKE '%kohli%'
  AND LOWER(fd.bowler_name) LIKE '%zampa%'
GROUP BY fd.batter_name, fd.bowler_name;
        """.strip(),
        keywords=["matchup", "versus", "vs", "head to head", "record", "dismissed"],
    ),
    # 4. Dot Ball Percentage in ODI
    GoldenQuery(
        title="Most Economical Dot Ball Bowlers in ODI",
        category="bowling",
        question="Which bowlers have the highest dot ball percentage in ODI cricket (min 300 balls)?",
        sql="""
SELECT 
    p.full_name,
    COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS legal_balls,
    COUNT(CASE WHEN fd.is_dot_ball THEN 1 END) AS dot_balls,
    ROUND((COUNT(CASE WHEN fd.is_dot_ball THEN 1 END)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END)) * 100, 2) AS dot_ball_pct,
    COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS wickets
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.bowler_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE dm.match_type IN ('ODI', 'ODM')
GROUP BY p.full_name
HAVING COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) >= 300
ORDER BY dot_ball_pct DESC
LIMIT 5;
        """.strip(),
        keywords=["dot ball", "percentage", "odi", "maidens", "pressure"],
    ),
    # 5. Career Batting Leaders by Season
    GoldenQuery(
        title="Top Run Scorers in a Specific Season",
        category="batting",
        question="Who scored the most runs in the 2023 season across all T20 matches?",
        sql="""
SELECT 
    p.full_name,
    COUNT(DISTINCT fd.match_id) AS matches,
    SUM(fd.runs_batter) AS total_runs,
    COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
    ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0)), 2) AS batting_average,
    ROUND((SUM(fd.runs_batter)::DOUBLE / COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END)) * 100, 2) AS strike_rate,
    SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
    SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes
FROM gold.fact_delivery fd
JOIN gold.dim_player p ON fd.batter_id = p.player_id
JOIN gold.dim_match dm ON fd.match_id = dm.match_id
WHERE dm.season = '2023'
  AND dm.match_type IN ('T20', 'IT20')
GROUP BY p.full_name
ORDER BY total_runs DESC
LIMIT 10;
        """.strip(),
        keywords=["season", "top runs", "most runs", "orange cap", "leaderboard"],
    ),
]


# ==========================================
# PARAMETRIC DUCKDB SEMANTIC TOOLS
# ==========================================


def get_player_phase_splits(
    con: duckdb.DuckDBPyConnection,
    player_uid: str,
    format: str = "T20",
    phase: str | None = None,
) -> dict[str, Any]:
    """Calculate batting and bowling performance partitioned by match phase.

    Strictly enforces canonical cricket denominators:
    - Batting balls faced strictly excludes wides (`is_wide = FALSE`).
    - Bowling economy strictly excludes byes and leg-byes (`runs_batter + extras on wide/no-ball`).
    - Bowling legal balls strictly excludes wides and no-balls (`is_wide = FALSE AND is_no_ball = FALSE`).
    - Average denominators use `NULLIF(..., 0)` to guarantee zero mathematical hallucinations.
    """
    if not con:
        raise ValueError("A valid DuckDBPyConnection must be provided.")

    match_format = normalize_match_format(format)
    target_phase_norm = phase.lower().strip() if phase and phase.lower() != "all" else None

    # Resolve player display name
    name_row = con.execute(
        "SELECT full_name FROM gold.dim_player WHERE player_id = ? OR LOWER(full_name) = LOWER(?) LIMIT 1;",
        [player_uid, player_uid],
    ).fetchone()
    player_name = name_row[0] if name_row else player_uid

    # 1. Batting Splits
    bat_sql = """
        SELECT 
            fd.phase,
            COUNT(DISTINCT fd.match_id) AS matches,
            COUNT(DISTINCT fd.match_id || '_' || fd.innings_number) AS innings,
            SUM(fd.runs_batter) AS runs,
            COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
            COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = ? THEN 1 END) AS dismissals,
            ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
            ROUND(SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = ? THEN 1 END), 0), 2) AS batting_average,
            COUNT(CASE WHEN fd.runs_batter = 0 AND fd.is_wide = FALSE THEN 1 END) AS dot_balls,
            ROUND((COUNT(CASE WHEN fd.runs_batter = 0 AND fd.is_wide = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS dot_ball_pct,
            SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes,
            ROUND((SUM(CASE WHEN fd.is_boundary_four THEN 4 WHEN fd.is_boundary_six THEN 6 ELSE 0 END)::DOUBLE / NULLIF(SUM(fd.runs_batter), 0)) * 100, 2) AS boundary_run_pct
        FROM gold.fact_delivery fd
        JOIN gold.dim_match dm ON fd.match_id = dm.match_id
        WHERE (fd.batter_id = ? OR LOWER(fd.batter_name) = LOWER(?))
          AND dm.match_type = ?
    """
    bat_params: list[Any] = [player_uid, player_uid, player_uid, player_uid, match_format]
    if target_phase_norm:
        bat_sql += " AND fd.phase = ?"
        bat_params.append(target_phase_norm)
    bat_sql += " GROUP BY fd.phase ORDER BY CASE fd.phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 WHEN 'death' THEN 3 ELSE 4 END;"

    bat_rows = con.execute(bat_sql, bat_params).fetchall()
    batting_splits = []
    for r in bat_rows:
        batting_splits.append(
            {
                "phase": r[0],
                "matches": r[1] or 0,
                "innings": r[2] or 0,
                "runs": r[3] or 0,
                "balls_faced": r[4] or 0,
                "dismissals": r[5] or 0,
                "strike_rate": r[6] or 0.0,
                "batting_average": r[7],
                "dot_balls": r[8] or 0,
                "dot_ball_pct": r[9] or 0.0,
                "fours": r[10] or 0,
                "sixes": r[11] or 0,
                "boundary_run_pct": r[12] or 0.0,
            }
        )

    # 2. Bowling Splits
    bowl_sql = """
        SELECT 
            fd.phase,
            COUNT(DISTINCT fd.match_id) AS matches,
            COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS legal_balls,
            ROUND(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 1) AS overs,
            SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END) AS runs_conceded,
            COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END) AS wickets,
            ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 0)), 2) AS economy,
            ROUND((SUM(fd.runs_batter + CASE WHEN fd.is_wide OR fd.is_no_ball THEN fd.runs_extras ELSE 0 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END), 0)), 2) AS bowling_average,
            ROUND((COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.dismissal_kind IN ('bowled', 'caught', 'lbw', 'stumped', 'caught and bowled', 'hit wicket') THEN 1 END), 0)), 2) AS bowling_strike_rate,
            COUNT(CASE WHEN fd.total_runs = 0 AND fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) AS dot_balls,
            ROUND((COUNT(CASE WHEN fd.total_runs = 0 AND fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END), 0)) * 100, 2) AS dot_ball_pct
        FROM gold.fact_delivery fd
        JOIN gold.dim_match dm ON fd.match_id = dm.match_id
        WHERE (fd.bowler_id = ? OR LOWER(fd.bowler_name) = LOWER(?))
          AND dm.match_type = ?
    """
    bowl_params: list[Any] = [player_uid, player_uid, match_format]
    if target_phase_norm:
        bowl_sql += " AND fd.phase = ?"
        bowl_params.append(target_phase_norm)
    bowl_sql += " GROUP BY fd.phase ORDER BY CASE fd.phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 WHEN 'death' THEN 3 ELSE 4 END;"

    bowl_rows = con.execute(bowl_sql, bowl_params).fetchall()
    bowling_splits = []
    for r in bowl_rows:
        bowling_splits.append(
            {
                "phase": r[0],
                "matches": r[1] or 0,
                "legal_balls": r[2] or 0,
                "overs": r[3] or 0.0,
                "runs_conceded": r[4] or 0,
                "wickets": r[5] or 0,
                "economy": r[6] or 0.0,
                "bowling_average": r[7],
                "bowling_strike_rate": r[8],
                "dot_balls": r[9] or 0,
                "dot_ball_pct": r[10] or 0.0,
            }
        )

    report = {
        "player_id": player_uid,
        "player_name": player_name,
        "format": match_format,
        "phase": target_phase_norm or "all",
        "batting": batting_splits,
        "bowling": bowling_splits,
    }
    return report


def get_head_to_head_matchup(
    con: duckdb.DuckDBPyConnection,
    batter_uid: str,
    bowler_uid: str,
    format: str | None = None,
    format_name: str | None = None,
) -> dict[str, Any]:
    """Calculate exact head-to-head record between a batter and a bowler.

    Canonical guarantees:
    - Balls faced strictly counts legal balls faced (`is_wide = FALSE`).
    - Runs scored counts batter runs off the bat.
    - Dismissals counts times this bowler dismissed this batter.
    - Strike rate is (runs_scored / balls_faced) * 100.
    """
    if not con:
        raise ValueError("A valid DuckDBPyConnection must be provided.")

    raw_format = format or format_name or "all"
    match_format = (
        normalize_match_format(raw_format) if raw_format and raw_format.lower() != "all" else None
    )

    query_overall = """
        SELECT 
            COALESCE(MAX(fd.batter_name), ?) AS batter_name,
            COALESCE(MAX(fd.bowler_name), ?) AS bowler_name,
            COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
            SUM(fd.runs_batter) AS runs_scored,
            COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS dismissals,
            ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
            ROUND(SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END), 0), 2) AS batting_average,
            COUNT(CASE WHEN fd.runs_batter = 0 AND fd.is_wide = FALSE THEN 1 END) AS dot_balls,
            ROUND((COUNT(CASE WHEN fd.runs_batter = 0 AND fd.is_wide = FALSE THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS dot_ball_pct,
            SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes,
            ROUND((SUM(CASE WHEN fd.is_boundary_four THEN 4 WHEN fd.is_boundary_six THEN 6 ELSE 0 END)::DOUBLE / NULLIF(SUM(fd.runs_batter), 0)) * 100, 2) AS boundary_pct
        FROM gold.fact_delivery fd
        JOIN gold.dim_match dm ON fd.match_id = dm.match_id
        WHERE (fd.batter_id = ? OR LOWER(fd.batter_name) = LOWER(?))
          AND (fd.bowler_id = ? OR LOWER(fd.bowler_name) = LOWER(?))
    """
    params: list[Any] = [batter_uid, bowler_uid, batter_uid, batter_uid, bowler_uid, bowler_uid]
    if match_format:
        query_overall += " AND dm.match_type = ?"
        params.append(match_format)

    row = con.execute(query_overall, params).fetchone()

    # Query phase breakdown
    query_phase = """
        SELECT 
            fd.phase,
            COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END) AS balls_faced,
            SUM(fd.runs_batter) AS runs_scored,
            COUNT(CASE WHEN fd.is_wicket AND fd.player_out_id = fd.batter_id THEN 1 END) AS dismissals,
            ROUND((SUM(fd.runs_batter)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS strike_rate,
            SUM(CASE WHEN fd.is_boundary_four THEN 1 ELSE 0 END) AS fours,
            SUM(CASE WHEN fd.is_boundary_six THEN 1 ELSE 0 END) AS sixes
        FROM gold.fact_delivery fd
        JOIN gold.dim_match dm ON fd.match_id = dm.match_id
        WHERE (fd.batter_id = ? OR LOWER(fd.batter_name) = LOWER(?))
          AND (fd.bowler_id = ? OR LOWER(fd.bowler_name) = LOWER(?))
    """
    phase_params: list[Any] = [batter_uid, batter_uid, bowler_uid, bowler_uid]
    if match_format:
        query_phase += " AND dm.match_type = ?"
        phase_params.append(match_format)
    query_phase += " GROUP BY fd.phase ORDER BY CASE fd.phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 WHEN 'death' THEN 3 ELSE 4 END;"

    phase_rows = con.execute(query_phase, phase_params).fetchall()
    phase_breakdown = [
        {
            "phase": pr[0],
            "balls_faced": pr[1] or 0,
            "runs_scored": pr[2] or 0,
            "dismissals": pr[3] or 0,
            "strike_rate": pr[4] or 0.0,
            "fours": pr[5] or 0,
            "sixes": pr[6] or 0,
        }
        for pr in phase_rows
    ]

    return {
        "batter_id": batter_uid,
        "batter_name": row[0] if row and row[0] else batter_uid,
        "bowler_id": bowler_uid,
        "bowler_name": row[1] if row and row[1] else bowler_uid,
        "format": match_format or "all",
        "balls_faced": row[2] if row and row[2] is not None else 0,
        "runs_scored": row[3] if row and row[3] is not None else 0,
        "dismissals": row[4] if row and row[4] is not None else 0,
        "strike_rate": row[5] if row and row[5] is not None else 0.0,
        "batting_average": row[6] if row else None,
        "dot_balls": row[7] if row and row[7] is not None else 0,
        "dot_ball_pct": row[8] if row and row[8] is not None else 0.0,
        "fours": row[9] if row and row[9] is not None else 0,
        "sixes": row[10] if row and row[10] is not None else 0,
        "boundary_pct": row[11] if row and row[11] is not None else 0.0,
        "phase_breakdown": phase_breakdown,
    }


def get_venue_phase_and_toss_profile(
    con: duckdb.DuckDBPyConnection,
    venue_id: str,
    format: str | None = None,
    format_name: str | None = None,
) -> dict[str, Any]:
    """Calculate historical venue intelligence: toss patterns, innings baselines, and phase run-rates.

    Canonical guarantees:
    - Toss decisions aggregate bat vs field choices.
    - Match outcomes compute true bat first vs chase win percentages.
    - Phase run rate measures runs per 6 legal balls (`is_wide = FALSE AND is_no_ball = FALSE`).
    """
    if not con:
        raise ValueError("A valid DuckDBPyConnection must be provided.")

    raw_format = format or format_name or "T20"
    match_format = normalize_match_format(raw_format)

    # 1. Venue details & Toss stats
    query_toss = """
        SELECT 
            dv.venue_id,
            dv.venue_name,
            dv.city,
            COUNT(DISTINCT dm.match_id) AS total_matches,
            COUNT(CASE WHEN LOWER(dm.toss_decision) = 'bat' THEN 1 END) AS toss_bat_count,
            COUNT(CASE WHEN LOWER(dm.toss_decision) = 'field' THEN 1 END) AS toss_field_count,
            COUNT(CASE WHEN dm.winner IS NOT NULL AND dm.winner = dm.toss_winner THEN 1 END) AS toss_winner_match_wins,
            COUNT(CASE WHEN (dm.win_by_runs > 0) OR (dm.winner = dm.team1 AND dm.result_type = 'runs') THEN 1 END) AS bat_first_wins,
            COUNT(CASE WHEN (dm.win_by_wickets > 0) OR (dm.winner = dm.team2 AND dm.result_type = 'wickets') THEN 1 END) AS chase_wins
        FROM gold.dim_venue dv
        LEFT JOIN gold.dim_match dm ON (dm.venue_name = dv.venue_name OR md5(dm.venue_name) = dv.venue_id)
        WHERE (dv.venue_id = ? OR LOWER(dv.venue_name) LIKE '%' || LOWER(?) || '%')
          AND (dm.match_type = ? OR dm.match_id IS NULL)
        GROUP BY dv.venue_id, dv.venue_name, dv.city
        LIMIT 1;
    """
    toss_row = con.execute(query_toss, [venue_id, venue_id, match_format]).fetchone()
    if not toss_row:
        # Fallback search by venue name directly in dim_match if dim_venue doesn't have it
        query_fallback = """
            SELECT 
                md5(dm.venue_name) AS venue_id,
                dm.venue_name,
                dm.city,
                COUNT(DISTINCT dm.match_id) AS total_matches,
                COUNT(CASE WHEN LOWER(dm.toss_decision) = 'bat' THEN 1 END) AS toss_bat_count,
                COUNT(CASE WHEN LOWER(dm.toss_decision) = 'field' THEN 1 END) AS toss_field_count,
                COUNT(CASE WHEN dm.winner IS NOT NULL AND dm.winner = dm.toss_winner THEN 1 END) AS toss_winner_match_wins,
                COUNT(CASE WHEN (dm.win_by_runs > 0) OR (dm.winner = dm.team1 AND dm.result_type = 'runs') THEN 1 END) AS bat_first_wins,
                COUNT(CASE WHEN (dm.win_by_wickets > 0) OR (dm.winner = dm.team2 AND dm.result_type = 'wickets') THEN 1 END) AS chase_wins
            FROM gold.dim_match dm
            WHERE (LOWER(dm.venue_name) LIKE '%' || LOWER(?) || '%' OR md5(dm.venue_name) = ?)
              AND dm.match_type = ?
            GROUP BY dm.venue_name, dm.city
            LIMIT 1;
        """
        toss_row = con.execute(query_fallback, [venue_id, venue_id, match_format]).fetchone()

    total_matches = toss_row[3] if toss_row else 0
    toss_bat = toss_row[4] if toss_row else 0
    toss_field = toss_row[5] if toss_row else 0
    toss_wins = toss_row[6] if toss_row else 0
    bat_1st_wins = toss_row[7] if toss_row else 0
    chase_wins = toss_row[8] if toss_row else 0

    # 2. Innings baseline totals
    query_innings = """
        SELECT 
            fi.innings_number,
            ROUND(AVG(fi.total_runs), 1) AS avg_runs,
            ROUND(AVG(fi.total_wickets), 1) AS avg_wickets
        FROM gold.fact_innings fi
        JOIN gold.dim_match dm ON fi.match_id = dm.match_id
        WHERE (LOWER(dm.venue_name) LIKE '%' || LOWER(?) || '%' OR md5(dm.venue_name) = ?)
          AND dm.match_type = ?
          AND fi.innings_number IN (1, 2)
        GROUP BY fi.innings_number
        ORDER BY fi.innings_number;
    """
    innings_rows = con.execute(query_innings, [venue_id, venue_id, match_format]).fetchall()
    avg_1st_score = None
    avg_2nd_score = None
    for ir in innings_rows:
        if ir[0] == 1:
            avg_1st_score = ir[1]
        elif ir[0] == 2:
            avg_2nd_score = ir[1]

    # 3. Phase profile
    query_phases = """
        SELECT 
            fd.phase,
            ROUND(SUM(fd.total_runs)::DOUBLE / NULLIF(COUNT(DISTINCT fd.match_id), 0), 1) AS avg_phase_runs,
            ROUND(COUNT(CASE WHEN fd.is_wicket THEN 1 END)::DOUBLE / NULLIF(COUNT(DISTINCT fd.match_id), 0), 2) AS avg_phase_wickets,
            ROUND((SUM(fd.total_runs)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE AND fd.is_no_ball = FALSE THEN 1 END) / 6.0, 0)), 2) AS run_rate,
            ROUND((COUNT(CASE WHEN fd.is_boundary_four OR fd.is_boundary_six THEN 1 END)::DOUBLE / NULLIF(COUNT(CASE WHEN fd.is_wide = FALSE THEN 1 END), 0)) * 100, 2) AS boundary_pct
        FROM gold.fact_delivery fd
        JOIN gold.dim_match dm ON fd.match_id = dm.match_id
        WHERE (LOWER(dm.venue_name) LIKE '%' || LOWER(?) || '%' OR md5(dm.venue_name) = ?)
          AND dm.match_type = ?
        GROUP BY fd.phase
        ORDER BY CASE fd.phase WHEN 'powerplay' THEN 1 WHEN 'middle' THEN 2 WHEN 'death' THEN 3 ELSE 4 END;
    """
    phase_rows = con.execute(query_phases, [venue_id, venue_id, match_format]).fetchall()
    phase_stats = [
        {
            "phase": pr[0],
            "avg_phase_runs": pr[1] or 0.0,
            "avg_phase_wickets": pr[2] or 0.0,
            "run_rate": pr[3] or 0.0,
            "boundary_pct": pr[4] or 0.0,
        }
        for pr in phase_rows
    ]

    return {
        "venue_id": toss_row[0] if toss_row else venue_id,
        "venue_name": toss_row[1] if toss_row else venue_id,
        "city": toss_row[2] if toss_row else None,
        "format": match_format,
        "total_matches": total_matches,
        "toss_decision": {
            "bat": toss_bat,
            "field": toss_field,
        },
        "match_outcomes": {
            "batting_first_wins": bat_1st_wins,
            "chasing_wins": chase_wins,
            "toss_winner_match_wins": toss_wins,
            "toss_win_match_win_pct": round((toss_wins / total_matches) * 100, 2)
            if total_matches > 0
            else 0.0,
        },
        "average_first_innings_score": avg_1st_score,
        "average_second_innings_score": avg_2nd_score,
        "phase_stats": phase_stats,
    }


# ==========================================
# REGISTRY CLASS
# ==========================================


class GoldenQueryRegistry:
    """Manages few-shot SQL examples and provides parametric DuckDB execution helpers."""

    def __init__(
        self,
        queries: list[GoldenQuery] | None = None,
        con: duckdb.DuckDBPyConnection | None = None,
    ):
        self.queries = queries or GOLDEN_QUERIES
        self.con = con

    def select_few_shot_examples(self, user_query: str, limit: int = 2) -> list[GoldenQuery]:
        """Rank and return the top `limit` most relevant golden queries matching user keywords."""
        query_lower = user_query.lower()
        scored_queries: list[tuple[float, GoldenQuery]] = []

        for gq in self.queries:
            score = 0.0
            for kw in gq.keywords:
                if kw in query_lower:
                    score += 1.0
            if gq.category in query_lower:
                score += 1.5

            scored_queries.append((score, gq))

        # Sort by relevance score descending
        scored_queries.sort(key=lambda x: x[0], reverse=True)
        return [q for _, q in scored_queries[:limit]]

    def get_few_shot_prompt_context(self, user_query: str, limit: int = 2) -> str:
        """Format selected few-shot queries into a prompt block for LLMs."""
        selected = self.select_few_shot_examples(user_query, limit=limit)
        if not selected:
            return ""

        lines = [
            "### FEW-SHOT VETTED SQL EXAMPLES",
            "Learn from these verified DuckDB queries for join patterns, CTE structures, and filtering:",
            "",
        ]

        for i, q in enumerate(selected, start=1):
            lines.append(f"#### Example {i}: {q.title}")
            lines.append(f"- **User Question**: {q.question}")
            lines.append(f"```sql\n{q.sql}\n```\n")

        return "\n".join(lines)

    # Parametric Semantic Tools exposed via Registry
    def get_player_phase_splits(
        self, player_uid: str, format: str = "T20", phase: str | None = None
    ) -> dict[str, Any]:
        """Parametric helper for player phase splits."""
        if not self.con:
            raise ValueError("GoldenQueryRegistry was initialized without a DuckDBPyConnection.")
        return get_player_phase_splits(self.con, player_uid, format, phase)

    def get_head_to_head_matchup(
        self, batter_uid: str, bowler_uid: str, format: str = "all"
    ) -> dict[str, Any]:
        """Parametric helper for batter vs bowler matchup."""
        if not self.con:
            raise ValueError("GoldenQueryRegistry was initialized without a DuckDBPyConnection.")
        return get_head_to_head_matchup(self.con, batter_uid, bowler_uid, format)

    def get_venue_phase_and_toss_profile(
        self, venue_id: str, format: str = "T20"
    ) -> dict[str, Any]:
        """Parametric helper for venue profile."""
        if not self.con:
            raise ValueError("GoldenQueryRegistry was initialized without a DuckDBPyConnection.")
        return get_venue_phase_and_toss_profile(self.con, venue_id, format)
