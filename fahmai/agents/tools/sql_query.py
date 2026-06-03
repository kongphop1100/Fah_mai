# -*- coding: utf-8 -*-
"""sql_query_tool — one read-only SELECT/WITH over the FahMai warehouse."""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.sql_tool import sql_query


@tool
def sql_query_tool(sql: str) -> str:
    """Execute ONE read-only SQL query over the FahMai Postgres warehouse and return the rows as a markdown table.

    Use this to fetch any value, count, aggregate, id, amount, or date from the warehouse. Send a
    single statement and work iteratively: run one focused query, read the result, then run the next.

    Args:
        sql: One read-only PostgreSQL SELECT or 'WITH … SELECT' statement. Plain SQL text only — no
            ```sql code fences, no trailing semicolon, no multiple statements. Prefer the curated
            v_* views (e.g. v_sales) over the raw fact_* tables.

    Returns:
        A markdown table of up to 100 rows (each cell truncated to 300 chars) — aggregate or add a
        LIMIT instead of dumping rows. '(0 rows)' means the query ran fine but matched nothing.
        'SQL ERROR: <message>' means it failed (syntax / unknown column / write attempt / 30s
        timeout): read <message>, fix the SQL, and try again. Writes and DDL
        (INSERT/UPDATE/DELETE/DROP/…) are rejected — the transaction is READ ONLY.

    Examples:
        "SELECT msrp_thb FROM dim_product WHERE sku_id = 'NT-LT-001'"
        "SELECT count(*) FROM dim_vendor"
        "SELECT round(sum(net_total_thb)) FROM v_sales WHERE fiscal_year_ce = 2025"
    """
    return sql_query(sql)
