# -*- coding: utf-8 -*-
"""Build a human-friendly CROSS-CHECK table for reviewing submission.csv.

Joins (by id, in submission.csv order) the agent's answers with the question, the rubric
ground-truth, and the verification source/method — one row per question — plus a heuristic
auto PASS/FAIL flag and blank columns for the human reviewer. The rubric `ground_truth` +
`source` are the authoritative basis for checking; verify against those.

Reads:  submission.csv, data/questions.csv, data/ground_truth.csv, data/question_methods.csv
Writes: crosscheck.csv (Excel/Sheets) and crosscheck.html (readable, color-coded)

    uv run python scripts/build_crosscheck.py
"""
from __future__ import annotations

import csv
import html
from pathlib import Path

from fahmai.utils import scoring

ROOT = Path(__file__).resolve().parents[1]

COLUMNS = [
    "id", "suite", "category", "question", "our_answer",
    "auto_score", "auto_detail", "ground_truth",
    "source", "method", "tables", "trap_note",
    "human_verdict", "human_note",
]


def _load(path: Path) -> dict[str, dict[str, str]]:
    """Read a csv keyed by id (all our inputs carry a BOM -> utf-8-sig)."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def _build_rows() -> list[dict[str, str]]:
    sub = _load(ROOT / "submission.csv")
    questions = _load(ROOT / "data" / "questions.csv")
    gt = _load(ROOT / "data" / "ground_truth.csv")
    methods = _load(ROOT / "data" / "question_methods.csv")

    rows: list[dict[str, str]] = []
    for qid, srow in sub.items():  # submission.csv order is the canonical order
        g = gt.get(qid, {})
        m = methods.get(qid, {})
        our = srow.get("response", "")
        confidence, reference = g.get("confidence", ""), g.get("answer", "")
        label, detail = scoring.score(confidence, reference, our)
        rows.append({
            "id": qid,
            "suite": m.get("suite", "") or g.get("suite", ""),
            "category": m.get("category", ""),
            "question": questions.get(qid, {}).get("question", ""),
            "our_answer": our,
            "auto_score": label,
            "auto_detail": detail,
            "ground_truth": reference,
            "source": g.get("source", ""),
            "method": m.get("method", ""),
            "tables": m.get("tables", ""),
            "trap_note": m.get("trap_note", ""),
            "human_verdict": "",
            "human_note": "",
        })
    return rows


def _write_csv(rows: list[dict[str, str]], out: Path) -> None:
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


# columns rendered with pre-wrap (long Thai prose) vs. compact
_WRAP = {"question", "our_answer", "ground_truth", "method", "trap_note", "human_note"}
_SCORE_CLASS = {"PASS": "pass", "FAIL": "fail", "REVIEW": "review"}

_CSS = """
:root { --bd:#d0d7de; }
* { box-sizing: border-box; }
body { font-family: 'Sarabun','Noto Sans Thai',Tahoma,sans-serif; margin:0; padding:16px;
       color:#1f2328; background:#fff; font-size:14px; }
h1 { font-size:20px; margin:0 0 4px; }
.sub { color:#57606a; margin:0 0 14px; }
.summary { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:14px; }
.pill { padding:4px 10px; border-radius:999px; font-weight:600; border:1px solid var(--bd); }
.pill.pass { background:#dafbe1; } .pill.fail { background:#ffe3e3; } .pill.review { background:#fff4ce; }
.pill.total { background:#eef1f4; }
table { border-collapse:collapse; width:100%; table-layout:fixed; }
th,td { border:1px solid var(--bd); padding:7px 9px; vertical-align:top; text-align:left;
        word-break:break-word; }
th { position:sticky; top:0; background:#f6f8fa; z-index:1; font-size:12px; }
td.wrap { white-space:pre-wrap; }
td.compact, th.compact { font-size:12px; color:#424a53; }
tr.pass td.score { background:#dafbe1; font-weight:700; }
tr.fail td.score { background:#ffe3e3; font-weight:700; }
tr.review td.score { background:#fff4ce; font-weight:700; }
tr:nth-child(even) { background:#fbfcfd; }
.idcell { font-family:ui-monospace,Consolas,monospace; font-size:12px; white-space:nowrap; }
td.human { background:#fffdf5; min-width:90px; }
"""

# (header label, css width %, is-wrap, extra class)
_HEAD = [
    ("id", 6, False, "compact"),
    ("suite", 5, False, "compact"),
    ("category", 8, False, "compact"),
    ("คำถาม", 17, True, ""),
    ("คำตอบของเรา", 20, True, ""),
    ("auto", 5, False, "score"),
    ("detail", 6, False, "compact"),
    ("เฉลยย่อ (ground_truth)", 20, True, ""),
    ("source", 9, False, "compact"),
    ("method", 12, True, "compact"),
    ("tables", 7, False, "compact"),
    ("trap_note", 10, True, "compact"),
    ("✔ ตรวจแล้ว", 6, False, "human"),
    ("หมายเหตุคนตรวจ", 9, True, "human"),
]
# map header order -> data keys (same order as COLUMNS)
_KEYS = ["id", "suite", "category", "question", "our_answer", "auto_score", "auto_detail",
         "ground_truth", "source", "method", "tables", "trap_note",
         "human_verdict", "human_note"]


def _write_html(rows: list[dict[str, str]], out: Path) -> None:
    n = len(rows)
    npass = sum(r["auto_score"] == "PASS" for r in rows)
    nfail = sum(r["auto_score"] == "FAIL" for r in rows)
    nrev = sum(r["auto_score"] == "REVIEW" for r in rows)
    suites: dict[str, int] = {}
    for r in rows:
        suites[r["suite"]] = suites.get(r["suite"], 0) + 1

    parts: list[str] = []
    parts.append("<!DOCTYPE html><html lang='th'><head><meta charset='utf-8'>")
    parts.append("<meta name='viewport' content='width=device-width, initial-scale=1'>")
    parts.append("<title>FahMai — Cross-check submission.csv</title>")
    parts.append(f"<style>{_CSS}</style></head><body>")
    parts.append("<h1>ตาราง Cross-check คำตอบ submission.csv</h1>")
    parts.append("<p class='sub'>auto_score เป็นเพียงไกด์อัตโนมัติ (heuristic) — "
                 "คำตัดสินจริงให้กรอกที่คอลัมน์ “✔ ตรวจแล้ว”</p>")

    parts.append("<div class='summary'>")
    parts.append(f"<span class='pill total'>ทั้งหมด {n}</span>")
    parts.append(f"<span class='pill pass'>PASS {npass}</span>")
    parts.append(f"<span class='pill fail'>FAIL {nfail}</span>")
    parts.append(f"<span class='pill review'>REVIEW {nrev}</span>")
    for s, c in suites.items():
        parts.append(f"<span class='pill'>{html.escape(s)}: {c}</span>")
    parts.append("</div>")

    # colgroup for stable widths
    parts.append("<table><colgroup>")
    for _, w, _, _ in _HEAD:
        parts.append(f"<col style='width:{w}%'>")
    parts.append("</colgroup><thead><tr>")
    for label, _, _, cls in _HEAD:
        c = f" class='{cls}'" if cls in ("compact", "human") else ""
        parts.append(f"<th{c}>{html.escape(label)}</th>")
    parts.append("</tr></thead><tbody>")

    for r in rows:
        rcls = _SCORE_CLASS.get(r["auto_score"], "")
        parts.append(f"<tr class='{rcls}'>")
        for (_, _, is_wrap, cls), key in zip(_HEAD, _KEYS):
            val = html.escape(r.get(key, "") or "")
            classes = []
            if is_wrap:
                classes.append("wrap")
            if cls:
                classes.append(cls)
            if key == "id":
                classes.append("idcell")
            cattr = f" class='{' '.join(classes)}'" if classes else ""
            parts.append(f"<td{cattr}>{val}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table></body></html>")

    out.write_text("".join(parts), encoding="utf-8")


def main() -> int:
    rows = _build_rows()
    _write_csv(rows, ROOT / "crosscheck.csv")
    _write_html(rows, ROOT / "crosscheck.html")

    npass = sum(r["auto_score"] == "PASS" for r in rows)
    nfail = sum(r["auto_score"] == "FAIL" for r in rows)
    nrev = sum(r["auto_score"] == "REVIEW" for r in rows)
    print(f"wrote crosscheck.csv + crosscheck.html | {len(rows)} rows")
    print(f"auto_score: PASS={npass}  FAIL={nfail}  REVIEW={nrev}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
