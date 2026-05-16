# Clarification Gate — Shared Template

Used by `/research`, `/deep-research`, and `/content-research` at Step 0.75
to detect underspecified invocations and prompt the user once (in a single
batch) before running searches.

**Core principle:** never serialize questions. Ask everything missing in
ONE message, not one-by-one. Wait for one answer, then proceed.

---

## When to trigger (the gate)

Skip the gate ENTIRELY if any of these apply:

- Invocation is **>50 words** — you've given enough context
- Invocation includes a **specific URL** (article, advisory, vendor page)
- Invocation includes a pointer **"using context from <file>"** or **"as a follow-up to <slug>"**
- Topic is **explicitly tagged self-applied** ("my stack", "my farm", "my apps")
- Invocation is **pasted article text** (rarely needs clarification)
- This is an **obvious smoke test** (single short topic, no qualifiers)

Otherwise, score the invocation against the skill's dimensions below. If
3+ dimensions are unclear, trigger the gate.

---

## Per-skill dimensions

### `/research` — full gate (5 dimensions)

| Dimension | Question shape |
|---|---|
| **Topic specificity** | "What angle of [topic] matters most?" |
| **Mode** | "Comparison, how-to, explainer, or landscape survey?" (only ask if ambiguous from input) |
| **Audience** | "Is this for you / a specific client / general reference?" |
| **Deliverable** | "What will you do with the output? (decision support, implementation prep, meeting prep, reference)" |
| **Lens** | "What specific angle should I emphasize?" |

Ask the 2-5 missing ones in a single numbered question block.

### `/deep-research` — light gate (1-3 dimensions max)

| Dimension | Question shape |
|---|---|
| **Self vs third-party** | "Is this for your stack or someone else's? (default: yours)" — only ask if the topic doesn't obviously match your stack |
| **Briefing vs deep-dive** | "Briefing (shareable, terse) or deep dive (full analysis with action items)?" — only ask if not specified |
| **Urgency** | "Is this immediate-action security work or informational research?" — only ask if no time signal in input |

If the input is a URL or pasted article, skip the gate entirely. If the
input is a specific product/CVE/vendor name, ask at most ONE question (the
self/third-party one, if non-obvious).

### `/content-research` — full target-context capture (handled in Step 1.5)

The target-template.md fields ARE the clarification gate for content-research.
See `~/.claude/skills/_research-lib/contexts/_target-template.md`. Same
trigger logic: skip if invocation is fully-specified, prompt once if not.

---

## Question format (universal)

Every clarification message follows this shape:

```
Before I dig in, [N] thing[s]:
1. **<Short label>:** <question phrased as a choice with options>?
2. **<Short label>:** <question>?
...

Or: skip these and I'll just run with [the default inference] — tell me to "go" if that's fine.
```

The "skip these" line is mandatory. It gives the user an escape hatch when
they don't want to specify and trust the default.

---

## Writing the answers to the run folder

After the user answers, write the captured info to:

- For `/research` and `/deep-research`: `{output-folder}/_context.md` —
  a small markdown file with the clarification answers as YAML frontmatter
  plus a short prose note.
- For `/content-research`: already covered by Step 1.5's `_context.md`.

This means every dated run folder has a `_context.md` recording WHY the
research happened. future-you can answer "why did I research this?" in
6 months by reading that one file.

Format for `/research` and `/deep-research` `_context.md`:

```markdown
---
engagement_for: "[answer or 'self']"
deliverable: "[answer]"
lens: "[answer]"
mode: "[answer or inferred]"
gate_triggered: true | false
filled_at: YYYY-MM-DD
---

## Why this run

[One paragraph synthesizing the clarification answers OR auto-derived from
the invocation if gate was skipped.]
```

---

## When the gate is skipped

When the gate is skipped (clear invocation OR user says "go"), still write
a minimal `_context.md` with `gate_triggered: false` and a one-line "Why
this run" derived from the invocation. The file exists for every run,
period — even if it's auto-generated.

---

## Memory-worthy signals

If the user's clarification answers reveal something durable that's not in
self.md (new client, new app, new working relationship, new
preference), note it in the run's report under a "Notable for memory"
section at the end. Don't auto-save — let the user decide.

Examples:
- "Working with [new client] — should this go in memory?"
- "You said you prefer X format — should I save that as a feedback memory?"
- "First time you've mentioned [tool/concept] — worth a reference memory?"
