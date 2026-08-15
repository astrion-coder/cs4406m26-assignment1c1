# PROMPTS.md

Log of prompts that materially shaped the project's design or implementation, per
`CLAUDE.md`. Each entry: the prompt (paraphrased where long), why it mattered, and
what was done in response.

---

### "read the @assignments/ folder and look at the assignment there. Understand the tasks we have to do before the 27th Aug deadline."

Kicked off the project. Claude read `assignments/Assignment1_v1.pdf` in full and
produced a roadmap covering all of Q1–Q9 (data pipeline, BM25, embeddings, eval
harness, Codabench submissions, design note, git/anti-gaming policy), then asked
one clarifying question about build order (both datasets together vs. one dataset
fully first) before locking in a plan.

### "doesnt the assignment require us to build a common pipeline for both datasets in Q1 and then combine them both and then do Q2-Q6? I am not quite sure, just verify once"

Important correction-seeking prompt. Re-reading Q1's exact wording ("unified
schema") together, we confirmed the assignment wants **one shared schema/codebase**
that's run separately per dataset — not a merged corpus — since MIND and EB-NeRD
have disjoint languages/users/IDs and Q5 requires two separate Codabench
submissions. This reshaped the whole Q1 design: dataset-namespaced IDs, per-dataset
output directories, generic pipeline code parameterized by dataset.

### "ok lets focus on Q1 for now, create a plan and write the details to SPEC.md for Q1 only"

Scoped the work down to Q1 only and asked for a written spec (`SPEC.md`) instead of
just an in-chat plan. Claude designed the unified schema (three tables:
`articles`/`behaviors`/`history`), computed the actual temporal-split cutoffs by
reading real timestamps off both datasets' raw files, and defined the feature-store
layout and one-command-rebuild mechanism, all written to `SPEC.md`.

### "Should we leave the body column for now and proceed with the assignment or do we have to scrape the data manually as well...?" (re: MIND's missing article body text)

Confirmed MIND's `body` field should stay permanently null (not scraped) — Q2/Q3
only require title+abstract, MSN's article URLs are dead, and scraping would break
Q1's reproducibility requirement. `SPEC.md`'s `articles` schema already modeled
`body` as nullable for exactly this reason.

### "Start implementing SPEC.md then"

Implemented `SPEC.md` end-to-end: built `src/build_pipeline.ipynb` (unify → split →
leakage tests → write feature store, following the project's markdown/feature/test
cell convention) and `build_pipeline.py` as the one-command rebuild entrypoint.
While validating the design against real data, found and fixed two issues the spec
hadn't anticipated: (1) the originally-planned MIND leakage check (history vs.
inview disjointness) doesn't hold on real data — ~11% of users legitimately have
overlap — so it was replaced with the invariant that does hold (one consistent
`history` string per user); (2) MIND's `train`/`dev` files both restart
`impression_id` at 1, so concatenating them without a source tag silently created
duplicate IDs — fixed by namespacing on `source_split` too. Ran the full pipeline
to completion against real data; all cell-level tests pass and
`data/processed/{ebnerd,mind}/` was produced correctly.

### "wait for a lot of these tables, I can see that the values are either NA or None, why are they different? also if the values are NA or None, why add them in the final schema at all?"

Good catch on an actual inconsistency: MIND's `body`/`session_id` were built with
pandas' `"string"` extension dtype (missing → `<NA>`), while MIND's history
sequence columns were plain `object` (missing → `None`) — two different missing
markers for the same underlying reason (dataset-wide absence), with no real
justification for the difference. Standardized on plain `None` everywhere (kept
`NaT` for `published_time`, which is the legitimate, standard datetime-missing
marker). Also explained why these all-null-for-one-dataset columns stay in the
schema at all: they're not null in general, only null in MIND's instance of a
shared schema — dropping them would break the "one unified schema, run per
dataset" design from the earlier Q1-scope clarification, and `session_id` /
`timestamp_sequence` map directly to the assignment's "session context" and
"recency/decay" requirements.

### "wait you didnt modify @build_pipeline.ipynb with this None edit"

Caught a real mistake: the fix above was made in the notebook-generator script and
the *parquet output* was re-verified as correct, but the actual notebook source
cells hadn't been regenerated yet — the parquet round-trip through
`pd.read_parquet` silently downcasts the `"string"` extension dtype's `<NA>` back
to plain `None`, which is what made the stale notebook's output look already
fixed. Re-ran the generator and confirmed the notebook source itself, not just the
downstream parquet file, now reflects the fix; re-executed the full pipeline to
confirm. Lesson: when verifying a source-code fix, check the source (or its
directly executed output), not a downstream artifact that can independently mask
the same symptom.

### "update SPEC.md with Q2 from the assignment"

Extended `SPEC.md` from Q1-only to also cover Q2 (BM25 lexical retrieval), design
only (no code yet). A Plan agent produced a fully hand-rolled BM25 design (own
inverted index, IDF, scoring) verified against real data — tokenization behavior
on Danish text, null rates, click-count distributions, per-split user counts.
Asked the user to choose between that hand-rolled approach (matches the
assignment's literal "build an inverted index" wording, no new dependency) and
using a library; **the user chose the `rank-bm25` library** instead, so the spec
was rewritten around `BM25Okapi`, with an explicit honest note that the library
doesn't expose a true sparse inverted index internally (dense per-term numpy
scoring instead) — mitigated by adding an inspection step that surfaces the
library's internal `idf`/`doc_freqs`/`doc_len`/`avgdl` attributes as the index
artifact, rather than hiding the gap between the assignment's wording and the
chosen implementation.

### "don't add context like this in the SPEC.md. It should only contain the details of the implementation... this like current work, what the plan agent did, responses to AskUserQuestion, etc are not part of SPEC.md"

Important standing correction to how `SPEC.md` should read: it's a pure technical
spec, not a narrated log of the planning process. Rewrote the Q2 plan/content to
strip all meta-narrative ("the user chose", "a Plan agent verified", "this task
does X") and state every design decision as plain fact, matching Q1's existing
tone exactly. This distinction — process narrative belongs in the plan file or
`PROMPTS.md`, never in `SPEC.md` itself — applies to all future spec edits.

### "Start implementing Q2"

Implemented the (then rank-bm25-based) Q2 spec: added the dependency, built
`src/bm25_retrieval.ipynb`, and ran it. It never finished — killed after 10
minutes. Benchmarked the actual bottleneck rather than guessing: a single
`BM25Okapi.get_scores` call on MIND's 65k-article corpus took ~2.9 seconds,
because the library does a Python-level dict lookup across every document per
query token instead of a sparse postings lookup — at ~70,000 required calls
(once per val/test user), that's 40+ hours. Fixed by building a real
postings-list inverted index (`term -> (doc_idx, tf)` arrays, scored via
`numpy`'s `np.add.at`), sourcing `idf`/`doc_len`/`avgdl` from the fitted
library object for cross-checking — measured at ~5ms/call, a ~1000x speedup.

### "ok do one thing, dont use rank_bm25, do a simple from scratch implementation of bm25, in module format, and see if it is faster or not"

Given the library was already reduced to just supplying statistics (the actual
scoring was hand-built for performance), the user asked to drop it entirely
and reimplement BM25 fully from scratch, as a proper importable module rather
than notebook cells — a deliberate exception to the project's usual
"all code in notebooks" rule for this one reusable, performance-sensitive
component. Built `src/cs4406m26_assignment1c1/bm25.py` (postings index, IDF,
scoring, top-K), benchmarked it standalone (~5ms/query on MIND, matching the
hybrid approach's speed), confirmed with the user before wiring it into the
notebook, then removed the `rank-bm25` dependency, rewrote
`src/bm25_retrieval.ipynb` and `SPEC.md`'s Q2 section around it, and reran the
full pipeline successfully (all test cells pass; recall@K monotonic and
bounded in [0,1] for both datasets).

### "Update SPEC.md with specs for all the other Qs in the assignment"

Extended `SPEC.md` from Q1+Q2 to cover Q3–Q9, design only (no code). A Plan
agent designed Q3 (embeddings) and Q4 (eval harness) together, verified
against real data throughout — e.g. it identified and measured that Q4's
AUC/MRR/nDCG can't reuse Q2/Q3's persisted top-K lists (candidate-generation
framing) and instead need an on-the-fly re-scoring adapter over each
impression's own `article_ids_inview` (re-ranking framing) — a real
reconciliation between the two question's evaluation setups, not just style
matching. The user was asked to pick Q3's embedding-source strategy (EB-NeRD
has provided pretrained artifacts, MIND has none) and chose one uniform
method for both datasets over an asymmetric or Colab-deferred approach.
Q5 (Codabench submission) needed external research — fetched both
competition pages directly rather than guessing a submission format; both
turned out to be JS-rendered SPAs requiring a login to see, so the spec
states that limitation explicitly instead of inventing a plausible-looking
format. Also noticed `design_note.tex`/`.pdf` already existed in the repo
(not created by this session) and grounded Q6's spec in that existing
skeleton rather than proposing a new location.

### "Start implementing Q3"

Before installing anything, asked whether to proceed with the planned
`sentence-transformers`+`torch` local benchmark (per SPEC.md's Q3 draft) or
skip to the lighter TF-IDF+SVD fallback. The user redirected entirely: don't
benchmark locally at all — build a Colab notebook that computes the
embeddings on a GPU there, downloaded back and placed locally, so the local
machine only ever does inference/retrieval math, never model
training/encoding. This matches `CLAUDE.md`'s own tech-stack note (heavy
compute belongs in Colab) better than the original local-benchmark plan did.
Built `src/compute_embeddings_colab.ipynb` (upload articles.parquet for both
datasets, encode with a GPU-loaded multilingual XLM-RoBERTa-based model,
download the resulting embeddings) with step-by-step usage instructions
inline and in `README.md`; syntax-checked every code cell since it can't be
executed locally (needs `google.colab` + a GPU). Rewrote SPEC.md's Q3 #1
around this split: Colab computes embeddings (no local speed constraint,
since GPU removes the concern that drove Q2's benchmark-first discipline),
local repo stays at zero new ML dependencies and only reads the resulting
parquet files.

### "why are the embeddings in .parquet format? shouldnt they be in .vec format?"

A genuine format-choice question, not a correction — explained the tradeoff
(parquet: consistent with every other artifact this pipeline produces,
typed/schema-enforced, carries the extra `dataset` column naturally; `.vec`:
the standard word2vec-style IR interchange format, human-greppable, and what
MIND's own provided KG embeddings happen to use — though that's just the
legacy format Microsoft's original TransE tooling exported, not a convention
this project chose, and those files aren't even used per Q3's design) and
asked whether there was a specific downstream interoperability reason (e.g.
loading into `gensim`) before proposing to actually change it. The user's
next message moved on to a different, larger change (Colab → Kaggle) instead
of answering this, so the format stayed parquet — worth re-raising if it
resurfaces.

### "ok nvm i wont use colab, i'll use kaggle, so modify everything accordingly"

Platform swap for Q3's hosted-GPU embedding step: replaced
`src/compute_embeddings_colab.ipynb` with `src/compute_embeddings_kaggle.ipynb`
(deleted the old file rather than leaving both). Worked out the real
mechanical differences rather than assuming Kaggle mirrors Colab's API —
Kaggle has no in-notebook upload/download calls (`google.colab.files.*`);
input comes from a Dataset attached via "+ Add Data" under
`/kaggle/input/...` before the notebook runs, and output is anything written
to `/kaggle/working/`, downloaded from the run's Output tab after "Save &
Run All". Also swapped GPU/internet setup instructions (Kaggle's Internet
toggle defaults off, unlike Colab, and is required for the `pip install` +
model download to work). Updated `SPEC.md` Q3 #1/#7 and `README.md`'s Q3
section to match, and grepped all three files afterward to confirm no
leftover Colab references remained.

### "I have dropped the output files at your specified location, now continue"

Verified the two Kaggle-computed `article_embeddings.parquet` files directly
before building anything on top of them (shape matches article counts, 768
dims, no NaNs, no duplicate IDs, article_id sets match `articles.parquet`
exactly) rather than assuming the hand-off worked. Built
`src/cs4406m26_assignment1c1/embeddings.py` (mean-pool, batched brute-force
cosine-similarity top-K) and benchmarked/sanity-checked it directly against
the real MIND embeddings before wiring it into a notebook — same discipline
as Q2. That benchmark surfaced a real, worth-understanding subtlety: a
same-query top-200 result and a separately-computed top-50 result didn't
match exactly. Root-caused it (not dismissed) — BLAS matrix multiplication
isn't bit-exact across different batch shapes, so near-tied cosine scores
(~6e-8 apart, float32 epsilon) can swap order between differently-shaped
calls; confirmed a single-call result matches a naive full sort exactly, so
the module itself is correct, and the real pipeline never compares across
separately-shaped calls anyway (it calls once at k=200, slices prefixes for
50/100). Documented the caveat in the function's docstring and designed the
notebook's nesting-invariant test to only ever compare same-shaped calls, so
it can't spuriously fail on this artifact. Built `src/embedding_retrieval.ipynb`
+ `embedding_retrieval.py` mirroring Q2's structure, including a cold-start
cross-check against Q2's already-persisted `bm25_metrics.json` (must match
exactly — same users, same criterion, independently recomputed in a separate
notebook) and a lexical-vs-semantic comparison table. Ran end-to-end
successfully; all 8 test cells pass, and the comparison table shows a
genuine mixed result (BM25 generally ahead, embeddings win on MIND's test
split at K=50) worth keeping for the design note.

### "modify the code based on updated CLAUDE.md" (re: new rule 4 — numeric claims need a one-command README verification)

`CLAUDE.md` gained a new rule: any numeric performance claim written into
`SPEC.md` must come with a command in `README.md` that reproduces it in one
shot. Audited `SPEC.md` for claims of that kind (a measured benchmark, not a
persisted metric already reproducible via the existing `build_pipeline.py`/
`bm25_retrieval.py`/`embedding_retrieval.py` commands) and found two: Q2 #1's
BM25 timing (`rank_bm25` vs. the from-scratch module) and Q3 #2's brute-force
matmul/top-K timing. Wrote `scripts/benchmark_bm25.py` and
`scripts/benchmark_embeddings.py`, ran both against the real feature store to
confirm the numbers are still in the right ballpark (BM25: ~2.8ms/query on
MIND, ~189s extrapolated; embeddings: 11.5s matmul + 19.0s top-K = 30.5s
total on MIND's full 65,173-user val/test population — both consistent with
`SPEC.md`'s claims), and documented both commands in `README.md` right after
their respective Q2/Q3 sections. The `rank_bm25` comparison itself isn't
re-run by the script since that dependency was deliberately removed; the
script benchmarks the shipped path only and notes how to re-add the library
if that specific comparison point needs re-verifying.

### "Finish Q4 in the spec"

Implemented Q4 (Offline Evaluation Harness) end-to-end from the design
already locked into `SPEC.md` — no new design decisions were open, so this
went straight to implementation rather than a plan/AskUserQuestion round.
Built `src/cs4406m26_assignment1c1/evaluation.py` (auc_impression, mrr,
ndcg_at_k, bootstrap_ci, intra_list_diversity, novelty, coverage — pure
functions, unit-tested against hand-computed toy values before touching real
data) and `src/evaluation_harness.ipynb` + `evaluation_harness.py`.

One real design gap had to be resolved during implementation, not just
transcribed from the spec: `score_inview` needs a defined score for
cold-start users (empty click history), but Q2/Q3's embedding path returns
nothing for a user with no mean-pooled vector. Resolved it by having both
adapters fall back to an all-zero score per inview item for a cold-start
user — BM25 already does this naturally (an empty query touches no
postings), so the embedding adapter was made to match. An all-zero vector
produces a well-defined but fully-tied ranking, which works out to exactly
AUC=0.5 by the rank-sum formula — confirmed on real data (MIND's cold-start
slice reports auc.point == 0.500 exactly, for both methods, both splits).
This is what makes cold-start-vs-warm a genuine *slice* for Q4's ranking
metrics (both groups get scored) rather than an *exclusion* like it is for
Q2/Q3's recall@K (a cold-start user literally has no query to retrieve
with). Also had to work out the efficient shape of `score_inview`: the outer
per-impression loop needed a uniform `(user_id, article_ids_inview) -> dict`
signature per SPEC.md, but a naive implementation would recompute BM25's
full-corpus `get_scores` on every impression; instead each split is
processed sorted by `user_id` and the BM25 adapter memoizes the last user's
score vector, so `get_scores` runs once per unique user (~72,591 total
across both datasets) rather than once per impression (~264K) — full
population caching was ruled out first (a full-corpus float vector per MIND
user would be ~26GB).

Ran the harness end-to-end (background, ~a few minutes given the per-user
BM25 rescoring volume) — all 11 test cells passed, including the cold-start
AUC=0.5 sanity check and a cross-check of head/tail popularity-skew figures
against SPEC.md's already-verified real-data numbers. A genuinely interesting
result for the design note: embeddings rank *better* than BM25 within each
impression's own inview candidates on both datasets (e.g. MIND test AUC
0.595 vs. 0.556), the opposite of Q2/Q3's recall@K where BM25 generally led
at full-catalog retrieval — the two framings measure different things
(finding vs. ranking) and don't have to agree.

Per `CLAUDE.md`'s numeric-claims-need-a-README-command rule, also wrote
`scripts/benchmark_bootstrap_ci.py` for Q4 #5's "well under a second" bootstrap
timing claim (measured: 0.47s for MIND's ~73K-impression test split, 1,000
iterations) and documented it in `README.md` alongside the new
"Run the offline evaluation harness (Q4)" section.
