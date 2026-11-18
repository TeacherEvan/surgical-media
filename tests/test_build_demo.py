"""The committed example board is generated code output, never hand-edited.
This test pins that contract: regenerating it from build_demo must be
byte-identical to what is checked in.
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import build_demo


def test_build_demo_regenerates_committed_example(monkeypatch, tmp_path):
    out = tmp_path / "regen.json"
    monkeypatch.setattr(build_demo, "OUT", out)
    build_demo.main()
    committed = (REPO / "examples" / "tri_archetype_storyboard.json").read_text(
        encoding="utf-8"
    )
    assert out.read_text(encoding="utf-8") == committed
