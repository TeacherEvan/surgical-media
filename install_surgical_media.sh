#!/usr/bin/env bash
# install_surgical_media.sh — Installs or refreshes the surgical-media skill cleanly.
#
# v3.0.0 is the priority social-video pipeline. Installs:
#   SKILL.md, README.md, LICENSE, AGENTS.md, CHANGELOG.md, SECURITY.md
#   pyproject.toml, requirements*.txt (so README's install commands work in-place)
#   scripts/ (all runtime CLIs + engine library, including spec_refresh,
#             pipeline_preflight, style_apply, tts_normalizer, media_harvester, qc_gate)
#   scripts/elements/ (painter package) + scripts/threejs/ (WebGL bridge)
#   assets/fonts/ (bundled OFL Inter, JetBrains Mono, Cormorant Garamond)
#   assets/styles/ (style presets)
#   references/ (specs-licensing-compliance, style-and-architecture,
#                pipeline-scripts, render-templates, archetypes, storyboard guide,
#                ffmpeg encoding, job workflow)
#   schemas/ (investigation_brief, production_job, script, storyboard, style)
#   examples/ (showcases + ref_* boards + jobs/ example job)
#   docs/adr/ + docs/index.md + docs/project-plan.md
#
# Usage:
#   ./install_surgical_media.sh           # install to default Hermes skill dir
#   ./install_surgical_media.sh /custom/dir

set -euo pipefail

HERMES_SKILL_DIR="${1:-${HOME}/.hermes/skills/creative/surgical-media}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[install_surgical_media] Installing Surgical Media (v3.0.0) to:"
echo "  ${HERMES_SKILL_DIR}"
echo

mkdir -p \
  "${HERMES_SKILL_DIR}/scripts" \
  "${HERMES_SKILL_DIR}/scripts/threejs" \
  "${HERMES_SKILL_DIR}/assets/fonts" \
  "${HERMES_SKILL_DIR}/assets/styles" \
  "${HERMES_SKILL_DIR}/references" \
  "${HERMES_SKILL_DIR}/schemas" \
  "${HERMES_SKILL_DIR}/examples/jobs" \
  "${HERMES_SKILL_DIR}/docs/adr"

for f in SKILL.md README.md LICENSE AGENTS.md CHANGELOG.md SECURITY.md \
         pyproject.toml requirements.txt requirements-dev.txt requirements-tts.txt; do
  cp "${SCRIPT_DIR}/${f}" "${HERMES_SKILL_DIR}/${f}"
done

# Drop root-level .py files that no longer exist in source (e.g. the old v1.x
# monolithic elements.py) before installing the current set. The elements/
# package is handled separately below.
for stale in "${HERMES_SKILL_DIR}"/scripts/*.py; do
  [ -e "${stale}" ] || continue
  base="$(basename "${stale}")"
  [ -f "${SCRIPT_DIR}/scripts/${base}" ] || rm -f "${stale}"
done

cp "${SCRIPT_DIR}/scripts/"*.py "${HERMES_SKILL_DIR}/scripts/"
rm -rf "${HERMES_SKILL_DIR}/scripts/elements"
cp -r "${SCRIPT_DIR}/scripts/elements" "${HERMES_SKILL_DIR}/scripts/elements"
cp "${SCRIPT_DIR}/scripts/threejs/package.json" \
  "${SCRIPT_DIR}/scripts/threejs/runner.mjs" \
  "${SCRIPT_DIR}/scripts/threejs/scenes.mjs" \
  "${SCRIPT_DIR}/scripts/threejs/stage.html" \
  "${SCRIPT_DIR}/scripts/threejs/svg_raster.mjs" \
  "${HERMES_SKILL_DIR}/scripts/threejs/"
cp "${SCRIPT_DIR}/references/"*.md "${HERMES_SKILL_DIR}/references/"
cp "${SCRIPT_DIR}/schemas/"*.json "${HERMES_SKILL_DIR}/schemas/"
cp "${SCRIPT_DIR}/assets/fonts/"*.ttf "${SCRIPT_DIR}/assets/fonts/"*.txt \
  "${SCRIPT_DIR}/assets/fonts/README.md" "${HERMES_SKILL_DIR}/assets/fonts/"
cp -r "${SCRIPT_DIR}/assets/styles/"* "${HERMES_SKILL_DIR}/assets/styles/"
cp "${SCRIPT_DIR}/examples/"*.json "${HERMES_SKILL_DIR}/examples/"
cp "${SCRIPT_DIR}/examples/jobs/"*.json "${HERMES_SKILL_DIR}/examples/jobs/"
cp "${SCRIPT_DIR}/docs/adr/"*.md "${HERMES_SKILL_DIR}/docs/adr/"
cp "${SCRIPT_DIR}/docs/index.md" "${SCRIPT_DIR}/docs/project-plan.md" "${HERMES_SKILL_DIR}/docs/"

if command -v npm >/dev/null 2>&1; then
  (cd "${HERMES_SKILL_DIR}/scripts/threejs" && npm install --no-audit --no-fund --silent)
fi

echo "[install_surgical_media] Done."
echo "Verify with:"
echo "  python3 ${HERMES_SKILL_DIR}/scripts/render_engine.py --demo --output /tmp/sm_demo.mp4"
echo "  python3 ${HERMES_SKILL_DIR}/scripts/qc_gate.py --help"
