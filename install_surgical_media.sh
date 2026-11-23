#!/usr/bin/env bash
# install_surgical_media.sh — Installs or refreshes the surgical-media skill cleanly.
#
# v3.2.0 is the priority social-video pipeline. Installs:
#   SKILL.md, README.md, LICENSE, AGENTS.md, CHANGELOG.md, SECURITY.md
#   pyproject.toml, requirements*.txt (so README's install commands work in-place)
#   scripts/ (all runtime CLIs + ci_gates.sh + engine library)
#   scripts/elements/ (painter package) + scripts/threejs/ (WebGL bridge)
#   assets/fonts/ (bundled OFL Inter, JetBrains Mono, Cormorant Garamond)
#   assets/styles/ (style presets)
#   references/ (specs-licensing-compliance, style-and-architecture,
#                pipeline-scripts, render-templates, archetypes, storyboard guide,
#                ffmpeg encoding, job workflow)
#   schemas/ (investigation_brief, production_job, script, storyboard, style)
#   examples/ (showcases + ref_* boards + jobs/ example job)
#   docs/adr/ + docs/audits/ + docs/index.md + docs/project-plan.md
#
# Usage:
#   ./install_surgical_media.sh               # install to default Hermes skill dir
#   ./install_surgical_media.sh /custom/dir   # install to a custom directory
#   ./install_surgical_media.sh --all-agents  # sync to Hermes/OpenCode, Antigravity, Agents, Claude, Codex

set -euo pipefail

VERSION="3.2.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

install_one_target() {
  local target_dir="$1"
  echo "[install_surgical_media] Installing Surgical Media (v${VERSION}) to:"
  echo "  ${target_dir}"

  mkdir -p \
    "${target_dir}/scripts" \
    "${target_dir}/scripts/threejs" \
    "${target_dir}/assets/fonts" \
    "${target_dir}/assets/styles" \
    "${target_dir}/references" \
    "${target_dir}/schemas" \
    "${target_dir}/examples/jobs" \
    "${target_dir}/examples/assets" \
    "${target_dir}/docs/adr" \
    "${target_dir}/docs/audits"

  for f in SKILL.md README.md LICENSE AGENTS.md CHANGELOG.md SECURITY.md \
           pyproject.toml requirements.txt requirements-dev.txt requirements-tts.txt; do
    cp "${SCRIPT_DIR}/${f}" "${target_dir}/${f}"
  done

  # Drop stale root-level files in scripts/ (e.g., old v1.x elements.py or .bak-* files).
  for stale in "${target_dir}"/scripts/*; do
    [ -e "${stale}" ] || continue
    [ -d "${stale}" ] && continue
    local base
    base="$(basename "${stale}")"
    [ -f "${SCRIPT_DIR}/scripts/${base}" ] || rm -f "${stale}"
  done

  cp "${SCRIPT_DIR}/scripts/"*.py "${target_dir}/scripts/"
  cp "${SCRIPT_DIR}/scripts/ci_gates.sh" "${target_dir}/scripts/ci_gates.sh"
  chmod +x "${target_dir}/scripts/ci_gates.sh"

  rm -rf "${target_dir}/scripts/elements"
  cp -r "${SCRIPT_DIR}/scripts/elements" "${target_dir}/scripts/elements"
  rm -rf "${target_dir}/scripts/elements/__pycache__"

  cp "${SCRIPT_DIR}/scripts/threejs/package.json" \
    "${SCRIPT_DIR}/scripts/threejs/runner.mjs" \
    "${SCRIPT_DIR}/scripts/threejs/scenes.mjs" \
    "${SCRIPT_DIR}/scripts/threejs/stage.html" \
    "${SCRIPT_DIR}/scripts/threejs/svg_raster.mjs" \
    "${target_dir}/scripts/threejs/"

  cp "${SCRIPT_DIR}/references/"*.md "${target_dir}/references/"
  cp "${SCRIPT_DIR}/schemas/"*.json "${target_dir}/schemas/"
  cp "${SCRIPT_DIR}/assets/fonts/"*.ttf "${SCRIPT_DIR}/assets/fonts/"*.txt \
    "${SCRIPT_DIR}/assets/fonts/README.md" "${target_dir}/assets/fonts/"
  cp -r "${SCRIPT_DIR}/assets/styles/"* "${target_dir}/assets/styles/"
  cp "${SCRIPT_DIR}/examples/"*.json "${target_dir}/examples/"
  cp "${SCRIPT_DIR}/examples/jobs/"*.json "${target_dir}/examples/jobs/"
  cp "${SCRIPT_DIR}/examples/assets/"*.jpg "${SCRIPT_DIR}/examples/assets/README.md" \
    "${target_dir}/examples/assets/"
  cp "${SCRIPT_DIR}/docs/adr/"*.md "${target_dir}/docs/adr/"
  cp "${SCRIPT_DIR}/docs/audits/"*.md "${target_dir}/docs/audits/"
  cp "${SCRIPT_DIR}/docs/index.md" "${SCRIPT_DIR}/docs/project-plan.md" "${target_dir}/docs/"

  if [ -d "${SCRIPT_DIR}/scripts/threejs/node_modules" ]; then
    if [ ! -d "${target_dir}/scripts/threejs/node_modules" ] || \
       [ "${SCRIPT_DIR}/scripts/threejs/package.json" -nt "${target_dir}/scripts/threejs/node_modules" ]; then
      rm -rf "${target_dir}/scripts/threejs/node_modules"
      cp -r "${SCRIPT_DIR}/scripts/threejs/node_modules" "${target_dir}/scripts/threejs/node_modules"
    fi
  elif command -v npm >/dev/null 2>&1; then
    (cd "${target_dir}/scripts/threejs" && npm install --no-audit --no-fund --silent)
  fi

  echo "${VERSION}" > "${target_dir}/.installed_version"

  # Verify v3.2.0 markers landed cleanly
  grep -q "def derive_queries" "${target_dir}/scripts/fetch_scene_assets.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 per-beat fetcher missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "def wire_board" "${target_dir}/scripts/asset_wire.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 asset_wire.py (image-first wiring) missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "subject_imagery" "${target_dir}/scripts/pipeline_preflight.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 image-first preflight gate missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "_draw_translucent" "${target_dir}/scripts/elements/svg.py" || {
    echo "[install_surgical_media] ERROR: patched SVG painter missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "_safe_child_path" "${target_dir}/scripts/render_engine.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 render_engine.py missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "ATTRIBUTION_REQUIRED_LICENSES" "${target_dir}/scripts/monetization_gate.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 monetization_gate.py missing in ${target_dir}" >&2
    exit 3
  }
  grep -q "validate-brief" "${target_dir}/scripts/job_cli.py" || {
    echo "[install_surgical_media] ERROR: v3.2.0 job_cli.py missing in ${target_dir}" >&2
    exit 3
  }
  echo "[install_surgical_media] Verified v${VERSION} in ${target_dir}."
}

if [ "${1:-}" = "--all-agents" ]; then
  TARGETS=(
    "${HOME}/.hermes/skills/creative/surgical-media"
    "${HOME}/.gemini/antigravity-cli/skills/surgical-media"
    "${HOME}/.agents/skills/surgical-media"
    "${HOME}/.claude/skills/surgical-media"
    "${HOME}/.codex/skills/surgical-media"
  )
  for t in "${TARGETS[@]}"; do
    install_one_target "$t"
    echo
  done
else
  TARGET="${1:-${HOME}/.hermes/skills/creative/surgical-media}"
  install_one_target "${TARGET}"
fi

echo "[install_surgical_media] Done."
