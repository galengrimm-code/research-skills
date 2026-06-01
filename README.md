# research-skills

> Four complementary research skills for Claude Code: general internet research, security-focused exposure analysis, full corpus extraction, and append-only delta updates of existing archives. v3.3.0 — adds a **Pulse / Recency** mode to `/research` (community sentiment over a recent window) and pulls **Hacker News** into both `/research` and `/deep-research` (real-time security discourse for exposure analysis). Reddit now uses the **OAuth API** — its public `*.json` is blocked to programmatic requests, so set `REDDIT_CLIENT_ID`/`SECRET` (falls back to `site:reddit.com` search otherwise). v3.2.0 added a shared YouTube transcript fallback chain (yt-dlp → youtube-transcript-api → Whisper); default Whisper model `large-v3-turbo`.

Built for solo developers and small teams who want **rigorous, sourced, repeatable** research — not vibes-summarized blog posts. Each skill produces structured artifacts (REPORT.md + raw scrapes + extracts) you can revisit months later.

---

## What's in this bundle

| Skill | When to use | Output |
|---|---|---|
| **`/research`** | "How does X work?" / "Compare Y vs Z" / "What's the landscape of Q?" / "What are people saying about Z lately?" — synthesized answer to a question | Dated topic-synthesis folder with `REPORT.md` + `_raw/` + `_extracts.md` |
| **`/deep-research`** | Security advisories, CVE exposure, supply-chain risk, "should I worry about X?" — synthesizes against YOUR stack | Same shape as `/research`, but with `-security` suffix and exposure mapping |
| **`/content-research`** | "Get me everything X has published" — competitive intel, expert dossier, podcast/YouTube/site archaeology | Entity archive folder with subfolders per source type (website, YouTube, podcast, press, social) |

**Shared plumbing:** SerpAPI / Serper (web search), Firecrawl (scrape), yt-dlp (YouTube transcripts), OpenAlex + Unpaywall (academic), Listen Notes (podcasts), local Whisper (audio transcription fallback), Playwright (JS-rendered pages).

---

## Decision matrix — which skill do I want?

```
Q: Do I want a synthesized ANSWER or a CORPUS?
├── ANSWER → /research or /deep-research
│   ├── Topic is security / CVE / stack-exposure? → /deep-research
│   └── Anything else (how-tos, comparisons, landscape, market) → /research
└── CORPUS (folder of source content) → /content-research
```

If you find yourself running `/research` on the same person/company three times, you probably want `/content-research` instead — build the corpus once, query it many times.

---

## Install

```bash
# Full bundle (all three skills + shared lib)
npx skills add galengrimm-code/research-skills --global

# Or one at a time
npx skills add galengrimm-code/research-skills@research --global
npx skills add galengrimm-code/research-skills@deep-research --global
npx skills add galengrimm-code/research-skills@content-research --global
```

(Or fork and substitute your own GitHub owner.)

---

## Setup (5 minutes)

### 1. API keys

Copy `.env.example` to `skills/deep-research/.env` and fill in keys:

```bash
cp .env.example ~/.claude/skills/deep-research/.env
# then edit the file with your keys
```

**Safety tip:** before any future edit of this file, use the included safety helper to back up:
```bash
bash ~/.claude/skills/_research-lib/env-safe-edit.sh
```
This creates a timestamped backup in `.env-backups/` and refuses to back up an empty/broken file (defense against a known failure mode where a broken in-place rewrite destroyed the file, then a "backup" step happily copied the empty result over the good backup).

The skills source from a single `.env` file (deep-research's) — no duplicates. Most services are free-tier-friendly.

### Services that take API keys

| Service | Free tier | Wired into | Used for |
|---|---|---|---|
| **SerpAPI** ([serpapi.com](https://serpapi.com)) | 100 searches/month | All 3 skills | Google-quality search |
| **Serper** ([serper.dev](https://serper.dev)) | 2,500 queries on signup | All 3 skills | Alternative web search (cheaper) |
| **Firecrawl** ([firecrawl.dev](https://firecrawl.dev)) | 500 lifetime credits | All 3 skills (tier-2 scrape) | Webpage scraping |
| **OpenAlex** ([openalex.org](https://openalex.org)) | $1/day allowance | `/research`, `/content-research` | Academic literature |
| **Unpaywall** ([unpaywall.org](https://unpaywall.org)) | Free (email-only) | `/research`, `/content-research` | Open-access PDF resolution |
| **Listen Notes** ([listennotes.com/api](https://listennotes.com/api)) | 30 results/query | `/research`, `/content-research` | Podcast search + transcripts |
| **GitHub** ([github.com/settings/tokens](https://github.com/settings/tokens)) | 5,000 req/hour authenticated | All 3 skills | Code search, Security Advisory Database (CVE→package), repo discovery |
| **Exa** ([exa.ai](https://exa.ai)) | $10 trial credits | `/research`, `/deep-research` | Semantic "find more like this" search |

### Services with no auth required

| Service | Wired into | Used for |
|---|---|---|
| **Wayback Machine CDX** ([web.archive.org](https://web.archive.org)) | `/content-research`, `/deep-research` | Historical web captures — deleted-page recovery, original security advisory archaeology |

### Local tools (no API, run on your machine)

| Tool | Wired into | Purpose |
|---|---|---|
| **WebFetch** (Claude built-in) | All 3 skills (tier-1) | First-attempt URL fetcher before falling back to Firecrawl |
| **yt-dlp** | All 3 skills | YouTube transcript extraction (uses auto-captions when available) |
| **faster-whisper** | `/content-research` | Audio transcription on local GPU when a podcast has no available transcript |
| **Playwright** | All 3 skills (fallback) | Scraper of last resort for sites that block WebFetch and Firecrawl |

You can install with no keys and the skills still run — they just skip sources they can't authenticate to and note "gaps" in the report. Start with **SerpAPI or Serper + Firecrawl + GitHub PAT** as a minimum viable setup.

### 2. Personal context (optional but recommended)

Copy `skills/_research-lib/contexts/EXAMPLE.md` to `skills/_research-lib/contexts/self.md` and fill in your tech stack, projects, and operating mode.

```bash
cp ~/.claude/skills/_research-lib/contexts/EXAMPLE.md \
   ~/.claude/skills/_research-lib/contexts/self.md
# then edit self.md with your details
```

With this file:
- `/research` decides whether topics are "self-applied" (your stack) or generic, and tailors output accordingly
- `/deep-research` maps CVEs against your stack for exposure analysis and explicitly flags non-exposure for tech you don't use ("you do NOT use AWS — not affected" — saves a lot of noise)

Without this file, both skills still work but produce more generic output.

`self.md` is `.gitignore`'d — your personal version stays local.

### 3. Optional: local Whisper for podcast transcription

`/content-research` falls back to local Whisper when a podcast has no available transcript. If you want this capability:

```bash
pip install faster-whisper
# GPU optional but much faster — see faster-whisper docs
```

Without Whisper, `/content-research` just notes "no transcript available" as a gap.

---

## Usage examples

### `/research`

```
/research How should I structure my Postgres tables for multi-tenancy?
```

The skill classifies the question type (architecture / how-to), runs web + academic searches, scrapes the top results, and synthesizes a comparison-and-recommendation report. Output lands in `~/Documents/AI/Content extraction/topics/{slug}-YYYY-MM-DD/`.

### `/deep-research`

Paste a CVE advisory or article URL:

```
/deep-research https://github.com/advisories/GHSA-... — is this serious for my stack?
```

The skill loads your `self.md`, identifies whether your stack uses the affected library/version, and produces a `REPORT.md` with `exposure: confirmed | likely | none` in the frontmatter plus prioritized action items.

### `/content-research`

```
/content-research John Kempf
```

The skill discovers John Kempf's website, YouTube channel, podcast appearances, press coverage, and social presence; scrapes content; transcribes audio where needed; and produces an entity archive at `~/Documents/AI/Content extraction/john-kempf-research-YYYY-MM-DD/` with subfolders per source type and a master `INDEX.md`.

---

## Architecture

```
research-skills/
├── README.md                         ← this file
├── LICENSE                           ← MIT
├── .gitignore
├── .env.example                      ← copy → skills/deep-research/.env
└── skills/
    ├── research/SKILL.md             ← /research — synthesized answer
    ├── deep-research/SKILL.md        ← /deep-research — security/exposure
    ├── content-research/SKILL.md     ← /content-research — corpus extraction
    └── _research-lib/                ← shared utilities
        ├── clarify-template.md       ← shared "is this prompt specific enough?" gate
        └── contexts/
            ├── EXAMPLE.md            ← template — copy to self.md
            └── _target-template.md   ← /content-research target-brief template
```

**Why three skills, not one:**
- Different output shape (synthesis vs corpus) → different prompts, different post-processing
- Different default sources (CVE feeds for security vs general web for everything else)
- Different value of personal context (security needs YOUR stack; corpus extraction doesn't)
- Different "definition of done" — `/research` ends at a report; `/content-research` ends when sources are exhausted

Forcing all three into one skill makes the prompt too sprawling and the outputs less rigorous.

---

## Output conventions

All three skills follow shared conventions documented in `~/Documents/AI/CONVENTIONS.md` (which you'd create on your end):

- **Output paths (v3.0.2+):** `~/Documents/AI/Content extraction/topics/{TopicArea}/{slug}-YYYY-MM-DD/` for `/research`; `~/Documents/AI/Content extraction/topics/{TopicArea}/{slug}-security-YYYY-MM-DD/` for `/deep-research` (the `-security` is appended to the folder name, not the slug itself); `~/Documents/AI/Content extraction/topics/{TopicArea}/{slug}-research-YYYY-MM-DD/` for `/content-research`. Skills resolve `{TopicArea}` per CONVENTIONS.md Rule 11 (caller arg → inferred from target if ≥90% confident → ask once if ambiguous → `ungrouped` falls back to `topics/` root with no `{TopicArea}` segment). Every run prints `TopicArea: X (source: arg|inferred|asked)` so you can verify routing at a glance.
- **Updateable archives (v3.0.3+):** Every archive auto-generates a `recipe.yaml` describing what was captured + how, and registers itself in a topic-area-level `MANIFEST.yaml`. These power a planned `/content-update` skill (v3.1) that detects deltas and pulls only new content on subsequent runs. See `skills/_research-lib/SCHEMAS.md` for the schemas and CONVENTIONS.md Rule 12 for the corpus-wide contract.
- **Frontmatter:** YAML at top of every REPORT.md with `target`, `slug`, `type`, `mode`, `run_date`, `status`, `apis_used`, `sources_count`, `gaps`, `tags`
- **Append to master INDEX:** every run adds a line to `~/Documents/AI/INDEX.md` so you can find old research later

You can override the output path per-run, but the conventions exist so future-you can find what past-you produced.

---

## What these skills are NOT

- **Not real-time** — every run hits live web APIs, takes 1-5 minutes
- **Not free at scale** — heavy usage will burn through free tiers; budget accordingly
- **Not a replacement for primary research** — they synthesize sources, they don't conduct interviews
- **Not Claude.ai web compatible (today)** — these are Claude Code skills; web-app support depends on Anthropic's evolving skill model

---

## Updating

```bash
npx skills update --global
```

Or for one skill:

```bash
npx skills update research --global
```

---

## License

MIT — see `LICENSE`. Use these freely, fork to your heart's content, attribution appreciated but not required.

---

## Acknowledgements

Built on top of work by:
- [SerpAPI](https://serpapi.com) and [Serper](https://serper.dev) for search
- [Firecrawl](https://firecrawl.dev) for scraping
- [OpenAlex](https://openalex.org) and [Unpaywall](https://unpaywall.org) for academic discovery
- [Listen Notes](https://listennotes.com/api) for podcast metadata
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for local audio transcription
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube extraction
- [Playwright](https://playwright.dev) for JS-rendered pages
