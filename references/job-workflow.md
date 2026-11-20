# Job workflow (3.0 job layer)

```text
job.json ──create──▶ VALIDATED ──plan──▶ SCRIPTING ──submit(storyboard)──▶ STORYBOARD_READY
   ──preview──▶ RENDERING ─▶ QC_PENDING ──audit──▶ REVIEW_PENDING ──approve──▶ APPROVED ──export──▶ PACKAGED
```

Failure paths: render failure → `FAILED`; audit failure or reviewer rejection →
`REJECTED` (→ `SCRIPTING` for rework); `cancel` from any non-terminal state.

```bash
python3 scripts/job_cli.py validate examples/jobs/horse_tenny.json
ID=$(python3 scripts/job_cli.py create examples/jobs/horse_tenny.json)
python3 scripts/job_cli.py plan $ID        # writes jobs/$ID/artifacts/agent_request.json
# agent produces storyboard.json from the brief …
python3 scripts/job_cli.py submit $ID --storyboard board.json
python3 scripts/job_cli.py preview $ID     # draft render
python3 scripts/job_cli.py audit $ID       # verify_output + monetization_gate
python3 scripts/job_cli.py approve $ID --reviewer "Name"
python3 scripts/job_cli.py export $ID      # publish_kit.md + package.json (never publishes)
```

Exit codes: `0` ok, `1` validation/audit failure, `2` job error (bad id, illegal
transition, gate). Contract: `schemas/production_job.schema.json`; runtime mirror
`scripts/job_model.py`. Design record: `docs/adr/0005-production-job-layer.md`.

A passing audit is technical + rights/ad-safety only. It is **not** an editorial
review and never a monetization guarantee; human approval is separate and mandatory.
