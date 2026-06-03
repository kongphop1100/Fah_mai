"""Chunk-level hybrid RAG retrieval over rag_chunks.

The chunk table is expected to keep the user's fixed chunk contract. Retrieval uses two
independent branches over that single table: dense vector search over `embedding`, and
token keyword search over `content_tokenized`, then fuses ranks with RRF.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from fahmai.embed import embed_batch
from fahmai.tools import ENGINE

try:  # PyThaiNLP is the intended tokenizer; fallback keeps imports usable before deps are synced.
    from pythainlp.tokenize import word_tokenize
except Exception:  # noqa: BLE001
    word_tokenize = None


RAG_CHUNKS_TABLE = os.getenv("FAHMAI_RAG_CHUNKS_TABLE", "rag_chunks")
RRF_K = int(os.getenv("FAHMAI_RRF_K", "60"))
CHUNK_CONTEXT_CHARS = int(os.getenv("FAHMAI_CHUNK_CONTEXT_CHARS", "2200"))
PYTHAINLP_ENGINE = os.getenv("FAHMAI_PYTHAINLP_ENGINE", "newmm")
CHUNK_EMBED_MODEL = os.getenv("FAHMAI_CHUNK_EMBED_MODEL") or os.getenv("EMBED_MODEL")
DEFAULT_TOP_K = int(os.getenv("FAHMAI_CHUNK_TOP_K", "6"))
DEFAULT_VECTOR_K = int(os.getenv("FAHMAI_CHUNK_VECTOR_K", "100"))
DEFAULT_KEYWORD_K = int(os.getenv("FAHMAI_CHUNK_KEYWORD_K", "17"))

_SPLIT_RE = re.compile(r"[\s,;:|/\\()[\]{}<>\"'`~!?]+")

# Keep raw chunk tokens unchanged, but ignore these high-frequency structural tokens at query time.
_STOP_TOKENS = {
    "agent",
    "chat",
    "chunk",
    "cs",
    "customer",
    "date",
    "document",
    "id",
    "line",
    "m",
    "message",
    "oa",
    "participants",
    "source",
    "text",
    "timestamp",
    "title",
    "type",
}


@dataclass
class ChunkHit:
    chunk_id: str
    document_id: str
    metadata: Any
    contextualized_content: str
    vector_rank: int | None = None
    keyword_rank: int | None = None
    rrf_score: float = 0.0


def _clean_token(token: str) -> str:
    return (token or "").strip().strip(".,;:!?()[]{}\"'`").strip()


def _expand_token(token: str) -> list[str]:
    token = _clean_token(token)
    if not token:
        return []
    if "," in token:
        parts = token.split(",")
        if all(part.isdigit() for part in parts if part):
            return [part for part in parts if part]
    return [token]


def tokenize_query(query: str) -> list[str]:
    """Tokenize a query with PyThaiNLP when available, then filter boilerplate tokens."""
    if word_tokenize is not None:
        raw = word_tokenize(query or "", engine=PYTHAINLP_ENGINE, keep_whitespace=False)
    else:
        raw = [p for p in _SPLIT_RE.split(query or "") if p]

    out: list[str] = []
    seen: set[str] = set()
    for token in raw:
        for t in _expand_token(str(token)):
            key = t.lower()
            if key in _STOP_TOKENS:
                continue
            if key not in seen:
                seen.add(key)
                out.append(t)
    return out


def _keyword_terms(tokens: list[str]) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        t = token.lower()
        if t and t not in seen:
            seen.add(t)
            terms.append(t)
    return terms


def _query_vec(query: str) -> str:
    kwargs = {"model": CHUNK_EMBED_MODEL} if CHUNK_EMBED_MODEL else {}
    emb = embed_batch([query], **kwargs)[0]
    return "[" + ",".join(f"{x:.8f}" for x in emb) + "]"


def _table_regclass(table: str) -> str | None:
    with ENGINE.connect() as c:
        return c.execute(text("select to_regclass(:name)"), {"name": table}).scalar()


def _column_info(table: str, column: str) -> tuple[str, str] | None:
    sql = """
        select data_type, udt_name
        from information_schema.columns
        where table_schema = current_schema()
          and table_name = :table
          and column_name = :column
        limit 1
    """
    with ENGINE.connect() as c:
        row = c.execute(text(sql), {"table": table, "column": column}).fetchone()
    return (row.data_type, row.udt_name) if row else None


def _metadata_where(source_type: str | None, date_from: str | None, date_to: str | None,
                    keyword: str | None) -> tuple[str, dict]:
    where: list[str] = []
    params: dict[str, Any] = {}
    if source_type:
        where.append("c.metadata->>'source_type' = :source_type")
        params["source_type"] = source_type
    if date_from:
        where.append("coalesce(c.metadata->>'event_date', c.metadata->>'source_date', c.metadata->>'date') >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where.append("coalesce(c.metadata->>'event_date', c.metadata->>'source_date', c.metadata->>'date') <= :date_to")
        params["date_to"] = date_to
    if keyword:
        where.append("(c.contextualized_content ilike :kw or c.content ilike :kw)")
        params["kw"] = f"%{keyword}%"
    return (" and ".join(where) if where else "true"), params


def _vector_cast_type() -> str | None:
    info = _column_info(RAG_CHUNKS_TABLE, "embedding")
    if not info:
        return None
    data_type, udt_name = (info[0] or "").lower(), (info[1] or "").lower()
    if "halfvec" in (data_type, udt_name):
        return "halfvec"
    if "vector" in (data_type, udt_name):
        return "vector"
    return None


def _token_source_sql() -> str | None:
    info = _column_info(RAG_CHUNKS_TABLE, "content_tokenized")
    if not info:
        return None
    data_type, udt_name = (info[0] or "").lower(), (info[1] or "").lower()
    if data_type == "array" or udt_name.startswith("_"):
        return "unnest(c.content_tokenized) as tok"
    if data_type == "jsonb" or udt_name == "jsonb":
        return "jsonb_array_elements_text(c.content_tokenized) as tok"
    if data_type == "json" or udt_name == "json":
        return "json_array_elements_text(c.content_tokenized) as tok"
    return None


def _vector_hits(query: str, vector_k: int, where_sql: str, params: dict) -> list[ChunkHit]:
    cast_type = _vector_cast_type()
    if not cast_type:
        return []

    qvec = _query_vec(query)
    sql = f"""
        select c.chunk_id, c.document_id, c.metadata, c.contextualized_content,
               row_number() over (order by c.embedding <=> cast(:qvec as {cast_type}))::int as vector_rank
        from {RAG_CHUNKS_TABLE} c
        where {where_sql}
          and c.embedding is not null
        order by c.embedding <=> cast(:qvec as {cast_type})
        limit :limit
    """
    run_params = {**params, "qvec": qvec, "limit": int(vector_k)}
    with ENGINE.connect() as c:
        rows = c.execute(text(sql), run_params).fetchall()
    return [
        ChunkHit(str(r.chunk_id), str(r.document_id or ""), r.metadata,
                 str(r.contextualized_content or ""), vector_rank=int(r.vector_rank))
        for r in rows
    ]


def _keyword_hits(tokens: list[str], keyword_k: int, where_sql: str, params: dict) -> list[ChunkHit]:
    token_source = _token_source_sql()
    if not token_source or not tokens:
        return []

    token_terms = _keyword_terms(tokens)
    sql = f"""
        with scored as (
            select c.chunk_id,
                   count(distinct lower(tok))::int as keyword_score
            from {RAG_CHUNKS_TABLE} c
            cross join lateral {token_source}
            where {where_sql}
              and lower(tok) = any(cast(:tokens as text[]))
            group by c.chunk_id
            order by keyword_score desc, c.chunk_id
            limit :limit
        )
        select c.chunk_id, c.document_id, c.metadata, c.contextualized_content,
               row_number() over (order by s.keyword_score desc, s.chunk_id)::int as keyword_rank
        from scored s
        join {RAG_CHUNKS_TABLE} c using (chunk_id)
        order by s.keyword_score desc, s.chunk_id
    """
    run_params = {**params, "tokens": token_terms, "limit": int(keyword_k)}
    with ENGINE.connect() as c:
        rows = c.execute(text(sql), run_params).fetchall()
    return [
        ChunkHit(str(r.chunk_id), str(r.document_id or ""), r.metadata,
                 str(r.contextualized_content or ""), keyword_rank=int(r.keyword_rank))
        for r in rows
    ]


def _fuse(vector_hits: list[ChunkHit], keyword_hits: list[ChunkHit], top_k: int) -> list[ChunkHit]:
    merged: dict[str, ChunkHit] = {}
    for hit in vector_hits:
        item = merged.setdefault(hit.chunk_id, hit)
        item.vector_rank = hit.vector_rank
        if hit.vector_rank:
            item.rrf_score += 1.0 / (RRF_K + hit.vector_rank)
    for hit in keyword_hits:
        item = merged.setdefault(hit.chunk_id, hit)
        item.keyword_rank = hit.keyword_rank
        if hit.keyword_rank:
            item.rrf_score += 1.0 / (RRF_K + hit.keyword_rank)
    return sorted(merged.values(), key=lambda h: (-h.rrf_score, h.chunk_id))[:top_k]


def _fmt_metadata(metadata: Any) -> str:
    if not metadata:
        return "-"
    if isinstance(metadata, dict):
        keep = ["source_type", "source_id", "event_date", "source_date", "date", "chunk_title", "message_ids"]
        parts = [f"{k}={metadata[k]}" for k in keep if metadata.get(k)]
        return "; ".join(parts) if parts else str(metadata)[:500]
    return str(metadata)[:500]


def _fmt_hits(hits: list[ChunkHit], tokens: list[str]) -> str:
    if not hits:
        return "(no matching chunks)"
    blocks = [f"query_tokens_after_filter={tokens or '[]'}"]
    for i, h in enumerate(hits, 1):
        ctx = h.contextualized_content
        if len(ctx) > CHUNK_CONTEXT_CHARS:
            ctx = ctx[:CHUNK_CONTEXT_CHARS] + "\n...(truncated)"
        blocks.append(
            f"[{i}] chunk_id={h.chunk_id} document_id={h.document_id} "
            f"vector_rank={h.vector_rank or '-'} keyword_rank={h.keyword_rank or '-'} "
            f"rrf_score={h.rrf_score:.6f}\n"
            f"metadata: {_fmt_metadata(h.metadata)}\n"
            f"{ctx}"
        )
    return "\n\n".join(blocks)


def search_chunks(query: str, top_k: int = DEFAULT_TOP_K, vector_k: int = DEFAULT_VECTOR_K,
                  keyword_k: int = DEFAULT_KEYWORD_K,
                  source_type: str | None = None, date_from: str | None = None,
                  date_to: str | None = None, keyword: str | None = None) -> str:
    """Hybrid chunk search: vector rank + PyThaiNLP-token keyword rank + RRF fusion."""
    if not _table_regclass(RAG_CHUNKS_TABLE):
        return f"(chunk search unavailable: table {RAG_CHUNKS_TABLE!r} does not exist)"

    where_sql, params = _metadata_where(source_type, date_from, date_to, keyword)
    tokens = tokenize_query(query)

    try:
        vectors = _vector_hits(query, vector_k, where_sql, params)
    except Exception as e:  # noqa: BLE001
        vectors = []
        vector_error = f"vector search error: {str(e).splitlines()[0]}"
    else:
        vector_error = ""

    try:
        keywords = _keyword_hits(tokens, keyword_k, where_sql, params)
    except Exception as e:  # noqa: BLE001
        keywords = []
        keyword_error = f"keyword search error: {str(e).splitlines()[0]}"
    else:
        keyword_error = ""

    fused = _fuse(vectors, keywords, max(int(top_k), 1))
    out = _fmt_hits(fused, tokens)
    errors = "; ".join(e for e in (vector_error, keyword_error) if e)
    return f"{errors}\n{out}" if errors else out
