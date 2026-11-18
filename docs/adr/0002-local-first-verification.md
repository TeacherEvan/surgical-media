# ADR 0002 — Local-first verification; no hosted CI by default

**Date:** 2026-11-18
**Status:** Accepted
**Supersedes:** the GitHub Actions workflow removed in the same commit series (`f85ac09`).

## Context

> **Update 2026-11-19 (v1.3.0):** the gate set grew to 9 gates — `mypy --strict` was inserted as gate 4 (the whole `scripts/` tree is annotated; zero issues enforced) — and the suite grew to 302 tests via `tests/test_fallback_paths.py`. The 285-test / 8-gate description below is the original 2026-11-18 snapshot of this decision.

`surgical-media` is a solo-maintained public skill repo. Since v1.1.0 its GitHub
Actions jobs had never run: the account is billing-locked, so every job was
rejected before start. The repo still showed a permanent red check, which
is worse than no check — it trains observers to ignore failures and implies a
verification signal that does not exist. An optional GitLab mirror
(`.gitlab-ci.yml`) was committed as of `f43194c` but has **never executed**;
it is configured, not verified.

The pipeline is verifiable in about 60–90 seconds on a maintainer machine:
`bash scripts/ci_gates.sh` runs storyboard validation → ruff → format check →
285 tests → JSON Schema metaschema → example-vs-schema validation → thumbnail
smoke gate → draft render + ffprobe QC.

## Decision

1. **GitHub Actions is removed.** Hosted verification exists only as the
   optional GitLab mirror running the same `scripts/ci_gates.sh` on import.
2. **Local gates are the enforced standard.** "Green" means: on the machine
   that changed the repo, `bash scripts/ci_gates.sh` exited 0 on the exact
   commit being pushed. AGENTS.md, README.md and CHANGELOG.md encode this.
3. **No claim of hosted CI anywhere** until a hosted pipeline actually passes;
   at that point the mirror's status line flips and branch protection can
   require it before merging.

## Consequences

- There is no external machine enforcing the gate. Pre-push discipline is
  maintainer responsibility; AGENTS.md is the contract.
- External contributors (if the repo ever draws them) need the same local
  toolchain (Python ≥ 3.10, Pillow, ffmpeg, ruff, pytest, check-jsonschema)
  — all documented in README.md and installable without network services.
- When GitHub billing clears or the GitLab pipeline passes N consecutive
  runs, this ADR is superseded by re-adding a hosted required check (and
  enabling branch protection on `main`).

## Alternatives considered

- **Keep a permanently red GitHub workflow** — rejected: a red badge that
  never runs teaches nothing and misleads everyone, including the maintainer.
- **Require the GitLab mirror before calling the repo verified** — rejected
  until it runs; an unverified gate is worse than an honest local one.
- **Self-hosted runner** — rejected: setup and maintenance burden exceeds a
  60–90 s local gate for a solo repo.
