"""search_docs (hybrid: metadata filter + optional keyword + vector rank) and get_document.

search_docs: semantic retrieval over doc_corpus⋈doc_vec, pre-filtered by metadata
(channel/topic/date) and optionally by an exact keyword (ILIKE) — exactly the access
pattern the questions need. get_document: full text of one doc for phrase/amount extraction.
"""
from __future__ import annotations

from sqlalchemy import text

from fahmai.embed import embed_batch
from fahmai.tools import ENGINE

SNIPPET = 280
DOC_MAXCHARS = 12000


def _vec(query: str) -> str:
    return "[" + ",".join(f"{x:.5f}" for x in embed_batch([query])[0]) + "]"


def search_docs(query: str, channel: str | None = None, topic: str | None = None,
                date_from: str | None = None, date_to: str | None = None,
                keyword: str | None = None, k: int = 8) -> str:
    """Hybrid doc search. Filters: channel, topic (prefix match), date range, exact keyword (ILIKE)."""
    where, params = [], {"q": _vec(query), "k": int(k)}
    if channel:
        where.append("dc.channel = :channel"); params["channel"] = channel
    if topic:
        where.append("dc.topic ILIKE :topic"); params["topic"] = f"{topic}%"
    if date_from:
        where.append("dc.doc_date >= :df"); params["df"] = date_from
    if date_to:
        where.append("dc.doc_date <= :dt"); params["dt"] = date_to
    if keyword:
        where.append("dc.content ILIKE :kw"); params["kw"] = f"%{keyword}%"
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    sql = f"""
        select dc.doc_id, dc.channel, dc.doc_date, dc.topic,
               round((1 - (dv.embedding <=> cast(:q as halfvec)))::numeric, 3) sim,
               left(dc.content, {SNIPPET}) snippet
        from doc_corpus dc join doc_vec dv using (doc_id)
        {clause}
        order by dv.embedding <=> cast(:q as halfvec)
        limit :k
    """
    try:
        with ENGINE.connect() as c:
            rows = c.execute(text(sql), params).fetchall()
    except Exception as e:  # noqa: BLE001
        return f"SEARCH ERROR: {str(e).splitlines()[0]}"
    if not rows:
        return "(no matching documents)"
    out = []
    for r in rows:
        snip = " ".join((r.snippet or "").split())
        out.append(f"[{r.sim}] {r.doc_id} ({r.channel}, {r.doc_date}, topic={r.topic or '-'})\n    {snip}")
    return "\n".join(out)


def _filters(channel, topic, date_from, date_to, keyword):
    """Build a metadata + keyword WHERE clause (no vector). Returns (clause, params)."""
    where, p = [], {}
    if channel:   where.append("channel = :ch");     p["ch"] = channel
    if topic:     where.append("topic ILIKE :tp");   p["tp"] = f"{topic}%"
    if date_from: where.append("doc_date >= :df");   p["df"] = date_from
    if date_to:   where.append("doc_date <= :dt");   p["dt"] = date_to
    if keyword:   where.append("content ILIKE :kw"); p["kw"] = f"%{keyword}%"
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    return clause, p


def _kw_snippet(content, keyword, width=240):
    """A snippet centred on the first keyword hit (else the head). For narrative extraction."""
    content = content or ""
    if keyword:
        i = content.lower().find(keyword.lower())
        if i >= 0:
            a = max(0, i - width // 3)
            return " ".join(content[a:a + width].split())
    return " ".join(content[:width].split())


def query_docs(channel=None, topic=None, date_from=None, date_to=None, keyword=None,
               k: int = 5, snippet_around: bool = True) -> list[dict]:
    """Metadata + exact-keyword document search (NO vector). Filter by channel / topic (prefix) /
    date range / keyword (ILIKE), ordered by doc_date. An EMPTY result is the definitive ABSENT
    signal (the info is not in the corpus)."""
    clause, p = _filters(channel, topic, date_from, date_to, keyword)
    p["k"] = int(k)
    sql = f"SELECT doc_id, channel, doc_date, topic, content FROM doc_corpus {clause} ORDER BY doc_date LIMIT :k"
    with ENGINE.connect() as c:
        rows = c.execute(text(sql), p).fetchall()
    return [dict(doc_id=r.doc_id, channel=r.channel, doc_date=str(r.doc_date), topic=r.topic or "-",
                 snippet=_kw_snippet(r.content, keyword if snippet_around else None)) for r in rows]


def count_docs(channel=None, topic=None, date_from=None, date_to=None, keyword=None) -> int:
    """Count documents under the same metadata+keyword filters (NO vector). Use for 'how many
    threads/chats' questions and to confirm absence (count 0 = not in the dataset)."""
    clause, p = _filters(channel, topic, date_from, date_to, keyword)
    with ENGINE.connect() as c:
        return c.execute(text(f"SELECT count(*) n FROM doc_corpus {clause}"), p).fetchone().n


def get_document(doc_id: str) -> str:
    """Return full content + metadata for one doc_id (for phrase/amount extraction)."""
    with ENGINE.connect() as c:
        r = c.execute(text("""select doc_id, channel, doc_date, topic, participants, path, content
                              from doc_corpus where doc_id = :id"""), {"id": doc_id}).fetchone()
    if not r:
        return f"(no document with doc_id={doc_id})"
    content = r.content or ""
    if len(content) > DOC_MAXCHARS:
        content = content[:DOC_MAXCHARS] + "\n…(truncated)"
    meta = f"doc_id={r.doc_id} channel={r.channel} date={r.doc_date} topic={r.topic or '-'}"
    if r.participants:
        meta += f" participants={r.participants}"
    return f"{meta}\npath={r.path}\n---\n{content}"


if __name__ == "__main__":
    print("=== search FAQ (mini pc) ===")
    print(search_docs("จอใช้กับ Mini PC ดาวเหนือได้ไหม", channel="kb_product", k=3))
    print("\n=== search chat_works invoice (DQ3) ===")
    print(search_docs("invoice PayWise ออกเลขซ้ำ", channel="chat_works", date_from="2025-04-05",
                      date_to="2025-04-05", k=3))
    print("\n=== get_document MEMO-PM1 ===")
    print(get_document("MEMO-PM1-2025-02-15")[:600])
