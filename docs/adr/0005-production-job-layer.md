# ADR 0005 — Production job layer around the deterministic renderer

**Status:** Accepted (2026-11-21) · **Source:** `docs/plans/Surgical_Media_3.0_Master_Implementation_Plan.md` (Wave 0/1)

## Context

The renderer (`storyboard → render_engine → verify_output`) is deterministic and
QC-gated. The 3.0 proposal adds agent-operated production: intake, planning,
review, approval, packaging. The proposal itself requires a repository audit first
([`docs/audits/initial-baseline.md`](../audits/initial-baseline.md)) and forbids
duplicating existing capability.

## Decision

1. **Wrap, don't restructure.** New flat modules in `scripts/` (`job_model`,
   `job_store`, `job_director`, `job_cli`) — no `src/` package, no moves.
2. **Renderer stays callable without the job layer.** The Director only imports
   `validate_storyboard`, `check_board_monetization`, `build_kit`, and shells out to
   `render_engine.py` / `verify_output.py` (list-form argv, `timeout=`).
3. **Framework-neutral agent contract.** File in / file out JSON; the Director never
   calls an LLM. `SKILL.md` metadata mentions Hermes but no code depends on it.
4. **Untrusted until validated.** Agent storyboards pass `validate_storyboard`
   (+ duration sanity) before the state advances; rejection leaves state unchanged.
5. **Prepare, never publish.** `export` writes `publish_kit.md` + `package.json`
   (`"published": false`). Human approval is mandatory and bound to the video hash.
6. **Durable + idempotent.** `job_id` = hash of the canonical request; atomic state
   writes; append-only `events.jsonl`; ids/artifact names are regex-confined.
7. **Budget gate.** `Director.charge` refuses spend above `budget.maximum_cost`
   (no paid providers exist yet; the hook is ready for Wave 3 adapters).
8. **Media policy unchanged:** procedural + open-licensed only (no external AI media
   providers) until the owner decides otherwise.

## Consequences

- Deferred (explicitly not built): research/claim registry, Audio/Visual Directors,
  provider adapters, visual QA, originality, HTTP API, publishing adapters.
- `examples/jobs/` holds job requests (not `examples/*.json`, which gates 1/7 treat
  as storyboards). Gate 11 validates them against `schemas/production_job.schema.json`.
- `jobs/` is gitignored runtime state.
