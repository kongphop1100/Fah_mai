# Department workflow (`fahmai.agents.departments`)

An alternative team shape for the FahMai agent: an **orchestrator** routes each subtask to the
**department** that owns the relevant tables, instead of one generic `sql` specialist that carries the
whole 32-table schema. Each department runs its SQL agent on a **narrow schema slice + domain gotchas**,
which raises text-to-SQL accuracy (bitemporal as-of, anti-shortcut traps) and lets a **faster/MoE model**
do the per-department work while a strong model handles routing and the final answer.

Selected by env — the legacy flat graph stays the default and the A/B baseline:

```bash
FAHMAI_ORCHESTRATOR=dept     # "flat" (default) = legacy planner → sql/doc
FAHMAI_DEPT_MODEL=<model>    # department SQL/doc agents (defaults to FAHMAI_MODEL)
FAHMAI_MODEL=<model>         # orchestrator + synth (synth does the Bucket-A arithmetic)
```

## Architecture

Three tiers wrapped by deterministic guardrail bookends. The orchestrator and synthesizer are the only
"wide-context" roles (they see the whole question / all findings); the departments are deliberately
"narrow-context" workers.

```
                         ┌──────────────────────────────────────────────┐
   question ─▶ input_guard (regex, no LLM)                               │
                         │                                               │
                         ▼                                               │
                ┌──────────────────┐   routing + dependency graph        │  strong model
                │  ORCHESTRATOR    │   → [{id, dept, subquestion, needs}] │  (FAHMAI_MODEL)
                └──────────────────┘                                     │
                         │ Send() per ready subtask (level-order)        │
          ┌──────────────┼───────────────┬───────────────┐              │
          ▼              ▼               ▼               ▼               │  fast / MoE model
     ┌─────────┐  ┌──────────┐    ┌────────────┐   ┌──────────┐         │  (FAHMAI_DEPT_MODEL)
     │ sales   │  │ finance  │ …  │ governance │   │  docs    │  ← department ReAct agents,
     │ (narrow │  │ (narrow  │    │ (narrow    │   │ (narrow  │    each owns a table-group +
     │  schema)│  │  schema) │    │  schema)   │   │  tools)  │    knows its domain gotchas
     └─────────┘  └──────────┘    └────────────┘   └──────────┘         │
          └──────────────┴───────────────┴───────────────┘              │
                         │ findings appended to the shared scratchpad    │
                         ▼                                               │
                ┌──────────────────┐                                     │  strong model
                │  SYNTHESIZER     │  merge findings → grounded Thai answer  (FAHMAI_MODEL)
                └──────────────────┘  (does the cross-finding arithmetic)│
                         │                                               │
                         ▼                                               │
   answer  ◀─ guard (deterministic scrub + ≤1 repair) ───────────────────┘
```

| tier | role | why it exists |
|------|------|---------------|
| **orchestrator** (`n_orchestrate`) | decompose the question, pick the owning **department** per part, mark cross-dept `needs` | one place holds the *whole* question and the routing map; departments never need to know about each other |
| **departments** (`departments.run`) | answer one subtask via a ReAct loop over **only their tables** | a small, domain-specific context is what makes text-to-SQL accurate and lets a cheap model do it |
| **synthesizer** (`n_synth`) | merge all findings into the final answer; compute ratios/% across findings | arithmetic lives in *one* strong-model step (SQL computes per-finding scalars; synth combines) — the Bucket-A fix |
| **guardrails** (`input_guard`/`guard`) | tag injection signals in, validate/scrub the answer out — pure regex/string | safety is deterministic and *outside* the model context, so a prompt can't talk its way past it |

**Design rationale.** The flat graph gave one `sql` agent all 32 tables; the more tables in context, the
more wrong-table / wrong-join errors and the more the model must "remember" each table's quirks. Splitting
ownership turns a 32-table problem into six ~6-table problems, each carrying *only* the rules that apply to
it. Routing and inter-step dependencies are lifted up to the orchestrator (which has the full picture),
while numeric reasoning is pushed down into SQL and concentrated in synth — so each role does the one thing
its context is sized for. Half the graph (`coverage`/`synth`/`guard`/guardrails/retry) is shared verbatim
with the flat workflow, so the change is localized to how subtasks are *produced and routed*.

## Graph

```
question
  → input_guard  regex-tag injection signals (no LLM)                 ← shared with flat
  → orchestrate  decompose → assign each subtask a DEPARTMENT (+ needs[] for cross-dept deps)
  → waves ⇄ worker_dept   level-order scheduler:
        • dispatch every subtask whose needs[] are satisfied → run IN PARALLEL on its department
        • a dependent subtask receives its prerequisites' findings as "CONTEXT FROM TEAM"
        • loop until no subtask is left, then → coverage
  → coverage     hard-failed (504/empty)? → replan; else → synth      ← shared with flat
  → synth        merge findings → grounded Thai answer                ← shared with flat
  → guard        deterministic output safety                         ← shared with flat
```

`coverage`, `synth`, `guard`, the guardrails and the retry/replan logic are **reused unchanged** from
the flat graph (`graph.py`) — only `plan`/`worker`/`dispatch` are replaced by
`orchestrate`/`worker_dept`/`waves`.

### Shared scratchpad (how cross-dept dependencies work)

The `findings` state channel (`Annotated[list, operator.add]`) **is** the shared scratchpad / blackboard:
every department appends its result there. A subtask the orchestrator marked `needs:[id]` is held back by
`route_waves` until its prerequisites have findings, then `_deps_context()` pulls those findings out of the
scratchpad and prepends them to the subquestion. Most questions are **one wave** (all parallel — same
wall-clock as flat); a genuine cross-department dependency adds **one wave** for that question only.

Same-domain "find X, then compute on X" is **not** split across departments — the orchestrator keeps it in
one subtask and the department's ReAct agent iterates query-by-query. That is the cheap fix for the
dependency-loses-context failure mode (Bucket B in `XHARD_IMPROVEMENT_PLAN.md`), with zero added latency.

## Departments

Shared read-only dims (`dim_product, dim_customer, dim_branch, dim_date`) and the governance/as-of +
leadership-canon + injection-defense fragment are injected into **every** SQL department, so any line
department can do an as-of policy/ladder join inline without hopping to another department.

| dept key     | owns (table-group)                                                                 | domain gotchas it knows |
|--------------|------------------------------------------------------------------------------------|-------------------------|
| `sales`      | v_sales, v_sales_items, v_promo, dim_promo_campaign/mechanic, pos_logs              | phantom promo dedup by txn_id; POS v1→v2 cutover 2025-04-01; discount cost = basket−net |
| `finance`    | v_vendor_payments, v_bank_txn, v_payroll, dim_vendor, dim_bank_account, dim_vendor_contract_version | vendors not in dim (V-007/013/014/018); V-013 duplicate invoice = two regimes; bitemporal contracts |
| `aftersales` | v_returns, v_refunds, v_warranty, v_loyalty, ocr_warranty_form, dim_product_recall_history, dim_care_plus_sku_tier | refund signing-authority as-of; NT-LT-001 pre/post-recall clusters; warranty routing as-of |
| `operations` | v_inventory, v_inventory_snapshot, v_cs, v_shipping                                 | monthly inventory snapshots; E2 shipping-delay window; CS channels/interaction types |
| `governance` | dim_employee, dim_department, dim_position_level, dim_policy_version, dim_signing_authority_ladder | leadership canon (CEO/Board, no CFO) for INJ defense; position_level rank; ladder ceilings as-of |
| `docs`       | doc_corpus (via query/count/get_document — narrative only)                          | topic tags E2/E3/DQ3-*/DQ4/CEO/SIGN; count==0 = absent; no secret echo |
| `general`    | full schema (= the flat `sql` agent)                                               | fallback when the orchestrator emits an unknown/missing dept — never worse than flat |

The taxonomy + gotchas live in `DEPARTMENTS` in `__init__.py`; each card is composed by
`fahmai/tools/schema_card.py::dept_card(owned, gotchas)` (which slices `MSCHEMA` to the owned + shared
tables and prepends the core/governance rule fragments).

## Context engineering

The whole design is an exercise in giving each LLM call the **smallest context that is sufficient** for its
job. What goes into a department agent's window, and why:

**1. Schema partitioning — show only the relevant tables.**
`dept_card()` calls `slice_mschema(owned + SHARED_DIMS)` so a department sees its ~6 tables plus the four
shared dims, not all 32. Fewer distractor tables → fewer wrong joins and less "which table holds this?"
guessing. The slice uses the auto-generated **M-Schema** (per-table types / PK / FK / example values),
which models parse more reliably than prose DDL.

**2. Layered prompt composition — one source per layer.**
A department system prompt is assembled, never hand-duplicated:
```
DEPT_BASE_SYS                      role + behaviour (iterate, JOIN dims for names, push arithmetic to SQL)
  + _DEPT_CORE                     universal hygiene (fiscal=พ.ศ., business_event_date, _thb, null FKs)
  + _GOVERNANCE_FRAGMENT           as-of rule + leadership canon + injection defense   ← every dept
  + slice_mschema(owned + shared)  the narrow table view
  + DEPARTMENT NOTES (gotchas)     the 2–3 quirks that actually trip up this domain
  + ENUM_CARD                      exact categorical values + hand-curated rankings
```
Edit a layer in exactly one place (`dept_base.md`, `schema_card.py`, or the `DEPARTMENTS` registry) and
every department inherits it.

**3. Cross-cutting knowledge is duplicated *on purpose*.**
The governance/as-of/leadership fragment is injected into every line department rather than living only in
the `governance` desk. The trade is a few hundred shared tokens per agent in exchange for **locality**: an
`aftersales` refund-ceiling question resolves the signing-authority ladder *inline* instead of paying a
cross-department hop (an extra wave + an extra model context). Locality beats deduplication here.

**4. Just-in-time dependency context — selective, not broadcast.**
The `findings` scratchpad accumulates every department's output, but an agent is **not** handed the whole
board. `_deps_context()` injects *only* a subtask's declared prerequisites (`needs:[id]`) as a short
"CONTEXT FROM TEAM" block telling it to use those exact values and not re-derive them. Independent subtasks
stay context-isolated, which is what lets them run in parallel safely.

**5. Reasoning is placed where its context lives.**
Per-finding numbers are computed **in SQL** (a CTE that ends in the scalar) — the tool result, not the
model's head, carries the precision. Only cross-finding combination (ratios, %, sums of separately-fetched
numbers) happens in `synth`, on the strong model. This is the structural fix for the arithmetic-drift
failure mode (Bucket A).

**6. Context size dictates the model tier.**
Because a department's window is small and domain-bounded, a fast/MoE `FAHMAI_DEPT_MODEL` handles it well;
the wide-context roles that must hold the whole question (orchestrator) or every finding (synth) keep the
strong `FAHMAI_MODEL`. Spend model capability where the context is hard, not uniformly.

**7. Safety signals are engineered out of the prose.**
Injection cues are extracted by regex in `input_guard` and passed to synth as compact, explicit constraints
(forced-strings to never emit, candidate values to never echo); the model isn't asked to *infer* an attack
from free text. Likewise the doc tools treat an empty result as a definitive **absent** signal, so an agent
never pads its context with hallucinated filler to "find something".

## Files

```
fahmai/agents/departments/__init__.py   DEPARTMENTS registry · build() (cached) · run(dept, subq)
fahmai/agents/prompts/orchestrator.md   decomposition + department directory + {dept, needs[]} schema
fahmai/agents/prompts/dept_base.md       SQL-analyst body WITHOUT a schema card (the slice is appended)
fahmai/tools/schema_card.py              slice_mschema() · dept_card() · _GOVERNANCE_FRAGMENT · SHARED_DIMS
fahmai/agents/graph.py                   n_orchestrate · route_waves · n_worker_dept · build_dept_team()
```

## A/B against the flat baseline

```bash
# baseline (default)
python main.py submit
# department workflow (e.g. strong synth/orchestrator, fast departments)
FAHMAI_ORCHESTRATOR=dept FAHMAI_MODEL=<strong> FAHMAI_DEPT_MODEL=<fast> python main.py submit
# score both
python scripts/build_crosscheck.py
```

Keep the default `flat` until the department graph beats it on the 100-question benchmark.

> Note: in `dept` mode the `coverage → replan` loop is a **bounded no-op** (each subtask is dispatched at
> most once); transient-failure resilience comes from the specialist-level retry in
> `specialists/base.py::run_specialist_async`.
