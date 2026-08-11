# Assignment 1 Spec

Covers Q1–Q9 of `assignments/Assignment1_v1.pdf`. Q1 and Q2 are implemented;
Q3–Q9 are design only, pending implementation.

# Q1 — Reproducible Data Pipeline

## 1. Goal

One pipeline, run twice (once per dataset), that turns the raw EB-NeRD demo and
MIND-small files into three unified-schema tables per dataset — `articles`,
`behaviors`, `history` — with a `split` column (`train`/`val`/`test`) assigned by
time, rebuildable from raw files with a single command.

The two datasets are **never merged**: outputs stay in separate per-dataset
directories with dataset-namespaced IDs. Only the schema (column names/types) and the
code that produces it are shared.

## 2. Unified schema

Namespacing: every ID is prefixed with its source dataset so cross-dataset joins can
never silently collide — `ebnerd_<native_id>` / `mind_<native_id>`. `<native_id>` is
kept in its original type/format for traceability (e.g. `ebnerd_123`, `mind_N55528`).

Only columns needed for Q1–Q4 are included. Dataset-specific columns that aren't
needed yet (EB-NeRD's `sentiment_score`, `entity`/`topic` tags, user demographics;
MIND's KG entity embeddings) are **not** part of this schema — they can be added as
nullable extension columns later if a later question needs them, per the
no-speculative-features guideline. `body` is kept because EB-NeRD has it and it's a
natural bonus signal for BM25/semantic retrieval later, even though MIND's is always
null.

### `articles` — one row per article

| Column | Type | Source: EB-NeRD | Source: MIND |
|---|---|---|---|
| `article_id` | str | `"ebnerd_" + article_id` | `"mind_" + news_id` |
| `dataset` | str | `"ebnerd"` | `"mind"` |
| `title` | str | `title` | `title` |
| `abstract` | str, nullable | `subtitle` | `abstract` |
| `body` | str, nullable | `body` | `null` (licensing — see README) |
| `category` | str | `category_str` | `category` |
| `subcategory` | str, nullable | `subcategory[0]` if present else null (EB-NeRD allows multiple; keep first, drop rest — not needed for Q1–Q4) | `subcategory` |
| `published_time` | datetime, nullable | `published_time` | `null` (not provided) |

### `behaviors` — one row per impression

| Column | Type | Source: EB-NeRD | Source: MIND |
|---|---|---|---|
| `impression_id` | str | `"ebnerd_" + impression_id` | `"mind_" + impression_id` |
| `dataset` | str | `"ebnerd"` | `"mind"` |
| `user_id` | str | `"ebnerd_" + user_id` | `"mind_" + user_id` |
| `impression_time` | datetime | `impression_time` | parsed `time` (`MM/DD/YYYY H:MM:SS AM/PM`) |
| `article_ids_inview` | list[str] | `article_ids_inview`, namespaced | `impressions` tokens (all), namespaced |
| `article_ids_clicked` | list[str] | `article_ids_clicked`, namespaced | `impressions` tokens with label `1`, namespaced |
| `session_id` | str, nullable | `"ebnerd_" + session_id` | `null` (not provided) |
| `split` | str | assigned by pipeline: `train`/`val`/`test` | assigned by pipeline: `train`/`val`/`test` |

### `history` — one row per user (pre-collection-window click history)

| Column | Type | Source: EB-NeRD | Source: MIND |
|---|---|---|---|
| `user_id` | str | `"ebnerd_" + user_id` | `"mind_" + user_id` |
| `dataset` | str | `"ebnerd"` | `"mind"` |
| `article_id_sequence` | list[str] | `article_id_fixed`, namespaced, chronological | first non-null `history` field seen for that user in `behaviors.tsv`, space-split, namespaced (order-only; see note) |
| `timestamp_sequence` | list[datetime], nullable | `impression_time_fixed` | `null` (MIND gives order only, no per-click timestamps) |
| `read_time_sequence` | list[float], nullable | `read_time_fixed` | `null` (not provided) |
| `scroll_percentage_sequence` | list[float], nullable | `scroll_percentage_fixed` | `null` (not provided) |

**MIND history note**: unlike EB-NeRD's dedicated `history.parquet`, MIND's `history`
field is embedded per-row in `behaviors.tsv` and is identical across all of a given
user's rows (it always describes clicks from *before* the log period, not
incrementally up to each impression). The pipeline must verify this invariant while
building the table (assert one distinct non-null `history` string per `user_id`) and
fail loudly if it doesn't hold, rather than silently picking one.

## 3. Temporal split

Both datasets already ship two chronologically contiguous provider splits (train,
then dev/validation) — there is no provider test split. Verified date ranges (from
the actual files on disk):

| | provider `train` | provider `dev`/`validation` |
|---|---|---|
| EB-NeRD demo | 2023-05-18 07:00 → 2023-05-25 07:00 (7 days) | 2023-05-25 07:00 → 2023-06-01 07:00 (7 days) |
| MIND-small | 2019-11-09 00:00 → 2019-11-15 00:00 (6 days) | 2019-11-15 00:00 → 2019-11-16 00:00 (1 day) |

Design decision: treat the provider's dev/validation split as our held-out **test**
set (untouched until final evaluation), and carve **our** validation set from the
last day of the provider's train split by time — never randomly. Concretely:

- EB-NeRD: `train` = impressions before `2023-05-24 07:00:00`; `val` = impressions in
  `[2023-05-24 07:00:00, 2023-05-25 07:00:00)`; `test` = all of provider `validation/`.
- MIND: `train` = impressions before `2019-11-14 00:00:00`; `val` = impressions in
  `[2019-11-14 00:00:00, 2019-11-15 00:00:00)`; `test` = all of provider `dev/`.

Cutoffs are named constants (per dataset) in the split module, not hardcoded inline,
so they're easy to audit or adjust later (e.g. if 1 day of validation proves too
small/noisy).

## 4. Feature store layout

```
data/processed/ebnerd/articles.parquet
data/processed/ebnerd/behaviors.parquet     # includes `split` column
data/processed/ebnerd/history.parquet
data/processed/ebnerd/manifest.json         # row counts, split date cutoffs, schema version, build timestamp
data/processed/mind/articles.parquet
data/processed/mind/behaviors.parquet
data/processed/mind/history.parquet
data/processed/mind/manifest.json
```

`data/` is added to `.gitignore` (matches Q8's "no large files / `data/`" policy).
Raw inputs stay wherever they already are on disk (`ebnerd_demo/`, `MINDsmall_train/`,
`MINDsmall_dev/`), also already gitignored — the pipeline reads from there and never
copies raw files into `data/`.

## 5. Implementation shape

Per `CLAUDE.md`, all code is notebook-based: one markdown title + one feature cell +
one pytest-style test cell per step, matching the existing style in
`src/explore_datasets.ipynb`. Q1 gets its own notebook, `src/build_pipeline.ipynb`,
with this cell sequence (each numbered item = title/feature/test cell triple):

1. Load raw EB-NeRD → unify to `articles` / `behaviors` / `history` (three
   title/feature/test triples, one per table)
2. Load raw MIND → unify to `articles` / `behaviors` / `history` (three more triples)
3. Temporal split — apply the cutoffs from §3, add `split` column to each dataset's
   `behaviors` table; test asserts per-split time ranges are non-overlapping and
   monotonically ordered `train < val < test` (this doubles as the Q9 leakage
   boundary test for split-level leakage)
4. History/behavior leakage test — for EB-NeRD, assert every timestamp in a user's
   `history.timestamp_sequence` is strictly earlier than every `impression_time` for
   that user in `behaviors` (verified on real data: 0/1590 violations). For MIND,
   content-overlap between history and `article_ids_inview` is **not** a valid
   leakage signal — verified empirically that ~11% of users legitimately have
   popular/previously-seen articles reappear as candidates, since candidate sets
   aren't filtered against history. The real, checkable invariant for MIND is
   structural: every user must have exactly **one** distinct `history` string across
   all of their impression rows (train+dev combined) — this is what proves history
   is a fixed pre-window snapshot rather than something that could be accidentally
   reconstructed per-impression from later data. Verified on real data: 0/91,935
   users violate this. This check is already required to build `mind_history` (§2
   step 6) and is additionally asserted as an explicit test here.
5. Write feature store — serialize all six parquet files + two manifests to
   `data/processed/`
6. One-command rebuild entrypoint

**One-command rebuild**: a thin `build_pipeline.py` at the repo root (as literally
named in the assignment) that shells out to
`jupyter nbconvert --to notebook --execute --inplace src/build_pipeline.ipynb`,
so the documented command is `uv run python build_pipeline.py`. Executing the
notebook top-to-bottom re-runs every feature+test cell, so a failed assertion in any
test cell aborts the rebuild — that's the pipeline's correctness gate. README gets a
one-line "Rebuild the feature store" section pointing at this command.

## 6. Dependencies

No new dependencies expected for Q1 — parsing (TSV via `pandas.read_csv`, JSON via
stdlib `json`, Parquet via existing `pyarrow`) and writing the feature store all fit
within `numpy`/`pandas`/`pyarrow`, already declared in `pyproject.toml`. Will confirm
before running `uv add` if something unexpected comes up during implementation.

## 7. Open questions / risks (flagged, not blocking)

- MIND's `history` field being null for cold-start users means those users get an
  empty `article_id_sequence` in `history` rather than no row at all — every
  `user_id` seen in `behaviors` should still get a `history` row (possibly all-empty
  lists) so downstream joins (Q2/Q3) don't need special-case null-row handling.
- EB-NeRD's `subcategory` can hold multiple IDs; taking only the first is a
  simplification — acceptable for Q1 since nothing here depends on it yet, but worth
  a one-line callout in the eventual design note (Q6) if it matters later.

# Q2 — Lexical Candidate Generation (BM25)

## 1. Approach

From-scratch BM25 (Okapi), no third-party BM25 library. Implemented as a
proper importable module, `src/cs4406m26_assignment1c1/bm25.py` (not inline
notebook cells like the rest of the project) — a deliberate exception to the
"all code in notebooks" convention, since this is a reusable, unit-testable
component with a real performance requirement (below), not a one-off analysis
step.

Two library options were evaluated and rejected before this: a hand-rolled
implementation using `rank-bm25`'s `BM25Okapi` purely to fit/validate `idf`,
`doc_len`, `avgdl`, paired with our own postings-list scoring. Both were
dropped because a from-scratch implementation performs just as well without
the extra dependency — verified below.

**Performance is the reason this is hand-built rather than a call to a
library's own scoring method.** `rank_bm25.BM25Okapi.get_scores` is O(corpus
size) per query token — for each token it does a Python-level `doc.get(term)`
lookup across *every* document's `doc_freqs` dict, not a sparse postings
lookup. Measured directly on MIND's 65,238-article corpus: ~2.9 seconds for a
single 20-title query. At the volume this pipeline needs (once per val/test
user — tens of thousands), that extrapolates to 40+ hours. `bm25.py`'s own
postings-list index — `term -> (doc_idx array, tf array)`, scored with
`numpy`'s `np.add.at` over only the documents that actually contain each query
term, then top-K selected via `np.argpartition` (not a Python-level `heapq` +
key function, which is also slow at corpus scale) — measured at ~5ms/query on
the same corpus: ~6 minutes extrapolated across all of MIND's val/test users,
well under a minute for EB-NeRD's smaller corpus and user count.

IDF uses the non-negative variant: `log((N - df + 0.5)/(df + 0.5) + 1)`. The
classic Robertson/Sparck-Jones IDF goes negative for terms appearing in more
than half the corpus; the `+1` guarantees `idf(term) >= 0` for every term.

## 2. Scope

Two independent BM25 indexes, one per dataset, each built over that dataset's
full `articles` table (all articles — articles aren't split, only `behaviors`
is). Same "shared code, separate runs per dataset" pattern as Q1.

## 3. Corpus text & tokenization

Corpus text is `title + " " + abstract` only — never `body` (Q2 says "titles
and abstracts"; MIND has no body at all per the Q1 schema). `abstract` must be
`.fillna("")`'d before concatenation: ~5.2% of MIND articles (3,415/65,238) have
a null abstract, and naive string concatenation would propagate NaN, silently
zeroing those articles' tokens/doc length and skewing `avgdl`. EB-NeRD has zero
abstract nulls.

Tokenizer: `re.findall(r"\w+", text.lower())`. Python's `re` is Unicode-aware by
default, so this correctly keeps Danish `æøå`/`ÆØÅ` as word characters under
`\w` and folds case correctly for both languages — no new dependency, no
stemming/stopword removal. Accepted imprecision: hyphens/apostrophes split
words (e.g. `harry's` → `harry`, `s`).

## 4. Query construction

Concatenate the **titles** of a user's most recent `RECENT_N_CLICKS = 20`
clicks from `history.article_id_sequence` (a named, adjustable constant).
`timestamp_sequence` is chronologically ascending, so "most recent N" =
`sequence[-20:]`, the *last* N elements, not the first. Median history length
is 71 (EB-NeRD) / 12 (MIND) — a fixed modest window keeps queries focused on
recent interest and comparable across datasets rather than dominated by
EB-NeRD's longer histories.

Cold-start users (empty `article_id_sequence` — 0 in EB-NeRD demo, 2,122 in
MIND) produce no query and are excluded from the recall@K aggregate, with
their impression count reported separately per split; cold-start-vs-warm
slicing itself is Q4's job.

## 5. Candidate generation semantics

BM25 retrieves its own top-K from the whole article catalog — this is not a
re-ranking of the impression's given `article_ids_inview`. Recall@K checks
whether `article_ids_clicked` appears in that independently-retrieved top-K.

## 6. Retrieval caching

Since the query depends only on the user's fixed pre-window `history`
(identical for every impression of that user), compute `get_scores` **once
per user** at `k=200`, then derive recall@50/@100/@200 as prefixes of that
single sorted list. This makes `top-50 ⊆ top-100 ⊆ top-200` true by
construction and avoids 3× redundant scoring.

Only users appearing in the `val` or `test` splits of `behaviors` need
retrieval computed (recall@K isn't reported on `train`); extending to
train-split users is deferred to whichever of Q3/Q4 needs it.

## 7. Recall@K definition

Fractional multi-relevant, not binary hit/miss: `article_ids_clicked` is not
always singleton — up to 7 clicks/impression in EB-NeRD, up to 35 in MIND (a
third of MIND impressions have multiple clicks). Per impression:

```
recall@K(impression) = |clicked ∩ top-K| / |clicked|
```

Macro-averaged over included (non-cold-start) impressions, computed for
`split ∈ {val, test}` × `K ∈ {50, 100, 200}`.

## 8. Persistence

Mirrors Q1's `manifest.json` conventions:

```
data/processed/{dataset}/bm25_topk.parquet
  user_id                str
  dataset                str
  n_retrieved            int
  retrieved_article_ids  list[str]    # score-descending
  retrieved_scores       list[float]  # parallel to retrieved_article_ids
data/processed/{dataset}/bm25_metrics.json
  schema_version, build_timestamp
  hyperparameters: {k1, b, recent_n_clicks, topk_max}
  recall_at_k: {val: {50, 100, 200}, test: {50, 100, 200}}
  n_impressions: {val: {total, evaluated, excluded_coldstart}, test: {...}}
  scope: "val_test_users_only"
```

Keyed by user, not impression, to avoid storing duplicate retrieval results
across a user's many impressions.

## 9. Implementation shape

The BM25 implementation itself (`tokenize`, `build_index`, `get_scores`,
`top_k`) lives in `src/cs4406m26_assignment1c1/bm25.py`, a plain importable
module (see §1 for why this one component breaks from the notebook-only
convention). Everything else — loading the feature store, query construction,
retrieval caching, evaluation, persistence — is notebook cells, in
`src/bm25_retrieval.ipynb`, following `build_pipeline.ipynb`'s
markdown/feature/test cell convention, with `bm25_retrieval.py` as the
one-command entrypoint (mirrors `build_pipeline.py`'s `nbconvert --execute
--inplace` wrapper). Cell sequence:

1. Setup — imports (incl. `from cs4406m26_assignment1c1.bm25 import ...`),
   load feature store, constants.
2. Tokenizer smoke test — Danish/English samples, `None`/empty-string handling
   (exercises the imported `tokenize`, not a notebook-local redefinition).
3. Per-dataset tokenized document corpus (`title+abstract`) + test — covers the
   `abstract.fillna("")` case explicitly using a known null-abstract MIND row.
4. Build a `BM25Index` per dataset (`build_index`) + test — cross-check
   `avgdl`/`doc_len` against independently-computed values, and a couple of
   `idf` values against a by-hand calculation on a small sample.
5. Top-K retrieval smoke test (`top_k`) — length, descending order, nesting
   invariant (`top200[:50] == top50`), empty query → `[]`.
6. Query construction from history + test — cold-start → `[]`; window correctly
   takes the *last* N clicks, not the first N.
7. Per-user retrieval cache, restricted to val/test users + test — cache keys
   are a subset of val∪test user_ids; cold-start count cross-checked
   independently per dataset (not hardcoded, since EB-NeRD's true count is 0).
8. Recall@K evaluation + test — monotonic `recall@50 ≤ recall@100 ≤ recall@200`;
   `n_evaluated + n_excluded == n_total`; values in `[0,1]`.
9. Persist `bm25_topk.parquet` + `bm25_metrics.json` + round-trip test.

# Manual Review Upto Here

# Q3 — Semantic Candidate Generation (Embeddings)

## 1. Embedding source

One uniform method for both datasets — not EB-NeRD's provided pretrained
artifacts (which would leave MIND on a separate, incomparable code path and
vector space regardless, since MIND has no provided article embeddings at
all, only unrelated KG entity embeddings already excluded from the Q1
schema). Same "shared code, separate runs per dataset" pattern as Q1/Q2.

Model: `paraphrase-xlm-r-multilingual-v1` (XLM-RoBERTa-based, 768-dim, via
`sentence-transformers`) — handles Danish and English in one model, matches
the assignment's "BERT/XLM-RoBERTa" suggestion directly, and produces
genuinely semantic (not lexical) vectors, which matters for item 5's
lexical-vs-semantic comparison to be meaningful.

**Computed on Kaggle Notebooks on a GPU, not locally.**
`sentence-transformers` + `torch` are a materially heavy dependency (hundreds
of MB to ~1GB+), and CLAUDE.md's own tech-stack note already says model
training/inference-heavy work belongs on a hosted GPU notebook, not the local
environment. The split:

- `src/compute_embeddings_kaggle.ipynb` — a standalone notebook, **not** part
  of the local one-command pipeline and **not** executed by any local
  `*.py` wrapper. Run on Kaggle (GPU accelerator, internet enabled): both
  datasets' `articles.parquet` are attached as a Kaggle Dataset input, the
  notebook encodes `title + " " + abstract` with the model above, and writes
  the resulting `article_embeddings.parquet` per dataset to
  `/kaggle/working/`, downloaded from that run's Output tab. A GPU makes
  runtime a non-issue at these corpus sizes (11,777 / 65,238 articles), so no
  local speed benchmark is needed for this step — unlike Q2's `rank_bm25`
  story, the constraint here is dependency weight and environment (Kaggle has
  a GPU and disposable install; the local dev environment doesn't), not raw
  throughput.
- The two downloaded files are placed at
  `data/processed/{ebnerd,mind}/article_embeddings.parquet` by hand (same
  manual-prerequisite pattern as Q1's raw dataset downloads — Part 0 of the
  assignment already requires a manual download step before the one-command
  rebuild can run).
- Everything downstream (§2–§7 below) runs locally with **zero new
  dependencies** — `numpy`/`pandas`/`pyarrow` (already in `pyproject.toml`)
  are sufficient once the embedding vectors already exist as a parquet file;
  the local repo never imports `torch` or `sentence-transformers`.

## 2. ANN index

Brute-force, not FAISS. At `dim ∈ {300–768}` and corpus sizes 11,777
(EB-NeRD) / 65,238 (MIND), a batched dense `numpy` matmul
(`user_vectors @ corpus_matrix.T`) plus `np.argpartition` top-K, measured
directly: ~7–12s for the full MIND val/test population (65,173 users) at the
matmul step, ~19–40s for top-K selection — under two minutes total, and
proportionally faster for EB-NeRD. FAISS would add a real dependency to
solve a problem plain numpy already solves in seconds at this scale. The one
real requirement is batching users (e.g. 2,000–5,000 per batch) — the full
similarity matrix at MIND scale is ~17GB and must never be materialized at
once.

## 3. User representation

Mean-pool the embeddings of a user's most recent `RECENT_N_CLICKS = 20`
clicks from `history.article_id_sequence` — same window Q2 uses for BM25
query construction (`sequence[-20:]`), kept identical rather than tuned
separately, so the lexical-vs-semantic comparison in §5 holds the input
click window constant and only varies the scoring method. Cold-start users
(empty `article_id_sequence`) produce no vector and are excluded from
recall@K, reusing Q2's already-computed `coldstart_users` sets (0 EB-NeRD /
2,122 MIND) rather than recomputing. Retrieval is cached once per val/test
user, identical rationale to Q2's caching (query depends only on fixed
pre-window history).

## 4. Recall@K

Same `K ∈ {50, 100, 200}`, same fractional multi-relevant definition as Q2
(`|clicked ∩ top-K| / |clicked|`, macro-averaged over non-cold-start
impressions per split) — retrieval-method-independent, reused directly
rather than redefined.

## 5. Lexical vs. semantic comparison

A comparison table reading both `bm25_metrics.json` and
`embedding_metrics.json` — `recall@{50,100,200}` × `{bm25, embedding}` ×
`{val, test}` × `{cold-start-excluded, warm-only}`, reusing Q2's
`coldstart_users` sets directly. EB-NeRD's 0 cold-start users makes that
slice degenerate there (state this plainly, don't hide it); MIND's
2,122-user cold-start population makes the slice meaningful.

## 6. Persistence

Schema-parallel to Q2's artifacts (deliberately identical shape so Q4 can
treat both methods uniformly):

```
data/processed/{dataset}/embedding_topk.parquet
  user_id, dataset, n_retrieved
  retrieved_article_ids  list[str]    # score-descending (cosine similarity)
  retrieved_scores       list[float]  # parallel, cosine similarity in [-1, 1]
data/processed/{dataset}/embedding_metrics.json
  schema_version, build_timestamp
  hyperparameters: {embedding_method, embedding_dim, recent_n_clicks, topk_max}
  recall_at_k: {val: {50, 100, 200}, test: {50, 100, 200}}
  n_impressions: {val: {total, evaluated, excluded_coldstart}, test: {...}}
  scope: "val_test_users_only"
data/processed/{dataset}/article_embeddings.parquet
  article_id  str
  dataset     str
  embedding   list[float32]   # aligned to articles.parquet order
```

`article_embeddings.parquet` has no Q2 equivalent — BM25's index rebuilds
cheaply from `articles.parquet` in seconds, but Q4's re-scoring adapter needs
raw embedding vectors (not just top-200 candidates) to score arbitrary
`article_ids_inview` items outside any user's cached top-200.

## 7. Implementation shape

`src/compute_embeddings_kaggle.ipynb` — the Kaggle-only notebook from §1.
Prerequisite artifact, run manually before anything below; not part of the
local one-command pipeline.

`src/cs4406m26_assignment1c1/embeddings.py` — a new local module, same
rationale as `bm25.py` (reusable, real performance requirement — the
batching in §2, not the embedding computation, which happened on Kaggle).
Functions: `mean_pool(article_ids, embedding_lookup) -> np.ndarray`,
`batched_top_k(query_matrix, corpus_matrix, doc_ids, k, batch_size)`,
`cosine_similarity_subset(query_vector, corpus_matrix, doc_ids, subset_ids)`
(reused by Q4's re-scoring adapter).

`src/embedding_retrieval.ipynb` + `embedding_retrieval.py`, mirroring
`bm25_retrieval.ipynb`'s cell sequence:

1. Setup — imports, load feature store, constants. Load
   `article_embeddings.parquet` per dataset; fail with a clear message
   pointing at `compute_embeddings_kaggle.ipynb` if missing.
2. Load article embeddings per dataset + test — shape, no-NaN, alignment
   with `articles.parquet` row order.
3. Build corpus embedding matrices + test — mirrors `test_corpus_alignment`.
4. Mean-pooling user representation + test — cold-start → no vector; window
   is the *last* N clicks, not the first N.
5. Batched brute-force top-K retrieval + test — self-similarity ≈1.0 sanity
   check, sorted-descending, nesting invariant (`top200[:50] == top50`),
   empty query → `[]`.
6. Per-user retrieval cache, restricted to val/test users + test — mirrors
   `test_user_retrieval_cache`.
7. Recall@K evaluation + test — monotonic, bounded, count-consistent.
8. Lexical-vs-semantic comparison (§5) + test — reloaded values match both
   persisted `*_metrics.json` files.
9. Persist `embedding_topk.parquet` + `embedding_metrics.json` +
   `article_embeddings.parquet` + round-trip test.

# Q4 — Offline Evaluation Harness

## 1. Candidate-generation vs. re-ranking — the central design fork

AUC, MRR, nDCG@5, and nDCG@10 require a full ranking over a candidate *set*
with known relevance labels — the only such set that exists per impression
is `article_ids_inview` (median 9 EB-NeRD / 24 MIND items), re-ranked by the
retrieval method's score. This is a different framing from Q2/Q3's
recall@K, which retrieves top-K from the whole catalog (11,777 / 65,238
articles):

| | Q2/Q3 recall@K | Q4 AUC/MRR/nDCG |
|---|---|---|
| Candidate set | Retrieval method's own top-K from the whole catalog | The impression's own `article_ids_inview` |
| Question | Can this method find the clicked article at all, among everything? | Given what was actually shown, does this method rank the clicked one(s) near the top? |
| Framing | Candidate generation | Re-ranking |

This matches how MIND's and EB-NeRD/RecSys2024's own official challenges
define these metrics. It also means Q4 cannot just consume the persisted
top-200 lists for ranking metrics — MIND's recall@200 is only 1.6–3.4% (from
Q2), so the clicked article is usually outside the cached top-200 entirely,
and a plain top-200 lookup would leave most rankings undefined.

Q4 needs a re-scoring adapter, one implementation per method, same
signature: `score_inview(dataset, method, user_id, article_ids_inview) ->
dict[article_id, float]`.
- BM25: rebuild the index (cheap, seconds) and call `get_scores` once per
  user (~5ms, per Q2's benchmark), subset by `article_ids_inview`.
- Embedding: cosine similarity of the user's mean-pooled vector against only
  the inview embeddings (trivial given inview sizes of 2–299).

The persisted top-K artifacts aren't wasted — they're the correct input for
coverage (§2) and the Q3 comparison table, which are legitimately
candidate-generation-framed; ranking metrics use on-the-fly inview
re-scoring instead. This split is the key reconciliation between Q2/Q3 and
Q4's framings.

## 2. Metric formulas

Binary relevance, `article_ids_clicked` ⊆ inview:

- **AUC** (per-impression rank-sum form): rank inview items by score;
  `AUC = (sum_of_ranks(positives) - n_pos*(n_pos+1)/2) / (n_pos * n_neg)`.
  Undefined only if `n_pos == 0` or `n_neg == 0` — verified this never
  happens (no zero-click impressions in either dataset; minimum inview size
  is 2).
- **MRR**: `1 / rank_of_first_clicked_item` in the score-descending inview
  ranking (standard IR definition — one value per impression even with
  multiple clicks).
- **nDCG@K** (binary relevance): `DCG@K = Σ_{i=1}^{K} rel_i / log2(i+1)`
  over the score-descending ranking; `IDCG@K` from the ideal ordering (all
  `min(n_pos, K)` positives first); `nDCG@K = DCG@K / IDCG@K`. Computed for
  `K ∈ {5, 10}`.

Each macro-averaged over evaluated impressions per `(dataset, method,
split)`.

## 3. Beyond-accuracy metrics

- **Intra-list diversity**: over the top-10 reranked inview list (matches
  nDCG@10's window). Category-based distance — `1 - same_category(i,j)`
  averaged over all pairs — since `category` exists for every article
  regardless of method, keeping Q4 runnable on BM25-only results without a
  hard Q3 dependency, and comparable across methods.
- **Novelty**: inverse train-split popularity,
  `novelty(item) = -log2(pop(item))` where
  `pop(item) = clicks_train(item) / total_train_clicks`. 90.2% (MIND) /
  91.8% (EB-NeRD) of the catalog never appears in train clicks — zero-click
  items get add-one-smoothed popularity
  `1 / (total_train_clicks + n_articles)` to avoid `log2(0)`. List-level
  novelty = mean over the same top-10 list used for diversity.
- **Coverage**: catalog coverage from the persisted top-K artifact, not the
  reranked list — `coverage@200 = |union of retrieved_article_ids across all
  evaluated val/test users| / |articles in that dataset|`. Directly reuses
  Q2/Q3's persisted artifacts.

## 4. Slicing

Cold-start vs. warm as the required slice — zero extra engineering, reuses
Q2's `coldstart_users` sets directly (0 EB-NeRD / 2,122 MIND). Head vs. tail
as an optional addition — train-split click counts computed from
`article_ids_clicked.explode()` on the `train` split (no dependency on
EB-NeRD's `total_pageviews`, not in the unified schema). Verified skew:
MIND's top 20% of ever-clicked articles account for 90.2% of train clicks
(median 2 clicks/article, max 4,316); EB-NeRD is more moderate (49.2% from
the top 20%). Head = top 20% by train-click-count among ever-clicked
articles; tail = everything else, including never-clicked articles.

## 5. Bootstrap 95% CI

Resample impressions (the natural per-impression evaluation unit here), not
users. Precompute the array of per-impression metric values once per
`(dataset, method, split, metric)`; for 1,000 iterations, draw `len(array)`
indices with replacement, take the mean, collect; report the 2.5th/97.5th
percentiles as the CI alongside the mean of the original array as the point
estimate. Computationally trivial at this scale (well under a second even
for MIND's ~70K-impression test split).

## 6. Uniform evaluation interface

One function/class, `evaluate(dataset, method, split, score_inview_fn) ->
dict`, iterating a split's impressions via the shared `score_inview_fn`
signature for ranking metrics, separately reading
`bm25_topk.parquet`/`embedding_topk.parquet` for recall@K and coverage
(zero method-specific branching there, since the two are schema-identical),
slicing, then bootstrapping CIs. Only the `score_inview_fn` adapter differs
per method.

## 7. Anti-gaming (Q9) tie-in

Confirmed directly — `behaviors.parquet`'s columns are exactly
`impression_id, dataset, user_id, impression_time, article_ids_inview,
article_ids_clicked, session_id, split`; `history.parquet`'s are `user_id,
dataset, article_id_sequence, timestamp_sequence, read_time_sequence,
scroll_percentage_sequence`. No `next_read_time` / `next_scroll_percentage`
or other look-ahead field was carried into the unified schema (Q1 already
excluded them). `read_time_sequence` / `scroll_percentage_sequence`
describe past, pre-window clicks used for user representation, not the
current impression's outcome — legitimate features, not leakage. There is
nothing in the current schema for a "with vs. without unavailable features"
comparison to toggle; this is stated as a one-line confirmation in the
harness output, not built as a separate mechanism.

## 8. Implementation shape

`src/cs4406m26_assignment1c1/evaluation.py` — pure metric functions
(`auc_impression`, `mrr`, `ndcg_at_k`, `bootstrap_ci`, `intra_list_diversity`,
`novelty`, `coverage`), reusable/unit-testable like `bm25.py` but without a
raw-performance requirement, just correctness.

`src/evaluation_harness.ipynb` + `evaluation_harness.py`:

1. Setup — rebuild BM25 indexes, load `article_embeddings.parquet`.
2. Metric-formula smoke tests — hand-computed toy rankings with known
   expected AUC/MRR/nDCG@5/@10 values.
3. `score_inview` adapters for BM25 and embeddings + test — uniform
   signature, no NaN.
4. Per-impression ranking metrics + test — value ranges,
   `n_evaluated + n_excluded == n_total`.
5. Beyond-accuracy metrics + test — ILD ∈ [0,1] and 0 for an
   identical-category list; novelty ≥ 0; coverage ∈ [0,1].
6. Slicing + test — complete, non-overlapping partition.
7. Bootstrap CI + test — `lo ≤ point ≤ hi`.
8. Anti-gaming confirmation cell (§7) — schema-column assertion, not new
   engineering.
9. Persist `data/processed/{dataset}/eval_metrics.json`
   (`{method: {split: {slice: {metric: {point, ci_lo, ci_hi}}}}}`) +
   round-trip test.

# Q5 — Codabench Submission

Both competition pages (`codabench.org/competitions/13967` and `.../2469`)
are JS-rendered and require a logged-in session to view — the exact
submission file format (columns, delimiter, zip structure) could not be
verified from this environment and must be confirmed manually against each
competition's "Submission"/starter-kit materials after registering, before
writing the final serializer.

What's implementation-ready without that: a prediction generator built on
Q4's existing infrastructure rather than new one-off code, since Codabench
submissions are themselves a ranking of each impression's actual candidate
set — the same re-ranking framing as Q4's AUC/MRR/nDCG, not Q2/Q3's
full-catalog retrieval.

`generate_predictions(dataset, method, split="test") -> DataFrame`: iterates
the test split's impressions, calls the same `score_inview_fn` adapter Q4
defines, and outputs one row per impression with candidates ranked by score
— shape `impression_id, ranked_article_ids` pending the real column
names/format once confirmed. `method` selects whichever of BM25/embedding
scored better in Q4's comparison for that dataset, or both if the design
note wants to show a comparison.

Registration on both leaderboards is a manual, one-time action (not
implementable) that must happen before submission; leaderboard screenshots
go into the design note (Q6) once submitted.

# Q6 — Design Note

Lives at `design_note.tex` (LaTeX skeleton already in the repo:
Introduction/Design/Discussion sections, currently empty) → `design_note.pdf`,
≤4 pages. Content maps onto the existing skeleton:

- **Introduction**: scope — both datasets, what pipeline stages were built
  (Q1–Q5).
- **Design**: per-question summary of what was built and key choices, one
  subsection per Q1–Q5, each pulling its "why" directly from the
  corresponding `SPEC.md` section (which already documents alternatives
  considered and why — e.g. Q2's rank_bm25-vs-hand-rolled story, Q3's
  embedding-source decision) rather than re-deriving that reasoning from
  scratch.
- **Discussion**: experimental observations — the Q3 lexical-vs-semantic
  comparison table (recall@K by method/slice), dataset differences (EB-NeRD
  vs. MIND: language, cold-start prevalence, popularity skew — numbers
  already computed in Q2–Q4), leaderboard screenshots (Q5), and a scale
  analysis ("where does this break at 10×") — concrete candidates already
  identified while building Q1–Q4, not hypothetical: Q1's per-user Python
  loops when building MIND's history table; Q2/Q3's per-user retrieval loops
  (already required batching to stay fast at current scale — a 10×
  corpus/user count would need this re-benchmarked, not assumed fine); the
  brute-force embedding similarity matrix (~17GB at current MIND scale — 10×
  users would need it, or the batch size, reconsidered); single-machine
  pandas/parquet I/O as a ceiling before a real feature store (e.g. a
  database or distributed format) would be needed.

# Q7 — Deliverables

Checklist against Q7's four required items, tracking what already exists:

1. Code (GitHub Classroom): reproducible pipeline (`build_pipeline.py`),
   retrieval/eval code (`bm25_retrieval.py`, plus `embedding_retrieval.py` /
   `evaluation_harness.py` once Q3/Q4 are implemented), prediction files
   (Q5), `README.md` with one-command-reproduce sections per stage (already
   the pattern for Q1/Q2, extend per stage as it lands). `.gitignore`
   excludes `data/` and raw dataset directories (done in Q1).
2. Design note: `design_note.tex`/`.pdf` (skeleton exists; content per Q6).
3. Leaderboard screenshots: pending Q5 (manual, post-submission).
4. AI usage log: `PROMPTS.md` (already being maintained throughout this
   project as each significant prompt lands).

# Q8 — Git Commit Policy

Already followed: commits are per logical unit of work with descriptive
messages, `.gitignore` excludes large/generated files (`data/`, raw dataset
directories, `__pycache__/`), and no force-pushes have occurred. No
additional engineering needed — noted here only for completeness against
the assignment's checklist.

# Q9 — Anti-Gaming

Two requirements, both already satisfied by existing work rather than
needing new engineering:

- **No future-click leakage**: enforced and tested in Q1 (temporal split
  boundary test + the EB-NeRD history-timestamp / MIND history-consistency
  leakage tests, both passing on real data).
- **Report metrics with/without serving-time-unavailable features**: per
  Q4 §7's anti-gaming tie-in, the unified schema never carries EB-NeRD's
  look-ahead fields (`next_read_time`, `next_scroll_percentage`) in the
  first place, so there's nothing to toggle — stated as a confirmation in
  Q4's harness output, not a separate mechanism.
