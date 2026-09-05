import re
from datetime import date, datetime
from typing import Any

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
_DENOMINATOR_HINTS = ("balls", "matches", "innings", "count", "_id")
_MAX_CHARTS = 3
_MAX_BAR_ROWS = 20
_MAX_LINE_ROWS = 100
_ACCENT = "#10B981"


class ChartSpecGenerator:
    """Synthesizes one or more Vega-Lite JSON visualization specs for tabular query results."""

    @classmethod
    def _is_temporal_like(cls, value: Any) -> bool:
        """Detect a year, date, or datetime value so time series render as line charts."""
        if isinstance(value, (date, datetime)):
            return True
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return 1900 <= value <= 2100
        if isinstance(value, str):
            return bool(_YEAR_RE.match(value) or _ISO_DATE_RE.match(value))
        return False

    @classmethod
    def _x_encoding_type(cls, value: Any) -> str:
        """Vega-Lite encoding type for a detected temporal column."""
        if isinstance(value, (date, datetime)):
            return "temporal"
        if isinstance(value, str) and _ISO_DATE_RE.match(value):
            return "temporal"
        return "ordinal"

    @classmethod
    def generate_spec(
        cls,
        rows: list[dict[str, Any]],
        subtitle: str | None = None,
    ) -> list[dict[str, Any]]:
        """Inspect columns in the query output and build one best-fit Vega-Lite spec per metric."""
        if not rows or len(rows) < 2:
            return []

        first_row = rows[0]
        keys = list(first_row.keys())

        nominal_col: str | None = None
        temporal_col: str | None = None
        temporal_type = "ordinal"
        quantitative_cols: list[str] = []

        for k in keys:
            val = first_row[k]
            if temporal_col is None and cls._is_temporal_like(val):
                temporal_col = k
                temporal_type = cls._x_encoding_type(val)
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                quantitative_cols.append(k)
            elif isinstance(val, str) and nominal_col is None:
                nominal_col = k

        x_field = temporal_col or nominal_col
        if not x_field or not quantitative_cols:
            return []

        # Prefer metrics over their denominators (e.g. strike_rate over balls_faced),
        # but never end up with zero chartable columns.
        primary_metrics = [
            c for c in quantitative_cols if not any(h in c.lower() for h in _DENOMINATOR_HINTS)
        ] or quantitative_cols
        primary_metrics = primary_metrics[:_MAX_CHARTS]

        is_time_series = temporal_col is not None
        x_title = x_field.replace("_", " ").title()
        chart_data = rows[:_MAX_LINE_ROWS] if is_time_series else rows[:_MAX_BAR_ROWS]

        specs: list[dict[str, Any]] = []
        for metric in primary_metrics:
            metric_title = metric.replace("_", " ").title()
            title: dict[str, str] | str = (
                {"text": f"{metric_title} by {x_title}", "subtitle": subtitle}
                if subtitle
                else f"{metric_title} by {x_title}"
            )

            if is_time_series:
                mark: dict[str, Any] = {"type": "line", "point": True}
                x_encoding = {
                    "field": x_field,
                    "type": temporal_type,
                    "axis": {"title": x_title},
                }
            else:
                mark = {"type": "bar", "cornerRadiusEnd": 4}
                x_encoding = {
                    "field": x_field,
                    "type": "nominal",
                    "sort": f"-{metric}",
                    "axis": {"labelAngle": -35, "title": x_title},
                }

            tooltip_fields = [x_field, metric, *[c for c in quantitative_cols if c != metric][:3]]

            specs.append(
                {
                    "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
                    "title": title,
                    "description": f"{metric_title} by {x_title}",
                    "data": {"values": chart_data},
                    "mark": mark,
                    "encoding": {
                        "x": x_encoding,
                        "y": {
                            "field": metric,
                            "type": "quantitative",
                            "axis": {"title": metric_title},
                        },
                        "tooltip": [
                            {
                                "field": f,
                                "type": "quantitative" if f in quantitative_cols else "nominal",
                            }
                            for f in tooltip_fields
                        ],
                        "color": {"value": _ACCENT},
                    },
                }
            )

        return specs
