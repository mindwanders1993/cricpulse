from typing import Any

import duckdb

from src.utils import setup_logging

logger = setup_logging()


class QualityGateFailure(Exception):
    """Raised when one or more data quality checks fail."""


def run_quality_gates(con: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """Execute automated Data Quality assertions against the DuckDB Star Schema."""
    checks = [
        (
            "dim_player_uniqueness",
            "SELECT COUNT(*) - COUNT(DISTINCT player_id) FROM gold.dim_player;",
            lambda res: res == 0,
            "Duplicate player_id detected in gold.dim_player",
        ),
        (
            "dim_match_uniqueness",
            "SELECT COUNT(*) - COUNT(DISTINCT match_id) FROM gold.dim_match;",
            lambda res: res == 0,
            "Duplicate match_id detected in gold.dim_match",
        ),
        (
            "delivery_grain_uniqueness",
            """
            SELECT COUNT(*) FROM (
                SELECT match_id, innings_number, over_number, delivery_number, COUNT(*) AS cnt
                FROM gold.fact_delivery
                GROUP BY 1, 2, 3, 4
                HAVING COUNT(*) > 1
            );
            """,
            lambda res: res == 0,
            "Duplicate deliveries detected violating atomic grain",
        ),
        (
            "referential_integrity_delivery_match",
            """
            SELECT COUNT(*) 
            FROM gold.fact_delivery fd
            LEFT JOIN gold.dim_match dm ON fd.match_id = dm.match_id
            WHERE dm.match_id IS NULL;
            """,
            lambda res: res == 0,
            "Orphan deliveries detected with non-existent match_id",
        ),
        (
            "non_negative_runs",
            """
            SELECT COUNT(*) 
            FROM gold.fact_delivery 
            WHERE runs_batter < 0 OR runs_extras < 0 OR total_runs < 0;
            """,
            lambda res: res == 0,
            "Negative runs detected in fact_delivery",
        ),
        (
            "valid_over_numbers",
            """
            SELECT COUNT(*) 
            FROM gold.fact_delivery 
            WHERE over_number < 1 OR over_number > 250;
            """,
            lambda res: res == 0,
            "Over numbers outside valid range [1, 250]",
        ),
        (
            "marts_populated",
            """
            SELECT 
                (SELECT COUNT(*) FROM gold.mart_player_batting_career) AS batting_count,
                (SELECT COUNT(*) FROM gold.mart_player_bowling_career) AS bowling_count;
            """,
            lambda res: res[0] > 0 and res[1] > 0,
            "Batting or bowling marts are empty",
        ),
    ]

    results: list[dict[str, Any]] = []
    failures: list[str] = []

    for name, sql, validator, error_msg in checks:
        try:
            raw_res = con.execute(sql).fetchone()
            val = raw_res[0] if raw_res and len(raw_res) == 1 else raw_res
            passed = bool(validator(val))

            results.append(
                {
                    "check": name,
                    "passed": passed,
                    "value": val,
                }
            )

            if not passed:
                logger.error("quality_gate_failed", check=name, value=val, message=error_msg)
                failures.append(f"[{name}] {error_msg} (got: {val})")
            else:
                logger.info("quality_gate_passed", check=name, value=val)

        except Exception as e:
            logger.error("quality_gate_error", check=name, error=str(e))
            failures.append(f"[{name}] SQL execution error: {e}")

    if failures:
        raise QualityGateFailure(
            f"Data Quality Gate Failed with {len(failures)} errors:\n" + "\n".join(failures)
        )

    return results
