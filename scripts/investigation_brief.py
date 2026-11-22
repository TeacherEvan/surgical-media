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

import math
import re
from typing import Any, TypeGuard

SCHEMA_VERSION = "1.0.0"
CLAIM_ID_RE = re.compile(r"^claim-[0-9a-f]{8}$")
CLAIM_TYPES = frozenset({"factual", "statistical", "anecdotal", "opinion", "satire"})
VISUAL_ARCHETYPES = frozenset({"geometry_rig", "doc_essay", "code_report", "mixed"})
TARGET_ASPECTS = frozenset({"16:9", "9:16", "1:1"})
TARGET_FPS = frozenset({24, 25, 30, 50, 60})
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
VISUAL_ANCHOR_KEYS = {"claim_index", "primitive", "archetype"}
REQUIRED_VISUAL_ANCHOR_KEYS = ("claim_index", "primitive")
VISUAL_ASSET_KEYS = {
    "file",
    "title",
    "creator",
    "license",
    "license_url",
    "source_url",
    "attribution",
}
REQUIRED_VISUAL_ASSET_KEYS = ("file", "license", "attribution")
TARGET_FORMAT_KEYS = {
    "aspect",
    "width",
    "height",
    "fps",
    "max_duration_sec",
    "platform",
}
REQUIRED_TARGET_FORMAT_KEYS = ("aspect",)


class BriefError(Exception):
    """Rejected investigation brief (bad request or claim-graph violation)."""


def _is_num(v: Any) -> TypeGuard[float]:
    return (
        isinstance(v, (int, float))
        and not isinstance(v, bool)
        and math.isfinite(float(v))
    )


def _is_int(v: Any) -> TypeGuard[int]:
    return isinstance(v, int) and not isinstance(v, bool)


def _validate_facts(facts: Any, errors: list[str]) -> int | None:
    if not isinstance(facts, list):
        errors.append("facts must be an array")
        return None
    if not 3 <= len(facts) <= 8:
        errors.append("facts must contain 3 to 8 items")
        return None
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
            errors.append(f"{where}: claim must be a non-empty string (<= 500 chars)")
        source = fact.get("source")
        if not isinstance(source, str) or not 1 <= len(source) <= 500:
            errors.append(f"{where}: source must be a non-empty string (<= 500 chars)")
        cid = fact.get("claim_id")
        if not isinstance(cid, str) or not CLAIM_ID_RE.match(cid):
            errors.append(f"{where}: claim_id must match ^claim-[0-9a-f]{{8}}$")
        elif cid in valid_ids:
            errors.append(f"{where}: duplicate claim_id {cid!r}")
        else:
            valid_ids.add(cid)
        if fact.get("claim_type") not in CLAIM_TYPES:
            errors.append(f"{where}: claim_type must be one of {sorted(CLAIM_TYPES)}")
        metric = fact.get("metric")
        if metric is not None and (not isinstance(metric, str) or len(metric) > 120):
            errors.append(f"{where}: metric must be a string (<= 120 chars)")
    for i, fact in enumerate(facts):
        if not isinstance(fact, dict):
            continue
        where = f"facts[{i}]"
        contra = fact.get("contradictions")
        if contra is None:
            continue
        if not isinstance(contra, list) or not all(isinstance(c, str) for c in contra):
            errors.append(f"{where}: contradictions must be an array of strings")
            continue
        if len(set(contra)) != len(contra):
            errors.append(f"{where}: contradictions must not repeat")
        for ref in contra:
            if ref not in valid_ids:
                errors.append(
                    f"{where}: contradictions references unknown claim_id {ref!r}"
                )
    return len(facts)


def _validate_visual_anchors(
    visual_anchors: Any, n_facts: int | None, errors: list[str]
) -> None:
    if not isinstance(visual_anchors, list):
        errors.append("visual_anchors must be an array")
        return
    if not 1 <= len(visual_anchors) <= 12:
        errors.append("visual_anchors must contain 1 to 12 items")
        return
    for i, anchor in enumerate(visual_anchors):
        where = f"visual_anchors[{i}]"
        if not isinstance(anchor, dict):
            errors.append(f"{where}: must be an object")
            continue
        for key in sorted(set(anchor) - VISUAL_ANCHOR_KEYS):
            errors.append(f"{where}: unknown field: {key!r}")
        for key in REQUIRED_VISUAL_ANCHOR_KEYS:
            if key not in anchor:
                errors.append(f"{where}: missing required field: {key}")
        claim_index = anchor.get("claim_index")
        if not _is_int(claim_index) or claim_index < 0:
            errors.append(f"{where}: claim_index must be a non-negative integer")
        elif n_facts is not None and claim_index >= n_facts:
            errors.append(
                f"{where}: claim_index {claim_index} out of range (0..{n_facts - 1})"
            )
        primitive = anchor.get("primitive")
        if not isinstance(primitive, str) or not 1 <= len(primitive) <= 200:
            errors.append(
                f"{where}: primitive must be a non-empty string (<= 200 chars)"
            )
        archetype = anchor.get("archetype")
        if archetype is not None and archetype not in VISUAL_ARCHETYPES:
            errors.append(
                f"{where}: archetype must be one of {sorted(VISUAL_ARCHETYPES)}"
            )


def _validate_visual_assets(visual_assets: Any, errors: list[str]) -> None:
    if visual_assets is None:
        return
    if not isinstance(visual_assets, list):
        errors.append("visual_assets must be an array")
        return
    if len(visual_assets) > 24:
        errors.append("visual_assets must contain at most 24 items")
        return
    for i, asset in enumerate(visual_assets):
        where = f"visual_assets[{i}]"
        if not isinstance(asset, dict):
            errors.append(f"{where}: must be an object")
            continue
        for key in sorted(set(asset) - VISUAL_ASSET_KEYS):
            errors.append(f"{where}: unknown field: {key!r}")
        for key in REQUIRED_VISUAL_ASSET_KEYS:
            if key not in asset:
                errors.append(f"{where}: missing required field: {key}")
        for req_s, limit in (("file", 500), ("license", 40), ("attribution", 500)):
            val = asset.get(req_s)
            if not isinstance(val, str) or not 1 <= len(val) <= limit:
                errors.append(
                    f"{where}: {req_s} must be a non-empty string (<= {limit} chars)"
                )
        for opt_s, limit in (
            ("title", 300),
            ("creator", 300),
            ("license_url", 500),
            ("source_url", 500),
        ):
            val = asset.get(opt_s)
            if val is not None and (not isinstance(val, str) or len(val) > limit):
                errors.append(f"{where}: {opt_s} must be a string (<= {limit} chars)")


def _validate_target_format(target_format: Any, errors: list[str]) -> None:
    if not isinstance(target_format, dict):
        errors.append("target_format must be an object")
        return
    for key in sorted(set(target_format) - TARGET_FORMAT_KEYS):
        errors.append(f"target_format: unknown field: {key!r}")
    for key in REQUIRED_TARGET_FORMAT_KEYS:
        if key not in target_format:
            errors.append(f"target_format: missing required field: {key}")
    if target_format.get("aspect") not in TARGET_ASPECTS:
        errors.append(f"target_format: aspect must be one of {sorted(TARGET_ASPECTS)}")
    for dim in ("width", "height"):
        val = target_format.get(dim)
        if val is not None and (not _is_int(val) or val < 160):
            errors.append(f"target_format: {dim} must be an integer >= 160")
    fps = target_format.get("fps")
    if fps is not None and (not _is_int(fps) or fps not in TARGET_FPS):
        errors.append(f"target_format: fps must be one of {sorted(TARGET_FPS)}")
    max_duration = target_format.get("max_duration_sec")
    if max_duration is not None and (
        not _is_num(max_duration) or max_duration <= 0 or max_duration > 3600
    ):
        errors.append(
            "target_format: max_duration_sec must be a number > 0 and <= 3600"
        )
    platform = target_format.get("platform")
    if platform is not None and (not isinstance(platform, str) or len(platform) > 40):
        errors.append("target_format: platform must be a string (<= 40 chars)")


def validate_request(data: Any) -> list[str]:
    """Return a list of error strings (empty == valid).

    Runtime mirror of ``schemas/investigation_brief.schema.json``.
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
    n_facts = _validate_facts(data.get("facts"), errors)
    _validate_visual_anchors(data.get("visual_anchors"), n_facts, errors)
    _validate_visual_assets(data.get("visual_assets"), errors)
    _validate_target_format(data.get("target_format"), errors)
    return errors
