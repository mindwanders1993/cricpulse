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

_FOLLOW_UPS_MARKER = re.compile(r"FOLLOW_UPS:", re.IGNORECASE)
_DENOMINATOR_HINTS = ("balls", "matches", "innings", "_id", "count")
_RATE_KEYWORDS = ("rate", "average", "avg", "percentage", "pct", "economy", "index")
_DEFAULT_FORMAT_FOLLOW_UPS = ["Only ODI?", "Only T20?", "Domestic matches only?"]


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

        # 5. Coverage disclosure — did the query scope to a single match format, or blend them all?
        coverage_scoped = "match_type" in executed_sql.lower()
        coverage = (
            None
            if coverage_scoped
            else "Blends all match formats (T20, ODI, Test, and domestic) — not filtered to one."
        )

        # 6. Synthesize Insight, grounded strictly in the returned rows, plus follow-up questions
        insight_prompt = f"""
Synthesize a concise 2-3 sentence journalistic cricket insight for the user's question based on these results.

QUESTION: {user_query}
COVERAGE: {coverage or "Filtered to a single match format, as scoped by the query."}
ROWS RETURNED ({len(rows)} total): {rows[:40]}

RULES:
- Only state numbers that literally appear in ROWS RETURNED. Never invent, round unexpectedly, or extrapolate a value.
- If you cite a superlative (best/highest/lowest/peak/most), it must be the row with the actual max/min value for that metric among ROWS RETURNED. Double-check before claiming it.
- If a row represents an unusually small sample (e.g. a count/balls/matches value far below the typical row in the set), do not call it a "peak" or "best" without noting the small sample.
- If COVERAGE says results blend multiple match formats, say so explicitly in the insight.
- Format each supporting number as a separate line starting with "- " when there is more than one supporting point.

After the insight, suggest exactly 3 short natural-language follow-up questions a curious user might ask next to narrow this down (by format, phase, or opponent). Output them as:
FOLLOW_UPS:
- <question 1>
- <question 2>
- <question 3>
        """.strip()
        raw_response = self.gemini.generate_text(system_instruction, insight_prompt)
        insight, follow_ups = self._parse_insight_and_follow_ups(raw_response)
        if not insight:
            insight = f"Found {len(rows)} matching results for your query."
        if not follow_ups:
            follow_ups = self._default_follow_ups(coverage_scoped)

        chart_specs = ChartSpecGenerator.generate_spec(rows, subtitle=coverage)
        key_points = self._compute_key_points(rows)

        return {
            "query": user_query,
            "insight": insight,
            "sql_executed": executed_sql,
            "rows": rows,
            "chart_specs": chart_specs,
            "follow_ups": follow_ups,
            "key_points": key_points,
            "coverage": coverage,
        }

    def _parse_insight_and_follow_ups(self, raw_text: str) -> tuple[str, list[str]]:
        """Split the LLM's response into the prose insight and its trailing FOLLOW_UPS block."""
        match = _FOLLOW_UPS_MARKER.search(raw_text)
        if not match:
            return raw_text.strip(), []

        insight_part = raw_text[: match.start()].strip()
        follow_up_lines = [
            line.strip().lstrip("-").strip()
            for line in raw_text[match.end() :].splitlines()
            if line.strip().startswith("-")
        ]
        return insight_part, [f for f in follow_up_lines[:3] if f]

    def _default_follow_ups(self, coverage_scoped: bool) -> list[str]:
        """Deterministic fallback follow-up chips when the LLM omits/malforms its FOLLOW_UPS block."""
        if not coverage_scoped:
            return _DEFAULT_FORMAT_FOLLOW_UPS

        phase_dim = self.catalog.model.dimensions.get("phase")
        phases: list[str] = []
        if phase_dim and phase_dim.allowed_values:
            for entry in phase_dim.allowed_values:
                if isinstance(entry, dict):
                    phases.extend(entry.keys())
                elif isinstance(entry, str):
                    phases.append(entry)
        phases = [p for p in phases if p != "regular"][:3] or ["powerplay", "middle", "death"]
        return [f"Only in the {p} overs?" for p in phases]

    def _compute_key_points(self, rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Deterministically compute headline stat tiles from the rows — never LLM-authored,
        so the most prominent numbers on screen can't be hallucinated."""
        if not rows:
            return []

        first_row = rows[0]
        label_col: str | None = None
        quant_cols: list[str] = []
        for k, v in first_row.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                quant_cols.append(k)
            elif isinstance(v, str) and label_col is None:
                label_col = k

        primary = [c for c in quant_cols if not any(h in c.lower() for h in _DENOMINATOR_HINTS)]
        metrics = (primary or quant_cols)[:2]
        if not metrics:
            return []

        points: list[dict[str, str]] = []
        for metric in metrics:
            values = [
                (row[metric], row)
                for row in rows
                if isinstance(row.get(metric), (int, float)) and not isinstance(row[metric], bool)
            ]
            if not values:
                continue

            best_value, best_row = max(values, key=lambda vr: vr[0])
            metric_title = metric.replace("_", " ").title()
            label = f"Best {metric_title}"
            if label_col and best_row.get(label_col):
                label = f"{label} · {best_row[label_col]}"
            points.append({"label": label, "value": self._format_number(best_value)})

            is_additive = not any(h in metric.lower() for h in _RATE_KEYWORDS)
            if is_additive and len(rows) > 1:
                total = sum(v for v, _ in values)
                total_label = (
                    metric_title if metric.lower().startswith("total") else f"Total {metric_title}"
                )
                points.append({"label": total_label, "value": self._format_number(total)})

        points.append({"label": "Rows returned", "value": f"{len(rows):,}"})
        return points[:4]

    @staticmethod
    def _format_number(value: int | float) -> str:
        return f"{value:,.2f}" if isinstance(value, float) else f"{value:,}"
