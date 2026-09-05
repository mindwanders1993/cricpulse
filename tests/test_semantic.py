from pathlib import Path

import duckdb
import pytest

from src.builder.loader import DuckDBLoader
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser
from src.semantic.catalog import SemanticCatalog
from src.semantic.golden_queries import GoldenQueryRegistry
from src.semantic.resolver import EntityResolver


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


def test_entity_resolver_teams_and_venues(populated_duckdb: duckdb.DuckDBPyConnection):
    resolver = EntityResolver(populated_duckdb)

    # Venue resolution
    v = resolver.resolve_venue("Church Street Park")
    assert v is not None
    assert "Church Street Park" in v.venue_name

    # Full query entity extraction
    entities = resolver.resolve_all_from_query("Analyze Quinton de Kock at Church Street Park")
    assert len(entities.players) >= 1
    assert entities.players[0].player_id == "372455c4"


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
