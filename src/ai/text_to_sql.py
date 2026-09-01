import re
from typing import Any

import duckdb

from src.ai.chart_spec import ChartSpecGenerator
from src.ai.gemini_client import GeminiClient
from src.ai.guardrails import SQLSecurityGuardrail, SQLSecurityViolation
from src.semantic.catalog import SemanticCatalog
from src.semantic.golden_queries import GoldenQueryRegistry
from src.semantic.resolver import EntityResolver
from src.utils import setup_logging

logger = setup_logging()


class TextToSQLAgent:
    """Analytical Text-to-SQL Agent with AST guardrails and autonomous 3-turn self-correction."""

    def __init__(
        self,
        con: duckdb.DuckDBPyConnection,
        catalog: SemanticCatalog | None = None,
        gemini_client: GeminiClient | None = None,
        golden_registry: GoldenQueryRegistry | None = None,
    ):
        self.con = con
        self.catalog = catalog or SemanticCatalog.load_from_yaml()
        self.gemini = gemini_client or GeminiClient()
        self.golden = golden_registry or GoldenQueryRegistry()
        self.resolver = EntityResolver(self.con)

    def extract_sql_from_response(self, text: str) -> str:
        """Extract clean SQL string from markdown code blocks or plain text."""
        match = re.search(r"```(?:sql)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        # Fallback to lines starting with SELECT or WITH
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for i, line in enumerate(lines):
            if line.upper().startswith(("SELECT", "WITH")):
                return " ".join(lines[i:])
        return text.strip()

    def query(self, user_query: str, max_reflection_turns: int = 3) -> dict[str, Any]:
        """Process natural language query into validated, executed SQL insights."""
        logger.info("processing_text_to_sql_query", query=user_query)

        # 1. Resolve Entities
        resolved_entities = self.resolver.resolve_all_from_query(user_query)
        entity_context = ""
        if resolved_entities.players:
            p_strs = [f"{p.full_name} (ID: {p.player_id})" for p in resolved_entities.players]
            entity_context += f"- Pre-resolved Players: {', '.join(p_strs)}\n"
        if resolved_entities.teams:
            t_strs = [t.team_name for t in resolved_entities.teams]
            entity_context += f"- Pre-resolved Teams: {', '.join(t_strs)}\n"

        # 2. Build Context Blocks
        metrics_block = self.catalog.get_metric_prompt_context()
        schema_block = self.catalog.get_schema_prompt_context(self.con)
        few_shot_block = self.golden.get_few_shot_prompt_context(user_query, limit=2)

        system_instruction = """
You are "Data Sensei", an expert Cricket Analytics AI for CricPulse.
Your task is to write precise, high-performance DuckDB SQL queries over the `gold.*` schema.

RULES:
1. Always use the canonical SQL metric formulas provided in the context.
2. Only query tables in the `gold` schema (e.g. `gold.fact_delivery`, `gold.dim_player`, `gold.mart_*`).
3. Output the final SQL query inside a ```sql ... ``` markdown block.
4. Keep the query read-only (SELECT / CTEs only).
        """.strip()

        prompt = f"""
USER QUESTION:
"{user_query}"

{entity_context}

{metrics_block}

{schema_block}

{few_shot_block}

Generate the exact DuckDB SQL query to answer the user question.
        """.strip()

        # 3. Generate initial SQL
        raw_response = self.gemini.generate_text(system_instruction, prompt)
        current_sql = self.extract_sql_from_response(raw_response)

        # 4. Self-Correction Reflection Loop (up to max_reflection_turns)
        rows: list[dict[str, Any]] = []
        executed_sql = current_sql
        last_error = ""

        for turn in range(1, max_reflection_turns + 1):
            try:
                # AST Guardrail check
                sanitized_sql = SQLSecurityGuardrail.validate_and_sanitize(current_sql)
                executed_sql = sanitized_sql

                # Execute on DuckDB
                rel = self.con.sql(sanitized_sql)
                raw_rows = rel.fetchall()
                col_names = rel.columns
                rows = [dict(zip(col_names, r, strict=False)) for r in raw_rows]
                logger.info("query_executed_successfully", turn=turn, row_count=len(rows))
                break

            except SQLSecurityViolation as sec_err:
                logger.error("sql_security_violation", error=str(sec_err), sql=current_sql)
                raise

            except Exception as exec_err:
                last_error = str(exec_err)
                logger.warn(
                    "query_execution_failed_reflecting",
                    turn=turn,
                    error=last_error,
                    sql=current_sql,
                )
                if turn == max_reflection_turns:
                    raise RuntimeError(
                        f"Failed to execute SQL after {max_reflection_turns} attempts: {last_error}"
                    ) from exec_err

                # Self-Correction Prompt
                reflection_prompt = f"""
The following DuckDB SQL query failed execution with error:
ERROR: {last_error}

FAULTY SQL:
{current_sql}

DATABASE SCHEMA:
{schema_block}

Fix the SQL query so it runs cleanly on DuckDB. Output ONLY the corrected query in a ```sql ... ``` code block.
                """.strip()

                repaired_response = self.gemini.generate_text(system_instruction, reflection_prompt)
                current_sql = self.extract_sql_from_response(repaired_response)

        # 5. Synthesize Insight & Chart Specification
        insight_prompt = f"""
Synthesize a concise 1-2 sentence journalistic cricket insight for the user's question based on these results:
QUESTION: {user_query}
ROWS RETURNED: {rows[:10]}
        """
        insight = self.gemini.generate_text(system_instruction, insight_prompt).strip()
        if not insight:
            insight = f"Found {len(rows)} matching results for your query."

        chart_spec = ChartSpecGenerator.generate_spec(rows, title=user_query)

        return {
            "query": user_query,
            "insight": insight,
            "sql_executed": executed_sql,
            "rows": rows,
            "chart_spec": chart_spec,
        }
