# Target Context — Template

Per-engagement context for `/content-research` runs. Filled at the start of
each run and saved alongside the archive as `_context.md`. Records WHY the
research is being done so future-you (or a future skill) can frame the
output appropriately.

The skill prompts you for the missing pieces if they aren't in the initial
invocation, then writes the filled version to the archive folder.

---

## Required frontmatter

```yaml
---
engagement_for: "[who asked / who this is for — name or 'self']"
relationship: "[employee | client | partner | competitor | friend | self | other]"
deliverable: "[what they need with the output — meeting prep, sales playbook, dossier, competitive analysis, etc.]"
deadline: "[ISO date or 'no deadline']"
sensitivity: "[public | internal | confidential]"
lens: "[what angle to emphasize — methodology, products, competitive position, talent, technology, market, etc.]"
filled_at: "YYYY-MM-DD"
---
```

---

## Required prose sections

### Why this target?
One paragraph. What surfaced this target? Why now? What question is the
research supposed to answer?

### What outcome does the requester need?
Specific. "Three differentiation angles for an upcoming sales meeting" beats
"general competitive context." If the deliverable is a meeting,
who's in it and what decision is on the table?

### What should NOT be in scope?
Explicitly bound the run. "Skip personal background — focus on commercial
methodology only." Or "Skip product details — focus on team history and
funding." This prevents the archive from sprawling.

### Sensitivities or constraints
Is the target a customer? A competitor? Someone in your network?
Sensitivity affects what gets surfaced in synthesis and how findings get
phrased.

---

## How the skill uses this

1. Skill reads this template at Step 1
2. Skill prompts you for any missing fields (in interactive mode) OR
   extracts them from the initial invocation (in batch mode)
3. Skill writes the filled version to
   `Documents\AI\Content extraction\{slug}-research-YYYY-MM-DD\_context.md`
4. Skill includes the lens and outcome in its synthesis decisions —
   specifically, what to surface in INDEX.md "Key Facts" and how to phrase
   the "Honest gaps" section

---

## Example filled version

```markdown
---
engagement_for: "Nathan Hrnicek, Director of Sales at NutraDrip"
relationship: "client"
deliverable: "Sales playbook outside review — looking for differentiation angles and competitive positioning input"
deadline: "no deadline"
sensitivity: "confidential"
lens: "methodology, sales narrative, competitive position vs other ag fertility brands"
filled_at: "2026-05-12"
---

### Why this target?
Sarah is leading sales at Acme Corp and asked you for an outside read on
their playbook. you have domain context and isn't inside the
company's narrative, so he can spot what NutraDrip is taking for granted.

### What outcome does the requester need?
A document Nathan can use to refine NutraDrip's sales-deck talking points.
Specifically: where their methodology genuinely differentiates from
Calibrated/AEA/SoilWorks, and where their current pitch overlaps with
competitors in ways that hurt them.

### What should NOT be in scope?
Internal financial / cap-table / personnel details. Stay on the public-facing
methodology and competitive positioning surface.

### Sensitivities or constraints
Nathan is a working relationship — output should be diplomatically framed,
not adversarial. Findings should be useful, not "here's why your pitch is
weak."
```

---

## When to skip this template

If `/content-research` is run on a target where engagement is genuinely
"self / for general reference" (e.g., archiving an agronomy practitioner's
content for future your-own reference), set `engagement_for: self` and
skip the prose sections. The template still gets written as `_context.md`
in the archive, but it's lighter.

Don't skip it entirely. Even "for reference" archives benefit from a
one-paragraph note about why this target was prioritized — future-you
won't remember in 6 months.
