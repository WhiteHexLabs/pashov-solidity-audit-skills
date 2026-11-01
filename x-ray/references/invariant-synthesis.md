# Invariant synthesis

Read this file at Step 2g, after source extraction, and not before. Follow it in order. Step 3a still decides how `x-ray.md` Section 3 points at `invariants.md`; this file decides which invariant rows exist.

### Step 2g: Invariant Synthesis

Using the delta writes, guard predicates, enum/one-shot transitions, and invariant comments extracted in Step 2 (from direct reads in Path A, or subagent output in Path B), systematically walk the following taxonomy to produce invariant candidates. This is a reasoning pass — no new tool calls needed (except the Grep batch in step 2 Pass B — see below).

**Terminology**: A *guard* is a per-call precondition enforced at a single callsite (e.g., `require(amount >= MIN)`). It is NOT a falsifiable invariant — the code itself guarantees it at that callsite. An *invariant* is a property that must hold globally across any sequence of calls (e.g., "every active position ≥ MIN"). Guards feed §1 of `invariants.md` (Enforced Guards reference) only. Invariants that are *lifted* from guards (see step 2 below) or stated in NatSpec feed §2 / §3 / §4.

**NatSpec routing** (run before the structural walk): For each NatSpec `@invariant` tag or inline comment asserting a global property (e.g., *"totalSupply always equals Σ balances"*, *"fee never exceeds MAX_BP"*, *"only one active epoch at a time"*), route DIRECTLY to §2 (or §3/§4 if the property spans contracts or derives from multiple primitives) by category shape (Conservation / Bound / Ratio / StateMachine / Temporal). Source tag: `NatSpec: Contract.sol:LN`. Do NOT place developer-stated global invariants in §1 — §1 is per-call guard predicates only. After routing, still run the structural scans below — they may confirm (On-chain=Yes) or contradict (On-chain=No) the NatSpec claim.

**Walk order** (each step uses the raw extraction data, not prior-step conclusions):

1. **Conservation scan**: For each function, find delta-write pairs where `Δ(A) = +expr` and `Δ(B) = -expr` (or `Δ(B) = +expr` for a mapping counterpart) in the same function body. Each matched pair is a conservation candidate: `A + B = const` or `A == Σ B[key]`.
   - For mapping writes (`mapping[key] += e` paired with `scalar += e`), infer `scalar == Σ mapping[key]`. Verify the pattern holds across ALL functions that write to either variable — if ANY function writes to one without the other, note the gap as "partial conservation" and split into Yes/No rows.
   - For transfer patterns (`mapping[from] -= e`, `mapping[to] += e` with no scalar change), confirm the mapping sum is self-conserving.
   - **Negative conservation** (important): If a function that *ought* to track a flow (e.g., flashloan pull/push, receive/forward) has zero storage Δ, record this as a Conservation-negative finding. Absence of Δ is itself an invariant observation.

2. **Guard extraction and lift** (two passes over each `require`/`assert`/`if-revert`):

   **Pass A — Extract verbatim (Enforced Guards reference)**: Every `require`/`assert`/`if-revert` becomes a `G-N` row in §1 of `invariants.md`. Quote the predicate verbatim with source location. This is a mechanical dump of per-call preconditions — not falsifiable, not fuzzed. Skip guards that only reference function parameters with no storage tie-back AND have no global implication (pure local input validation with no audit value beyond Pass B).

   **Pass B — Lift to global property, then check all write sites**: For each guard, ask: *"does this imply a property that must hold across any sequence of calls, not just at this callsite?"*
   - If **NO** (the guard only constrains a transient parameter that is consumed by the function and does not tie to persistent storage) → leave in §1 only. Do not promote.
   - If **YES** (the guard implies a persistent property — e.g., `require(amount >= MIN)` at deposit implies "every active position ≥ MIN"; `require(_fee <= 10)` at setter implies "fee ∈ [0, 10]") → rewrite the guard as a global property, then locate ALL write sites of the constrained storage variable using Grep on the variable name across scope files. Batch ALL write-site Greps for all lifted guards into a SINGLE parallel message — do not verify one at a time:
     - If **ALL write sites** enforce an equivalent guard → promote to §2 as a Bound invariant with On-chain=**Yes**. Derivation: cite the guard + confirm all write sites.
     - If **ANY write site** writes the variable without an equivalent guard → promote to §2 as a Bound invariant with On-chain=**No**, and cite the unguarded write site(s) as the gap. **This is the high-signal output** — the gap is simultaneously an invariant and a potential bug.

   Include setter-level bounds where a setter writes to a storage variable constrained by its own parameter check. Run the same all-write-site check — if multiple setters write the same variable but only some enforce the bound, the property is On-chain=No.

3. **Ratio scan**: For each storage write of form `A = B * C / D` where B, C, D are storage variables or function-scoped snapshots of storage, record the ratio. Note whether the snapshot is taken before or after other state changes in the same function (ordering matters — e.g., `totalSupply` snapshotted before `_burn` vs after).

4. **State machine / one-shot scan**: For each enum/uint/address variable in `require(var == X); ... var = Y` patterns, record the transition. Distinguish:
   - **One-shot latch**: `require(var == default); var = concrete` with no path back (e.g., `setStrategy`, `setLeverager`).
   - **Togglable flag**: `require(var == false); var = true` but another function flips it back (e.g., `freeze/unFreeze`, `toggleVaultLeverage`). NOT a state machine invariant — skip.
   - **Cyclic state**: `false → true → false` driven by timing/condition (e.g., `ongoingVestingPosition`). Record as a cycle invariant.

5. **Temporal scan**: For each `block.timestamp` or `block.number` comparison involving a storage variable (deadline, lastUpdate, lockPeriod, interval), extract the temporal constraint. Note whether the constraint is checked-then-updated (safe) or updated-then-checked (potential stale read).

6. **Cross-contract scan**: For each external call where the return value is used in arithmetic or a storage write, record what the caller assumes. Then find the callee's write sites for that state. If the callee can change it independently (via another function), the assumption is unvalidated — record as a cross-contract invariant with On-chain=No. ONLY include rows where BOTH sides (caller assumption + callee write sites) are inside the scope files. Do not speculate about out-of-scope contracts.
   - Also include: **setter-vs-invariant mismatches** — where an admin setter writes a storage value without checking that existing invariants still hold (e.g., `setReserveCapacity` without checking against current liquidity). These are cross-contract in the sense that the setter is one contract/function and the invariant is enforced elsewhere.

7. **Economic derivation**: After steps 1-6, check if any combination of single-contract + cross-contract invariants implies a higher-order property. Each economic invariant must cite the specific I-N / X-N IDs it derives from. If the derivation chain has a gap (one of the source invariants is On-chain=No), the economic invariant is also On-chain=No.

**Verification gate** (MANDATORY before including any inferred invariant):
- Conservation: confirm the Δ-pair exists at the cited lines (same function body).
- Guard (Pass A, §1 row): confirm the require/assert/if-revert is verbatim from code.
- Guard lift (Pass B, §2 row): confirm the lifted global property references persistent storage (not just a transient parameter restatement). Confirm all write sites of the constrained variable have been enumerated via Grep, and the On-chain=Yes/No verdict matches the enumeration — if any write site lacks the guard and the row says On-chain=Yes, the row is invalid.
- NatSpec: confirm the `@invariant` tag or comment exists verbatim at the cited location AND asserts a global property (not a per-call note). If it's a per-call note, drop — do not route to §2.
- Ratio: confirm the formula is exact and the snapshot ordering (before/after other writes in the same function) is noted.
- StateMachine: confirm both sides of the edge exist AND confirm no reverse path. If there IS a reverse path, it's a togglable flag — drop.
- Temporal: confirm the comparison involves a storage variable, not just block.timestamp vs parameters.
- Cross-contract: confirm both caller usage AND callee write site exist in scope.
- Economic: confirm all referenced I-N / X-N IDs are themselves verified.
- If you cannot verify → drop the row. "Could not verify" is not a valid row.

**Output**: Invariant candidates feed directly into `invariants.md` (Step 3a). x-ray.md Section 3 gets Enforced Guards (Reference) + top 3-5 inferred (prioritize On-chain=No from Conservation, Cross-Contract, and lifted-guard gaps; include one high-signal Yes row for structural coverage like a ratio or state-machine latch).
