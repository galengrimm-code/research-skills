---
name: storm-verify
version: "1.0.0"
description: Adversarial proofing pass for a completed research report. Independently verifies the load-bearing claims of a /research, /deep-research, /content-research, or /content-update run against their PRIMARY sources, re-scores confidence, tallies fabricated/corrected/demoted claims, and produces an assert/caveat/avoid claim-safety guide. Appends a Verification section to the report (non-destructive) and optionally renders a shareable HTML briefing. Invoke with /storm-verify [run-folder-or-report-path], or accept the "Storm protocol" offer at the end of a research run. This is the verified-proofing slice of the STORM method — it does NOT do its own web research; it checks work already produced.
argument-hint: "[path to a run folder or REPORT.md — defaults to the most recent research run]"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Agent
---

# Storm-Verify

## What this does

Takes a research report that already exists and **proofs it**: independently verifies its load-bearing claims against primary sources, downgrades what doesn't hold, and tells you plainly what is safe to assert. It is the adversarial-verification slice of the STORM method, decoupled from STORM's own research — the sourcing was already done by `/research` (or a sibling). This step exists to keep an over-confident synthesis honest before you act on it or hand it to someone.

It never re-runs the research. It never invents sources. It checks, corrects, and grades.

## When it runs

- **Chained (offered, never automatic):** the two skills that produce a synthesized, claim-bearing report — `research` and `deep-research` — offer it at the end of a run. It runs ONLY on an explicit yes; decline with "drop the storm protocol" and nothing happens. (`content-research` and `content-update` do not offer it: a content-research run is an extraction dossier, not a synthesis, and content-update never changes a report's claims — so there is rarely anything to proof. Both can still be proofed standalone if a specific run warrants it.)
- **Standalone:** `/storm-verify <run-folder>` or `/storm-verify <path/to/REPORT.md>` on any prior run.
- **No argument:** default to the most recently modified research run (see Phase 0).

## Phase 0: Locate the report

1. If `$ARGUMENTS` names a folder or a `.md` file, use it. A folder must contain a `REPORT.md` (or `INDEX.md` for content-research dossiers); a file is treated as the report directly.
2. Otherwise find the most recent run under the conventions root:
   ```bash
   ROOT="$HOME/Documents/AI/Content extraction/topics"
   # most recently modified REPORT.md (research / deep-research), fall back to INDEX.md (dossiers)
   latest=$(ls -dt "$ROOT"/**/REPORT.md "$ROOT"/*/REPORT.md 2>/dev/null | head -1)
   [ -z "$latest" ] && latest=$(ls -dt "$ROOT"/**/INDEX.md "$ROOT"/*/INDEX.md 2>/dev/null | head -1)
   echo "Target: $latest"
   ```
   Confirm the resolved path with the user in one line before proceeding ("Proofing: <path> — go?"). If nothing is found, tell the user there's no run to proof and stop.
3. Set `RUN_DIR` = the report's folder and `REPORT_PATH` = the resolved report file (`REPORT.md`, or `INDEX.md` for a content-research dossier). Every later step that appends does so to `REPORT_PATH` — never to a hard-coded filename. The `_raw/` subfolder (if present) holds the originally fetched sources — the verifiers may consult it, but must confirm against the live primary source the report cited, not just the cached copy.

## Phase 1: Extract the load-bearing claims

Read the report. Pull the claims the conclusions actually rest on — the facts that, if wrong, would change the answer.

- **If the report has a "Key Claims & Evidence Chains" table** (`/research` v3.4.0+ and `/deep-research` produce one): use its rows directly. That table already names each claim, its independent-line count, and what it traces back to — it is the ideal input.
- **Otherwise** derive 4–8 load-bearing claims yourself: every cited figure, benchmark, pricing/limit fact, causal claim, and "most people have moved to X" trend claim. Skip decorative or clearly-hedged statements.
- **For a content-research dossier (INDEX.md):** there is usually little synthesized claim-making — it's captured content. Extract only the explicit claims in any summary/synthesis section. If there are none, say so and stop cleanly (nothing to proof is a valid, honest result — not a failure).

For each claim, record: the claim text, the exact figure/quote, the source it's attributed to in the report, and the source URL if present. This is the verification worklist.

**Only claims the report attributes to a source are verifiable here.** If a load-bearing claim carries no cited or named source, record it as `UNVERIFIED (uncited)` and move on — do NOT go find a fresh source to confirm it. Discovering new sources for uncited assertions is new research, which this skill does not do; an uncited claim confirmed by a source the report never used is exactly the false-confidence this pass exists to prevent.

## Phase 2: Adversarial primary-source verification (parallel agents)

Group related claims into 4–6 clusters (by shared source or topic). Spawn one `general-purpose` agent per cluster **in a single message** so they run concurrently. Each agent is a skeptic whose job is to *refute*, not confirm. Use this prompt per cluster:

> Independently verify these claims against their PRIMARY source. Be skeptical — do NOT trust secondary blog summaries or the report's own characterization. For each claim: {claim + cited figure + named source + URL}. Locate the actual primary source *behind the citation the report already names* (original paper, official data page, vendor changelog, filing) — do NOT hunt for some new source to rescue a claim the report left uncited; a claim with no source the report actually used is UNVERIFIED by definition. Confirm or correct: exact title/author/venue/year/URL, the real figure or effect size as published, the sample/method and any author-stated limits, and — for research claims — peer-review status (published vs preprint). For any contested claim, find the strongest credible counter-source. Default toward skepticism: if you cannot reach the cited primary source, the verdict is UNVERIFIED, not CONFIRMED. Return, per claim: VERDICT = CONFIRMED / PARTIALLY CONFIRMED / UNVERIFIED / FALSE, then the corrected one-line citation, then 2–4 bullets of specifics with the primary URL. Under 300 words per claim.

Collect all verdicts. Do not soften them.

## Phase 3: Re-score after verification (inline, no agents)

**Build on the report's own analysis — do not redo it.** If the report already carries a `Key Claims & Evidence Chains` table (`/research` Step 4.5) or a `Settled / Contested / Unknown` section (Step 5), its independence-counting, citation-laundering, and recency judgments are already done. Read them and carry them forward; this phase only records what *verification* changed. Only run the checks below from scratch on a legacy/nonconforming report that lacks that tracing.

1. **Confidence re-score (always)** — assign each claim a 1–10 reliability score on the evidence hierarchy: peer-reviewed causal > official policy/financial data > single commissioned survey > analogy > preprint. The score reflects post-verification evidence quality (the verdict from Phase 2), not how confident the original author sounded, and not the report's pre-verification score.
2. **Weakest link (always)** — name the load-bearing claim whose verdict is softest and what single check would settle it.
3. **Only if the report did NOT already trace this:** flag citation laundering (multiple "independent" citations tracing to one origin — collapse to one line of evidence) and staleness (a "settled" claim resting on evidence older than ~18 months in a fast-moving domain supports "was true," not "is true"). If the report's Key Claims table already covered it, cite that rather than recomputing.

## Phase 4: Apply corrections + build the outputs

**4a. Compute the tally.** Across all verdicts:
- `fabricated` = FALSE verdicts (claim/figure/source does not exist or is materially wrong)
- `corrected` = PARTIALLY CONFIRMED (right direction, wrong specifics — figure/date/title fixed)
- `demoted` = CONFIRMED-but-thin, preprint, single-source, or stale → confidence lowered / moved to "contested"
- `verified` = CONFIRMED and solid

**4b. Build the claim-safety guide** from the verdicts:
- **✓ Assert** — CONFIRMED against a primary/official source. Safe to state flatly.
- **⚠ Caveat** — PARTIALLY CONFIRMED or single-source. State only with attribution/qualification.
- **✕ Avoid** — FALSE, UNVERIFIED, contested, or preprint. Name each so it doesn't slip back in.

**4c. Append to the report (default output, non-destructive).** Add this section to the END of `REPORT_PATH` (the file resolved in Phase 0 — `REPORT.md` or a dossier's `INDEX.md`) — never rewrite existing content. If a `Verification & Claim Safety` section already exists from a prior pass, append a new dated one below it; never overwrite the earlier verdicts.

```markdown
## Verification & Claim Safety — storm-verify v1.0.0 (YYYY-MM-DD)

**Result: N claims checked · X fabricated · Y corrected · Z demoted.** Confidence scores below reflect post-verification evidence quality.

### Verdicts
| # | Claim | Verdict | Confidence | Correction / note | Primary source |
|---|-------|---------|-----------|-------------------|----------------|
| 1 | ... | CONFIRMED | 9/10 | — | [title](url) |
| 2 | ... | PARTIALLY CONFIRMED | 5/10 | figure was 34%, not 60% | [title](url) |

### Claim safety
- **✓ Assert:** ...
- **⚠ Caveat:** ...
- **✕ Avoid:** ...
```

You may also *add* (never overwrite) the keys `storm_verified: true` and `storm_verify_date: YYYY-MM-DD` to the report's YAML frontmatter if it has frontmatter — this is the one permitted edit outside the appended section, and it must only insert those two new keys, never change an existing key's value. Leave dossiers without frontmatter untouched.

**4d. Offer the HTML briefing.** Ask once: "Also render the shareable HTML briefing? (y/n)". If yes:
1. Read `report-template.html` in this skill folder. Clone it; keep the `<style>` block verbatim.
2. Fill: the verify banner (the tally), the 60-second summary (from the report's TL;DR / Bottom Line), the verified findings as finding cards (confidence score + Supported / Challenged / Corrected chips), the claim-safety guide, and the references with per-citation verification-status tags (`ok` / `part` / `weak`). Put any demoted/contested claim in the contested sidebar.
3. Write to `RUN_DIR/briefing.html`.
4. Open it: Windows `start "" "<path>"` (or PowerShell `Start-Process "<path>"`), macOS `open`, Linux `xdg-open`.

## Output

Report to the user, tight:
- The report path that was proofed and the line appended.
- The tally: `N/N checked · X fabricated · Y corrected · Z demoted`.
- The one-line claim-safety summary: what's safe to assert vs what to avoid.
- The HTML path, if rendered.

## Guardrails

- **Proofing only — no new research.** This skill checks claims already in the report; it does not go discover new ones or rewrite the analysis. If the report is thin, say so; don't backfill it.
- **Non-destructive.** Only ever *append* to the report body (`REPORT_PATH`) and *add* the two `storm_verify*` frontmatter keys (4c). Never change existing prose or an existing frontmatter value; never delete anything. On a re-run, append a new dated Verification section — don't overwrite the old one. Never overwrite a prior `briefing.html` — version it (`briefing-v2.html`) if one exists.
- **Skepticism is the default.** No reachable primary source ⇒ UNVERIFIED, never CONFIRMED. The tally must be truthful — a proofing pass that flatters the report is worthless.
- **Reliability = evidence quality, not author confidence.** Score on the source hierarchy, not on how certain the prose sounded.
- **Nothing to verify is a valid result.** A pure extraction dossier with no synthesized claims gets an honest "no load-bearing claims to proof" — not a manufactured verdict table.
- **Cost.** ~4–6 verifier agents per run. Do not fan out one agent per claim; cluster them.
