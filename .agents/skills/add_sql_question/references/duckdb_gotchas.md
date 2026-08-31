# DuckDB vs. PostgreSQL/Spark SQL — Dialect Gotcha Reference

> **Purpose**: Every KaizenCodes ground truth SQL query MUST be verified against this list before committing.
> Reference this file in `add_sql_question` and `batch_add_sql_questions` workflows.

---

## ⚠️ Integer Division

| Context | PostgreSQL / Spark | DuckDB |
|:---|:---|:---|
| `5 / 2` | `2` (integer) | `2.5` (float) |
| Force integer division | `5 / 2` | `5 // 2` |

**Fix**: If the question requires integer division, use `//` or cast explicitly: `CAST(5 AS INTEGER) / CAST(2 AS INTEGER)`.

---

## 📅 Date & Time Functions

| Operation | PostgreSQL | Spark SQL | DuckDB |
|:---|:---|:---|:---|
| Current date | `CURRENT_DATE` | `CURRENT_DATE` | `CURRENT_DATE` ✅ |
| Date arithmetic | `date + INTERVAL '1 day'` | `date_add(date, 1)` | `date + INTERVAL 1 DAY` |
| Truncate to month | `DATE_TRUNC('month', col)` | `DATE_TRUNC('MONTH', col)` | `DATE_TRUNC('month', col)` ✅ |
| Day of week (1=Mon) | `EXTRACT(ISODOW FROM col)` | `DAYOFWEEK(col)` | `ISODOW(col)` or `EXTRACT(ISODOW FROM col)` |
| String → Date | `TO_DATE(col, 'YYYY-MM-DD')` | `TO_DATE(col, 'yyyy-MM-dd')` | `STRPTIME(col, '%Y-%m-%d')::DATE` |
| Make a date | `MAKE_DATE(y, m, d)` | `MAKE_DATE(y, m, d)` | `MAKE_DATE(y, m, d)` ✅ |
| Diff in days | `col1 - col2` | `DATEDIFF(col1, col2)` | `DATEDIFF('day', col2, col1)` |

---

## 🔤 String Functions

| Operation | PostgreSQL | Spark SQL | DuckDB |
|:---|:---|:---|:---|
| Split string | `STRING_TO_ARRAY(col, ',')` | `SPLIT(col, ',')` | `STRING_SPLIT(col, ',')` |
| String aggregate | `STRING_AGG(col, ',')` | `COLLECT_LIST(col)` | `STRING_AGG(col, ',')` ✅ |
| Regex match | `col ~ 'pattern'` | `col RLIKE 'pattern'` | `REGEXP_MATCHES(col, 'pattern')` |
| Regex extract | `REGEXP_MATCH(col, '...')` | `REGEXP_EXTRACT(col, '...')` | `REGEXP_EXTRACT(col, '...')` |
| Position | `POSITION('x' IN col)` | `INSTR(col, 'x')` | `POSITION('x' IN col)` ✅ |

---

## 🪟 Window Functions & QUALIFY

| Operation | PostgreSQL | Spark SQL | DuckDB |
|:---|:---|:---|:---|
| Filter on window result | Subquery required | `QUALIFY` supported | `QUALIFY` supported ✅ |
| ROWS vs RANGE | Supported | Supported | Supported ✅ |
| `LEAD`/`LAG` | Supported | Supported | Supported ✅ |
| `PERCENT_RANK` | Supported | Supported | Supported ✅ |

**DuckDB Advantage**: Use `QUALIFY` to filter on window function results without a subquery:
```sql
SELECT *, RANK() OVER (PARTITION BY dept ORDER BY salary DESC) AS rnk
FROM employees
QUALIFY rnk <= 3;
```

---

## 🔢 Data Types

| Type | PostgreSQL | DuckDB |
|:---|:---|:---|
| Integer | `INTEGER`, `INT` | `INTEGER`, `INT32` |
| Big integer | `BIGINT` | `BIGINT`, `INT64` |
| Auto-increment | `SERIAL` | `SEQUENCE` or `INTEGER PRIMARY KEY` |
| JSON | `JSON`, `JSONB` | `JSON` (via `json_extract`) |
| Array | `ARRAY` | `LIST` (e.g., `INTEGER[]`) |
| Struct/Row | `ROW` | `STRUCT` |

---

## 🚫 Unsupported or Different in DuckDB

| Feature | PostgreSQL | DuckDB Status |
|:---|:---|:---|
| `ATTACH` remote DB | N/A | **BLOCKED** by KaizenCodes SQL sanitizer |
| `COPY TO/FROM` | Supported | **BLOCKED** |
| `CREATE EXTENSION` | Supported | Not applicable |
| `UNNEST` on array | `UNNEST(array_col)` | `UNNEST(array_col)` ✅ |
| `PIVOT` | Not native | `PIVOT` supported natively ✅ |
| `UNPIVOT` | Not native | `UNPIVOT` supported natively ✅ |
| `ASOF JOIN` | Not supported | Supported ✅ |
| `LATERAL JOIN` | Supported | Supported ✅ |

---

## ✅ DuckDB-Native Features to Leverage

These are DuckDB advantages you can build questions around:
- **`PIVOT` / `UNPIVOT`**: Native syntax, no CTE tricks needed.
- **`QUALIFY`**: Clean window function filtering.
- **`LIST_AGG`, `ARRAY_AGG`**: Collect values into arrays.
- **`STRUCT`**: Return complex nested objects.
- **`EXCLUDE` in SELECT**: `SELECT * EXCLUDE (col_to_drop)`.
- **`COLUMNS(*)`**: Pattern-based column selection.
- **`SAMPLE`**: `SELECT * FROM table USING SAMPLE 10%`.

---

## 📦 Serialization Safety (Always apply via `df_to_json_rows()`)

When returning DataFrame results to the frontend, NEVER use `df.values.tolist()`. Always use:
```python
from app.engine.serializer import df_to_json_rows

rows = df_to_json_rows(df)
```
This handles: `pd.Timestamp`, `np.datetime64`, `np.int64`, `np.floating`, `NaN`, `NaT`, `pd.Timedelta`, `bytes`.
