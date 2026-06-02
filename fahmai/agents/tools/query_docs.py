# -*- coding: utf-8 -*-
"""query_docs_tool / count_docs_tool — metadata + exact-keyword doc retrieval (NO vector).

The doc corpus has hand-tagged `topic` incident tags (E2/E3/DQ3-*/DQ4/L1/CEO/SIGN-*), so the
narrative questions are answered by filtering on channel/topic/date/keyword instead of semantic
ranking. An empty result / count==0 is the definitive ABSENT signal (no relevance threshold needed).
"""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.doc_tool import count_docs, query_docs


@tool
def query_docs_tool(channel: str = "", topic: str = "", date_from: str = "", date_to: str = "",
                    keyword: str = "", k: int = 5) -> str:
    """Search documents by metadata + exact keyword (NO vector). channel in
    (chat_oa, chat_works, email, memo, minutes, kb_policy, kb_product, store_info, report);
    topic = incident tag (E2, E3, DQ3-2025-04-05, DQ3-2025-09-10, DQ4, L1, L2, CEO, SIGN-L1);
    date_from/date_to = YYYY-MM-DD; keyword = exact term/id/SKU. Resolve the incident to a topic
    FIRST and filter by it. An EMPTY RESULT means the info is ABSENT / not in the dataset."""
    rows = query_docs(channel=channel or None, topic=topic or None, date_from=date_from or None,
                      date_to=date_to or None, keyword=keyword or None, k=k)
    if not rows:
        return "(no matching documents — treat as ABSENT / not in the dataset)"
    return " || ".join(f"[{r['doc_date']} {r['channel']} topic={r['topic']}] {r['doc_id']}: {r['snippet']}"
                       for r in rows)


@tool
def count_docs_tool(channel: str = "", topic: str = "", date_from: str = "", date_to: str = "",
                    keyword: str = "") -> str:
    """Count documents under metadata+keyword filters (NO vector). Use for 'how many threads/chats'
    questions, and to confirm absence (a count of 0 means it is not in the dataset)."""
    return str(count_docs(channel=channel or None, topic=topic or None, date_from=date_from or None,
                          date_to=date_to or None, keyword=keyword or None))
