# -*- coding: utf-8 -*-
"""calculator_tool — exact arithmetic so the agent never computes a number in its head."""
from __future__ import annotations

from langchain_core.tools import tool

from fahmai.tools.calc import calc


@tool
def calculator_tool(expression: str) -> str:
    """Evaluate an arithmetic expression EXACTLY. Use this for every sum / difference / product /
    ratio / percentage instead of computing it in your head — LLM mental math drifts.

    Args:
        expression: One arithmetic expression over numeric literals. Supports + - * / // % ** ,
            parentheses, and round/abs/min/max/sum. No variables or other functions.

    Returns:
        The result as a string with thousands separators (e.g. '55,500'), or 'CALC ERROR: <msg>'.

    Examples:
        "5500 + 6000 + 6500 + 7000 + 7250 + 7500 + 7750 + 8000"   -> 55,500
        "round(143301515 / 7542185, 1)"                            -> 19.0
        "sum([2500, 3000, 3500, 4000, 4250, 4500])"                -> 21,750
    """
    return calc(expression)
