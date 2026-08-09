# Assignment 1 Spec

Covers Q1 (reproducible data pipeline) and Q2 (lexical/BM25 candidate generation).
Q3–Q9 are out of scope for this document; see `assignments/Assignment1_v1.pdf`.

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
