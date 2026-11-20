#!/usr/bin/env bash
# ci_gates.sh — the single source of truth for the verification gate set.
# The GitLab mirror (.gitlab-ci.yml) calls this, and so should you — locally:
#
#     PATH=<your-venv>/bin:$PATH bash scripts/ci_gates.sh
#
# Exits non-zero on the first failing gate.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/9: example storyboards validate =="
for board in examples/*.json; do
  python3 scripts/storyboard.py "$board"
done

echo "== gate 2/9: lint =="
ruff check --no-cache scripts/ tests/

echo "== gate 3/9: format check =="
ruff format --check --no-cache scripts/ tests/

echo "== gate 4/9: typecheck (mypy --strict, config in pyproject.toml) =="
python3 -m mypy scripts/

echo "== gate 5/9: test suite =="
python3 -m pytest tests/ -q

echo "== gate 6/9: JSON Schemas are valid Draft 2020-12 =="
check-jsonschema --check-metaschema schemas/*.schema.json

echo "== gate 7/9: example storyboards validate against their JSON Schema =="
check-jsonschema --schemafile schemas/storyboard.schema.json examples/*.json

echo "== gate 8/9: thumbnail smoke gate (visual path, 2D + hybrid 3D + Three.js 3D) =="
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs
python3 scripts/render_engine.py --storyboard examples/hybrid_3d_storyboard.json --thumbnails /tmp/sm_hybrid_thumbs
python3 scripts/render_engine.py --storyboard examples/threejs_3d_storyboard.json --thumbnails /tmp/sm_threejs_thumbs

echo "== gate 9/9: draft render + QC =="
python3 scripts/render_engine.py --demo --output /tmp/sm_ci_gate.mp4 --quality draft
python3 scripts/verify_output.py --input /tmp/sm_ci_gate.mp4 --storyboard examples/tri_archetype_storyboard.json

echo "== gate 10/10: style_lint on examples (advisory, report mode) =="
python3 scripts/style_lint.py examples/*.json

echo "ci_gates: all gates green"
