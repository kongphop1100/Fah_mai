# -*- coding: utf-8 -*-
"""Run the REAL team graph on the 13 doc-dependent questions and score vs ground_truth.

Verifies the production no-vector doc path (query_docs/count_docs/get_document) end-to-end through the
full LangGraph flow (planner → sql‖doc → synth → guard). Writes data/eval_docset_after.csv.

    uv run python scripts/run_doc_eval.py
"""
from __future__ import annotations

import asyncio
import csv

from fahmai.agents.config import CONCURRENCY, DATA
from fahmai.agents.data import QMAP, load_ground_truth
from fahmai.agents.graph import aanswer
from fahmai.utils import scoring

DOC_SET = [
    "L3-Q-REF-001", "L3-Q-REF-008", "L3-Q-REF-019", "L3-Q-REF-021", "L3-Q-REF-023",
    "L3-Q-HARD-001", "L3-Q-HARD-015", "L3-Q-HARD-017", "L3-Q-HARD-018", "L3-Q-HARD-019",
    "L3-Q-HARD-020", "L3-Q-XHARD-008", "L3-Q-XHARD-015", "L3-Q-INJ-009",
]
OUT = DATA / "eval_docset_after.csv"


async def _run(ids: list[str]) -> dict[str, str]:
    sem = asyncio.Semaphore(CONCURRENCY)
    answers: dict[str, str] = {}

    async def work(qid: str):
        async with sem:
            try:
                ans = await aanswer(QMAP[qid])
            except Exception as e:  # noqa: BLE001
                ans = f"(error: {str(e)[:160]})"
            answers[qid] = " ".join(str(ans).split())

    await asyncio.gather(*[work(q) for q in ids])
    return answers


def main() -> int:
    gt = load_ground_truth()
    ids = [q for q in DOC_SET if q in QMAP]
    print(f"running {len(ids)} doc questions through the real graph (concurrency={CONCURRENCY})...\n")
    answers = asyncio.run(_run(ids))

    rows, npass = [], 0
    for qid in ids:
        g = gt.get(qid, {})
        conf, ref, ag = str(g.get("confidence", "")), str(g.get("answer", "")), answers.get(qid, "")
        label, detail = scoring.score(conf, ref, ag)
        npass += label == "PASS"
        rows.append((qid, conf, label, detail, ref, ag))

    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "confidence", "score", "detail", "ground_truth", "agent_answer"])
        w.writerows(rows)

    for qid, conf, label, detail, ref, ag in rows:
        print(f"{qid:<16} {conf:<7} {label:<7} {detail}")
        print(f"   AG: {ag[:170]}\n")
    print(f"PASS {npass}/{len(rows)}  ->  {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
