#!/usr/bin/env python3
"""Light checks for the findings index. Run: python3 solidity-auditor/references/test_findings_index.py"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("write_findings_index.py")
PROOF = "PROOF-SENTINEL " + ("abcdefghij" * 400)  # 4000+ chars, must survive verbatim


def run_case(root: Path) -> dict:
    run = root / "runs" / "20260101-000000"
    run.mkdir(parents=True)
    (run / "scope.tsv").write_text(
        "name\tvault\nmode\tdefault\nfiles\tsrc/Vault.sol src/Router.sol\n",
        encoding="utf-8",
    )
    (run / "run-1.md").write_text(
        "\n".join(
            [
                "# Run 1",
                "<!--F key=vault|withdraw|reentrancy conf=95 kind=FINDING agents=3-->",
                "",
                "[95] **Withdraw sends ETH before it lowers the balance**",
                "",
                "`Vault.withdraw` · Confidence: 95",
                "",
                "**Description**",
                "Any caller can take the same deposit twice, because withdraw sends ETH before it lowers the balance.",
                "",
                "**Fix**",
                "",
                "```diff",
                "- send then write",
                "+ write then send",
                "```",
                "",
                "<!--/F-->",
                "",
                "<!--F key=vault|sweep|unchecked-recipient conf= kind=LEAD agents=1-->",
                "",
                "- **Sweep does not check the recipient** — `Vault.sweep` — the call has no recipient check — we did not finish the trace.",
                "",
                "<!--/F-->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    # A later pass rewrites the same finding and must win, keeping its longer body.
    (run / "run-2.md").write_text(
        "\n".join(
            [
                "<!--F key=vault|withdraw|reentrancy conf=95 kind=FINDING agents=4-->",
                "",
                "[95] **Withdraw sends ETH before it lowers the balance**",
                "",
                "`Vault.withdraw` · Confidence: 95",
                "",
                "**Description**",
                "Any caller can take the same deposit twice, because withdraw sends ETH before it lowers the balance.",
                "",
                "**Fix**",
                "",
                "```diff",
                "- send then write",
                "+ write then send",
                "```",
                "",
                PROOF,
                "",
                "<!--/F-->",
                "",
            ]
        ),
        encoding="utf-8",
    )
    bundle = root / "bundle"
    bundle.mkdir()
    (bundle / "agent-1-out.md").write_text(
        "\n".join(
            [
                "## Findings",
                "FINDING | contract: Vault | function: withdraw | bug_class: reentrancy | group_key: Vault | withdraw | reentrancy",
                "path: caller → withdraw → ETH out → balance write",
                f"proof: {PROOF}",
                "description: Any caller can take the same deposit twice.",
                "fix: write the balance before the call",
                "",
            ]
        ),
        encoding="utf-8",
    )
    out = root / "lifecycle" / "findings-index.json"
    note = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dir",
            str(run),
            "--run-id",
            "run-abc",
            "--target",
            "vault",
            "--out",
            str(out),
            "--checkpoints",
            str(bundle),
            "--note",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    doc = json.loads((run / "findings-index.json").read_text(encoding="utf-8"))
    copied = json.loads(out.read_text(encoding="utf-8"))
    assert copied == doc
    assert doc["schema"] == "whitehexlabs.audit-findings-index/v1"
    assert doc["skill"] == "solidity-auditor"
    assert doc["run_id"] == "run-abc"
    assert doc["target"] == "vault"
    assert doc["scope"] == ["src/Vault.sol", "src/Router.sol"]
    assert len(doc["findings"]) == 2
    finding = next(f for f in doc["findings"] if f["kind"] == "finding")
    lead = next(f for f in doc["findings"] if f["kind"] == "lead")
    assert finding["id"] == "solidity-auditor:vault|withdraw|reentrancy"
    assert finding["confidence"] == 95
    assert finding["severity"] is None
    assert finding["bug_class"] == "reentrancy"
    assert PROOF in finding["evidence"]
    assert "write then send" in finding["recommendation"]
    assert "agent checkpoint" in finding["evidence"]
    assert "caller → withdraw → ETH out → balance write" in finding["evidence"]
    assert lead["kind"] == "lead"
    assert "we did not finish the trace" in lead["evidence"]
    assert len(note.stdout) <= 1600
    assert "findings=1" in note.stdout
    assert "leads=1" in note.stdout
    assert PROOF not in note.stdout
    return doc


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        run_case(Path(tmp))
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
