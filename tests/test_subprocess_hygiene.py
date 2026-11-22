"""AST gate for SECURITY.md: list-form argv, explicit timeout, never shell=True."""

from __future__ import annotations

import ast
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TIMEOUT_CALLS = {"run", "check_output", "check_call", "call"}


def _sources() -> list[Path]:
    return [p for p in SCRIPTS.rglob("*.py") if "node_modules" not in p.parts]


def _subprocess_calls(tree: ast.AST) -> list[ast.Call]:
    out: list[ast.Call] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "subprocess"
        ):
            out.append(node)
    return out


def test_no_shell_true_and_timeouts_present() -> None:
    problems: list[str] = []
    for path in _sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for call in _subprocess_calls(tree):
            assert isinstance(call.func, ast.Attribute)
            name = call.func.attr
            kws = {k.arg: k.value for k in call.keywords}
            where = f"{path.name}:{call.lineno} subprocess.{name}"
            shell = kws.get("shell")
            if isinstance(shell, ast.Constant) and shell.value:
                problems.append(f"{where}: shell=True")
            if name in TIMEOUT_CALLS and "timeout" not in kws:
                problems.append(f"{where}: missing timeout=")
    assert not problems, "\n".join(problems)


def test_popen_sites_manage_their_own_timeout() -> None:
    """Popen has no timeout kwarg; require wait/communicate(timeout=) in the file."""
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        if any(c.func.attr == "Popen" for c in _subprocess_calls(tree)):  # type: ignore[attr-defined]
            has_wait_timeout = any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"wait", "communicate"}
                and any(kw.arg == "timeout" for kw in node.keywords)
                for node in ast.walk(tree)
            )
            assert has_wait_timeout, (
                f"{path.name}: Popen without .wait(timeout=...) or .communicate(timeout=...)"
            )
