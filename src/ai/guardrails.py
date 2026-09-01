import sqlglot
from sqlglot import exp

from src.utils import setup_logging

logger = setup_logging()


class SQLSecurityViolation(Exception):
    """Raised when an SQL query violates security guardrails."""


class SQLSecurityGuardrail:
    """Hardened Abstract Syntax Tree (AST) validator for AI-generated SQL queries."""

    ALLOWED_TABLES = {
        "dim_player",
        "dim_match",
        "dim_venue",
        "dim_team",
        "player_aliases",
        "player_identifiers",
        "fact_delivery",
        "fact_innings",
        "fact_match_result",
        "fact_wicket_detail",
        "fact_player_match",
        "mart_player_batting_career",
        "mart_player_bowling_career",
        "mart_player_matchup_matrix",
    }

    FORBIDDEN_EXPRESSIONS = (
        exp.Drop,
        exp.Delete,
        exp.Insert,
        exp.Update,
        exp.Alter,
        exp.Create,
        exp.Command,
        exp.Pragma,
        exp.Transaction,
        exp.Commit,
        exp.Rollback,
    )

    FORBIDDEN_FUNCTIONS = {
        "read_csv",
        "read_csv_auto",
        "read_parquet",
        "read_json",
        "read_json_auto",
        "glob",
        "write_csv",
        "write_parquet",
        "duckdb_settings",
        "pragma_version",
        "getenv",
        "system",
        "httpfs",
    }

    @classmethod
    def validate_and_sanitize(cls, sql_text: str, default_limit: int = 500) -> str:
        """Validate an SQL query for read-only safety, authorized tables, and inject row limits.

        Returns sanitized and formatted SQL if valid, or raises SQLSecurityViolation.
        """
        cleaned_sql = sql_text.strip().rstrip(";")
        if not cleaned_sql:
            raise SQLSecurityViolation("Empty SQL query is not permitted.")

        try:
            parsed = sqlglot.parse_one(cleaned_sql, read="duckdb")
        except Exception as e:
            raise SQLSecurityViolation(f"SQL Syntax Parsing Error: {e}") from e

        # 1. Statement Type Check: Must be SELECT or UNION
        if not isinstance(parsed, (exp.Select, exp.Union)):
            raise SQLSecurityViolation(
                f"Security Violation: Only SELECT / UNION queries are allowed (got: {type(parsed).__name__})."
            )

        # 2. Recursive Search for Destructive Expressions across CTEs and Subqueries
        for forbidden_type in cls.FORBIDDEN_EXPRESSIONS:
            if parsed.find(forbidden_type):
                raise SQLSecurityViolation(
                    f"Security Violation: Forbidden statement '{forbidden_type.__name__}' detected."
                )

        # 3. Block Forbidden Ingestion/System Functions
        for func in parsed.find_all(exp.Anonymous):
            func_name = func.this.lower() if isinstance(func.this, str) else ""
            if func_name in cls.FORBIDDEN_FUNCTIONS:
                raise SQLSecurityViolation(
                    f"Security Violation: Function '{func_name}' is not permitted."
                )

        # 4. Extract CTE Alias Names so they aren't flagged as unauthorized external tables
        cte_aliases: set[str] = set()
        with_exp = parsed.find(exp.With)
        if with_exp:
            for cte in with_exp.expressions:
                if isinstance(cte, exp.CTE) and cte.alias:
                    cte_aliases.add(cte.alias.lower())

        # 5. Validate Table References
        for tbl in parsed.find_all(exp.Table):
            tbl_name = tbl.name.lower() if tbl.name else ""
            db_schema = tbl.db.lower() if tbl.db else ""

            # Bypass CTE aliases
            if tbl_name in cte_aliases:
                continue

            # Schema must either be empty or 'gold'
            if db_schema and db_schema not in ("gold", "main"):
                raise SQLSecurityViolation(
                    f"Security Violation: Schema '{db_schema}' is unauthorized. Only 'gold' is permitted."
                )

            if tbl_name not in cls.ALLOWED_TABLES:
                raise SQLSecurityViolation(
                    f"Security Violation: Table '{tbl_name}' is not in the authorized Gold table catalog."
                )

        # 6. Ensure row limit is present to prevent massive out-of-memory queries
        if not parsed.find(exp.Limit):
            parsed = parsed.limit(default_limit)

        return parsed.sql(dialect="duckdb")
