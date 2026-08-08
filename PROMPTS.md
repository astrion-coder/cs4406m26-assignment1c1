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
