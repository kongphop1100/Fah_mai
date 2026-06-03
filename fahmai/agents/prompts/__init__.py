# -*- coding: utf-8 -*-
"""Team prompts — single source of truth.

Edit the wording in the sibling .md files (planner.md / sql.md / synth.md / doc.md / verify.md);
this module just loads them and exposes the constants the rest of the code imports.

  sql.md  — keep the {PREFER} placeholder (filled by the env A/B toggle below); the schema card is
            appended here, and the body is whitespace-normalized so you can wrap lines freely.
  verify.md — currently retired (verification lives in graph.py's `coverage` gate); kept editable so
            it can be re-enabled as a critic node.
"""
from __future__ import annotations

import os
from pathlib import Path

from fahmai.tools.schema_card import SCHEMA_CARD

_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """Read prompts/<name> and return its text (trailing newlines trimmed)."""
    return (_DIR / name).read_text(encoding="utf-8").rstrip("\n")


PLANNER_SYS = load_prompt("planner.md")
SYNTH_SYS = load_prompt("synth.md")
DOC_SYS = load_prompt("doc.md")
VERIFY_SYS = load_prompt("verify.md")

# A/B toggle (must match build_mschema): RAW = query raw fact_* and do BE→CE + dedup yourself.
_PREFER = ("Use the raw fact_* tables; the schema card lists them. Apply the BE→CE year and dedup "
           "rules yourself (e.g. derive the calendar year from business_event_date; fact_sales is "
           "clean but dedup fact_promo_redemption by txn_id). "
           if os.getenv("FAHMAI_SCHEMA_RAW", "0").lower() in ("1", "true", "on")
           else "Prefer the curated v_* views. ")

SQL_SYS = " ".join(load_prompt("sql.md").split()).replace("{PREFER}", _PREFER) + "\n\n" + SCHEMA_CARD

__all__ = ["load_prompt", "PLANNER_SYS", "SQL_SYS", "DOC_SYS", "SYNTH_SYS", "VERIFY_SYS"]
