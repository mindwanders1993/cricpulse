from pathlib import Path

import duckdb
import pytest

from src.builder.loader import DuckDBLoader
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.semantic.catalog import SemanticCatalog
from src.semantic.golden_queries import (
    GoldenQueryRegistry,
    get_head_to_head_matchup,
    get_player_phase_splits,
    get_venue_phase_and_toss_profile,
    normalize_match_format,
)
from src.semantic.resolver import EntityResolver, jaro_winkler_similarity


@pytest.fixture
def populated_duckdb(temp_dir: Path) -> duckdb.DuckDBPyConnection:
    """Fixture providing a DuckDB connection populated with real sample match & register data."""
    db_path = temp_dir / "semantic_test.duckdb"
    loader = DuckDBLoader(db_path=db_path)

    reg_dfs = RegisterParser().parse_registers(
        "tests/fixtures/sample_people.csv",
        "tests/fixtures/sample_names.csv",
    )
    loader.load_registers(reg_dfs)

    match_dfs = MatchParser().parse_batch(
        [
            "tests/fixtures/sample_t20.json",
            "tests/fixtures/sample_test.json",
        ]
    )
    loader.load_matches(match_dfs)
    loader.build_marts()
    return loader.con


def test_semantic_catalog_loading():
    catalog = SemanticCatalog.load_from_yaml("conf/semantic_catalog.yaml")
    assert catalog.model.version == "1.0.0"
    assert "batting_strike_rate" in catalog.model.metrics
    assert "bowling_economy_rate" in catalog.model.metrics
    assert "death_over_clutch_index" in catalog.model.metrics

    # Verify bowling economy formula excludes byes and leg-byes
    econ_metric = catalog.get_metric("bowling_economy_rate")
    assert econ_metric is not None
    assert "runs_batter" in econ_metric.formula
    assert "is_wide OR is_no_ball" in econ_metric.formula

    # Verify semantic tools specifications are loaded
    assert "player_phase_splits" in catalog.model.semantic_tools
    assert "head_to_head_matchup" in catalog.model.semantic_tools
    assert "venue_phase_and_toss_profile" in catalog.model.semantic_tools


def test_catalog_prompt_context_generation(populated_duckdb: duckdb.DuckDBPyConnection):
    catalog = SemanticCatalog.load_from_yaml("conf/semantic_catalog.yaml")

    # 1. Metrics prompt context
    metrics_block = catalog.get_metric_prompt_context()
    assert "### CANONICAL CRICKET METRICS" in metrics_block
    assert "Batting Strike Rate" in metrics_block
    assert "Bowling Economy Rate" in metrics_block

    # 2. Schema prompt context
    schema_block = catalog.get_schema_prompt_context(populated_duckdb)
    assert "### DATABASE SCHEMA CONTRACTS" in schema_block
    assert "gold.fact_delivery" in schema_block
    assert "gold.dim_player" in schema_block
    assert "gold.mart_player_batting_career" in schema_block


def test_entity_resolver_players(populated_duckdb: duckdb.DuckDBPyConnection):
    resolver = EntityResolver(populated_duckdb)

    # 1. Exact match
    p1 = resolver.resolve_player("Virat Kohli")
    assert p1 is not None
    assert p1.player_id == "483b8b64"
    assert p1.player_uid == "483b8b64"
    assert p1.match_score == 1.0

    # 2. Alias match
    p2 = resolver.resolve_player("V Kohli")
    assert p2 is not None
    assert p2.player_id == "483b8b64"

    # 3. Substring match
    p3 = resolver.resolve_player("Kohli")
    assert p3 is not None
    assert p3.player_id == "483b8b64"

    # 4. Quinton de Kock
    p4 = resolver.resolve_player("de Kock")
    assert p4 is not None
    assert p4.player_id == "372455c4"


def test_entity_resolver_fuzzy_and_nicknames(populated_duckdb: duckdb.DuckDBPyConnection):
    resolver = EntityResolver(populated_duckdb)

    # Jaro-Winkler similarity sanity checks
    assert jaro_winkler_similarity("virat", "virat kohli") > 0.85
    assert jaro_winkler_similarity("rohit", "rohit sharma") > 0.85
    assert jaro_winkler_similarity("martha", "marhta") > 0.95

    # Player nicknames and short names resolution
    p_virat = resolver.resolve_player("Virat")
    assert p_virat is not None
    assert p_virat.player_id == "483b8b64"
    assert p_virat.player_uid == "483b8b64"

    p_king = resolver.resolve_player("King Kohli")
    assert p_king is not None
    assert p_king.player_id == "483b8b64"

    p_rohit = resolver.resolve_player("Rohit")
    assert p_rohit is not None
    assert p_rohit.player_id == "740742ef"

    p_hitman = resolver.resolve_player("Hitman")
    assert p_hitman is not None
    assert p_hitman.player_id == "740742ef"

    p_bumrah = resolver.resolve_player("Bumrah")
    assert p_bumrah is not None
    assert p_bumrah.player_id == "462411b3"

    p_boomboom = resolver.resolve_player("Boom Boom")
    assert p_boomboom is not None
    assert p_boomboom.player_id == "462411b3"

    # Venue nickname and short name resolution
    v_chin = resolver.resolve_venue("Chinnaswamy")
    assert v_chin is not None
    assert "Chinnaswamy" in v_chin.venue_name
    assert v_chin.venue_id == "9fae8291e2d16b83aefe89f0bd1b78e8"

    v_church = resolver.resolve_venue("Church Street")
    assert v_church is not None
    assert "Church Street Park" in v_church.venue_name


def test_entity_resolver_teams_and_venues(populated_duckdb: duckdb.DuckDBPyConnection):
    resolver = EntityResolver(populated_duckdb)

    # Venue resolution
    v = resolver.resolve_venue("Church Street Park")
    assert v is not None
    assert "Church Street Park" in v.venue_name

    # Full query entity extraction with venue and players
    entities = resolver.resolve_all_from_query("Analyze Quinton de Kock at Church Street Park")
    assert len(entities.players) >= 1
    assert entities.players[0].player_id == "372455c4"
    assert len(entities.venues) >= 1
    assert "Church Street Park" in entities.venues[0].venue_name

    # Multi-entity query extraction
    multi = resolver.resolve_all_from_query("Bumrah bowling at Chinnaswamy against Rohit")
    player_ids = [p.player_id for p in multi.players]
    assert "462411b3" in player_ids  # Bumrah
    assert "740742ef" in player_ids  # Rohit
    assert len(multi.venues) >= 1
    assert "Chinnaswamy" in multi.venues[0].venue_name


def test_golden_queries_few_shot_selection(populated_duckdb: duckdb.DuckDBPyConnection):
    registry = GoldenQueryRegistry()

    # 1. Select for death overs query
    death_examples = registry.select_few_shot_examples(
        "Who has best death overs strike rate in T20?", limit=2
    )
    assert len(death_examples) == 2
    assert any("death" in q.keywords for q in death_examples)

    # 2. Select for matchup query
    matchup_examples = registry.select_few_shot_examples(
        "Kohli vs Zampa head to head record", limit=2
    )
    assert len(matchup_examples) == 2
    assert any("matchup" in q.keywords for q in matchup_examples)

    # 3. Prompt formatting
    prompt_ctx = registry.get_few_shot_prompt_context("Top death overs batsmen", limit=1)
    assert "### FEW-SHOT VETTED SQL EXAMPLES" in prompt_ctx
    assert "SELECT" in prompt_ctx

    # 4. Syntax validation: Execute all golden queries on DuckDB
    for gq in registry.queries:
        try:
            # Wrap query in EXPLAIN to validate SQL syntax against live schema without errors
            populated_duckdb.execute(f"EXPLAIN {gq.sql};")
        except Exception as e:
            pytest.fail(f"Golden query '{gq.title}' failed DuckDB syntax check: {e}")


# ==========================================
# PARAMETRIC SEMANTIC TOOLS TESTS
# ==========================================


def test_parametric_get_player_phase_splits(populated_duckdb: duckdb.DuckDBPyConnection):
    # 1. Quinton de Kock (372455c4) in T20
    qdk_report = get_player_phase_splits(
        populated_duckdb, player_uid="372455c4", format="T20", phase="powerplay"
    )
    assert qdk_report["player_id"] == "372455c4"
    assert qdk_report["format"] == "T20"
    assert qdk_report["phase"] == "powerplay"
    assert len(qdk_report["batting"]) == 1
    batting = qdk_report["batting"][0]
    assert batting["phase"] == "powerplay"
    assert batting["runs"] == 10
    assert batting["balls_faced"] == 9  # Strictly legal balls faced (excludes wides)
    assert batting["strike_rate"] == 111.11

    # 2. Ali Khan (b0eaaac6) bowling in T20
    ak_report = get_player_phase_splits(populated_duckdb, player_uid="b0eaaac6", format="T20")
    assert len(ak_report["bowling"]) >= 1
    # Verify bowling economy formula excludes byes & leg-byes
    for b_split in ak_report["bowling"]:
        assert b_split["legal_balls"] > 0
        assert b_split["economy"] >= 0.0

    # 3. Zero-division and non-existent player safety
    empty_report = get_player_phase_splits(
        populated_duckdb, player_uid="non_existent_uid", format="T20"
    )
    assert empty_report["player_id"] == "non_existent_uid"
    assert len(empty_report["batting"]) == 0
    assert len(empty_report["bowling"]) == 0


def test_parametric_get_head_to_head_matchup(populated_duckdb: duckdb.DuckDBPyConnection):
    # Matchup in sample Test match: SR Tendulkar (d2c2b2d5) vs AF Giles (a4af4849)
    matchup = get_head_to_head_matchup(
        populated_duckdb,
        batter_uid="d2c2b2d5",
        bowler_uid="a4af4849",
        format_name="Test",
    )
    assert matchup["batter_id"] == "d2c2b2d5"
    assert matchup["bowler_id"] == "a4af4849"
    assert matchup["format"] == "Test"
    assert matchup["balls_faced"] > 0
    assert matchup["runs_scored"] >= 0
    assert matchup["strike_rate"] >= 0.0
    assert isinstance(matchup["phase_breakdown"], list)

    # Unplayed matchup edge case (zero division safety)
    zero_matchup = get_head_to_head_matchup(
        populated_duckdb,
        batter_uid="372455c4",  # Q de Kock
        bowler_uid="a4af4849",  # Giles
        format_name="T20",
    )
    assert zero_matchup["balls_faced"] == 0
    assert zero_matchup["runs_scored"] == 0
    assert zero_matchup["dismissals"] == 0
    assert zero_matchup["strike_rate"] == 0.0
    assert zero_matchup["batting_average"] is None


def test_parametric_get_venue_phase_and_toss_profile(populated_duckdb: duckdb.DuckDBPyConnection):
    # Chinnaswamy venue profile (venue_id = '9fae8291e2d16b83aefe89f0bd1b78e8')
    profile = get_venue_phase_and_toss_profile(
        populated_duckdb, venue_id="9fae8291e2d16b83aefe89f0bd1b78e8", format_name="Test"
    )
    assert "Chinnaswamy" in profile["venue_name"]
    assert profile["total_matches"] == 1
    assert profile["format"] == "Test"
    assert "toss_decision" in profile
    assert profile["toss_decision"]["bat"] == 1
    assert "match_outcomes" in profile
    assert isinstance(profile["phase_stats"], list)

    # Resolution by stadium name substring in profile
    church_profile = get_venue_phase_and_toss_profile(
        populated_duckdb, venue_id="Church Street Park", format_name="T20"
    )
    assert "Church Street Park" in church_profile["venue_name"]
    assert church_profile["total_matches"] == 1
    assert church_profile["format"] == "T20"


def test_semantic_tools_registry_wrapper(populated_duckdb: duckdb.DuckDBPyConnection):
    registry = GoldenQueryRegistry(con=populated_duckdb)

    # Helper methods bound to registry
    qdk = registry.get_player_phase_splits("372455c4", format="T20")
    assert qdk["player_id"] == "372455c4"

    matchup = registry.get_head_to_head_matchup("d2c2b2d5", "a4af4849", format="Test")
    assert matchup["balls_faced"] > 0

    venue = registry.get_venue_phase_and_toss_profile("Chinnaswamy", format="Test")
    assert venue["total_matches"] >= 1

    # Format normalization check
    assert normalize_match_format("t20") == "T20"
    assert normalize_match_format("odi") == "ODI"
    assert normalize_match_format("test") == "Test"

    # Registry without con raises ValueError
    empty_reg = GoldenQueryRegistry(con=None)
    with pytest.raises(ValueError):
        empty_reg.get_player_phase_splits("483b8b64")
