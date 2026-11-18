#!/usr/bin/env bash
# ci_gates.sh — the single source of truth for the verification gate set.
# Both .github/workflows/skill-ci.yml and .gitlab-ci.yml call this, and so
# can you locally:
#
#     PATH=<your-venv>/bin:$PATH bash scripts/ci_gates.sh
#
# Exits non-zero on the first failing gate.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== gate 1/7: example storyboard validates =="
python3 scripts/storyboard.py examples/tri_archetype_storyboard.json

echo "== gate 2/7: lint =="
ruff check --no-cache scripts/ tests/

echo "== gate 3/7: format check =="
ruff format --check --no-cache scripts/ tests/

echo "== gate 4/7: test suite =="
python3 -m pytest tests/ -q

echo "== gate 5/7: JSON Schemas are valid Draft 2020-12 =="
check-jsonschema --check-metaschema schemas/*.schema.json

echo "== gate 6/7: thumbnail smoke gate (visual path) =="
python3 scripts/render_engine.py --demo --thumbnails /tmp/sm_thumbs

echo "== gate 7/7: draft render + QC =="
python3 scripts/render_engine.py --demo --output /tmp/sm_ci_gate.mp4 --quality draft
python3 scripts/verify_output.py --input /tmp/sm_ci_gate.mp4 --storyboard examples/tri_archetype_storyboard.json

echo "ci_gates: all gates green"
