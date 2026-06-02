# -*- coding: utf-8 -*-
"""LangChain @tool wrappers over the low-level fahmai.tools.* functions."""
from fahmai.agents.tools.search_chunks import search_chunks_tool
from fahmai.agents.tools.sql_query import sql_query_tool

ALL_TOOLS = [sql_query_tool, search_chunks_tool]

__all__ = [
    "sql_query_tool",
    "search_chunks_tool",
    "ALL_TOOLS",
]
