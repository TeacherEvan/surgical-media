#!/usr/bin/env bash
# ci_gates.sh — the single source of truth for the verification gate set.
# The GitLab mirror (.gitlab-ci.yml) calls this, and so should you — locally:
#
#     PATH=<your-venv>/bin:$PATH bash scripts/ci_gates.sh
#
# Exits non-zero on the first failing gate.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/8: example storyboards validate =="
for board in examples/*.json; do
  python3 scripts/storyboard.py "$board"
done

echo "== gate 2/8: lint =="
ruff check --no-cache scripts/ tests/

echo "== gate 3/8: format check =="
ruff format --check --no-cache scripts/ tests/

echo "== gate 4/8: test suite =="
python3 -m pytest tests/ -q

echo "== gate 5/8: JSON Schemas are valid Draft 2020-12 =="
check-jsonschema --check-metaschema schemas/*.schema.json

echo "== gate 6/8: example storyboards validate against their JSON Schema =="
check-jsonschema --schemafile schemas/storyboard.schema.json examples/*.json

echo "== gate 7/8: thumbnail smoke gate (visual path, both 2D and hybrid 3D) =="
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs
python3 scripts/render_engine.py --storyboard examples/hybrid_3d_storyboard.json --thumbnails /tmp/sm_hybrid_thumbs

echo "== gate 8/8: draft render + QC =="
python3 scripts/render_engine.py --demo --output /tmp/sm_ci_gate.mp4 --quality draft
python3 scripts/verify_output.py --input /tmp/sm_ci_gate.mp4 --storyboard examples/tri_archetype_storyboard.json

echo "ci_gates: all gates green"
