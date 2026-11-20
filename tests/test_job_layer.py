"""Job layer: model, store, director, CLI (offline; render/QC runner is faked)."""

from __future__ import annotations

import copy
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from job_cli import main as cli_main
from job_director import Director
from job_model import (
    TERMINAL,
    TRANSITIONS,
    JobError,
    JobState,
    can_transition,
    validate_request,
)
from job_store import JobStore, job_id_for
from storyboard import total_duration

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_JOB = ROOT / "examples" / "jobs" / "horse_tenny.json"
BOARD = json.loads((ROOT / "examples" / "tri_archetype_storyboard.json").read_text())


def _request(**over: Any) -> dict[str, Any]:
    req = json.loads(EXAMPLE_JOB.read_text())
    req["target_duration_seconds"] = round(total_duration(BOARD))
    req.update(over)
    return req


def _fake_runner(rc: int = 0) -> Any:
    def run(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        if "--output" in argv:
            Path(argv[argv.index("--output") + 1]).write_bytes(b"fake-mp4")
        return subprocess.CompletedProcess(argv, rc, stdout="{}", stderr="boom")

    return run


@pytest.fixture
def director(tmp_path: Path) -> Director:
    return Director(JobStore(tmp_path / "jobs"), runner=_fake_runner())


def _to_review(d: Director) -> str:
    jid = d.create(_request())
    d.plan(jid)
    board = d.store.job_dir(jid).parent / "board.json"
    board.write_text(json.dumps(BOARD))
    assert d.submit(jid, board) == []
    d.preview(jid)
    return jid


# -- model ---------------------------------------------------------------
def test_example_job_is_valid() -> None:
    assert validate_request(json.loads(EXAMPLE_JOB.read_text())) == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("topic"),
        lambda r: r.update(profile="gossip"),
        lambda r: r.update(platforms=["myspace"]),
        lambda r: r.update(platforms=[]),
        lambda r: r.update(target_duration_seconds=1),
        lambda r: r.update(target_duration_seconds=999),  # > shorts cap (180s)
        lambda r: r.update(approval_policy="none"),
        lambda r: r.update(budget={"currency": "usd", "maximum_cost": 1}),
        lambda r: r.update(budget={"currency": "USD", "maximum_cost": -1}),
        lambda r: r.update(surprise=True),
        lambda r: r.update(schema_version="9"),
    ],
)
def test_bad_requests_rejected(mutate: Any) -> None:
    req = json.loads(EXAMPLE_JOB.read_text())
    mutate(req)
    assert validate_request(req)


def test_non_object_rejected() -> None:
    assert validate_request([]) == ["top level must be a JSON object"]


def test_schema_runtime_parity() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads((ROOT / "schemas" / "production_job.schema.json").read_text())
    good = json.loads(EXAMPLE_JOB.read_text())
    jsonschema.validate(good, schema)
    for key, val in [("profile", "gossip"), ("platforms", ["myspace"]), ("x", 1)]:
        bad = copy.deepcopy(good)
        bad[key] = val
        assert validate_request(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, schema)


def test_transition_table_is_closed() -> None:
    assert set(TRANSITIONS) == set(JobState)
    assert all(not TRANSITIONS[s] for s in TERMINAL)
    assert can_transition(JobState.VALIDATED, JobState.SCRIPTING)
    assert not can_transition(JobState.DRAFT, JobState.APPROVED)


# -- store ---------------------------------------------------------------
def test_create_is_idempotent_and_survives_restart(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    req = _request()
    jid = store.create(req, JobState.VALIDATED)
    assert jid == job_id_for(req) == store.create(req, JobState.DRAFT)
    store.transition(jid, JobState.SCRIPTING)
    again = JobStore(tmp_path)  # new process, same disk
    assert again.state(jid) is JobState.SCRIPTING
    assert again.load_request(jid) == req
    assert [e["event"] for e in again.events(jid)] == ["created", "transition"]


def test_illegal_transition_blocked(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    jid = store.create(_request(), JobState.VALIDATED)
    with pytest.raises(JobError, match="illegal transition"):
        store.transition(jid, JobState.APPROVED)
    assert store.state(jid) is JobState.VALIDATED


@pytest.mark.parametrize("bad", ["../etc", "job-xyz", "", "job-" + "0" * 12 + "/x"])
def test_job_id_traversal_rejected(tmp_path: Path, bad: str) -> None:
    with pytest.raises(JobError):
        JobStore(tmp_path).job_dir(bad)


def test_artifact_name_traversal_rejected(tmp_path: Path) -> None:
    store = JobStore(tmp_path)
    jid = store.create(_request(), JobState.VALIDATED)
    for name in ("../job.json", "a/b", ".hidden", "x..y/../z"):
        with pytest.raises(JobError):
            store.artifact_path(jid, name)


# -- director ------------------------------------------------------------
def test_invalid_request_fails_before_any_work(director: Director) -> None:
    with pytest.raises(JobError, match="invalid job request"):
        director.create(_request(profile="gossip"))
    assert not any(director.store.root.glob("job-*"))


def test_invalid_agent_storyboard_rejected_state_unchanged(director: Director) -> None:
    jid = director.create(_request())
    director.plan(jid)
    bad = director.store.root / "bad.json"
    bad.write_text(json.dumps({"scenes": []}))
    assert director.submit(jid, bad)
    assert director.store.state(jid) is JobState.SCRIPTING
    assert director.store.events(jid)[-1]["event"] == "storyboard_rejected"


def test_unreadable_storyboard_rejected(director: Director) -> None:
    jid = director.create(_request())
    director.plan(jid)
    assert director.submit(jid, director.store.root / "missing.json")


def test_duration_far_from_target_rejected(director: Director) -> None:
    jid = director.create(_request(target_duration_seconds=170))
    director.plan(jid)
    p = director.store.root / "b.json"
    p.write_text(json.dumps(BOARD))
    assert any("far from target" in e for e in director.submit(jid, p))


def test_submit_requires_plan(director: Director) -> None:
    jid = director.create(_request())
    with pytest.raises(JobError):
        director.submit(jid, director.store.root / "x.json")


def test_plan_is_idempotent(director: Director) -> None:
    jid = director.create(_request())
    assert director.plan(jid) == director.plan(jid)
    assert director.create(_request()) == jid


def test_full_happy_path(director: Director) -> None:
    jid = _to_review(director)
    assert director.store.state(jid) is JobState.QC_PENDING
    report = director.audit(jid)
    assert report["ok"], report
    assert director.store.state(jid) is JobState.REVIEW_PENDING
    with pytest.raises(JobError, match="APPROVED"):
        director.export(jid)  # approval gate
    director.approve(jid, "Evan")
    kit = director.export(jid)
    assert kit.is_file()
    pkg = director.store.read_json(jid, "package.json")
    assert pkg["published"] is False
    assert director.store.state(jid) is JobState.PACKAGED


def test_failed_render_marks_job_failed(tmp_path: Path) -> None:
    d = Director(JobStore(tmp_path), runner=_fake_runner(rc=1))
    jid = d.create(_request())
    d.plan(jid)
    p = tmp_path / "b.json"
    p.write_text(json.dumps(BOARD))
    d.submit(jid, p)
    with pytest.raises(JobError, match="render failed"):
        d.preview(jid)
    assert d.store.state(jid) is JobState.FAILED


def test_failed_qc_rejects_job(tmp_path: Path) -> None:
    d = Director(JobStore(tmp_path), runner=_fake_runner())
    jid = _to_review(d)
    d.runner = _fake_runner(rc=1)
    assert d.audit(jid)["ok"] is False
    assert d.store.state(jid) is JobState.REJECTED


def test_reject_then_rework(director: Director) -> None:
    jid = _to_review(director)
    director.audit(jid)
    director.approve(jid, "Evan", approve=False)
    assert director.store.state(jid) is JobState.REJECTED
    director.store.transition(jid, JobState.SCRIPTING)  # rework allowed


def test_reviewer_required(director: Director) -> None:
    jid = _to_review(director)
    director.audit(jid)
    with pytest.raises(JobError, match="reviewer"):
        director.approve(jid, "  ")


def test_export_blocked_if_video_changed_after_approval(director: Director) -> None:
    jid = _to_review(director)
    director.audit(jid)
    director.approve(jid, "Evan")
    director.store.artifact_path(jid, "preview.mp4").write_bytes(b"tampered")
    with pytest.raises(JobError, match="re-audit"):
        director.export(jid)


def test_budget_enforced(director: Director) -> None:
    jid = director.create(_request(budget={"currency": "USD", "maximum_cost": 1.0}))
    assert director.charge(jid, 0.6, "tts") == pytest.approx(0.6)
    with pytest.raises(JobError, match="budget exceeded"):
        director.charge(jid, 0.6, "image")
    assert director.store.read_json(jid, "usage.json")["total"] == pytest.approx(0.6)
    with pytest.raises(JobError):
        director.charge(jid, -1, "bad")


def test_cancel(director: Director) -> None:
    jid = director.create(_request())
    director.cancel(jid)
    assert director.store.state(jid) is JobState.CANCELLED
    with pytest.raises(JobError):
        director.plan(jid)


# -- CLI -----------------------------------------------------------------
def test_cli_validate_and_create_status(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = ["--root", str(tmp_path / "jobs")]
    assert cli_main(["validate", str(EXAMPLE_JOB)]) == 0
    job_file = tmp_path / "job.json"
    job_file.write_text(json.dumps(_request()))
    assert cli_main([*root, "create", str(job_file)]) == 0
    jid = capsys.readouterr().out.strip().splitlines()[-1]
    assert cli_main([*root, "status", jid]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "VALIDATED"


def test_cli_error_exit_codes(tmp_path: Path) -> None:
    root = ["--root", str(tmp_path / "jobs")]
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    assert cli_main(["validate", str(bad)]) == 1
    assert cli_main([*root, "create", str(bad)]) == 2
    assert cli_main([*root, "status", "job-000000000000"]) == 2
    assert cli_main(["validate", str(tmp_path / "nope.json")]) == 2
