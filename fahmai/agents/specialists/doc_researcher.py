# -*- coding: utf-8 -*-
"""Document researcher sub-agent: narrative retrieval over the doc corpus."""
from __future__ import annotations

from fahmai.agents.config import DOC_RECURSION
from fahmai.agents.prompts import DOC_SYS
from fahmai.agents.specialists.base import build_react
from fahmai.agents.tools import count_docs_tool, get_document_tool, query_docs_tool

KIND = "doc"
RECURSION = DOC_RECURSION   # cap ~tool calls (anti-loop)


def build():
    # metadata + keyword retrieval (no vector): query/count/get_document
    return build_react(DOC_SYS, [query_docs_tool, count_docs_tool, get_document_tool])
