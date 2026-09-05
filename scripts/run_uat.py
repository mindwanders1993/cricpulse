"""Automated User Acceptance Testing (UAT) Harness for CricPulse.

Executes end-to-end scenarios against all API endpoints, verifying status codes,
response schemas, multi-agent outputs, and security guardrails.
"""

import sys
import time
from pathlib import Path
from typing import Any

import duckdb
from fastapi.testclient import TestClient
from rich.console import Console
from rich.table import Table

from src.ai.guardrails import SQLSecurityGuardrail, SQLSecurityViolation
from src.api.app import create_app
from src.builder.loader import DuckDBLoader
from src.config import get_settings
from src.parsers.match_parser import MatchParser
from src.parsers.register_parser import RegisterParser

console = Console()


def ensure_uat_database() -> Path:
    """Ensure a validated DuckDB database exists for UAT execution."""
    settings = get_settings()
    published_db = settings.published_dir / "cricket_latest.duckdb"

    if published_db.exists():
        try:
            conn = duckdb.connect(str(published_db), read_only=True)
            conn.close()
            console.print(f"[green]✓ Found published DuckDB lakehouse:[/green] {published_db}")
            return published_db
        except Exception:
            console.print(
                f"[yellow]⚠️ {published_db} is locked by an external process (e.g. DBeaver). Falling back to isolated UAT database.[/yellow]"
            )

    uat_db = settings.data_dir / "uat_test.duckdb"
    console.print(f"[yellow]Building UAT database from test fixtures at {uat_db}...[/yellow]")
    if uat_db.exists():
        uat_db.unlink()

    loader = DuckDBLoader(db_path=uat_db)
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
    return uat_db


def run_uat_suite() -> int:
    start_time = time.time()
    console.print("\n[bold cyan]🏏 =========================================[/bold cyan]")
    console.print("[bold cyan]🏏 CricPulse End-to-End Automated UAT Suite [/bold cyan]")
    console.print("[bold cyan]🏏 =========================================[/bold cyan]\n")

    db_path = ensure_uat_database()
    app = create_app(db_path=db_path)
    results: list[dict[str, Any]] = []

    with TestClient(app) as client:
        # Scenario 1: Health & Readiness Probe
        try:
            r1 = client.get("/health")
            r2 = client.get("/ready")
            assert r1.status_code == 200 and r1.json()["status"] == "healthy"
            assert r2.status_code == 200 and r2.json()["database_connected"] is True
            results.append(
                {
                    "scenario": "1. Health & Readiness Probes",
                    "endpoint": "GET /health, GET /ready",
                    "status": "PASS",
                    "details": f"Tables registered: {r2.json().get('tables_count', 0)}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "1. Health & Readiness Probes",
                    "endpoint": "GET /health, GET /ready",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 2: Batting Leaderboard
        try:
            r = client.get("/api/v1/analytics/leaderboards/batting?match_type=T20&limit=5")
            assert r.status_code == 200
            data = r.json()
            assert data["category"] == "batting"
            assert len(data["data"]) > 0
            top_batter = data["data"][0].get("full_name", "N/A")
            results.append(
                {
                    "scenario": "2. Batting Career Leaderboard",
                    "endpoint": "GET /api/v1/analytics/leaderboards/batting",
                    "status": "PASS",
                    "details": f"Top batter: {top_batter}, Count: {len(data['data'])}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "2. Batting Career Leaderboard",
                    "endpoint": "GET /api/v1/analytics/leaderboards/batting",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 3: Bowling Leaderboard
        try:
            r = client.get("/api/v1/analytics/leaderboards/bowling?match_type=T20&limit=5")
            assert r.status_code == 200
            data = r.json()
            assert data["category"] == "bowling"
            assert len(data["data"]) > 0
            top_bowler = data["data"][0].get("full_name", "N/A")
            results.append(
                {
                    "scenario": "3. Bowling Career Leaderboard",
                    "endpoint": "GET /api/v1/analytics/leaderboards/bowling",
                    "status": "PASS",
                    "details": f"Top bowler: {top_bowler}, Count: {len(data['data'])}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "3. Bowling Career Leaderboard",
                    "endpoint": "GET /api/v1/analytics/leaderboards/bowling",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 4: AI Text-to-SQL + AST Security
        try:
            r_valid = client.post(
                "/api/v1/ai/query",
                json={"query": "Who scored the most runs in death overs?", "include_chart": True},
            )
            assert r_valid.status_code == 200
            valid_data = r_valid.json()
            assert "insight" in valid_data and "sql_executed" in valid_data

            blocked = False
            try:
                SQLSecurityGuardrail.validate_and_sanitize("DROP TABLE gold.dim_player;")
            except SQLSecurityViolation:
                blocked = True
            assert blocked is True

            results.append(
                {
                    "scenario": "4. Text-to-SQL & AST Security",
                    "endpoint": "POST /api/v1/ai/query",
                    "status": "PASS",
                    "details": f"SQL executed cleanly; DDL attacks blocked. Chart spec: {valid_data.get('chart_spec') is not None}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "4. Text-to-SQL & AST Security",
                    "endpoint": "POST /api/v1/ai/query",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 5: Tactical Matchup Simulation
        try:
            r = client.post(
                "/api/v1/ai/scout",
                json={
                    "batter_name": "Virat Kohli",
                    "bowler_name": "Jasprit Bumrah",
                    "phase": "death",
                },
            )
            assert r.status_code == 200
            data = r.json()
            assert "metrics" in data
            assert "tactical_report" in data
            results.append(
                {
                    "scenario": "5. Tactical Matchup Scout",
                    "endpoint": "POST /api/v1/ai/scout",
                    "status": "PASS",
                    "details": f"Matchup: {data['batter']} vs {data['bowler']} ({data['phase']})",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "5. Tactical Matchup Scout",
                    "endpoint": "POST /api/v1/ai/scout",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 6: Narrative Match Story & Momentum Chart
        try:
            con = app.state.db
            row = con.execute("SELECT match_id FROM gold.dim_match LIMIT 1;").fetchone()
            match_id = str(row[0]) if row else "sample_match"

            r = client.post(
                "/api/v1/ai/story",
                json={"match_id": match_id, "focus": "turning points", "include_chart": True},
            )
            assert r.status_code == 200
            story = r.json()
            assert "headline" in story and "editorial_recap" in story
            results.append(
                {
                    "scenario": "6. Narrative Storyteller Agent",
                    "endpoint": "POST /api/v1/ai/story",
                    "status": "PASS",
                    "details": f"Headline: '{story['headline'][:35]}...', Chart: {story.get('chart_spec') is not None}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "6. Narrative Storyteller Agent",
                    "endpoint": "POST /api/v1/ai/story",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 7: Supervisor Unified Chat Router
        try:
            r = client.post(
                "/api/v1/ai/chat",
                json={"message": "Analyze Kohli vs Bumrah in death overs", "include_chart": True},
            )
            assert r.status_code == 200
            chat_data = r.json()
            assert chat_data["routed_agent"] == "TacticalScoutAgent"
            assert chat_data["intent"] == "tactical_scout"
            results.append(
                {
                    "scenario": "7. Supervisor Intent Router",
                    "endpoint": "POST /api/v1/ai/chat",
                    "status": "PASS",
                    "details": f"Routed to: {chat_data['routed_agent']}, Intent: {chat_data['intent']}",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "7. Supervisor Intent Router",
                    "endpoint": "POST /api/v1/ai/chat",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

        # Scenario 8: Internal Scheduled Sync Webhook
        try:
            r = client.post("/api/v1/internal/sync-daily")
            assert r.status_code in (200, 401)
            results.append(
                {
                    "scenario": "8. Internal Scheduled Sync Webhook",
                    "endpoint": "POST /api/v1/internal/sync-daily",
                    "status": "PASS",
                    "details": f"Endpoint mounted and responsive (status: {r.status_code})",
                }
            )
        except Exception as e:
            results.append(
                {
                    "scenario": "8. Internal Scheduled Sync Webhook",
                    "endpoint": "POST /api/v1/internal/sync-daily",
                    "status": "FAIL",
                    "details": str(e),
                }
            )

    # Display UAT Report Table
    table = Table(title="CricPulse Automated UAT Results")
    table.add_column("Scenario", style="bold white")
    table.add_column("Endpoint", style="cyan")
    table.add_column("Result", justify="center")
    table.add_column("Details", style="dim")

    all_passed = True
    for res in results:
        status_style = (
            "[bold green]PASS[/bold green]"
            if res["status"] == "PASS"
            else "[bold red]FAIL[/bold red]"
        )
        if res["status"] != "PASS":
            all_passed = False
        table.add_row(res["scenario"], res["endpoint"], status_style, res["details"])

    console.print(table)
    elapsed = round(time.time() - start_time, 2)

    if all_passed:
        console.print(
            f"\n[bold green]🎉 ALL UAT SCENARIOS PASSED 100% IN {elapsed}s![/bold green]\n"
        )
        return 0
    else:
        console.print(f"\n[bold red]❌ SOME UAT SCENARIOS FAILED IN {elapsed}s![/bold red]\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_uat_suite())
