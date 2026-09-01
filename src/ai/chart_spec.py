from typing import Any


class ChartSpecGenerator:
    """Automatically synthesizes Vega-Lite JSON visualization specifications for tabular query results."""

    @classmethod
    def generate_spec(
        cls,
        rows: list[dict[str, Any]],
        title: str = "Query Result Visualization",
    ) -> dict[str, Any] | None:
        """Inspect columns in the query output and build a best-fit Vega-Lite spec."""
        if not rows or len(rows) < 2:
            return None

        first_row = rows[0]
        keys = list(first_row.keys())

        # Categorize columns
        nominal_col = None
        quantitative_cols: list[str] = []

        for k in keys:
            val = first_row[k]
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                quantitative_cols.append(k)
            elif isinstance(val, str) and not nominal_col:
                nominal_col = k

        if not nominal_col or not quantitative_cols:
            return None

        primary_metric = quantitative_cols[0]

        # Build Bar Chart Spec
        return {
            "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
            "title": title,
            "data": {"values": rows[:20]},  # Limit visualization to top 20 rows
            "mark": {"type": "bar", "cornerRadiusEnd": 4},
            "encoding": {
                "x": {
                    "field": nominal_col,
                    "type": "nominal",
                    "sort": f"-{primary_metric}",
                    "axis": {"labelAngle": -35, "title": nominal_col.replace("_", " ").title()},
                },
                "y": {
                    "field": primary_metric,
                    "type": "quantitative",
                    "axis": {"title": primary_metric.replace("_", " ").title()},
                },
                "tooltip": [
                    {"field": k, "type": "quantitative" if k in quantitative_cols else "nominal"}
                    for k in keys[:5]
                ],
                "color": {"value": "#10B981"},
            },
        }
