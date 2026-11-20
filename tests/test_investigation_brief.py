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
        "visual_assets": [
            {"file": "horse.png", "license": "CC0", "attribution": "Public domain"}
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


# -- visual_anchors --------------------------------------------------------


def test_visual_anchors_required() -> None:
    bad = _brief()
    bad.pop("visual_anchors")
    assert validate_request(bad)


def test_visual_anchors_min_max_items() -> None:
    bad = _brief()
    bad["visual_anchors"] = []
    assert validate_request(bad)
    bad = _brief()
    bad["visual_anchors"] = [{"claim_index": 0, "primitive": "x"}] * 13
    assert validate_request(bad)


def test_visual_anchor_required_fields() -> None:
    bad = _brief()
    bad["visual_anchors"][0].pop("claim_index")
    assert validate_request(bad)
    bad = _brief()
    bad["visual_anchors"][0].pop("primitive")
    assert validate_request(bad)


def test_visual_anchor_claim_index_bounds() -> None:
    bad = _brief()
    bad["visual_anchors"][0]["claim_index"] = -1
    assert validate_request(bad)
    # Note: schema does not constrain claim_index to facts array bounds
    # (cross-field validation is a runtime concern, not in JSON Schema)


def test_visual_anchor_primitive_bounds() -> None:
    bad = _brief()
    bad["visual_anchors"][0]["primitive"] = ""
    assert validate_request(bad)
    bad = _brief()
    bad["visual_anchors"][0]["primitive"] = "x" * 201
    assert validate_request(bad)


def test_visual_anchor_archetype_enum() -> None:
    bad = _brief()
    bad["visual_anchors"][0]["archetype"] = "not-an-archetype"
    assert validate_request(bad)


def test_visual_anchor_unknown_field() -> None:
    bad = _brief()
    bad["visual_anchors"][0]["surprise"] = True
    assert validate_request(bad)


# -- visual_assets ---------------------------------------------------------


def test_visual_assets_max_items() -> None:
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "CC0", "attribution": "x"}] * 25
    assert validate_request(bad)


def test_visual_asset_required_fields() -> None:
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "CC0"}]  # missing attribution
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "attribution": "x"}]  # missing license
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"license": "CC0", "attribution": "x"}]  # missing file
    assert validate_request(bad)


def test_visual_asset_field_bounds() -> None:
    bad = _brief()
    bad["visual_assets"] = [{"file": "", "license": "CC0", "attribution": "x"}]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x" * 501, "license": "CC0", "attribution": "x"}]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "", "attribution": "x"}]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "x" * 41, "attribution": "x"}]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "CC0", "attribution": ""}]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [{"file": "x", "license": "CC0", "attribution": "x" * 501}]
    assert validate_request(bad)


def test_visual_asset_optional_fields() -> None:
    bad = _brief()
    bad["visual_assets"] = [
        {"file": "x", "license": "CC0", "attribution": "x", "title": "x" * 301}
    ]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [
        {"file": "x", "license": "CC0", "attribution": "x", "creator": "x" * 301}
    ]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [
        {"file": "x", "license": "CC0", "attribution": "x", "license_url": "x" * 501}
    ]
    assert validate_request(bad)
    bad = _brief()
    bad["visual_assets"] = [
        {"file": "x", "license": "CC0", "attribution": "x", "source_url": "x" * 501}
    ]
    assert validate_request(bad)


def test_visual_asset_unknown_field() -> None:
    bad = _brief()
    bad["visual_assets"] = [
        {"file": "x", "license": "CC0", "attribution": "x", "surprise": True}
    ]
    assert validate_request(bad)


# -- target_format ---------------------------------------------------------


def test_target_format_required() -> None:
    bad = _brief()
    bad.pop("target_format")
    assert validate_request(bad)


def test_target_format_aspect_enum() -> None:
    bad = _brief()
    bad["target_format"]["aspect"] = "4:3"
    assert validate_request(bad)


def test_target_format_width_height_bounds() -> None:
    bad = _brief()
    bad["target_format"]["width"] = 100
    assert validate_request(bad)
    bad = _brief()
    bad["target_format"]["height"] = 100
    assert validate_request(bad)
    bad = _brief()
    bad["target_format"]["width"] = "wide"
    assert validate_request(bad)


def test_target_format_fps_enum() -> None:
    bad = _brief()
    bad["target_format"]["fps"] = 15
    assert validate_request(bad)


def test_target_format_max_duration_bounds() -> None:
    bad = _brief()
    bad["target_format"]["max_duration_sec"] = 0
    assert validate_request(bad)
    bad = _brief()
    bad["target_format"]["max_duration_sec"] = 3601
    assert validate_request(bad)
    bad = _brief()
    bad["target_format"]["max_duration_sec"] = -5
    assert validate_request(bad)


def test_target_format_platform_bounds() -> None:
    bad = _brief()
    bad["target_format"]["platform"] = "x" * 41
    assert validate_request(bad)


def test_target_format_unknown_field() -> None:
    bad = _brief()
    bad["target_format"]["surprise"] = True
    assert validate_request(bad)


def test_schema_runtime_parity() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    good = _brief()
    jsonschema.validate(good, SCHEMA)
    for mutate in [
        lambda r: r.__setitem__("facts", [dict(r["facts"][0], claim_id="bad-id")]),
        lambda r: r.__setitem__("facts", [dict(r["facts"][0], claim_type="rumor")]),
        lambda r: r.update(surprise=True),
        lambda r: r.__setitem__(
            "visual_anchors", [dict(r["visual_anchors"][0], archetype="nope")]
        ),
        lambda r: r.__setitem__(
            "visual_anchors", [dict(r["visual_anchors"][0], surprise=True)]
        ),
        lambda r: r.__setitem__(
            "visual_assets", [dict(r["visual_assets"][0], file="")]
        ),
        lambda r: r.__setitem__(
            "visual_assets", [dict(r["visual_assets"][0], surprise=True)]
        ),
        lambda r: r.__setitem__(
            "target_format", dict(r["target_format"], aspect="4:3")
        ),
        lambda r: r.__setitem__("target_format", dict(r["target_format"], width=100)),
        lambda r: r.__setitem__(
            "target_format", dict(r["target_format"], surprise=True)
        ),
    ]:
        bad = copy.deepcopy(good)
        mutate(bad)
        assert validate_request(bad)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(bad, SCHEMA)
