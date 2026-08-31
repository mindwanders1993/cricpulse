from pathlib import Path

import duckdb
import yaml

from src.semantic.models import MetricDefinition, SemanticCatalogModel
from src.utils import setup_logging

logger = setup_logging()


class SemanticCatalog:
    """Loads, validates, and synthesizes semantic metric and schema context for AI agents."""

    def __init__(self, catalog_model: SemanticCatalogModel):
        self.model = catalog_model

    @classmethod
    def load_from_yaml(
        cls, yaml_path: Path | str = "conf/semantic_catalog.yaml"
    ) -> "SemanticCatalog":
        """Load and validate the canonical YAML semantic catalog."""
        path = Path(yaml_path)
        if not path.exists():
            raise FileNotFoundError(f"Semantic catalog not found at {path}")

        raw_data = yaml.safe_load(path.read_text(encoding="utf-8"))
        model = SemanticCatalogModel.model_validate(raw_data)
        logger.info(
            "semantic_catalog_loaded", version=model.version, metrics_count=len(model.metrics)
        )
        return cls(model)

    def get_metric(self, metric_key: str) -> MetricDefinition | None:
        """Fetch a specific metric definition by key."""
        return self.model.metrics.get(metric_key)

    def get_metric_prompt_context(self, filter_keys: list[str] | None = None) -> str:
        """Generate a token-optimized Markdown block of canonical metric definitions and SQL expressions."""
        lines = [
            "### CANONICAL CRICKET METRICS & MATHEMATICAL FORMULAS",
            "Use these EXACT SQL expressions when calculating cricket metrics. Do NOT invent alternate formulas:",
            "",
        ]

        metrics_to_show = (
            {k: v for k, v in self.model.metrics.items() if k in filter_keys}
            if filter_keys
            else self.model.metrics
        )

        for key, m in metrics_to_show.items():
            lines.append(f"- **{m.name}** (`{key}`): {m.description}")
            lines.append(f"  - Formula: `{m.formula}`")
            lines.append(f"  - Unit: `{m.unit}` | Default Sort: `{m.default_sort}`")

        # Add dimension enums
        if self.model.dimensions:
            lines.append("\n### CANONICAL DIMENSION ENUMS")
            if "phase" in self.model.dimensions:
                lines.append(
                    "- **Match Phase (`phase`)**: `'powerplay'` (T20: 1-6, ODI: 1-10), `'middle'` (T20: 7-15, ODI: 11-40), `'death'` (T20: 16-20, ODI: 41-50)"
                )
            if "dismissal_kind" in self.model.dimensions:
                dim = self.model.dimensions["dismissal_kind"]
                if dim.bowler_credited:
                    lines.append(
                        f"- **Bowler-Credited Wickets**: {', '.join(repr(x) for x in dim.bowler_credited)}"
                    )
                if dim.non_bowler_credited:
                    lines.append(
                        f"- **Non-Bowler Dismissals (Run Outs, etc.)**: {', '.join(repr(x) for x in dim.non_bowler_credited)}"
                    )

        return "\n".join(lines)

    def get_schema_prompt_context(self, con: duckdb.DuckDBPyConnection) -> str:
        """Query DuckDB metadata and synthesize condensed table contracts for AI prompts."""
        tables_query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'gold'
            ORDER BY table_name;
        """
        table_rows = con.execute(tables_query).fetchall()
        table_names = [r[0] for r in table_rows]

        lines = [
            "### DATABASE SCHEMA CONTRACTS (`gold.*` tables)",
            "All queries MUST operate on these Gold tables. Do NOT query raw or silver schemas:",
            "",
        ]

        for tbl in table_names:
            cols_query = f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_schema = 'gold' AND table_name = '{tbl}'
                ORDER BY ordinal_position;
            """
            cols = con.execute(cols_query).fetchall()
            col_signatures = [f"{c[0]} ({c[1].lower()})" for c in cols]
            lines.append(f"- **`gold.{tbl}`**: {', '.join(col_signatures)}")

        return "\n".join(lines)
