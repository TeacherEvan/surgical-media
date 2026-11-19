#!/usr/bin/env bash
# install_surgical_media.sh — Installs or refreshes the surgical-media skill cleanly.
#
# Installs:
#   SKILL.md
#   README.md
#   LICENSE
#   AGENTS.md
#   scripts/ (all runtime CLIs + engine library)
#   assets/fonts/ (bundled OFL Inter — captions/HUD face)
#   references/ (archetypes, storyboard guide, ffmpeg encoding)
#   schemas/ (investigation_brief, script, storyboard)
#   examples/ (tri-archetype + hybrid-3D showcase boards)
#   docs/adr/ (decision records) + docs/index.md + docs/project-plan.md
#
# Usage:
#   ./install_surgical_media.sh           # install to default Hermes skill dir
#   ./install_surgical_media.sh /custom/dir

set -euo pipefail

HERMES_SKILL_DIR="${1:-${HOME}/.hermes/skills/creative/surgical-media}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[install_surgical_media] Installing Surgical Media (v1.4.0) to:"
echo "  ${HERMES_SKILL_DIR}"
echo

mkdir -p \
  "${HERMES_SKILL_DIR}/scripts" \
  "${HERMES_SKILL_DIR}/scripts/threejs" \
  "${HERMES_SKILL_DIR}/assets/fonts" \
  "${HERMES_SKILL_DIR}/references" \
  "${HERMES_SKILL_DIR}/schemas" \
  "${HERMES_SKILL_DIR}/examples" \
  "${HERMES_SKILL_DIR}/docs/adr"

for f in SKILL.md README.md LICENSE AGENTS.md; do
  cp "${SCRIPT_DIR}/${f}" "${HERMES_SKILL_DIR}/${f}"
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
cp "${SCRIPT_DIR}/assets/fonts/"*.ttf "${SCRIPT_DIR}/assets/fonts/"*.txt "${SCRIPT_DIR}/assets/fonts/README.md" "${HERMES_SKILL_DIR}/assets/fonts/"
cp "${SCRIPT_DIR}/examples/"*.json "${HERMES_SKILL_DIR}/examples/"
cp "${SCRIPT_DIR}/docs/adr/"*.md "${HERMES_SKILL_DIR}/docs/adr/"
cp "${SCRIPT_DIR}/docs/index.md" "${SCRIPT_DIR}/docs/project-plan.md" "${HERMES_SKILL_DIR}/docs/"

echo "[install_surgical_media] Done."
echo "Verify with:"
echo "  python3 ${HERMES_SKILL_DIR}/scripts/render_engine.py --demo --output /tmp/sm_demo.mp4"
