#!/usr/bin/env python3
"""Measure instruction bytes and ~tokens (bytes/4) loaded by each skill.

Before sizes come from git ref `main`. After sizes come from the working tree.
Target-source bytes are not included: they vary by repository. Source is reported
as how many times a completed run ingests the in-scope tree.

Run from the repo root:
  python3 scripts/measure_skill_context.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = "main"

SPECIALTIES = [
    "solidity-auditor/references/hacking-agents/math-precision-agent.md",
    "solidity-auditor/references/hacking-agents/access-control-agent.md",
    "solidity-auditor/references/hacking-agents/economic-security-agent.md",
    "solidity-auditor/references/hacking-agents/execution-trace-agent.md",
    "solidity-auditor/references/hacking-agents/invariant-agent.md",
    "solidity-auditor/references/hacking-agents/periphery-agent.md",
    "solidity-auditor/references/hacking-agents/first-principles-agent.md",
    "solidity-auditor/references/hacking-agents/asymmetry-agent.md",
    "solidity-auditor/references/hacking-agents/boundary-agent.md",
    "solidity-auditor/references/hacking-agents/numerical-gap-agent.md",
    "solidity-auditor/references/hacking-agents/trust-gap-agent.md",
    "solidity-auditor/references/hacking-agents/flow-gap-agent.md",
]

SHARED = [
    "solidity-auditor/references/senior-auditor-sop.md",
    "solidity-auditor/references/hacking-agents/shared-rules.md",
    "solidity-auditor/references/report-language.md",
]

FIZZ_AGENTS = [
    "fizz/agents/invariant-discovery/conservation-auditor.md",
    "fizz/agents/invariant-discovery/roundtrip-rounding-analyst.md",
    "fizz/agents/invariant-discovery/state-transition-mapper.md",
    "fizz/agents/invariant-discovery/adversarial-profit-maximizer.md",
    "fizz/agents/invariant-discovery/protocol-type-specialist.md",
    "fizz/agents/invariant-discovery/synthesizer.md",
]

# Files the procedure opens, excluding target source.
# eager = in context before the target tree is read.
# later = opened on a completed run, after that point.
PLANS = {
    "before": {
        "solidity-auditor": {
            "eager": [
                "solidity-auditor/SKILL.md",
                "solidity-auditor/references/report-formatting.md",
                "solidity-auditor/references/judging.md",
                "solidity-auditor/references/agent-prompts.md",
                "solidity-auditor/references/report-language.md",
            ],
            "later": ["solidity-auditor/references/dedup-and-assembly.md"],
            "passes": 3,
            "agents": 12,
            "source_reads": 36,
            "source_note": "12 agents x 3 passes each read the full tree inside their bundle. The parent cats it and does not Read it.",
        },
        "x-ray": {
            "eager": [
                "x-ray/SKILL.md",
                "x-ray/references/threats.md",
                "x-ray/references/templates.md",
            ],
            "later": [],
            "passes": 1,
            "agents": 0,
            "source_reads": 1,
            "source_note": "Path A: the parent reads each in-scope file once. Path B: subagents partition the files, still one read each. forge coverage stdout and the git JSON were returned into the parent before that read.",
        },
        "fizz": {
            "eager": ["fizz/SKILL.md", "fizz/references/template-map.md"],
            "later": [
                "fizz/references/selection-policy.md",
                "fizz/references/setup-playbook.md",
                "fizz/references/handler-patterns.md",
                "fizz/references/property-generation.md",
                *FIZZ_AGENTS,
            ],
            "passes": 1,
            "agents": 5,
            "source_reads": 6,
            "source_note": "Step 9a read the tree in the parent, pasted that context into 5 prompts, and told each agent to read the files.",
        },
    },
    "after": {
        "solidity-auditor": {
            "eager": [
                "solidity-auditor/SKILL.md",
                "solidity-auditor/references/agent-prompts.md",
            ],
            "later": [
                "solidity-auditor/references/dedup-and-assembly.md",
                "solidity-auditor/references/report-formatting.md",
                "solidity-auditor/references/judging.md",
                "solidity-auditor/references/report-language.md",
            ],
            "passes": 3,
            "agents": 12,
            "source_reads": 36,
            "source_note": "Unchanged: 12 fresh agents x 3 passes. The parent still does not Read the tree. maintainer-notes.md is not loaded.",
        },
        "x-ray": {
            "eager": ["x-ray/SKILL.md"],
            "later": [
                "x-ray/references/threats.md",
                "x-ray/references/invariant-synthesis.md",
                "x-ray/references/templates.md",
            ],
            "passes": 1,
            "agents": 0,
            "source_reads": 1,
            "source_note": "Same one read of the tree. Coverage and git JSON stay on disk until the step that uses them. Doc extraction is no longer capped at 200 lines.",
        },
        "fizz": {
            "eager": ["fizz/SKILL.md"],
            "later": [
                "fizz/references/template-map.md",
                "fizz/references/selection-policy.md",
                "fizz/references/setup-playbook.md",
                "fizz/references/handler-patterns.md",
                "fizz/references/property-generation.md",
                *FIZZ_AGENTS,
            ],
            "passes": 1,
            "agents": 5,
            "source_reads": 5,
            "source_note": "A script writes the extract. The parent does not read the tree at step 9. Five agents still each read the full file list once. Prompts are paths, not pasted source.",
        },
    },
}


def blob_size(rel: str, which: str) -> int:
    if which == "before":
        proc = subprocess.run(
            ["git", "show", f"{REF}:{rel}"],
            cwd=ROOT,
            capture_output=True,
        )
        if proc.returncode != 0:
            return 0
        return len(proc.stdout)
    path = ROOT / rel
    if not path.is_file():
        return 0
    return path.stat().st_size


def tokens(n: int) -> int:
    return n // 4


def plan_bytes(plan: dict, which: str) -> dict:
    eager = sum(blob_size(p, which) for p in plan["eager"])
    later = sum(blob_size(p, which) for p in plan["later"])
    shared = sum(blob_size(p, which) for p in SHARED) if plan["agents"] and "solidity" in plan["eager"][0] else 0
    specialty = sum(blob_size(p, which) for p in SPECIALTIES) if shared else 0
    worker = 0
    if shared:
        worker = plan["passes"] * (plan["agents"] * shared + specialty)
    elif plan["agents"]:
        # Fizz: each discovery agent receives its own prompt file once.
        # The synthesizer is in `later` (the parent reads it) and is not multiplied.
        discovery = [p for p in FIZZ_AGENTS if not p.endswith("synthesizer.md")]
        worker = sum(blob_size(p, which) for p in discovery)
    return {
        "eager": eager,
        "later": later,
        "full": eager + later,
        "worker": worker,
        "source_reads": plan["source_reads"],
        "source_note": plan["source_note"],
    }


def cell(before: int, after: int) -> str:
    delta = after - before
    sign = "+" if delta > 0 else ""
    return f"{tokens(before):,} → {tokens(after):,} ({sign}{tokens(delta):,})"


def main() -> int:
    rows = []
    print("Instruction tokens at ~4 chars/token. Target source is excluded.\n")
    print("| Skill | Eager before source | Full-run instruction | Worker instruction x fan-out | Full-tree reads |")
    print("| --- | ---: | ---: | ---: | ---: |")
    for skill in ("solidity-auditor", "x-ray", "fizz"):
        before = plan_bytes(PLANS["before"][skill], "before")
        after = plan_bytes(PLANS["after"][skill], "after")
        rows.append((skill, before, after))
        reads = f"{before['source_reads']} → {after['source_reads']}"
        print(
            f"| {skill} | {cell(before['eager'], after['eager'])} "
            f"| {cell(before['full'], after['full'])} "
            f"| {cell(before['worker'], after['worker'])} "
            f"| {reads} |"
        )
    print()
    for skill, before, after in rows:
        print(f"{skill}: {after['source_note']}")
    print()
    print("Not in the table: forge/hardhat coverage stdout and the x-ray git JSON no longer enter the parent as a tool result. Their size depends on the target. The files stay on disk.")
    print("Not in the table: solidity-auditor still sends each agent the full in-scope tree. Narrowing that would drop cross-contract coverage. The 12 x 3 multiplier is the method.")
    print("Chat return when the lifecycle orchestrator invoked the skill: a note of at most 1,600 characters. The findings index on disk holds the full text.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
