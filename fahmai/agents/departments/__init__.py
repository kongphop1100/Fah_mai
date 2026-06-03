# -*- coding: utf-8 -*-
"""Department registry (ORCHESTRATOR=dept).

Each department owns a table-group and runs a ReAct SQL agent on a NARROW schema slice (its tables +
shared dims + the governance/as-of fragment) — smaller context + domain gotchas make text-to-SQL more
accurate and let a faster/MoE DEPT_MODEL handle it. "docs" reuses the narrative doc researcher; "general"
is a full-schema fallback for any subtask the orchestrator routes to an unknown department.

Built lazily (no LLM calls at import) and cached, mirroring fahmai.agents.specialists.
"""
from __future__ import annotations

from fahmai.agents.config import DEPT_MODEL, DOC_RECURSION, SQL_RECURSION
from fahmai.agents.prompts import DEPT_BASE_SYS, DOC_SYS, SQL_SYS
from fahmai.agents.specialists.base import build_react, run_specialist_async
from fahmai.agents.tools import (calculator_tool, count_docs_tool, get_document_tool,
                                 query_docs_tool, sql_query_tool)
from fahmai.tools.schema_card import dept_card

# dept key -> (owned tables, domain gotchas). fact_* names are listed too so the slice still works under
# FAHMAI_SCHEMA_RAW (the slicer silently skips any table absent from the active M-Schema).
DEPARTMENTS = {
    "sales": (
        ["v_sales", "v_sales_items", "v_promo", "dim_promo_campaign", "dim_promo_mechanic", "pos_logs",
         "fact_sales", "fact_sales_line_item", "fact_promo_redemption"],
        "v_promo has PHANTOM duplicate rows (same txn_id across `channel`) — count real redemptions with "
        "count(distinct txn_id). pos_logs is BKK-CTW only; v1->v2 cutover 2025-04-01 renamed discount_amt "
        "-> discount_total_thb and v2 added payment_terminal_id, loyalty_tier_at_purchase. Discount cost = "
        "basket_total_thb - net_total_thb.",
    ),
    "finance": (
        ["v_vendor_payments", "v_bank_txn", "v_payroll", "dim_vendor", "dim_bank_account",
         "dim_vendor_contract_version", "fact_vendor_payment", "fact_bank_transaction", "fact_payroll"],
        "Only 6 vendors are in dim_vendor; ids like V-007/V-013/V-014/V-018 appear in payments but NOT in "
        "dim_vendor — resolve them from dim_vendor_contract_version / docs. PayWise (V-013) has a duplicate "
        "invoice billed under two contract versions = two DISTINCT cash outflows (different regimes), not an "
        "over-payment. Reconcile on business_event_date, not posting_date.",
    ),
    "aftersales": (
        ["v_returns", "v_refunds", "v_warranty", "v_loyalty", "ocr_warranty_form",
         "dim_product_recall_history", "dim_care_plus_sku_tier", "fact_return", "fact_refund_paid",
         "fact_warranty_claim", "fact_loyalty_ledger"],
        "Resolve each refund's signing-authority ceiling from dim_signing_authority_ladder AS-OF that "
        "refund's business_event_date (pre/post the 2025-02-15 cutover differ). NT-LT-001 has a pre-recall "
        "'battery swelling concern' claim cluster that is SEPARATE from post-recall returns — don't merge "
        "them. Warranty routing (fahmai_cs vs novatech_service) is policy-driven and as-of.",
    ),
    "operations": (
        ["v_inventory", "v_inventory_snapshot", "v_cs", "v_shipping", "fact_inventory_movement",
         "fact_inventory_monthly_snapshot", "fact_cs_interaction", "fact_shipping"],
        "Inventory snapshots are monthly (keyed by as_of_date). E2 shipping-delay window = 2024-08-22..24. "
        "v_cs channels are in_person / line_oa; interaction_type ∈ chat_general/refund_request/warranty_claim.",
    ),
    "governance": (
        ["dim_employee", "dim_department", "dim_position_level", "dim_policy_version",
         "dim_signing_authority_ladder"],
        "position_level rank low->high: IC < Manager < Director < C-level (use CASE, never max()). The "
        "signing-authority ladder gives amount_ceiling per position_level/department/policy_version, valid "
        "AS-OF business_event_date. Report raw ladder values; do not attach invented L1/L2 tier labels.",
    ),
}

DOC_KIND = "docs"
_BUILT: dict = {}


def build() -> dict:
    """Build & cache every department agent. Returns {dept_key: agent}."""
    if not _BUILT:
        for key, (owned, gotchas) in DEPARTMENTS.items():
            sys = DEPT_BASE_SYS + "\n\n" + dept_card(owned, gotchas)
            # calculator_tool: exact arithmetic over values the SQL can't aggregate in one shot
            _BUILT[key] = build_react(sys, [sql_query_tool, calculator_tool], model=DEPT_MODEL)
        _BUILT[DOC_KIND] = build_react(DOC_SYS, [query_docs_tool, count_docs_tool, get_document_tool],
                                       model=DEPT_MODEL)
        # full-schema fallback for unknown / mis-routed departments (never worse than flat sql agent);
        # also the natural home for a cross-finding "compute" subtask (SQL + calculator)
        _BUILT["general"] = build_react(SQL_SYS, [sql_query_tool, calculator_tool], model=DEPT_MODEL)
    return _BUILT


async def run(dept: str, subq: str) -> str:
    """Route a sub-question to a department agent (unknown SQL dept -> 'general'; 'doc' -> 'docs')."""
    agents = build()
    key = "docs" if dept in ("docs", "doc") else (dept if dept in agents else "general")
    recursion = DOC_RECURSION if key == "docs" else SQL_RECURSION
    return await run_specialist_async(agents[key], subq, recursion)


__all__ = ["DEPARTMENTS", "DOC_KIND", "build", "run"]
