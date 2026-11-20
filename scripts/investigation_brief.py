"""investigation_brief.py — Stage 1 research-brief contract (claim-ID research).

Mirrors ``schemas/investigation_brief.schema.json`` (parity pinned by
``tests/test_investigation_brief.py``). Stdlib-only, no I/O.

The claim layer gives every verifiable fact a stable, hash-friendly
``claim_id``, a ``claim_type`` for risk weighting (satire/opinion are
lower-risk than factual/statistical claims), and an explicit
``contradictions`` cross-reference so conflicting research can be
flagged before scripting.
"""

from __future__ import annotations

import re
from typing import Any, TypeGuard

SCHEMA_VERSION = "1.0.0"
CLAIM_ID_RE = re.compile(r"^claim-[0-9a-f]{8}$")
CLAIM_TYPES = frozenset({"factual", "statistical", "anecdotal", "opinion", "satire"})
REQUEST_KEYS = {
    "schema_version",
    "subject",
    "sources",
    "facts",
    "visual_anchors",
    "visual_assets",
    "target_format",
}
REQUIRED_KEYS = (
    "schema_version",
    "subject",
    "facts",
    "visual_anchors",
    "target_format",
)
FACT_KEYS = {
    "claim",
    "source",
    "claim_id",
    "claim_type",
    "contradictions",
    "metric",
}
REQUIRED_FACT_KEYS = ("claim", "source", "claim_id", "claim_type")


class BriefError(Exception):
    """Rejected investigation brief (bad request or claim-graph violation)."""


def _is_num(v: Any) -> TypeGuard[float]:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_request(data: Any) -> list[str]:
    """Return a list of error strings (empty == valid).

    Runtime mirror of ``schemas/investigation_brief.schema.json``. Two-pass:
    pass one validates each fact and collects well-formed claim ids; pass two
    checks that every ``contradictions`` entry references a known claim id.
    """
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
    subject = data.get("subject")
    if not isinstance(subject, str) or not 1 <= len(subject.strip()) <= 300:
        errors.append("subject must be a non-empty string (<= 300 chars)")
    sources = data.get("sources")
    if sources is not None:
        if not isinstance(sources, list) or len(sources) > 20:
            errors.append("sources must be an array of at most 20 strings")
        else:
            for s in sources:
                if not isinstance(s, str) or not 1 <= len(s) <= 500:
                    errors.append(
                        "each source must be a non-empty string (<= 500 chars)"
                    )
    facts = data.get("facts")
    if not isinstance(facts, list):
        errors.append("facts must be an array")
    elif not 3 <= len(facts) <= 8:
        errors.append("facts must contain 3 to 8 items")
    else:
        valid_ids: set[str] = set()
        for i, fact in enumerate(facts):
            where = f"facts[{i}]"
            if not isinstance(fact, dict):
                errors.append(f"{where}: must be an object")
                continue
            for key in sorted(set(fact) - FACT_KEYS):
                errors.append(f"{where}: unknown field: {key!r}")
            for key in REQUIRED_FACT_KEYS:
                if key not in fact:
                    errors.append(f"{where}: missing required field: {key}")
            claim = fact.get("claim")
            if not isinstance(claim, str) or not 1 <= len(claim) <= 500:
                errors.append(
                    f"{where}: claim must be a non-empty string (<= 500 chars)"
                )
            source = fact.get("source")
            if not isinstance(source, str) or not 1 <= len(source) <= 500:
                errors.append(
                    f"{where}: source must be a non-empty string (<= 500 chars)"
                )
            cid = fact.get("claim_id")
            if not isinstance(cid, str) or not CLAIM_ID_RE.match(cid):
                errors.append(f"{where}: claim_id must match ^claim-[0-9a-f]{{8}}$")
            elif cid in valid_ids:
                errors.append(f"{where}: duplicate claim_id {cid!r}")
            else:
                valid_ids.add(cid)
            ctype = fact.get("claim_type")
            if ctype not in CLAIM_TYPES:
                errors.append(
                    f"{where}: claim_type must be one of {sorted(CLAIM_TYPES)}"
                )
            metric = fact.get("metric")
            if metric is not None and (
                not isinstance(metric, str) or len(metric) > 120
            ):
                errors.append(f"{where}: metric must be a string (<= 120 chars)")
        # pass two: contradictions must reference known claim ids
        for i, fact in enumerate(facts):
            if not isinstance(fact, dict):
                continue
            where = f"facts[{i}]"
            contra = fact.get("contradictions")
            if contra is None:
                continue
            if not isinstance(contra, list) or not all(
                isinstance(c, str) for c in contra
            ):
                errors.append(f"{where}: contradictions must be an array of strings")
                continue
            if len(set(contra)) != len(contra):
                errors.append(f"{where}: contradictions must not repeat")
            for ref in contra:
                if ref not in valid_ids:
                    errors.append(
                        f"{where}: contradictions references unknown claim_id {ref!r}"
                    )
    return errors
