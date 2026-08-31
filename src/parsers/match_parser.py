from pathlib import Path
from typing import Any

import orjson
import polars as pl

from src.parsers.edge_cases import compute_phase, normalize_season
from src.utils import setup_logging

logger = setup_logging()


MATCHES_SCHEMA = {
    "match_id": pl.Utf8,
    "match_date": pl.Utf8,
    "match_type": pl.Utf8,
    "gender": pl.Utf8,
    "season": pl.Utf8,
    "venue": pl.Utf8,
    "city": pl.Utf8,
    "team1": pl.Utf8,
    "team2": pl.Utf8,
    "toss_winner": pl.Utf8,
    "toss_decision": pl.Utf8,
    "winner": pl.Utf8,
    "result_type": pl.Utf8,
    "win_by_runs": pl.Int64,
    "win_by_wickets": pl.Int64,
    "player_of_match": pl.Utf8,
    "player_of_match_id": pl.Utf8,
    "is_dls_applied": pl.Boolean,
    "overs_limit": pl.Int64,
    "revision": pl.Int64,
}

INNINGS_SCHEMA = {
    "match_id": pl.Utf8,
    "innings_number": pl.Int64,
    "batting_team": pl.Utf8,
    "total_runs": pl.Int64,
    "total_wickets": pl.Int64,
    "total_deliveries": pl.Int64,
}

DELIVERIES_SCHEMA = {
    "delivery_id": pl.Utf8,
    "match_id": pl.Utf8,
    "innings_number": pl.Int64,
    "over_number": pl.Int64,
    "delivery_number": pl.Int64,
    "phase": pl.Utf8,
    "batter_id": pl.Utf8,
    "batter_name": pl.Utf8,
    "bowler_id": pl.Utf8,
    "bowler_name": pl.Utf8,
    "non_striker_id": pl.Utf8,
    "non_striker_name": pl.Utf8,
    "runs_batter": pl.Int64,
    "runs_extras": pl.Int64,
    "total_runs": pl.Int64,
    "is_dot_ball": pl.Boolean,
    "is_boundary_four": pl.Boolean,
    "is_boundary_six": pl.Boolean,
    "is_wide": pl.Boolean,
    "is_no_ball": pl.Boolean,
    "is_bye": pl.Boolean,
    "is_leg_bye": pl.Boolean,
    "is_wicket": pl.Boolean,
    "dismissal_kind": pl.Utf8,
    "player_out_id": pl.Utf8,
    "player_out_name": pl.Utf8,
}

WICKETS_SCHEMA = {
    "delivery_id": pl.Utf8,
    "match_id": pl.Utf8,
    "innings_number": pl.Int64,
    "over_number": pl.Int64,
    "delivery_number": pl.Int64,
    "player_out_name": pl.Utf8,
    "player_out_id": pl.Utf8,
    "dismissal_kind": pl.Utf8,
    "bowler_name": pl.Utf8,
    "bowler_id": pl.Utf8,
    "fielders": pl.Utf8,
}

MATCH_PLAYERS_SCHEMA = {
    "match_id": pl.Utf8,
    "team_name": pl.Utf8,
    "player_id": pl.Utf8,
    "player_name": pl.Utf8,
}


class MatchParser:
    """Parses Cricsheet match JSON documents into structured Polars DataFrames."""

    def parse_file(self, json_path: Path | str) -> dict[str, pl.DataFrame]:
        """Parse a single Cricsheet match JSON file."""
        json_path = Path(json_path)
        raw_bytes = json_path.read_bytes()
        data = orjson.loads(raw_bytes)
        match_id = json_path.stem.replace("wi_", "")  # Support Women's International prefix
        return self.parse_json(match_id, data)

    def parse_json(self, match_id: str, data: dict[str, Any]) -> dict[str, pl.DataFrame]:
        """Parse in-memory Cricsheet JSON dictionary into Polars DataFrames."""
        meta = data.get("meta", {})
        info = data.get("info", {})
        innings_list = data.get("innings", [])

        # Extract registry people mapping: display_name -> cricsheet_id (8-char hex UUID)
        registry_people: dict[str, str] = info.get("registry", {}).get("people", {})

        def resolve_id(name: str | None) -> str | None:
            if not name:
                return None
            return registry_people.get(name, name)

        # 1. Match Metadata
        match_type = info.get("match_type", "Unknown")
        dates = info.get("dates", [])
        match_date = str(dates[0]) if dates else "1970-01-01"
        teams = info.get("teams", [])
        team1 = teams[0] if len(teams) > 0 else "Team 1"
        team2 = teams[1] if len(teams) > 1 else "Team 2"
        toss = info.get("toss", {})
        outcome = info.get("outcome", {})
        by_dict = outcome.get("by", {})
        pom = info.get("player_of_match", [])
        player_of_match = pom[0] if pom else None

        match_row = {
            "match_id": match_id,
            "match_date": match_date,
            "match_type": match_type,
            "gender": info.get("gender", "male"),
            "season": normalize_season(info.get("season")),
            "venue": info.get("venue", "Unknown Venue"),
            "city": info.get("city"),
            "team1": team1,
            "team2": team2,
            "toss_winner": toss.get("winner"),
            "toss_decision": toss.get("decision"),
            "winner": outcome.get("winner"),
            "result_type": outcome.get("result", "win" if outcome.get("winner") else "no result"),
            "win_by_runs": by_dict.get("runs"),
            "win_by_wickets": by_dict.get("wickets"),
            "player_of_match": player_of_match,
            "player_of_match_id": resolve_id(player_of_match),
            "is_dls_applied": bool(outcome.get("method") == "D/L" or "DLS" in str(outcome)),
            "overs_limit": info.get("overs"),
            "revision": int(meta.get("revision", 1)),
        }

        # 2. Match Players
        match_players_rows: list[dict[str, Any]] = []
        for team_name, player_list in info.get("players", {}).items():
            for p_name in player_list:
                match_players_rows.append(
                    {
                        "match_id": match_id,
                        "team_name": team_name,
                        "player_id": resolve_id(p_name),
                        "player_name": p_name,
                    }
                )

        # 3. Innings, Deliveries, and Wickets
        innings_rows: list[dict[str, Any]] = []
        delivery_rows: list[dict[str, Any]] = []
        wicket_rows: list[dict[str, Any]] = []

        for inn_idx, inn in enumerate(innings_list, start=1):
            batting_team = inn.get("team", f"Innings {inn_idx}")
            inn_total_runs = 0
            inn_total_wickets = 0
            inn_delivery_count = 0

            for over_obj in inn.get("overs", []):
                raw_over = over_obj.get("over", 0)
                over_number = raw_over + 1  # 1-indexed over number
                phase = compute_phase(match_type, over_number)

                for ball_idx, deliv in enumerate(over_obj.get("deliveries", []), start=1):
                    inn_delivery_count += 1
                    delivery_id = f"{match_id}_{inn_idx}_{over_number}_{ball_idx}"

                    batter = deliv.get("batter", "Unknown")
                    bowler = deliv.get("bowler", "Unknown")
                    non_striker = deliv.get("non_striker", "Unknown")

                    runs_obj = deliv.get("runs", {})
                    runs_batter = int(runs_obj.get("batter", 0))
                    runs_extras = int(runs_obj.get("extras", 0))
                    total_runs = int(runs_obj.get("total", runs_batter + runs_extras))
                    inn_total_runs += total_runs

                    extras_obj = deliv.get("extras", {})
                    is_wide = "wides" in extras_obj
                    is_no_ball = "noballs" in extras_obj
                    is_bye = "byes" in extras_obj
                    is_leg_bye = "legbyes" in extras_obj

                    is_dot_ball = total_runs == 0 and not is_wide
                    is_boundary_four = runs_batter == 4 and not is_wide
                    is_boundary_six = runs_batter == 6 and not is_wide

                    # Wickets handling
                    wickets_list = deliv.get("wickets", [])
                    is_wicket = bool(wickets_list)

                    primary_dismissal_kind = None
                    primary_player_out = None
                    primary_player_out_id = None

                    if is_wicket:
                        inn_total_wickets += len(wickets_list)
                        # Extract primary dismissal (prefer bowler credited kind if multi-wicket)
                        first_w = wickets_list[0]
                        primary_player_out = first_w.get("player_out")
                        primary_dismissal_kind = first_w.get("kind")
                        primary_player_out_id = resolve_id(primary_player_out)

                        # Record all dismissals in discrete wickets table
                        for w in wickets_list:
                            w_player_out = w.get("player_out")
                            fielders = [
                                f.get("name") for f in w.get("fielders", []) if f.get("name")
                            ]
                            wicket_rows.append(
                                {
                                    "delivery_id": delivery_id,
                                    "match_id": match_id,
                                    "innings_number": inn_idx,
                                    "over_number": over_number,
                                    "delivery_number": ball_idx,
                                    "player_out_name": w_player_out,
                                    "player_out_id": resolve_id(w_player_out),
                                    "dismissal_kind": w.get("kind"),
                                    "bowler_name": bowler,
                                    "bowler_id": resolve_id(bowler),
                                    "fielders": ", ".join(fielders) if fielders else None,
                                }
                            )

                    delivery_rows.append(
                        {
                            "delivery_id": delivery_id,
                            "match_id": match_id,
                            "innings_number": inn_idx,
                            "over_number": over_number,
                            "delivery_number": ball_idx,
                            "phase": phase,
                            "batter_id": resolve_id(batter),
                            "batter_name": batter,
                            "bowler_id": resolve_id(bowler),
                            "bowler_name": bowler,
                            "non_striker_id": resolve_id(non_striker),
                            "non_striker_name": non_striker,
                            "runs_batter": runs_batter,
                            "runs_extras": runs_extras,
                            "total_runs": total_runs,
                            "is_dot_ball": is_dot_ball,
                            "is_boundary_four": is_boundary_four,
                            "is_boundary_six": is_boundary_six,
                            "is_wide": is_wide,
                            "is_no_ball": is_no_ball,
                            "is_bye": is_bye,
                            "is_leg_bye": is_leg_bye,
                            "is_wicket": is_wicket,
                            "dismissal_kind": primary_dismissal_kind,
                            "player_out_id": primary_player_out_id,
                            "player_out_name": primary_player_out,
                        }
                    )

            innings_rows.append(
                {
                    "match_id": match_id,
                    "innings_number": inn_idx,
                    "batting_team": batting_team,
                    "total_runs": inn_total_runs,
                    "total_wickets": inn_total_wickets,
                    "total_deliveries": inn_delivery_count,
                }
            )

        return {
            "matches": pl.DataFrame([match_row], schema=MATCHES_SCHEMA),
            "innings": pl.DataFrame(innings_rows, schema=INNINGS_SCHEMA)
            if innings_rows
            else pl.DataFrame(schema=INNINGS_SCHEMA),
            "deliveries": pl.DataFrame(delivery_rows, schema=DELIVERIES_SCHEMA)
            if delivery_rows
            else pl.DataFrame(schema=DELIVERIES_SCHEMA),
            "wickets": pl.DataFrame(wicket_rows, schema=WICKETS_SCHEMA)
            if wicket_rows
            else pl.DataFrame(schema=WICKETS_SCHEMA),
            "match_players": pl.DataFrame(match_players_rows, schema=MATCH_PLAYERS_SCHEMA)
            if match_players_rows
            else pl.DataFrame(schema=MATCH_PLAYERS_SCHEMA),
        }

    def parse_batch(self, json_paths: list[Path | str]) -> dict[str, pl.DataFrame]:
        """Parse multiple Cricsheet match files and concatenate them into combined DataFrames."""
        all_matches: list[pl.DataFrame] = []
        all_innings: list[pl.DataFrame] = []
        all_deliveries: list[pl.DataFrame] = []
        all_wickets: list[pl.DataFrame] = []
        all_players: list[pl.DataFrame] = []

        for p in json_paths:
            dfs = self.parse_file(p)
            if not dfs["matches"].is_empty():
                all_matches.append(dfs["matches"])
            if not dfs["innings"].is_empty():
                all_innings.append(dfs["innings"])
            if not dfs["deliveries"].is_empty():
                all_deliveries.append(dfs["deliveries"])
            if not dfs["wickets"].is_empty():
                all_wickets.append(dfs["wickets"])
            if not dfs["match_players"].is_empty():
                all_players.append(dfs["match_players"])

        return {
            "matches": pl.concat(all_matches, how="vertical_relaxed")
            if all_matches
            else pl.DataFrame(),
            "innings": pl.concat(all_innings, how="vertical_relaxed")
            if all_innings
            else pl.DataFrame(),
            "deliveries": pl.concat(all_deliveries, how="vertical_relaxed")
            if all_deliveries
            else pl.DataFrame(),
            "wickets": pl.concat(all_wickets, how="vertical_relaxed")
            if all_wickets
            else pl.DataFrame(),
            "match_players": pl.concat(all_players, how="vertical_relaxed")
            if all_players
            else pl.DataFrame(),
        }
