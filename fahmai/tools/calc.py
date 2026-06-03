# -*- coding: utf-8 -*-
"""Safe arithmetic evaluator — exact numeric compute for the agents (no eval()).

Whitelists numeric literals, the usual binary/unary operators, and a few aggregate functions
(round/abs/min/max/sum). Anything else (names, attribute access, calls to other functions) is rejected,
so an LLM can pass an arithmetic string and get an exact result without code-execution risk.
"""
from __future__ import annotations

import ast
import operator

_BIN = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS = {"round": round, "abs": abs, "min": min, "max": max, "sum": sum}


def _ev(node):
    if isinstance(node, ast.Expression):
        return _ev(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_ev(node.left), _ev(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
        return _UNARY[type(node.op)](_ev(node.operand))
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_ev(e) for e in node.elts]
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCS and not node.keywords):
        return _FUNCS[node.func.id](*[_ev(a) for a in node.args])
    raise ValueError("unsupported expression (numbers + - * / // % ** round abs min max sum only)")


def calc(expr: str) -> str:
    """Evaluate one arithmetic expression and return the result as a string (or 'CALC ERROR: ...')."""
    try:
        result = _ev(ast.parse(expr.strip(), mode="eval"))
    except Exception as e:  # noqa: BLE001
        return f"CALC ERROR: {str(e)[:120]}"
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    if isinstance(result, (int, float)):
        return f"{result:,}"          # thousands separators for readability (e.g. 55,500)
    return str(result)
