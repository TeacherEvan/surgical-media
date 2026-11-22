"""job_cli.py — command-line front end for the production-job layer.

job_cli.py validate JOB.json
job_cli.py create JOB.json            # prints job id
job_cli.py status JOB_ID
job_cli.py plan JOB_ID                # writes artifacts/agent_request.json
job_cli.py submit JOB_ID --storyboard board.json
job_cli.py preview JOB_ID | audit JOB_ID
job_cli.py approve JOB_ID --reviewer NAME [--reject]
job_cli.py export JOB_ID              # prepares a package; never publishes
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = str(Path(__file__).resolve().parent)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import investigation_brief
from job_director import Director
from job_model import JobError, validate_request
from job_store import DEFAULT_ROOT, JobStore


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="surgical-media production jobs")
    p.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="jobs directory")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("validate", "create"):
        sub.add_parser(name).add_argument("job_file", type=Path)
    vb = sub.add_parser("validate-brief")
    vb.add_argument("brief_file", type=Path)
    for name in ("status", "preview", "audit", "export", "cancel"):
        sub.add_parser(name).add_argument("job_id")
    pl = sub.add_parser("plan")
    pl.add_argument("job_id")
    pl.add_argument("--brief", type=Path, default=None)
    s = sub.add_parser("submit")
    s.add_argument("job_id")
    s.add_argument("--storyboard", type=Path, required=True)
    a = sub.add_parser("approve")
    a.add_argument("job_id")
    a.add_argument("--reviewer", required=True)
    a.add_argument("--reject", action="store_true")
    return p


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"cannot read {path}: {exc}") from exc


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    director = Director(JobStore(args.root))
    try:
        if args.cmd == "validate":
            errors = validate_request(_load(args.job_file))
            for err in errors:
                print(f"FAIL {err}", file=sys.stderr)
            if errors:
                return 1
            print(f"OK {args.job_file}")
        elif args.cmd == "validate-brief":
            errors = investigation_brief.validate_request(_load(args.brief_file))
            for err in errors:
                print(f"FAIL {err}", file=sys.stderr)
            if errors:
                return 1
            print(f"OK {args.brief_file}")
        elif args.cmd == "create":
            print(director.create(_load(args.job_file)))
        elif args.cmd == "status":
            st = director.store.state(args.job_id)
            print(json.dumps({"job_id": args.job_id, "state": st.value}))
        elif args.cmd == "plan":
            print(director.plan(args.job_id, brief_path=args.brief))
        elif args.cmd == "submit":
            errors = director.submit(args.job_id, args.storyboard)
            for err in errors:
                print(f"FAIL {err}", file=sys.stderr)
            if errors:
                return 1
            print("storyboard accepted")
        elif args.cmd == "preview":
            print(director.preview(args.job_id))
        elif args.cmd == "audit":
            report = director.audit(args.job_id)
            print(json.dumps({"ok": report["ok"]}))
            return 0 if report["ok"] else 1
        elif args.cmd == "approve":
            director.approve(args.job_id, args.reviewer, approve=not args.reject)
            print("recorded")
        elif args.cmd == "export":
            print(director.export(args.job_id))
        elif args.cmd == "cancel":
            director.cancel(args.job_id)
            print("cancelled")
    except JobError as exc:
        print(f"job_cli: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
