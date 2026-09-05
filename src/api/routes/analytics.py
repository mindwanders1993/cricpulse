from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, Request

from src.api.schemas import LeaderboardResponse

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/leaderboards/batting", response_model=LeaderboardResponse)
def get_batting_leaderboard(
    request: Request,
    match_type: Annotated[str, Query(description="Match format (T20, ODI, Test)")] = "T20",
    sort_by: Annotated[
        str, Query(description="Sorting metric (total_runs, strike_rate, batting_average)")
    ] = "total_runs",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardResponse:
    """Fetch paginated batting career leaderboards from DuckDB Mart."""
    con = request.app.state.db
    valid_sorts = {
        "total_runs": "DESC",
        "strike_rate": "DESC",
        "batting_average": "DESC",
        "fours": "DESC",
        "sixes": "DESC",
    }
    order_dir = valid_sorts.get(sort_by, "DESC")

    query = f"""
        SELECT *
        FROM gold.mart_player_batting_career
        WHERE UPPER(match_type) = UPPER(?)
        ORDER BY {sort_by} {order_dir} NULLS LAST
        LIMIT ? OFFSET ?;
    """
    rel = con.execute(query, [match_type, limit, offset])
    cols = [d[0] for d in rel.description]
    rows = [dict(zip(cols, r, strict=False)) for r in rel.fetchall()]

    return LeaderboardResponse(
        category="batting",
        match_type=match_type,
        count=len(rows),
        offset=offset,
        limit=limit,
        data=rows,
    )


@router.get("/leaderboards/bowling", response_model=LeaderboardResponse)
def get_bowling_leaderboard(
    request: Request,
    match_type: Annotated[str, Query(description="Match format (T20, ODI, Test)")] = "T20",
    sort_by: Annotated[
        str, Query(description="Sorting metric (wickets, economy_rate, bowling_average)")
    ] = "wickets",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeaderboardResponse:
    """Fetch paginated bowling career leaderboards from DuckDB Mart."""
    con = request.app.state.db
    valid_sorts = {
        "wickets": "DESC",
        "economy_rate": "ASC",
        "bowling_average": "ASC",
        "bowling_strike_rate": "ASC",
        "dot_balls": "DESC",
    }
    order_dir = valid_sorts.get(sort_by, "DESC")

    query = f"""
        SELECT *
        FROM gold.mart_player_bowling_career
        WHERE UPPER(match_type) = UPPER(?)
        ORDER BY {sort_by} {order_dir} NULLS LAST
        LIMIT ? OFFSET ?;
    """
    rel = con.execute(query, [match_type, limit, offset])
    cols = [d[0] for d in rel.description]
    rows = [dict(zip(cols, r, strict=False)) for r in rel.fetchall()]

    return LeaderboardResponse(
        category="bowling",
        match_type=match_type,
        count=len(rows),
        offset=offset,
        limit=limit,
        data=rows,
    )


@router.get("/players/{player_id}")
def get_player_profile(player_id: str, request: Request) -> dict[str, Any]:
    """Retrieve full player profile and career records across all formats."""
    con = request.app.state.db

    # 1. Dimension info
    p_row = con.execute(
        "SELECT player_id, full_name, unique_name, espncricinfo_id, cricbuzz_id FROM gold.dim_player WHERE player_id = ? LIMIT 1;",
        [player_id],
    ).fetchone()

    if not p_row:
        raise HTTPException(status_code=404, detail=f"Player '{player_id}' not found")

    profile = {
        "player_id": p_row[0],
        "full_name": p_row[1],
        "unique_name": p_row[2],
        "espncricinfo_id": p_row[3],
        "cricbuzz_id": p_row[4],
    }

    # 2. Batting career stats
    bat_rows = con.execute(
        "SELECT * FROM gold.mart_player_batting_career WHERE player_id = ?;", [player_id]
    ).fetchall()
    bat_cols = [d[0] for d in con.description]
    profile["batting_career"] = [dict(zip(bat_cols, r, strict=False)) for r in bat_rows]

    # 3. Bowling career stats
    bowl_rows = con.execute(
        "SELECT * FROM gold.mart_player_bowling_career WHERE player_id = ?;", [player_id]
    ).fetchall()
    bowl_cols = [d[0] for d in con.description]
    profile["bowling_career"] = [dict(zip(bowl_cols, r, strict=False)) for r in bowl_rows]

    return {"status": "success", "data": profile}
