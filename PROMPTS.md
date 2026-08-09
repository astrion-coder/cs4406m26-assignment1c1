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
