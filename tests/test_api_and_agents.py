from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

from src.ai.chart_spec import ChartSpecGenerator
from src.ai.guardrails import SQLSecurityGuardrail, SQLSecurityViolation
from src.ai.narrative_storyteller import NarrativeStorytellerAgent
from src.ai.supervisor import SupervisorAgent
from src.ai.tactical_scout import TacticalScoutAgent
from src.ai.text_to_sql import TextToSQLAgent
from src.api.app import create_app
from src.builder.loader import DuckDBLoader
from src.config import get_settings
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser


@pytest.fixture
def populated_db_path(temp_dir: Path) -> Path:
    """Build a populated DuckDB database file for API and Agent tests."""
    db_file = temp_dir / "api_test.duckdb"
    loader = DuckDBLoader(db_path=db_file)

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
    loader.close()
    return db_file


@pytest.fixture
def api_client(populated_db_path: Path) -> TestClient:
    """Create FastAPI TestClient configured with the populated test database."""
    app_instance = create_app(db_path=populated_db_path)
    with TestClient(app_instance) as client:
        yield client


# ==========================================
# 1. SQL AST SECURITY GUARDRAIL TESTS
# ==========================================


def test_guardrail_valid_select_and_cte():
    valid_query = """
    WITH death_batters AS (
        SELECT batter_name, SUM(runs_batter) AS runs
        FROM gold.fact_delivery
        WHERE phase = 'death'
        GROUP BY batter_name
    )
    SELECT * FROM death_batters ORDER BY runs DESC;
    """
    sanitized = SQLSecurityGuardrail.validate_and_sanitize(valid_query)
    assert "LIMIT" in sanitized
    assert "death_batters" in sanitized


def test_guardrail_blocks_destructive_statements():
    malicious_queries = [
        "DROP TABLE gold.dim_player;",
        "DELETE FROM gold.fact_delivery WHERE 1=1;",
        "INSERT INTO gold.dim_player VALUES ('1', 'bad', 'bad', null, null, null, null);",
        "UPDATE gold.dim_match SET match_type = 'hack';",
        "ALTER TABLE gold.dim_player DROP COLUMN full_name;",
        "ATTACH 'evil.db' AS evil;",
    ]
    for q in malicious_queries:
        with pytest.raises(SQLSecurityViolation):
            SQLSecurityGuardrail.validate_and_sanitize(q)


def test_guardrail_blocks_unauthorized_tables_and_functions():
    with pytest.raises(SQLSecurityViolation):
        SQLSecurityGuardrail.validate_and_sanitize("SELECT * FROM raw.match_data;")

    with pytest.raises(SQLSecurityViolation):
        SQLSecurityGuardrail.validate_and_sanitize("SELECT * FROM attacker_table;")

    with pytest.raises(SQLSecurityViolation):
        SQLSecurityGuardrail.validate_and_sanitize("SELECT * FROM read_csv('secret.csv');")


# ==========================================
# 2. VEGA-LITE CHART SPEC TESTS
# ==========================================


def test_chart_spec_generator():
    rows = [
        {"player_name": "Heinrich Klaasen", "strike_rate": 215.4, "balls": 118},
        {"player_name": "Nicholas Pooran", "strike_rate": 198.6, "balls": 148},
        {"player_name": "Dinesh Karthik", "strike_rate": 192.1, "balls": 114},
    ]
    spec = ChartSpecGenerator.generate_spec(rows, title="Top Strike Rates")
    assert spec is not None
    assert spec["mark"]["type"] == "bar"
    assert spec["encoding"]["x"]["field"] == "player_name"
    assert spec["encoding"]["y"]["field"] == "strike_rate"


# ==========================================
# 3. AI AGENTS INTEGRATION TESTS
# ==========================================


def test_text_to_sql_agent(populated_db_path: Path):
    con = duckdb.connect(str(populated_db_path), read_only=True)
    agent = TextToSQLAgent(con=con)

    result = agent.query("Who scored the most runs in death overs?")
    assert result["status"] == "success" if "status" in result else True
    assert "sql_executed" in result
    assert "rows" in result
    assert len(result["rows"]) > 0
    assert result["insight"] is not None
    con.close()


def test_tactical_scout_agent(populated_db_path: Path):
    con = duckdb.connect(str(populated_db_path), read_only=True)
    agent = TacticalScoutAgent(con=con)

    report = agent.scout_matchup(batter_name="Q de Kock", bowler_name="Ali Khan", phase="powerplay")
    assert report["batter"] is not None
    assert "metrics" in report
    assert "balls_faced" in report["metrics"]
    assert "tactical_report" in report
    con.close()


# ==========================================
# 4. FASTAPI ENDPOINTS INTEGRATION TESTS
# ==========================================


def test_api_health_and_readiness(api_client: TestClient):
    resp_health = api_client.get("/health")
    assert resp_health.status_code == 200
    assert resp_health.json()["status"] == "healthy"

    resp_ready = api_client.get("/ready")
    assert resp_ready.status_code == 200
    assert resp_ready.json()["database_connected"] is True
    assert resp_ready.json()["tables_count"] > 0


def test_api_analytics_leaderboards(api_client: TestClient):
    # Batting leaderboard
    resp_bat = api_client.get("/api/v1/analytics/leaderboards/batting?match_type=T20&limit=10")
    assert resp_bat.status_code == 200
    bat_data = resp_bat.json()
    assert bat_data["category"] == "batting"
    assert len(bat_data["data"]) > 0

    # Bowling leaderboard
    resp_bowl = api_client.get("/api/v1/analytics/leaderboards/bowling?match_type=T20&limit=10")
    assert resp_bowl.status_code == 200
    bowl_data = resp_bowl.json()
    assert bowl_data["category"] == "bowling"
    assert len(bowl_data["data"]) > 0


def test_api_ai_query_endpoint(api_client: TestClient):
    payload = {"query": "Top death overs batsmen in T20s", "include_chart": True}
    resp = api_client.post("/api/v1/ai/query", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "insight" in data
    assert "sql_executed" in data
    assert "rows" in data


def test_api_ai_scout_endpoint(api_client: TestClient):
    payload = {
        "batter_name": "Virat Kohli",
        "bowler_name": "Adam Zampa",
        "phase": "middle",
        "match_type": "T20",
    }
    resp = api_client.post("/api/v1/ai/scout", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["batter"] == "Virat Kohli"
    assert "metrics" in data
    assert "tactical_report" in data


def test_narrative_storyteller_agent(populated_db_path: Path):
    con = duckdb.connect(str(populated_db_path), read_only=True)
    agent = NarrativeStorytellerAgent(con=con)

    # Get sample match
    match_row = con.execute("SELECT match_id FROM gold.dim_match LIMIT 1;").fetchone()
    assert match_row is not None
    match_id = str(match_row[0])

    story = agent.generate_story(match_id=match_id)
    assert story["match_id"] == match_id
    assert "headline" in story
    assert len(story["headline"]) > 0
    assert "editorial_recap" in story
    assert len(story["editorial_recap"]) > 0
    assert story["chart_spec"] is not None
    con.close()


def test_supervisor_agent(populated_db_path: Path):
    con = duckdb.connect(str(populated_db_path), read_only=True)
    supervisor = SupervisorAgent(con=con)

    # 1. Test intent classification
    assert (
        supervisor.classify_intent("Who scored the most runs in death overs?") == "ANALYTICAL_SQL"
    )
    assert supervisor.classify_intent("Rohit vs Starc in powerplay") == "TACTICAL_SCOUT"
    assert supervisor.classify_intent("Recap match 1384400") == "NARRATIVE_STORY"

    # 2. Test chat dispatch
    res_sql = supervisor.chat("Who scored the most runs in death overs?")
    assert res_sql["status"] == "success"
    assert res_sql["intent"] == "analytical_sql"
    assert res_sql["routed_agent"] == "TextToSQLAgent"
    assert "reply" in res_sql

    res_scout = supervisor.chat("Analyze Kohli vs Zampa matchup")
    assert res_scout["status"] == "success"
    assert res_scout["intent"] == "tactical_scout"
    assert res_scout["routed_agent"] == "TacticalScoutAgent"

    con.close()


def test_api_ai_story_endpoint(api_client: TestClient, populated_db_path: Path):
    con = duckdb.connect(str(populated_db_path), read_only=True)
    match_row = con.execute("SELECT match_id FROM gold.dim_match LIMIT 1;").fetchone()
    con.close()

    assert match_row is not None
    payload = {"match_id": str(match_row[0]), "focus": "turning points"}
    resp = api_client.post("/api/v1/ai/story", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["match_id"] == str(match_row[0])
    assert "headline" in data
    assert "editorial_recap" in data


def test_api_ai_chat_endpoint(api_client: TestClient):
    payload = {"message": "Who scored the most runs?", "include_chart": True}
    resp = api_client.post("/api/v1/ai/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "reply" in data
    assert "routed_agent" in data


def test_api_internal_sync_endpoint(api_client: TestClient, monkeypatch):
    settings = get_settings()

    # 1. In test environment, sync is allowed without token
    monkeypatch.setattr(settings, "app_env", "test")
    # Mock download_registers to avoid external HTTP in unit tests
    from unittest.mock import patch

    with (
        patch(
            "src.downloaders.register_downloader.RegisterDownloader.download_registers"
        ) as mock_reg,
        patch(
            "src.downloaders.match_downloader.MatchDownloader.download_and_extract"
        ) as mock_match,
    ):
        mock_reg.return_value = (
            Path("tests/fixtures/sample_people.csv"),
            Path("tests/fixtures/sample_names.csv"),
        )
        mock_match.return_value = [Path("tests/fixtures/sample_t20.json")]

        resp = api_client.post("/api/v1/internal/sync-daily")
        assert resp.status_code == 200
        sync_data = resp.json()
        assert sync_data["status"] == "success"
        assert "matches_downloaded" in sync_data

    # 2. In production environment with token, unauthorized without header
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "sync_secret_token", "super_secret_token_123")

    resp_unauth = api_client.post("/api/v1/internal/sync-daily")
    assert resp_unauth.status_code == 401

    # 3. Authorized with correct header
    with (
        patch(
            "src.downloaders.register_downloader.RegisterDownloader.download_registers"
        ) as mock_reg,
        patch(
            "src.downloaders.match_downloader.MatchDownloader.download_and_extract"
        ) as mock_match,
    ):
        mock_reg.return_value = (
            Path("tests/fixtures/sample_people.csv"),
            Path("tests/fixtures/sample_names.csv"),
        )
        mock_match.return_value = [Path("tests/fixtures/sample_t20.json")]

        resp_auth = api_client.post(
            "/api/v1/internal/sync-daily",
            headers={"X-Sync-Token": "super_secret_token_123"},
        )
        assert resp_auth.status_code == 200
