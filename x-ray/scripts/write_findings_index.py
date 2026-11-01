#!/usr/bin/env python3
"""Write a whitehexlabs.audit-findings-index/v1 file from an x-ray directory.

x-ray does not confirm exploits. Blocks in invariants.md whose On-chain field
is No are indexed as leads, because that file already treats them as potential
bugs. The block text is copied in full. Yes-blocks and enforced guards are
not indexed. The report files are not modified.

See solidity-auditor/references/write_findings_index.py for the field set.
`severity` and `confidence` are null: x-ray does not score them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "whitehexlabs.audit-findings-index/v1"
SKILL = "x-ray"
NOTE_LIMIT = 1600
HEADING_RE = re.compile(r"^####\s+((?:I|X|E|G)-\d+)\s*$", re.M)
NO_RE = re.compile(r"On-chain:\s*(?:\*\*)?No(?:\*\*)?", re.I)


def blocks(text: str) -> list[tuple[str, str]]:
    matches = list(HEADING_RE.finditer(text))
    found = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        ident = match.group(1)
        if ident.startswith("G-"):
            continue
        body = text[start:end].strip("\n")
        if NO_RE.search(body):
            found.append((ident, body))
    return found


def claim_line(body: str) -> str:
    for line in body.splitlines():
        stripped = line.strip().lstrip("> ").strip()
        if not stripped or stripped.startswith("####") or stripped.startswith("On-chain"):
            continue
        if stripped.startswith("**") and stripped.endswith("**"):
            continue
        return stripped
    return body.splitlines()[0] if body else ""


def build_note(doc: dict, index_path: Path) -> str:
    lines = [
        f"x-ray run={doc['run_id']} target={doc['target']}",
        f"leads={len(doc['findings'])} (On-chain=No invariant blocks, full text in the index)",
        f"report={doc['report']}",
        f"index={index_path}",
    ]
    for finding in doc["findings"]:
        extra = f"- {finding['id'].split(':', 1)[1]} {finding['title']}"
        tentative = "\n".join(lines + [extra])
        if len(tentative) > NOTE_LIMIT - 60:
            lines.append("remaining leads are in the index, with full text.")
            break
        lines.append(extra)
    note = "\n".join(lines)
    if len(note) > NOTE_LIMIT:
        note = note[: NOTE_LIMIT - 20].rstrip() + "\n…see index"
    return note


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the x-ray findings index")
    parser.add_argument("--dir", required=True, help="x-ray output directory")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--out", default="")
    parser.add_argument("--note", action="store_true")
    args = parser.parse_args(argv)
    out_dir = Path(args.dir)
    if not out_dir.is_dir():
        print(f"write_findings_index.py: no such directory {out_dir}", file=sys.stderr)
        return 2
    invariants = out_dir / "invariants.md"
    text = invariants.read_text(encoding="utf-8", errors="replace") if invariants.is_file() else ""
    findings = []
    for ident, body in blocks(text):
        title = claim_line(body)
        findings.append(
            {
                "id": f"{SKILL}:{ident}",
                "title": title,
                "severity": None,
                "confidence": None,
                "kind": "lead",
                "bug_class": None,
                "location": {
                    "file": "x-ray/invariants.md",
                    "line": None,
                    "contract": None,
                    "function": None,
                    "display": ident,
                },
                "description": body,
                "recommendation": None,
                "evidence": body,
            }
        )
    report = str(out_dir / "x-ray.md")
    doc = {
        "schema": SCHEMA,
        "skill": SKILL,
        "run_id": args.run_id or out_dir.name,
        "target": args.target or out_dir.parent.name,
        "report": report,
        "log": str(out_dir / "coverage.log") if (out_dir / "coverage.log").is_file() else None,
        "scope": [],
        "findings": findings,
    }
    index_path = out_dir / "findings-index.json"
    payload = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
    index_path.write_text(payload, encoding="utf-8")
    if args.out:
        dest = Path(args.out)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(payload, encoding="utf-8")
    print(f"wrote {index_path} — {len(findings)} leads", file=sys.stderr)
    if args.note:
        sys.stdout.write(build_note(doc, index_path))
        if not build_note(doc, index_path).endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
