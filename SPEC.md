# Q1 Spec — Reproducible Data Pipeline

Scope: **Q1 only** (unified schema, clean/parse, temporal split, feature store, one-command
rebuild). Q2–Q9 are out of scope for this document; see
`assignments/Assignment1_v1.pdf` and the approved roadmap in the session plan for how Q1
feeds into them.

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
