from pathlib import Path

import pytest

from src.parsers.edge_cases import compute_phase, normalize_season
from src.parsers.match_parser import MatchParser
from src.publisher import archive
from src.utils import compute_bytes_sha256


def test_normalize_season():
    assert normalize_season(2024) == "2024"
    assert normalize_season("2011/12") == "2011/12"
    assert normalize_season("2007") == "2007"
    assert normalize_season(None) == "Unknown"


def test_compute_phase():
    # T20 phases
    assert compute_phase("T20", 1) == "powerplay"
    assert compute_phase("T20", 6) == "powerplay"
    assert compute_phase("T20", 7) == "middle"
    assert compute_phase("T20", 15) == "middle"
    assert compute_phase("T20", 16) == "death"
    assert compute_phase("T20", 20) == "death"

    # ODI phases
    assert compute_phase("ODI", 5) == "powerplay"
    assert compute_phase("ODI", 10) == "powerplay"
    assert compute_phase("ODI", 25) == "middle"
    assert compute_phase("ODI", 45) == "death"

    # Test format
    assert compute_phase("Test", 10) == "regular"


def test_parse_sample_t20_match():
    fixture_path = Path("tests/fixtures/sample_t20.json")
    assert fixture_path.exists(), "Sample T20 fixture must exist"

    parser = MatchParser()
    dfs = parser.parse_file(fixture_path)

    # 1. Matches DataFrame
    matches_df = dfs["matches"]
    assert len(matches_df) == 1
    assert matches_df["match_id"][0] == "sample_t20"
    assert matches_df["match_type"][0] == "T20"
    assert matches_df["winner"][0] == "Los Angeles Knight Riders"
    assert matches_df["win_by_wickets"][0] == 2

    # 2. Innings DataFrame
    innings_df = dfs["innings"]
    assert len(innings_df) == 2

    # 3. Deliveries DataFrame
    delivs_df = dfs["deliveries"]
    assert len(delivs_df) > 200
    assert "delivery_id" in delivs_df.columns
    assert "phase" in delivs_df.columns
    assert "batter_id" in delivs_df.columns
    assert "bowler_id" in delivs_df.columns
    assert "is_wicket" in delivs_df.columns

    # Verify 1-indexed over number
    assert delivs_df["over_number"].min() == 1
    assert delivs_df["over_number"].max() <= 20

    # 4. Wickets DataFrame
    wickets_df = dfs["wickets"]
    assert len(wickets_df) > 0
    assert "dismissal_kind" in wickets_df.columns
    assert "player_out_name" in wickets_df.columns

    # 5. Match Players
    players_df = dfs["match_players"]
    assert len(players_df) >= 22


def test_parse_batch():
    p1 = Path("tests/fixtures/sample_t20.json")
    p2 = Path("tests/fixtures/sample_test.json")

    parser = MatchParser()
    combined = parser.parse_batch([p1, p2])

    assert len(combined["matches"]) == 2
    assert len(combined["deliveries"]) > len(parser.parse_file(p1)["deliveries"])


# M0b dossier D-16(c): Cricsheet 1229824 (Isle of Man tour of Guernsey, 2020) lists "J Butler" for both
# teams and its registry gives that name one id, so match_players held (1229824, efcb778e) twice.
BOTH_TEAMS = Path("tests/fixtures/both_teams_1229824.json")


def test_player_listed_for_both_teams_raises():
    with pytest.raises(ValueError, match=r"^player listed for both teams: J Butler$"):
        MatchParser().parse_file(BOTH_TEAMS)


def test_player_listed_for_both_teams_is_quarantined_others_parsed(tmp_path: Path):
    t20 = Path("tests/fixtures/sample_t20.json").read_bytes()
    items = [
        ("1001", compute_bytes_sha256(t20), t20),
        ("1229824", "sha", BOTH_TEAMS.read_bytes()),
    ]
    state = archive.parse_to_staging(items, tmp_path / "_staging" / "v1")

    assert state.changed_ids == ["1001"]
    assert state.quarantined == [("1229824", "ValueError: player listed for both teams: J Butler")]
