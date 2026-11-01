#!/usr/bin/env python3
"""Write a whitehexlabs.audit-findings-index/v1 file from a solidity-auditor run.

The finding-lifecycle repository was not readable while this script was added.
The object below is the contract this skill emits. A later editor who has the
upstream schema should map fields, not drop bodies.

Every finding string is copied in full. This script never clips `description`,
`recommendation`, or `evidence`. The only length cap is the chat note from
`--note`, which points at the JSON and is not a second copy of the findings.

Output:
{
  "schema": "whitehexlabs.audit-findings-index/v1",
  "skill": "solidity-auditor",
  "run_id": "...",
  "target": "...",
  "report": "...",
  "log": null | "...",
  "scope": ["..."],
  "findings": [
    {
      "id": "solidity-auditor:<key>",
      "title": "<full>",
      "severity": null,
      "confidence": null | <int>,
      "kind": "finding" | "lead",
      "bug_class": null | "<full>",
      "location": {
        "file": null,
        "line": null,
        "contract": null | "<full>",
        "function": null | "<full>",
        "display": "<full>"
      },
      "description": "<full>",
      "recommendation": null | "<full>",
      "evidence": "<full>"
    }
  ]
}

`severity` stays null. This skill scores confidence, not Critical/High/Medium/Low.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCHEMA = "whitehexlabs.audit-findings-index/v1"
SKILL = "solidity-auditor"
NOTE_LIMIT = 1600

OPEN_RE = re.compile(r"^<!--F\s+(.*?)-->\s*$")
CLOSE = "<!--/F-->"
ATTR_RE = re.compile(r"(\w+)=(\S+)")
TITLE_RE = re.compile(r"^\[[0-9]+\] \*\*(.+)\*\*\s*$", re.M)
LEAD_TITLE_RE = re.compile(r"^- \*\*(.+?)\*\*", re.M)
LOC_RE = re.compile(r"`([^`]*)`")
AGENT_START_RE = re.compile(r"^(FINDING|LEAD) \|")


def norm_seg(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return value


def norm_key(parts: list[str]) -> str:
    return "|".join(norm_seg(p) for p in parts if p.strip())


def parse_attrs(raw: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in ATTR_RE.finditer(raw)}


def parse_run(text: str, pass_num: int) -> list[tuple[dict[str, str], str, int]]:
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        match = OPEN_RE.match(lines[i])
        if not match:
            i += 1
            continue
        attrs = parse_attrs(match.group(1))
        i += 1
        body: list[str] = []
        while i < len(lines) and lines[i].strip() != CLOSE:
            body.append(lines[i])
            i += 1
        blocks.append((attrs, "\n".join(body).strip("\n"), pass_num))
        if i < len(lines) and lines[i].strip() == CLOSE:
            i += 1
    return blocks


def scope_value(scope_path: Path, key: str) -> str:
    if not scope_path.is_file():
        return ""
    value = ""
    for line in scope_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "\t" not in line:
            continue
        k, v = line.split("\t", 1)
        if k == key:
            value = v
    return value


def split_location(display: str) -> tuple[str | None, str | None]:
    if not display or "." not in display:
        return None, None
    contract, function = display.rsplit(".", 1)
    contract = contract.strip() or None
    function = function.strip() or None
    return contract, function


def section_after(raw: str, heading: str, until: str | None) -> str | None:
    marker = f"**{heading}**"
    start = raw.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = raw.find(f"**{until}**", start) if until else -1
    chunk = raw[start:end].strip("\n") if end >= 0 else raw[start:].strip("\n")
    return chunk if chunk else None


def finding_from_block(attrs: dict[str, str], raw: str, ordinal: int) -> dict:
    kind_raw = attrs.get("kind", "FINDING").upper()
    kind = "lead" if kind_raw == "LEAD" else "finding"
    key = attrs.get("key", "").strip()
    if not key:
        key = f"unkeyed-{ordinal}"
    conf_raw = attrs.get("conf")
    confidence = int(conf_raw) if conf_raw and conf_raw.isdigit() else None
    title_match = TITLE_RE.search(raw) or LEAD_TITLE_RE.search(raw)
    title = title_match.group(1).strip() if title_match else (raw.strip() or key)
    display = ""
    loc_match = LOC_RE.search(raw)
    if loc_match:
        display = loc_match.group(1)
    contract, function = split_location(display)
    parts = key.split("|")
    bug_class = parts[2] if len(parts) >= 3 else None
    if contract is None and len(parts) >= 1 and not key.startswith("unkeyed-"):
        contract = parts[0] or None
    if function is None and len(parts) >= 2 and not key.startswith("unkeyed-"):
        function = parts[1] or None
    description = section_after(raw, "Description", "Fix")
    recommendation = section_after(raw, "Fix", None)
    if description is None:
        description = raw
    return {
        "id": f"{SKILL}:{key}",
        "title": title,
        "severity": None,
        "confidence": confidence,
        "kind": kind,
        "bug_class": bug_class,
        "location": {
            "file": None,
            "line": None,
            "contract": contract,
            "function": function,
            "display": display or key,
        },
        "description": description,
        "recommendation": recommendation,
        "evidence": raw,
    }


def rank(kind: str) -> int:
    return 1 if kind == "FINDING" else 0


def select_blocks(blocks: list[tuple[dict[str, str], str, int]]) -> list[tuple[dict[str, str], str]]:
    """Same winner rule as assemble.sh: stronger kind, then higher confidence, then later pass."""
    best: dict[str, tuple[int, int, int, dict[str, str], str]] = {}
    order: list[str] = []
    for ordinal, (attrs, raw, pass_num) in enumerate(blocks):
        key = attrs.get("key", "").strip() or f"unkeyed-{ordinal}"
        kind = attrs.get("kind", "FINDING").upper()
        conf_raw = attrs.get("conf")
        conf = int(conf_raw) if conf_raw and conf_raw.isdigit() else -1
        cand = (rank(kind), conf, pass_num, attrs, raw)
        if key not in best:
            order.append(key)
            best[key] = cand
            continue
        if cand[:3] >= best[key][:3]:
            best[key] = cand
    return [(best[k][3], best[k][4]) for k in order]


def agent_blocks(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    found: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if not AGENT_START_RE.match(lines[i]):
            i += 1
            continue
        start = i
        i += 1
        while i < len(lines) and not AGENT_START_RE.match(lines[i]) and not lines[i].startswith("## "):
            i += 1
        block = "\n".join(lines[start:i]).strip("\n")
        header = lines[start]
        key = ""
        group = re.search(r"group_key:\s*(.+)$", header)
        if group:
            key = norm_key([p for p in group.group(1).split("|")])
        else:
            contract = re.search(r"contract:\s*([^|]+)", header)
            function = re.search(r"function:\s*([^|]+)", header)
            bug = re.search(r"bug_class:\s*([^|]+)", header)
            parts = []
            if contract:
                parts.append(contract.group(1))
            if function:
                parts.append(function.group(1))
            if bug:
                parts.append(bug.group(1))
            key = norm_key(parts)
        if block:
            found.append((key, block))
    return found


def attach_checkpoints(findings: list[dict], checkpoint_dir: Path | None) -> None:
    if checkpoint_dir is None or not checkpoint_dir.is_dir():
        return
    extras: dict[str, list[str]] = {}
    for path in sorted(checkpoint_dir.glob("agent-*-out.md")):
        for key, block in agent_blocks(path.read_text(encoding="utf-8", errors="replace")):
            if not key:
                continue
            extras.setdefault(key, [])
            if block not in extras[key]:
                extras[key].append(block)
    for finding in findings:
        key = finding["id"].split(":", 1)[1]
        blocks = extras.get(key, [])
        addition = []
        for block in blocks:
            if block and block not in finding["evidence"]:
                addition.append(block)
        if addition:
            finding["evidence"] = (
                finding["evidence"].rstrip("\n")
                + "\n\n--- agent checkpoint ---\n"
                + "\n\n".join(addition)
            )


def load_runs(run_dir: Path) -> list[tuple[dict[str, str], str, int]]:
    paths = []
    for path in run_dir.glob("run-*.md"):
        match = re.search(r"run-(\d+)\.md$", path.name)
        if match:
            paths.append((int(match.group(1)), path))
    blocks = []
    for pass_num, path in sorted(paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        blocks.extend(parse_run(text, pass_num))
    return blocks


def build_note(doc: dict, index_path: Path) -> str:
    findings = [f for f in doc["findings"] if f["kind"] == "finding"]
    leads = [f for f in doc["findings"] if f["kind"] == "lead"]
    lines = [
        f"solidity-auditor run={doc['run_id']} target={doc['target']}",
        f"findings={len(findings)} leads={len(leads)}",
        f"report={doc['report']}",
        f"index={index_path}",
    ]
    ranked = sorted(findings, key=lambda f: -(f["confidence"] if isinstance(f["confidence"], int) else -1))
    shown = 0
    for finding in ranked:
        conf = finding["confidence"] if finding["confidence"] is not None else "-"
        extra = f"- [{conf}] {finding['title']} ({finding['location']['display']})"
        tentative = "\n".join(lines + [extra])
        if len(tentative) > NOTE_LIMIT - 80:
            rest = len(ranked) - shown
            if rest:
                lines.append(f"{rest} more findings are in the index, with full text.")
            break
        lines.append(extra)
        shown += 1
    note = "\n".join(lines)
    if len(note) > NOTE_LIMIT:
        note = note[: NOTE_LIMIT - 20].rstrip() + "\n…see index"
    return note


def build_document(args: argparse.Namespace) -> tuple[dict, Path]:
    run_dir = Path(args.dir)
    report = args.report or str(run_dir / "full-report.md")
    run_id = args.run_id or run_dir.name
    target = args.target or scope_value(run_dir / "scope.tsv", "name") or run_dir.name
    scope_files = scope_value(run_dir / "scope.tsv", "files").split()
    log_path = run_dir / "scan.log"
    selected = select_blocks(load_runs(run_dir))
    findings = [finding_from_block(attrs, raw, i) for i, (attrs, raw) in enumerate(selected, start=1)]
    attach_checkpoints(findings, Path(args.checkpoints) if args.checkpoints else None)
    doc = {
        "schema": SCHEMA,
        "skill": SKILL,
        "run_id": run_id,
        "target": target,
        "report": report,
        "log": str(log_path) if log_path.is_file() else None,
        "scope": scope_files,
        "findings": findings,
    }
    index_path = run_dir / "findings-index.json"
    return doc, index_path


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the solidity-auditor findings index")
    parser.add_argument("--dir", required=True, help="runs/{stamp} directory")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--target", default="")
    parser.add_argument("--report", default="")
    parser.add_argument("--out", default="", help="extra copy of the index, usually the lifecycle work dir")
    parser.add_argument("--checkpoints", default="", help="bundle dir holding agent-N-out.md, read before it is deleted")
    parser.add_argument("--note", action="store_true", help="print a <=1600 character return note")
    args = parser.parse_args(argv)
    run_dir = Path(args.dir)
    if not run_dir.is_dir():
        print(f"write_findings_index.py: no such directory {run_dir}", file=sys.stderr)
        return 2
    doc, index_path = build_document(args)
    write_json(index_path, doc)
    if args.out:
        write_json(Path(args.out), doc)
    print(f"wrote {index_path} — {len(doc['findings'])} entries", file=sys.stderr)
    if args.note:
        sys.stdout.write(build_note(doc, index_path))
        if not build_note(doc, index_path).endswith("\n"):
            sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
