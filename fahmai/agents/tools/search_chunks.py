# -*- coding: utf-8 -*-
"""search_chunks_tool - chunk-level hybrid RAG search with RRF fusion."""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.chunk_tool import search_chunks


@tool
def search_chunks_tool(query: str, source_type: str = "", date_from: str = "",
                       date_to: str = "", keyword: str = "", top_k: int = 0,
                       vector_k: int = 0, keyword_k: int = 0) -> str:
    """Hybrid chunk search over rag_chunks.

    Uses vector search over chunk embeddings, token keyword search over content_tokenized
    with PyThaiNLP query tokens, and RRF fusion. Pre-filter with source_type, date_from,
    date_to, or exact keyword when useful. Returns contextualized_content for final answers.
    """
    return search_chunks(
        query,
        top_k=top_k or 5,
        vector_k=vector_k or 50,
        keyword_k=keyword_k or 50,
        source_type=source_type or None,
        date_from=date_from or None,
        date_to=date_to or None,
        keyword=keyword or None,
    )
