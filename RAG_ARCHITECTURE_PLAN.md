# RAG Architecture Change Plan

## Summary

Replace the current document-level RAG retrieval with chunk-level hybrid retrieval. Keep the provided chunk schema unchanged. Use each chunk's `embedding` for vector search, `content_tokenized` for keyword search with PyThaiNLP query tokens, and combine both ranked result lists with RRF, Reciprocal Rank Fusion.

## Current State

- Current RAG stores whole documents in `doc_corpus` and one embedding per document in `doc_vec`.
- Current retrieval uses metadata/date/topic filters, optional SQL `ILIKE`, and vector ranking.
- Current system has no chunk-level retrieval, no PyThaiNLP keyword ranking, and no RRF.
- Current keyword behavior is substring filtering, not real token-based keyword search.

## Target Chunk Store

Keep the provided chunk object unchanged:

```text
chunk_id
parent_section_id
document_id
content
parent_content
contextualized_content
metadata
content_tokenized
embedding
content_sha256
```

Store chunks in a single table, recommended name: `rag_chunks`.

Keep `embedding` logically as `array<number>` in the chunk object, but store it in Postgres as `vector` or `halfvec` if possible for pgvector search.

Keep `content_tokenized` logically as `array<string>`, stored as `text[]` or `jsonb`.

Add indexes/views only, not helper tables, to respect the current schema constraint.

## Target Retrieval Flow

```text
user query
-> tokenize query with PyThaiNLP
-> filter common/noise query tokens
-> embed query with current embedding model, currently Qwen3 embedding 8B
-> vector search over rag_chunks.embedding
-> keyword search over rag_chunks.content_tokenized
-> RRF fuse vector results and keyword results
-> return final top_k chunks
-> send contextualized_content to the answer generation step
```

## Keyword Search

- Keyword search means token-based search using PyThaiNLP, not SQL `ILIKE`.
- Query tokens are compared against each chunk's `content_tokenized`.
- Rank chunks by useful token overlap or weighted token overlap.
- Do not create an inverted-index table for v1.
- Keep SQL `ILIKE` only as an optional fallback for exact substring checks, not as the main keyword path.

## Token Filtering

Do not rewrite stored `content_tokenized`.

Filter or downweight common boilerplate terms during keyword search.

Ignore or downweight tokens such as:

```text
Document, Chat, Source, Type, Chunk, Title, Message, Participants,
CUSTOMER, CS, AGENT, text, M, ID, Date, Timestamp, line, oa
```

Keep useful terms such as:

```text
Powercell, X3, ใบแจ้งหนี้, 176, 800, บาท, รับประกัน, เซ็นทรัลลาดพร้าว
```

If all query tokens are removed by filtering, skip keyword search and rely on vector search.

## RRF Fusion

- Run vector search and keyword search independently.
- Each branch returns a ranked list of `chunk_id`.
- Use RRF to combine ranks:

```text
fused_score = 1 / (k + vector_rank) + 1 / (k + keyword_rank)
```

- Use `k = 60` as the default RRF constant.
- Chunks present in both result lists should usually rank higher than chunks present in only one list.
- Final result returns top `top_k` chunks after fusion.

## Interface Changes

Replace the current document search tool with a chunk search tool.

Recommended tool behavior:

```text
search_chunks(query, top_k=5, vector_k=50, keyword_k=50, filters={...})
```

Returned result should include:

```text
chunk_id
document_id
metadata
contextualized_content
vector_rank
keyword_rank
rrf_score
```

Existing doc agent should consume `contextualized_content` instead of whole-document snippets.

Do not fall back to `search_docs_tool`, `get_document_tool`, `doc_corpus`, or `doc_vec` for RAG
retrieval. If chunk search returns no matches or the `rag_chunks` table is unavailable, report that
chunk retrieval did not find usable context rather than switching to document-level retrieval.

## Test Plan

- Query `ใบแจ้งหนี้ 176,800 บาท` should keep `ใบแจ้งหนี้`, `176`, `800`, `บาท` and rank invoice chunks highly.
- Query `Powercell X3 สต็อก` should rank Powercell stock chunks, not generic chat chunks.
- Query with mostly boilerplate terms should not crash; keyword search can return empty while vector search still works.
- Verify RRF promotes chunks that appear high in both vector and keyword lists.
- Verify existing SQL/database routing remains separate from RAG retrieval.
- Verify final returned context uses `contextualized_content`.

## Assumptions

- The chunk schema provided by the user is fixed.
- No separate inverted-index table will be added in v1.
- Indexes and views are allowed.
- Qwen3 embedding 8B is the current embedding model, but the retrieval code should make the embedding model configurable for future replacement.
- `RRF` is the correct term, not `RFF`.
