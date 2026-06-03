"""Qwen embeddings via the ModelHarbor OpenAI-compatible embeddings API."""
from __future__ import annotations

import math
import os
import time

import httpx

from fahmai.db import ROOT  # noqa: F401  (import triggers .env load)

EMBED_MODEL = os.getenv("EMBED_MODEL", "qwen3-embedding")
EMBED_DIM = int(os.getenv("EMBED_DIM", "4096"))
EMBED_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "http://swarm-manager.modelharbor.com:52157/v1")
EMBED_API_KEY_ENV = os.getenv("EMBEDDING_API_KEY_ENV", "EMBEDDING_API_KEY")
EMBED_NORMALIZE = os.getenv("EMBEDDING_NORMALIZE", "true").lower() in {"1", "true", "yes", "on"}


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"missing required environment variable {name}")
    return value


def _normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if not norm:
        return vec
    return [x / norm for x in vec]


def embed_batch(texts: list[str], retries: int = 5, model: str | None = None) -> list[list[float]]:
    key = _required_env(EMBED_API_KEY_ENV)
    url = EMBED_BASE_URL.rstrip("/") + "/embeddings"
    payload = {"model": model or EMBED_MODEL, "input": texts}
    last = None
    for attempt in range(retries):
        try:
            r = httpx.post(url, headers={"Authorization": f"Bearer {key}"},
                           json=payload, timeout=180)
            if r.status_code == 200:
                j = r.json()
                if isinstance(j, dict) and j.get("data"):
                    data = sorted(j["data"], key=lambda d: d["index"])
                    embs = [list(map(float, d["embedding"])) for d in data]
                    return [_normalize(e) for e in embs] if EMBED_NORMALIZE else embs
                # 200 but no data (transient error body / rate notice) -> retry
                last = f"200 no-data: {str(j)[:150]}"
                time.sleep(2 ** attempt)
                continue
            last = f"{r.status_code} {r.text[:150]}"
            if r.status_code in (408, 429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(last)
        except (httpx.HTTPError, ValueError) as e:  # ValueError = bad JSON
            last = str(e)
            time.sleep(2 ** attempt)
    raise RuntimeError(f"embed failed after {retries}: {last}")
