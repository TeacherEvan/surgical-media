#!/usr/bin/env bash
# setup_kokoro.sh — install the local Kokoro-82M voice runtime.
#
# Idempotent. Creates a Python 3.12 venv (the pipeline itself runs on any
# Python >= 3.10; onnxruntime has no wheels for very new interpreters),
# downloads the quantised ONNX model and an openly-licensed voice bank from
# Hugging Face, and builds the npz voice file kokoro-onnx expects.
#
# Overrides: KOKORO_HOME, KOKORO_PYTHON.
set -euo pipefail

HOME_DIR="${KOKORO_HOME:-$HOME/.cache/surgical-media/kokoro}"
VENV="$HOME_DIR/venv"
PY="${KOKORO_PYTHON:-$VENV/bin/python}"
MODEL_URL="https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/onnx/model_quantized.onnx"
VOICE_URL="https://huggingface.co/onnx-community/Kokoro-82M-v1.0-ONNX/resolve/main/voices"
VOICES="af_heart,af_bella,af_nicole,af_sky,am_adam,am_eric,am_michael,bm_george"

mkdir -p "$HOME_DIR"
export PATH="$HOME/.hermes/bin:$PATH"

if ! command -v uv >/dev/null 2>&1; then
  echo "setup_kokoro: uv is required (https://docs.astral.sh/uv/)" >&2
  exit 1
fi

if [ ! -x "$PY" ]; then
  echo "setup_kokoro: creating Python 3.12 venv at $VENV"
  uv python install 3.12
  uv venv "$VENV" --python 3.12
else
  echo "setup_kokoro: reusing venv at $VENV"
fi

echo "setup_kokoro: installing kokoro-onnx"
uv pip install --python "$PY" kokoro-onnx >/dev/null

if [ ! -s "$HOME_DIR/model_quantized.onnx" ]; then
  echo "setup_kokoro: downloading quantised model (~89 MB)"
  curl -L --fail --silent --show-error -o "$HOME_DIR/model_quantized.onnx" "$MODEL_URL"
fi

IFS=',' read -ra NAMES <<< "$VOICES"
for name in "${NAMES[@]}"; do
  if [ ! -s "$HOME_DIR/$name.bin" ]; then
    echo "setup_kokoro: downloading voice $name"
    curl -L --fail --silent --show-error \
      -o "$HOME_DIR/$name.bin" "$VOICE_URL/$name.bin"
  fi
done

echo "setup_kokoro: building voice bank"
"$PY" - "$HOME_DIR" "$VOICES" <<'PY'
import sys
from pathlib import Path

import numpy as np

home = Path(sys.argv[1])
names = sys.argv[2].split(",")
vectors = {
    name: np.fromfile(home / f"{name}.bin", dtype=np.float32).reshape(510, 1, 256)
    for name in names
}
np.savez(home / "voices.npz", **vectors)
print(f"setup_kokoro: {len(vectors)} voices -> {home / 'voices.npz'}")
PY

echo "setup_kokoro: runtime ready at $HOME_DIR (default voice: af_heart)"
