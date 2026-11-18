"""Schema-contract tests: runtime validator vs JSON Schema must agree.

The hand-rolled validator in storyboard.py exists for hard-fail-fast runtime
errors; schemas/*.schema.json is the normative contract. These tests pin the
two together so they cannot silently drift. jsonschema is optional (the CI
gate uses check-jsonschema); parity assertions skip cleanly without it.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import storyboard

EXAMPLE = REPO / "examples" / "tri_archetype_storyboard.json"
SCHEMA = REPO / "schemas" / "storyboard.schema.json"


def _example():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def _validator():
    jsonschema = pytest.importorskip("jsonschema")
    return jsonschema.Draft202012Validator(
        json.loads(SCHEMA.read_text(encoding="utf-8"))
    )


def test_runtime_validator_accepts_example():
    assert storyboard.validate_storyboard(_example()) == []


def test_example_passes_json_schema():
    pytest.importorskip("jsonschema")
    errors = list(_validator().iter_errors(_example()))
    assert errors == []


MUTATIONS = {
    # (label, mutate(data)) — both validators must reject every one of these
    "scene missing scene_id": lambda d: d["scenes"][0].pop("scene_id"),
    "bad archetype enum": lambda d: d["scenes"][0].update(
        archetype="not_a_real_archetype"
    ),
    "negative duration": lambda d: d["scenes"][0].update(duration_sec=-1.0),
    "bad fps enum": lambda d: d["format"].update(fps=23),
    "elements removed": lambda d: d["scenes"][0].pop("elements"),
    "width out of bounds": lambda d: d["format"].update(width=9999),
}


@pytest.mark.parametrize("label", sorted(MUTATIONS))
def test_runtime_validator_rejects_mutation(label):
    data = _example()
    MUTATIONS[label](data)
    assert storyboard.validate_storyboard(data) != []


@pytest.mark.parametrize("label", sorted(MUTATIONS))
def test_schema_and_runtime_validator_agree(label):
    pytest.importorskip("jsonschema")
    data = _example()
    MUTATIONS[label](data)
    schema_rejects = bool(list(_validator().iter_errors(data)))
    runtime_rejects = bool(storyboard.validate_storyboard(data))
    assert schema_rejects == runtime_rejects, (
        f"validators disagree on mutation {label!r}: "
        f"schema_rejects={schema_rejects} runtime_rejects={runtime_rejects}"
    )
