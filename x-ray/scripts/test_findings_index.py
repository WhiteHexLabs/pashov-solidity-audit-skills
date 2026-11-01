#!/usr/bin/env python3
"""Light checks for the x-ray findings index."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).with_name("write_findings_index.py")
GAP = "UNGUARDED-WRITE " + ("0123456789" * 300)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp)
        text = f"""# Invariants

#### G-1

`require(amount > 0)` · `Vault.sol:10` · stops a zero deposit

#### I-1

`Bound` · On-chain: **Yes**

> fee stays inside the cap

**Derivation** — every writer checks the cap

#### I-2

`Bound` · On-chain: **No**

> {GAP}

**Derivation** — `Vault.sol:40` writes `fee` with no cap

**If violated** — a later deposit uses the uncapped fee

#### X-3

On-chain: **Yes**

> the callee's total matches the caller

#### E-4

On-chain: **No**

> assets cover shares

**Follows from** — `I-2`

**If violated** — {GAP}
"""
        (out / "invariants.md").write_text(text, encoding="utf-8")
        (out / "x-ray.md").write_text("# X-Ray\n\n## X-Ray Verdict\n\nTier: ready\n", encoding="utf-8")
        note = subprocess.run(
            [sys.executable, str(SCRIPT), "--dir", str(out), "--run-id", "xr-1", "--target", "demo", "--note"],
            check=True,
            capture_output=True,
            text=True,
        )
        doc = json.loads((out / "findings-index.json").read_text(encoding="utf-8"))
        ids = [f["id"] for f in doc["findings"]]
        assert ids == ["x-ray:I-2", "x-ray:E-4"], ids
        assert all(f["kind"] == "lead" for f in doc["findings"])
        assert all(GAP in f["evidence"] for f in doc["findings"])
        assert "require(amount > 0)" not in json.dumps(doc["findings"])
        assert len(note.stdout) <= 1600
        assert GAP not in note.stdout
        assert "leads=2" in note.stdout
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
