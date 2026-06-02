# -*- coding: utf-8 -*-
"""LangChain @tool wrappers over the low-level fahmai.tools.* functions."""
from fahmai.agents.tools.get_document import get_document_tool
from fahmai.agents.tools.query_docs import count_docs_tool, query_docs_tool
from fahmai.agents.tools.search_docs import search_docs_tool
from fahmai.agents.tools.sql_query import sql_query_tool

# doc retrieval is now metadata+keyword (query/count); search_docs_tool (vector) kept for back-compat
ALL_TOOLS = [sql_query_tool, query_docs_tool, count_docs_tool, get_document_tool]

__all__ = ["sql_query_tool", "query_docs_tool", "count_docs_tool", "search_docs_tool",
           "get_document_tool", "ALL_TOOLS"]
