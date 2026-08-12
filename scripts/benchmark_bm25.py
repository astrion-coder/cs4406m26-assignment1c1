"""Verifies SPEC.md Q2 #1's from-scratch BM25 timing claim (~5ms/query on
MIND's 65,238-article corpus, well under a minute extrapolated across all
val/test users) against the real feature store and bm25.py module.

Usage: uv run python scripts/benchmark_bm25.py
"""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

from cs4406m26_assignment1c1.bm25 import build_index, tokenize, top_k

ROOT = Path(__file__).resolve().parent.parent
RECENT_N_CLICKS = 20
TOPK_MAX = 200
SAMPLE_USERS = 500


def build_query(article_id_sequence, titles_by_id: dict[str, str]) -> list[str]:
    recent = list(article_id_sequence)[-RECENT_N_CLICKS:]
    text = " ".join(titles_by_id.get(aid, "") for aid in recent)
    return tokenize(text)


def benchmark(dataset: str) -> None:
    processed = ROOT / "data" / "processed" / dataset
    articles = pd.read_parquet(processed / "articles.parquet")
    behaviors = pd.read_parquet(processed / "behaviors.parquet")
    history = pd.read_parquet(processed / "history.parquet")

    docs = (articles["title"].fillna("") + " " + articles["abstract"].fillna("")).tolist()
    doc_tokens = [tokenize(text) for text in docs]
    index = build_index(articles["article_id"].tolist(), doc_tokens)

    titles_by_id = dict(zip(articles["article_id"], articles["title"]))
    val_test_users = behaviors.loc[behaviors["split"].isin(["val", "test"]), "user_id"].unique()
    history_by_user = history.set_index("user_id")["article_id_sequence"]

    queries = []
    for user_id in val_test_users[:SAMPLE_USERS]:
        seq = history_by_user.get(user_id)
        if seq is None or len(seq) == 0:
            continue
        query = build_query(seq, titles_by_id)
        if query:
            queries.append(query)

    start = time.perf_counter()
    for query in queries:
        top_k(index, query, k=TOPK_MAX)
    elapsed = time.perf_counter() - start

    per_query_ms = 1000 * elapsed / len(queries)
    total_users = len(val_test_users)
    extrapolated_s = (per_query_ms / 1000) * total_users

    print(
        f"[{dataset}] corpus={len(articles)} docs, sampled {len(queries)} queries "
        f"out of {total_users} val/test users"
    )
    print(
        f"[{dataset}] {per_query_ms:.2f} ms/query -> "
        f"~{extrapolated_s:.1f}s extrapolated across all {total_users} val/test users"
    )


if __name__ == "__main__":
    for dataset in ("ebnerd", "mind"):
        benchmark(dataset)
