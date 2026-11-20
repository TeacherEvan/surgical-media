"""Claim-ID research contract: investigation-brief validator + schema parity.

Offline; mirrors ``scripts/investigation_brief.py`` against
``schemas/investigation_brief.schema.json``.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from investigation_brief import validate_request

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((ROOT / "schemas" / "investigation_brief.schema.json").read_text())


def _brief(**over: Any) -> dict[str, Any]:
    base = {
        "schema_version": "1.0.0",
        "subject": "Horse Tenny's disastrous first date",
        "sources": ["https://example.com/tenny"],
        "facts": [
            {
                "claim": "Horse Tenny is a fictional horse.",
                "source": "https://example.com/tenny",
                "claim_id": "claim-11111111",
                "claim_type": "factual",
            },
            {
                "claim": "First dates are awkward 87% of the time.",
                "source": "https://example.com/dating-study",
                "claim_id": "claim-22222222",
                "claim_type": "statistical",
                "metric": "87%",
            },
            {
                "claim": "This story is satire.",
                "source": "https://example.com/tenny",
                "claim_id": "claim-33333333",
                "claim_type": "satire",
                "contradictions": ["claim-11111111"],
            },
        ],
        "visual_anchors": [
            {"claim_index": 0, "primitive": "horse silhouette", "archetype": "mixed"}
        ],
        "target_format": {"aspect": "9:16", "width": 1080, "height": 1920, "fps": 30},
    }
    base.update(over)
    return base


# -- model -----------------------------------------------------------------


def test_valid_brief_passes() -> None:
    assert validate_request(_brief()) == []


def test_non_object_rejected() -> None:
    assert validate_request([]) == ["top level must be a JSON object"]
    assert validate_request("nope") == ["top level must be a JSON object"]


@pytest.mark.parametrize(
    "mutate",
    [
        lambda r: r.pop("subject"),
        lambda r: r.update(subject=""),
        lambda r: r.update(subject="x" * 301),
        lambda r: r.pop("facts"),
        lambda r: r.update(facts=[]),  # below minItems
        lambda r: r.update(facts=[{}] * 9),  # above maxItems
        lambda r: r.update(schema_version="9"),
        lambda r: r.update(surprise=True),
        lambda r: r.update(sources=["x"] * 21),  # above maxItems
    ],
)
def test_bad_briefs_rejected(mutate: Any) -> None:
    assert validate_request(mutate(_brief()))


def test_missing_required_fact_keys_rejected() -> None:
    bad = _brief()
    bad["facts"][0].pop("claim_id")
    assert validate_request(bad)
    bad = _brief()
    bad["facts"][0].pop("claim_type")
    assert validate_request(bad)


def test_claim_id_format_enforced() -> None:
    bad = _brief()
    bad["facts"][0]["claim_id"] = "not-a-claim-id"
    assert validate_request(bad)
    bad = _brief()
    bad["facts"][0]["claim_id"] = "claim-11111111"
    bad["facts"][1]["claim_id"] = "claim-11111111"  # duplicate
    assert validate_request(bad)


def test_claim_type_enum_enforced() -> None:
    bad = _brief()
    bad["facts"][0]["claim_type"] = "rumor"
    assert validate_request(bad)


def test_contradictions_must_reference_known_ids() -> None:
    bad = _brief()
    bad["facts"][2]["contradictions"] = ["claim-99999999"]  # unknown
    assert validate_request(bad)
    bad = _brief()
    bad["facts"][2]["contradictions"] = ["claim-11111111", "claim-11111111"]  # repeat
    assert validate_request(bad)


def test_schema_runtime_parity() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    good = _brief()
    jsonschema.validate(good, SCHEMA)
    for mutate in [
        lambda r: r.__setitem__("facts", [dict(r["facts"][0], claim_id="bad-id")]),
        lambda r: r.__setitem__("facts", [dict(r["facts"][0], claim_type="rumor")]),
        lambda r: r.update(surprise=True),
    ]:
        bad = copy.deepcopy(good)
        mutate(bad)
        assert validate_request(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, SCHEMA)
