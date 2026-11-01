# Maintainer notes — not loaded during a scan

SKILL.md tells the running audit not to open this file. The notes are the reasons behind rules that used to be restated, at length, inside the prompt.

## Clocks

The orientation line in SKILL.md (1 pass ≈ 25 min, 3 passes ≈ 70 min, 5 passes ≈ 2 h) is a derived estimate for the 4-slot queue: twelve agents through four slots is about three agent-times end to end. It is not a measurement.

A real 3-pass scan of 2,228 lines of Solidity across 10 files, 12 agents per pass on Opus, all running at once, took 43 minutes wall clock: 11 minutes for pass 1 and about 16 for each of passes 2 and 3. Individual agents ran 3.5–11 minutes. That width is no longer the one this skill uses. Read it as a floor. When a real 4-slot scan is timed, correct the orientation line in SKILL.md. Do not add a third estimate.

## Rules a later editor keeps breaking

- A 1-pass scan does not touch the ledger. Making any memory step unconditional is a behavior change.
- Every scan writes `.solidity-auditor/runs/{stamp}/`, including a 1-pass scan. That directory is not the memory feature.
- Warn on `VERSION` only when the local number is lower than the published one. A local number that is higher is an unreleased edit.
- Do not put a model picker or a pass-count question back. Both block an unattended run.
- `--file-output` copies the assembled report. It does not decide whether the report exists.
- Do not inline source into agent prompts, and do not Read `source.md` or the bundles into the orchestrator context.
- Respawn an agent once per pass. A second death is not retried. The September 2026 scan that motivated this: three agents died of stalled streams, three replacements finished, and a second retry was still refused.
- The READ-ONLY rule stays unconditional. A scan where an agent wrote a Foundry PoC into the audited tree and deleted it afterwards is why. The tree was clean and the run was still wrong.
- Only a client `stall-death` narrows the queue to 2 slots. A watchdog kill does not.
- Turn 5 does not compose the report and does not compose the findings index. Both are scripts.
