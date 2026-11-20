"""job_model.py — production-job contract: request validation + lifecycle states.

Part of the 3.0 job layer (``docs/adr/0005-production-job-layer.md``). The renderer
stays callable without this layer; this module is stdlib-only and has no I/O.

The runtime validator mirrors ``schemas/production_job.schema.json`` (parity pinned
by ``tests/test_job_model.py``).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, TypeGuard

from platform_presets import PRESETS

SCHEMA_VERSION = "1.0.0"
PROFILES = ("comedy", "documentary", "education", "politics", "commercial")
APPROVAL_POLICIES = ("human_before_export",)
# Profiles that must never relax the approval gate (fail closed).
HIGH_RISK_PROFILES = frozenset({"politics", "commercial"})
REQUEST_KEYS = {
    "schema_version",
    "topic",
    "profile",
    "audience",
    "language",
    "target_duration_seconds",
    "platforms",
    "approval_policy",
    "budget",
    "creative_constraints",
}
REQUIRED_KEYS = (
    "schema_version",
    "topic",
    "profile",
    "target_duration_seconds",
    "platforms",
    "approval_policy",
    "budget",
)


class JobState(str, Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    SCRIPTING = "SCRIPTING"
    STORYBOARD_READY = "STORYBOARD_READY"
    RENDERING = "RENDERING"
    QC_PENDING = "QC_PENDING"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    PACKAGED = "PACKAGED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL = frozenset({JobState.PACKAGED, JobState.FAILED, JobState.CANCELLED})
_S = JobState
TRANSITIONS: dict[JobState, frozenset[JobState]] = {
    _S.DRAFT: frozenset({_S.VALIDATED, _S.CANCELLED}),
    _S.VALIDATED: frozenset({_S.SCRIPTING, _S.CANCELLED}),
    _S.SCRIPTING: frozenset({_S.STORYBOARD_READY, _S.FAILED, _S.CANCELLED}),
    _S.STORYBOARD_READY: frozenset(
        {_S.RENDERING, _S.SCRIPTING, _S.FAILED, _S.CANCELLED}
    ),
    _S.RENDERING: frozenset({_S.QC_PENDING, _S.FAILED, _S.CANCELLED}),
    _S.QC_PENDING: frozenset({_S.REVIEW_PENDING, _S.REJECTED, _S.CANCELLED}),
    _S.REVIEW_PENDING: frozenset({_S.APPROVED, _S.REJECTED, _S.CANCELLED}),
    _S.APPROVED: frozenset({_S.PACKAGED, _S.FAILED, _S.CANCELLED}),
    _S.REJECTED: frozenset({_S.SCRIPTING, _S.CANCELLED}),
    _S.PACKAGED: frozenset(),
    _S.FAILED: frozenset(),
    _S.CANCELLED: frozenset(),
}


class JobError(Exception):
    """Any rejected job operation (bad request, illegal transition, gate)."""


def can_transition(src: JobState, dst: JobState) -> bool:
    return dst in TRANSITIONS[src]


def _is_num(v: Any) -> TypeGuard[float]:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_request(data: Any) -> list[str]:
    """Return a list of error strings (empty == valid)."""
    if not isinstance(data, dict):
        return ["top level must be a JSON object"]
    errors: list[str] = []
    for key in sorted(set(data) - REQUEST_KEYS):
        errors.append(f"unknown field: {key}")
    for key in REQUIRED_KEYS:
        if key not in data:
            errors.append(f"missing required field: {key}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION!r}")
    topic = data.get("topic")
    if not isinstance(topic, str) or not 1 <= len(topic.strip()) <= 300:
        errors.append("topic must be a non-empty string (<= 300 chars)")
    if data.get("profile") not in PROFILES:
        errors.append(f"profile must be one of {list(PROFILES)}")
    dur = data.get("target_duration_seconds")
    if not _is_num(dur) or not 5 <= dur <= 3600:
        errors.append("target_duration_seconds must be a number in [5, 3600]")
    plats = data.get("platforms")
    if not isinstance(plats, list) or not plats:
        errors.append("platforms must be a non-empty array")
    else:
        for p in plats:
            if p not in PRESETS:
                errors.append(
                    f"unknown platform preset: {p!r} (known: {sorted(PRESETS)})"
                )
        if len(set(map(str, plats))) != len(plats):
            errors.append("platforms must not repeat")
        elif _is_num(dur):
            for p in plats:
                cap = PRESETS.get(p, {}).get("max_total_sec")
                if cap is not None and dur > cap:
                    errors.append(f"target_duration_seconds exceeds {p} max ({cap}s)")
    if data.get("approval_policy") not in APPROVAL_POLICIES:
        errors.append(f"approval_policy must be one of {list(APPROVAL_POLICIES)}")
    budget = data.get("budget")
    if not isinstance(budget, dict):
        errors.append("budget must be an object")
    else:
        for key in sorted(set(budget) - {"currency", "maximum_cost"}):
            errors.append(f"budget: unknown field: {key}")
        cur = budget.get("currency")
        if not isinstance(cur, str) or len(cur) != 3 or not cur.isupper():
            errors.append("budget.currency must be a 3-letter uppercase code")
        mx = budget.get("maximum_cost")
        if not _is_num(mx) or mx < 0:
            errors.append("budget.maximum_cost must be a number >= 0")
    for key in ("audience", "language"):
        if key in data and (not isinstance(data[key], str) or not data[key]):
            errors.append(f"{key} must be a non-empty string")
    cc = data.get("creative_constraints")
    if cc is not None and not isinstance(cc, dict):
        errors.append("creative_constraints must be an object")
    return errors
