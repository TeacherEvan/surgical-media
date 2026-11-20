"""job_store.py — durable on-disk job workspace.

Layout (``jobs/`` is gitignored)::

    jobs/<job_id>/job.json        immutable input snapshot
    jobs/<job_id>/state.json      current state (atomic replace)
    jobs/<job_id>/events.jsonl    append-only transition/event log
    jobs/<job_id>/artifacts/      storyboard, preview, audit, approval, package

``job_id`` is derived from the canonical request hash, so re-creating the same
request is idempotent. All paths are confined to the job directory.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from job_model import JobError, JobState, can_transition

DEFAULT_ROOT = Path("jobs")
_ID_RE = re.compile(r"^job-[0-9a-f]{12}$")
_ARTIFACT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def job_id_for(request: dict[str, Any]) -> str:
    digest = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()
    return f"job-{digest[:12]}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class JobStore:
    def __init__(self, root: Path = DEFAULT_ROOT) -> None:
        self.root = Path(root)

    # -- paths ---------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        if not _ID_RE.match(job_id):
            raise JobError(f"invalid job id: {job_id!r}")
        return self.root / job_id

    def artifact_path(self, job_id: str, name: str) -> Path:
        if not _ARTIFACT_RE.match(name) or ".." in name:
            raise JobError(f"invalid artifact name: {name!r}")
        return self.job_dir(job_id) / "artifacts" / name

    def exists(self, job_id: str) -> bool:
        return (self.job_dir(job_id) / "state.json").is_file()

    # -- lifecycle -----------------------------------------------------
    def create(self, request: dict[str, Any], state: JobState) -> str:
        """Create the job (idempotent: an existing job is returned untouched)."""
        job_id = job_id_for(request)
        d = self.job_dir(job_id)
        if self.exists(job_id):
            return job_id
        (d / "artifacts").mkdir(parents=True, exist_ok=True)
        _atomic_write(d / "job.json", json.dumps(request, indent=2) + "\n")
        _atomic_write(d / "state.json", json.dumps({"state": state.value}) + "\n")
        self.log(job_id, "created", {"state": state.value})
        return job_id

    def load_request(self, job_id: str) -> dict[str, Any]:
        try:
            data = json.loads((self.job_dir(job_id) / "job.json").read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JobError(f"cannot read job {job_id}: {exc}") from exc
        if not isinstance(data, dict):
            raise JobError(f"job {job_id}: job.json is not an object")
        return data

    def state(self, job_id: str) -> JobState:
        try:
            raw = json.loads((self.job_dir(job_id) / "state.json").read_text("utf-8"))
            return JobState(raw["state"])
        except (OSError, json.JSONDecodeError, KeyError, ValueError) as exc:
            raise JobError(f"cannot read state of {job_id}: {exc}") from exc

    def transition(
        self, job_id: str, dst: JobState, note: str = "", **extra: Any
    ) -> JobState:
        src = self.state(job_id)
        if not can_transition(src, dst):
            raise JobError(f"illegal transition {src.value} -> {dst.value}")
        _atomic_write(
            self.job_dir(job_id) / "state.json", json.dumps({"state": dst.value}) + "\n"
        )
        self.log(
            job_id,
            "transition",
            {"from": src.value, "to": dst.value, "note": note, **extra},
        )
        return dst

    # -- events & artifacts -------------------------------------------
    def log(
        self, job_id: str, event: str, detail: dict[str, Any] | None = None
    ) -> None:
        rec = {"ts": _now(), "event": event, **(detail or {})}
        with (self.job_dir(job_id) / "events.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(canonical_json(rec) + "\n")

    def events(self, job_id: str) -> list[dict[str, Any]]:
        p = self.job_dir(job_id) / "events.jsonl"
        if not p.is_file():
            return []
        return [json.loads(line) for line in p.read_text("utf-8").splitlines() if line]

    def write_json(self, job_id: str, name: str, data: Any) -> Path:
        path = self.artifact_path(job_id, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, json.dumps(data, indent=2) + "\n")
        return path

    def read_json(self, job_id: str, name: str) -> Any:
        path = self.artifact_path(job_id, name)
        try:
            return json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JobError(f"cannot read artifact {name}: {exc}") from exc
