---
name: deep-research
version: "3.3.0"
description: Deep research on AI news, security advisories, tech articles, and industry topics. Scrapes articles, YouTube transcripts, PDFs, and related sources across the internet, then synthesizes into exposure analysis for the user's tech stack. Invoke with /deep-research followed by pasted article text, URLs, or a topic description.
allowed-tools: Bash, WebSearch, WebFetch, Agent
---

# Deep Research Skill

Comprehensive internet research that goes beyond Claude's built-in web search. Uses SerpAPI (search), Serper (search), Firecrawl (scraping), yt-dlp (YouTube transcripts), and Playwright (fallback) to fetch, read, and analyze everything related to a topic.

## Step 0: BOOTSTRAP (run automatically at start of every session)

Export API keys from `.env` file and verify yt-dlp. Run this block first, every time:

```bash
source ~/.claude/skills/deep-research/.env && echo "Keys: SERPAPI=${SERPAPI_KEY:+OK} SERPER=${SERPER_API_KEY:+OK} FIRECRAWL=${FIRECRAWL_API_KEY:+OK} EXA=${EXA_API_KEY:+OK} GITHUB=${GITHUB_TOKEN:+OK} LISTEN=${LISTEN_API_KEY:+OK}"
python -m yt_dlp --version
python -c "import youtube_transcript_api" 2>&1 || python -m pip install youtube-transcript-api $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
```

**YouTube transcript fetching (v3.2.0+):** when this skill processes a YouTube URL, use the shared helper at `~/.claude/skills/_research-lib/yt_transcript_fallback.py`. It runs a three-tier chain per video (yt-dlp → youtube-transcript-api → Whisper on audio) so a single YouTube rate-limit doesn't kill the whole research run. See `content-research/SKILL.md` Wave B for usage examples. Default Whisper model is `large-v3-turbo`.

**API roles in `/deep-research`:**
- **SerpAPI / Serper / Firecrawl** — primary web discovery and scraping (always-on)
- **Exa** — semantic discovery for adjacent security coverage when topic is conceptual
- **GitHub** — GitHub Security Advisory Database queries for CVE-to-package mapping
- **OpenAlex / Unpaywall** — not used by default; security work rarely needs academic literature. If a CVE genuinely requires academic paper context, mention it and we'll add the lookup ad hoc.

**Output conventions live at** `~/Documents/AI\CONVENTIONS.md`. That doc defines slug format, frontmatter schema, output paths, and the master INDEX append protocol. Skills MUST follow it. If the file is missing, alert the user — don't improvise.

If `.env` is missing or keys show blank, tell the user to create `~/.claude/skills/deep-research/.env` with:
```
export SERPAPI_KEY="your-key-here"
export SERPER_API_KEY="your-key-here"
export FIRECRAWL_API_KEY="your-key-here"
```

If yt-dlp is missing, install it: `python -m pip install --user yt-dlp`

Key management:
- SerpAPI: https://serpapi.com (100 free searches/month)
- Serper: https://serper.dev (2,500 free queries on signup)
- Firecrawl: https://firecrawl.dev (500 free lifetime credits)

## Input Modes

The user can provide any combination of:
1. **Pasted article text** with or without URLs embedded
2. **One or more URLs** to scrape
3. **A topic description** ("Langflow CVE exploit chain", "AI agent security risks 2026")

Detect which mode(s) apply and proceed accordingly.

## Processing Pipeline

Execute these steps in order. Parallelize where possible using the Agent tool.

### Step 0.5: LOAD self-context (MANDATORY for /deep-research)

Before any search or analysis, read the self-context file:

```bash
cat ~/.claude/skills/_research-lib/contexts/self.md
```

This file is the canonical source of your tech stack, app portfolio,
security exposure surface, and decision preferences. Every exposure
assessment in Step 4 MUST be grounded against this file — not against
hardcoded assumptions.

If the file is missing, alert the user and halt — exposure analysis without
current stack context produces wrong recommendations. Don't improvise from
memory.

### Step 0.75: CLARIFY if underspecified (light gate)

Most `/deep-research` invocations don't need clarification — the skill itself is narrow (security/exposure analysis), the audience is implicit (you, his stack), and the lens is fixed (security). But occasionally a vague topic warrants a quick check.

Read the shared gate logic:

```bash
cat ~/.claude/skills/_research-lib/clarify-template.md
```

Apply the **light gate** (1-3 dimensions max) for `/deep-research`:
- Self vs third-party (only ask if topic doesn't obviously match your stack — rare)
- Briefing vs deep-dive (only ask if not specified)
- Urgency (only ask if no time signal in input)

**Skip the gate entirely** (the common case) if:
- Input is a URL — context is in the URL
- Input is pasted article text
- Input names a specific product/CVE/vendor (e.g., "Langflow CVE-2026-XXX", "Supabase RLS bypass")
- Topic obviously concerns your stack (Vercel, Supabase, Firebase, Next.js, etc.)

**Trigger only when:**
- Input is a vague topic with no specific anchor ("AI agent security risks", "supply chain attacks 2026")
- Topic might be third-party (rare for deep-research — flag and ask)

When triggered, ask AT MOST 2 questions in one batch, with the "skip" escape hatch.

After the gate (or when skipped), write `_context.md` to the output folder per the template's protocol. Every run gets a `_context.md` — even if auto-derived from the invocation.

### Step 1: EXTRACT

Parse the user's input:
- Extract all URLs from pasted text (look for `https://`, `http://`, `www.`)
- Identify YouTube URLs separately (youtube.com, youtu.be)
- Identify PDF URLs separately (.pdf extension or known PDF hosts)
- Identify the core topic/keywords for search

### Step 2: DISCOVER

Use BOTH search APIs in parallel to find related sources the article may reference or that provide additional context:

**SerpAPI search** (broader, supports YouTube):
```bash
curl -s "https://serpapi.com/search.json?q=QUERY&api_key=$SERPAPI_KEY&num=10"
```

For YouTube-specific searches:
```bash
curl -s "https://serpapi.com/search.json?engine=youtube&search_query=QUERY&api_key=$SERPAPI_KEY"
```

**Serper search** (faster, Google-focused):
```bash
curl -s -X POST "https://google.serper.dev/search" \
  -H "X-API-KEY: $SERPER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "QUERY", "num": 10}'
```

**Exa semantic search** (skip if `EXA_API_KEY` empty). Use for finding adjacent security coverage — different vulnerability classes, related exploits, similar attack chains. Especially useful when the input is a single article and you want to find what else has been written on the same conceptual surface.

```bash
curl -s -X POST 'https://api.exa.ai/search' \
  -H "x-api-key: $EXA_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "QUERY_TEXT",
    "type": "deep",
    "num_results": 10,
    "contents": {
      "highlights": true
    }
  }' > _raw/exa_search.json
```

**GitHub Advisory Database** (skip if `GITHUB_TOKEN` empty). The authoritative source for CVE-to-package mapping across npm, pip, Maven, RubyGems, etc. Replaces Google-scraping for the structured "which packages am I exposed to" question.

Use when the CVE or topic concerns a specific package or ecosystem:

```bash
# Get advisories for a specific ecosystem (npm, pip, rubygems, etc.):
curl -s "https://api.github.com/advisories?ecosystem=npm&severity=high&per_page=30" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_advisories_npm.json

# Lookup a specific advisory by GHSA ID:
curl -s "https://api.github.com/advisories/GHSA-xxxx-xxxx-xxxx" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_advisory_lookup.json

# Search advisories by CVE ID:
curl -s "https://api.github.com/advisories?cve_id=CVE-2026-XXXXX" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_advisory_by_cve.json
```

Parse each advisory for: `ghsa_id`, `cve_id`, `severity`, `cvss.score`, `vulnerabilities[].package` (ecosystem + name), `vulnerabilities[].vulnerable_version_range`, `vulnerabilities[].first_patched_version`, `references[]`, `published_at`.

In Step 4 ANALYZE, cross-reference vulnerable package names against the self-context's stack listing — when a vulnerable npm package matches something your apps use (per `self.md`), flag with concrete exposure detail (which app, what version range affected).
```

For news-specific:
```bash
curl -s -X POST "https://google.serper.dev/news" \
  -H "X-API-KEY: $SERPER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "QUERY", "num": 10}'
```

Search strategy:
- Run the core topic as-is
- Add "CVE" or "advisory" if it's security-related
- Add "mitigation" or "patch" to find remediation guidance
- Add "[vendor name] response" to find official vendor statements
- Deduplicate URLs across both search results

**Hacker News** — real-time security discourse (Algolia API, public, no key). CVE disclosures, severity debates, "is this actually exploitable / seen in the wild," and vendor-response threads often surface on HN before the formal writeups. For "does this affect my apps" exposure work this is genuine signal — it tells you whether to act now or file it.

```bash
# Search stories + comments for the CVE / advisory / topic. Security is recency-sensitive but
# not 30-day-bound (a vuln from months ago still matters), so sort by recency rather than hard-
# filtering. Add &numericFilters=created_at_i>TIMESTAMP only if you deliberately want a window.
curl -s "https://hn.algolia.com/api/v1/search?query=QUERY&tags=story&hitsPerPage=20"
curl -s "https://hn.algolia.com/api/v1/search?query=QUERY&tags=comment&hitsPerPage=15"
# Recency-first variant:
curl -s "https://hn.algolia.com/api/v1/search_by_date?query=QUERY&tags=story&hitsPerPage=20"
```
Parse per hit: `title`, `url`, `points`, `num_comments`, `author`, `created_at`, `objectID`. Weight by points/comments — a 300-point thread with heated debate beats a 2-point submission. In Step 4 ANALYZE, fold this into the exposure call: if practitioners report active exploitation or dispute the official severity, say so explicitly.

### Step 3: FETCH

Scrape all discovered URLs. Use parallel Agent subagents for speed.

**Wayback Machine archaeology (recommended for security advisories).** Vendors sometimes silently edit or delete embarrassing CVE disclosures. Before treating a current vendor advisory as the canonical source, check Wayback for historical captures:

```bash
# CDX query — list all captured snapshots of a URL
curl -s "http://web.archive.org/cdx/search/cdx?url=VENDOR_ADVISORY_URL&output=json&fl=timestamp,original,statuscode&filter=statuscode:200&collapse=urlkey&limit=50" > _raw/wayback_cdx.json

# Fetch a specific archived version (the `id_` modifier returns raw archived content without Wayback's frame):
curl -s "http://web.archive.org/web/{timestamp}id_/{original_url}" > _raw/wayback_archived.html
```

When to use:
- Vendor advisory page exists but feels incomplete (suspiciously short, missing version details)
- Current page differs from what was originally reported in news coverage
- Article references a vendor link that now 404s
- Reverse-chronology: compare today's advisory to versions from 3-6 months ago to spot silent edits

Cost: free, no auth, low rate limits — Wayback is the only reliable counter to silent CVE-disclosure edits.

**Fetch tier strategy — try the cheapest tool that works.** Firecrawl has only 500 lifetime credits; conserve them.

| Tier | Tool | Cost | Use for |
|---|---|---|---|
| 1 | **WebFetch** (Claude built-in) | Free | Static news, NVD pages, Wikipedia, gov/edu sources — most cases |
| 2 | **Firecrawl** | 1 credit / page | Vendor security advisories on JS-heavy sites, PDFs, sites that block WebFetch |
| 3 | **Playwright** | Free, slower | Auth-walled, captcha-protected |

**Default to WebFetch.** Fall back to Firecrawl only when WebFetch returns near-empty content. Pre-flight check on Firecrawl credits:
```bash
curl -s "https://api.firecrawl.dev/v1/team/credit-usage" -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
If <50 credits remaining, warn user and aggressively prefer WebFetch.

**For articles/web pages, use Firecrawl (tier 2):**
```bash
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "TARGET_URL", "formats": ["markdown"]}'
```

The response JSON has the content at `.data.markdown`.

**For YouTube videos, use yt-dlp:**
```bash
# Extract auto-generated or manual subtitles
python -m yt_dlp --skip-download --write-auto-subs --write-subs --sub-lang en --convert-subs srt -o "%(title)s.%(ext)s" "YOUTUBE_URL"

# Then read the .srt file and strip timestamps for clean text
```

To strip SRT timestamps into clean text:
```bash
python -c "
import re, sys, glob
for f in glob.glob('*.srt'):
    with open(f) as fh:
        text = fh.read()
    lines = [l for l in text.split('\n') if l.strip() and not re.match(r'^\d+$', l.strip()) and not re.match(r'^\d{2}:\d{2}', l.strip())]
    seen = set()
    deduped = [l for l in lines if l not in seen and not seen.add(l)]
    print('\n'.join(deduped))
"
```

**For PDFs, use Firecrawl** (handles PDFs natively):
```bash
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "PDF_URL", "formats": ["markdown"]}'
```

**Fallback chain if Firecrawl fails:**
1. Try WebFetch (built-in Claude tool)
2. Try Playwright: `playwright-cli goto URL` then `playwright-cli snapshot`
3. If all fail, note in output: "Source unavailable, analysis based on available context"

### Step 4: ANALYZE

Once all content is gathered, synthesize into a comprehensive analysis. Structure your thinking around:

1. **What happened?** Factual timeline from sources.
2. **Who disclosed it?** Source credibility assessment.
3. **What's the attack surface?** Technical details.
4. **Who is affected?** Industry, company size, tech stack.
5. **your exposure?** Map findings against his current stack — defined in `~/.claude/skills/_research-lib/contexts/self.md` (loaded in Step 0.5). Specifically:
   - Cross-reference findings against the "Security exposure surface" section
   - Explicitly note non-exposure for technologies in the "What is NOT exposed to" list (e.g., "you do NOT use AWS — not affected")
   - Surface any current open security items (e.g., the standing Pearls of Parchment Firebase key rotation) if relevant to the finding
   - If the topic doesn't intersect with anything in self.md's stack, say so plainly — "no exposure" is a valid conclusion
6. **What should you do?** Prioritized action items for a solo developer. Anchor to his actual operating mode per self.md (single dev machine, no enterprise security tooling, internal vs commercial app distinction).
7. **Strategic implications?** What does this mean for the app roadmap, security posture, or tech stack decisions? Treat New Maint App (`mntlog.net`) — his only paid SaaS — with more caution than internal tools.

### Step 5: OUTPUT

Ask the user which format BEFORE generating:

**Option A: Deep dive** (personal analysis). Frontmatter REQUIRED per `CONVENTIONS.md` Rule 2.
```markdown
---
target: "[Topic]"
slug: [slug-form]
canonical_entity_id: [slug-form]             # NEW v3.0.3: stable across renames. Default = slug on first run.
topic_area: [TopicArea or null]              # NEW v3.0.3
type: deep-research
skill_version: "3.3.0"                       # NEW v3.0.3
run_date: YYYY-MM-DD
status: complete
apis_used: [serpapi, serper, firecrawl, yt-dlp]
sources_count: [N]
cves: [CVE-YYYY-XXXX, ...]              # if applicable
exposure: [confirmed | likely | none]   # to your stack
gaps:
  - "[paywalled / unavailable sources]"
supersedes: null
tags:
  domain: security
  artifact_type: topic-synthesis
---

# Deep Research: [Topic]
Generated: YYYY-MM-DD

## TL;DR
[3 sentences max]

## What Happened
[Factual timeline with source citations]

## Technical Detail
[Full analysis: CVEs, exploit chains, attack vectors, affected versions]

## Exposure Assessment
[Specific: which services, apps, or data is at risk]
[Include: "you do NOT use [X]" where relevant, to confirm non-exposure]

## Action Items
### Immediate (This Week)
- [ ] ...
### Near-term (30 Days)
- [ ] ...
### Strategic (90 Days)
- [ ] ...

## Industry Context
[What other orgs are doing, vendor responses, regulatory implications]

## Source Assessment
| # | Source | Type | Credibility | Key Contribution |
|---|--------|------|-------------|------------------|
| 1 | ... | ... | ... | ... |

## All Sources
1. [Title](URL)
2. ...
```

**Option B: Leadership briefing** (shareable)
```markdown
# Briefing: [Topic]
Date: YYYY-MM-DD
Prepared for: the user

## Bottom Line
[2 sentences. What happened and why it matters.]

## What It Means for My Apps
- [Bullet 1: Are any of my apps or services exposed?]
- [Bullet 2: What's the risk if I do nothing?]
- [Bullet 3: What's the fix?]

## Required Actions
1. [Action] — Owner: [who] — Deadline: [when]
2. ...

## Risk if We Do Nothing
[1 paragraph. Concrete consequences, not hypotheticals.]

## Background
[2-3 paragraphs for context. Non-technical language.]
```

**Option C: Both** — Generate deep dive first, then distill into briefing.

## Step 6: SAVE (mandatory, automatic — do NOT ask permission)

Every run saves to disk. Path resolution per `CONVENTIONS.md`:

1. **Resolve topic-area** (per `CONVENTIONS.md` Rule 11). Track which resolution path was used; you'll disclose it in step 6.
   - **(a) Arg:** If caller passed `--topic-area=Foo` or named one in the prompt, use it. Create `~/Documents/AI\Content extraction\topics\Foo\` (with a `README.md` stub) if it doesn't exist. Source = `arg`.
   - **(b) Infer:** Otherwise, list existing topic-areas. On bash: `ls -d ~/Documents/AI/Content\ extraction/topics/*/ 2>/dev/null`. If listing fails, fall back to asking (skip to step c). **Only auto-route if you are ≥90% confident** the security topic fits an existing area (e.g., CVE in a Supabase library → `Tech` if that area exists; vulnerability in an agronomy tool → `Agronomy`). Borderline cases must ask. Source = `inferred`.
   - **(c) Ask:** If ambiguous or listing failed, ask the user once: `"Which topic-area? (Existing: <list>. Or 'new:Foo' to create one. Or 'ungrouped' to keep at topics/ root.)"` Source = `asked`.
   - **(d) Ungrouped:** If user picks `ungrouped` or no topic-area is appropriate, set `TopicArea` to empty and skip the `{TopicArea}\` segment everywhere below (no double slashes, no literal `{TopicArea}` in paths or links).

2. **Output path:**
   - With topic-area: `~/Documents/AI\Content extraction\topics\{TopicArea}\{slug}-security-YYYY-MM-DD\`
   - Ungrouped: `~/Documents/AI\Content extraction\topics\{slug}-security-YYYY-MM-DD\`
   - `-security` suffix on the folder name (after slug) distinguishes deep-research output from `/research` topic syntheses
   - Slug: lowercase, hyphenated, max 50 chars, stopwords stripped
   - Date: ISO 8601, today's date
   - Same-day re-run: append `-v2`, `-v3`, etc.

3. **Files written:**
   - `REPORT.md` — the deep-dive analysis (Option A — frontmatter per Step 5 template)
   - `BRIEFING.md` — the leadership briefing (Option B — if user chose Option C "Both")
   - `_raw/` subfolder — raw API responses, fetched HTML, transcripts (preserve untouched per `CONVENTIONS.md` Rule 5)

4. **Append to master INDEX** — final step, mandatory. Add one line to `~/Documents/AI\INDEX.md` under "Topic syntheses". Path matches the output path resolution above:
   - With topic-area: `- YYYY-MM-DD [deep] [{Topic}](Content%20extraction/topics/{TopicArea}/{slug}-security-YYYY-MM-DD/) — exposure: {confirmed|likely|none}`
   - Ungrouped: `- YYYY-MM-DD [deep] [{Topic}](Content%20extraction/topics/{slug}-security-YYYY-MM-DD/) — exposure: {confirmed|likely|none}`

5. **Append to entity catalog** — also add a row to `~/Documents/AI\Content extraction\INDEX.md` under the appropriate topic-area's "Topic syntheses" table (or under the "Other topic syntheses (ungrouped)" section if ungrouped). Read the existing rows in the target table and match their column structure exactly — don't invent a new format. The link is relative to `Content extraction/`, so it includes the `topics/{TopicArea}/` prefix when topic-grouped, or just `topics/` when ungrouped:
   - With topic-area row link: `[{slug}-security-YYYY-MM-DD](topics/{TopicArea}/{slug}-security-YYYY-MM-DD/)`
   - Ungrouped row link: `[{slug}-security-YYYY-MM-DD](topics/{slug}-security-YYYY-MM-DD/)`
   - If the target topic-area has no "Topic syntheses" table yet, add one with a header that matches the style of sibling topic-areas' tables.

6. **WRITE `recipe.yaml` to the archive root + UPDATE topic-area `MANIFEST.yaml`** (NEW in v3.0.3 — mandatory). See `~/.claude/skills/_research-lib/SCHEMAS.md` for full schemas, identity resolution, `source_key` derivation, and merge-key precedence. Summary:
   - **Resolve `canonical_entity_id` first** per SCHEMAS.md "Identity resolution procedure": if the archive folder already exists, READ existing recipe.yaml and reuse its `canonical_entity_id` verbatim — never change it on a re-run. Only set it (= slug) on first creation. Renames go to `aliases[]`.
   - **`recipe.yaml`** in the archive folder with `schema_version: 1`, `skill_version: "3.3.0"`, `skill_name: deep-research`, `generated_at` + `last_updated_at` (UTC ISO-8601), `target` block (with `canonical_entity_id` from above, `topic_area` as string name OR YAML null if ungrouped — NOT the string "ungrouped"), `sources[]` array. Each source MUST have: `source_key` (per SCHEMAS.md rules), `type`, `discovery_method`, `api_used`, `captured_count`, `last_run_at_utc`, `resumable`. **Skill-specific top-level fields allowed**: `exposure` (`confirmed | likely | none | null`) and `cves: []` (list of CVE IDs).
   - **For every resumable source, write a captured-IDs file in `_raw/`** with stable item IDs (one per line). Counts alone aren't enough.
   - **`topics/{TopicArea}/MANIFEST.yaml`** (or `topics/MANIFEST.yaml` if topic_area is null). **Merge key precedence**: match by `canonical_entity_id` first, `path` second (legacy fallback). NEVER use `slug` alone. Entry fields: `slug`, `canonical_entity_id`, `path`, `created_at_utc` (first run only), `last_updated_at_utc`, `skill_version_at_creation` (first only), `skill_version_at_last_update`, `has_recipe_yaml: true`, `sources_summary` keyed by `source_key`.
   - **Use UTC timestamps everywhere** (`date -u +%Y-%m-%dT%H:%M:%SZ` in bash, `datetime.now(timezone.utc).isoformat().replace('+00:00','Z')` in Python). Never local time.
   - Without this metadata, this security archive cannot be updated incrementally by `/content-update` — only re-created from scratch as a new dated snapshot.

7. **Tell the user the exact path saved AND the topic-area resolution.** Two-line format, mandatory on every run:
   ```
   TopicArea: <Name or "ungrouped"> (source: arg|inferred|asked)
   Saved: <full path>
   ```
   If versioning was applied, append `(v{N})` to the path. If a new topic-area was created, append `(new topic-area created)`.

**Never overwrite an existing report.** Security analyses especially: prior conclusions may be referenced for incident response.

## Parallelization Strategy

Use the Agent tool to parallelize independent work:
- Launch one agent per search API (SerpAPI + Serper in parallel)
- Launch one agent per URL to scrape (up to 5 concurrent)
- YouTube transcript extraction runs as a separate agent
- All fetch agents return content, main thread does the synthesis

## Error Handling

| Error | Action |
|-------|--------|
| API key missing | Tell user which key, link to signup page |
| Firecrawl 402 (credits exhausted) | Fall back to WebFetch, then Playwright |
| Firecrawl 429 (rate limit) | Wait 5s, retry once, then fall back |
| yt-dlp no subtitles found | Note "No transcript available" in output |
| SerpAPI 429 | Use Serper results only |
| Serper 429 | Use SerpAPI results only |
| URL returns 403/404 | Try Playwright, note if still inaccessible |
| Paywall detected | Note in output, summarize from available snippets |

## Usage Examples

```
/deep-research https://venturebeat.com/security/langflow-cve-2026-33017/
```

```
/deep-research [paste full article text here]
```

```
/deep-research AI pipeline security vulnerabilities April 2026
```

```
/deep-research https://www.youtube.com/watch?v=VIDEO_ID
```

## Important Notes

- All API calls go to US-based services (SerpAPI, Serper, Firecrawl). No data leaves to non-US servers.
- yt-dlp runs entirely locally. No external service involved.
- Only public internet content is fetched through these APIs. Never send internal Riverview URLs.
- Firecrawl is SOC2 Type 2 certified. Can be self-hosted later if needed.
- Output is saved automatically per Step 6 — see `~/Documents/AI\CONVENTIONS.md` for canonical rules (including Rule 11 on topic-area subfolders). Default path: `Documents\AI\Content extraction\topics\{TopicArea}\{slug}-security-YYYY-MM-DD\` (or `Documents\AI\Content extraction\topics\{slug}-security-YYYY-MM-DD\` if `ungrouped` — no `{TopicArea}` segment, no double slash). The `-security` is appended to the folder name (after `{slug}`), not to the slug itself; this distinguishes deep-research output from `/research` topic syntheses.
