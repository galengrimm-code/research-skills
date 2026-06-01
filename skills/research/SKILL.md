---
name: research
version: "3.3.0"
description: General-purpose internet research on any topic — how-to guides, comparisons, explainers, landscape surveys, recent community sentiment (what people are saying lately on Reddit/Hacker News), product research. Scrapes articles, YouTube transcripts, PDFs, and community discussion, then synthesizes into a question-type-aware report. Invoke with /research followed by pasted text, URLs, or a topic. For security/vulnerability research with stack-exposure mapping, use /deep-research instead.
allowed-tools: Bash, WebSearch, WebFetch, Agent
---

# Research Skill

General-purpose internet research. Same plumbing as `/deep-research` (SerpAPI, Serper, Firecrawl, yt-dlp, Playwright) but with a neutral analysis template — no security framing, no stack-exposure mapping. Use this for how-tos, comparisons, explainers, and landscape surveys.

## Step 0: BOOTSTRAP (run automatically at start of every session)

Reuse the deep-research skill's API keys. One source of truth — no duplicate `.env`.

```bash
source ~/.claude/skills/deep-research/.env && echo "Keys: SERPAPI=${SERPAPI_KEY:+OK} SERPER=${SERPER_API_KEY:+OK} FIRECRAWL=${FIRECRAWL_API_KEY:+OK} OPENALEX=${OPENALEX_KEY:+OK} UNPAYWALL=${UNPAYWALL_EMAIL:+OK} EXA=${EXA_API_KEY:+OK} GITHUB=${GITHUB_TOKEN:+OK} LISTEN=${LISTEN_API_KEY:+OK} REDDIT=${REDDIT_CLIENT_ID:+OK}"
python -m yt_dlp --version
python -c "import youtube_transcript_api" 2>&1 || python -m pip install youtube-transcript-api $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
```

**YouTube transcript fetching (v3.2.0+):** when this skill processes a YouTube URL, use the shared helper at `~/.claude/skills/_research-lib/yt_transcript_fallback.py`. It runs a three-tier chain per video (yt-dlp → youtube-transcript-api → Whisper on audio) so a single YouTube rate-limit doesn't kill the whole research run. See `content-research/SKILL.md` Wave B for usage examples. Default Whisper model is `large-v3-turbo`.

**Graceful degradation:** OpenAlex and Unpaywall enrich academic discovery but aren't required. If `OPENALEX_KEY` is empty, skip academic-literature queries and note in the report's "gaps" frontmatter field. If `UNPAYWALL_EMAIL` is empty, skip DOI-to-OA-PDF resolution. Tell the user once at bootstrap, then proceed.

**Output conventions live at** `~/Documents/AI\CONVENTIONS.md`. That doc defines slug format, frontmatter schema, output paths, and the master INDEX append protocol. Skills MUST follow it. If the file is missing, alert the user — don't improvise.

If keys show blank, tell the user `~/.claude/skills/deep-research/.env` is missing and link to signup:
- SerpAPI: https://serpapi.com (100 free searches/month) — keys at https://serpapi.com/manage-api-key
- Serper: https://serper.dev (2,500 free queries on signup) — keys at https://serper.dev/api-keys
- Firecrawl: https://firecrawl.dev (500 free lifetime credits) — keys at https://www.firecrawl.dev/app/api-keys

## Input Modes

The user can provide any combination of:
1. **Pasted text** with or without URLs embedded
2. **One or more URLs** to scrape
3. **A topic description or question** ("How should I structure a knowledge base", "Compare vector databases 2026", "Why are LLM agents failing at long tasks")

## Step 0.5: LOAD self-context (conditional)

Read `~/.claude/skills/_research-lib/contexts/self.md` at the start of every run.

Then decide whether the topic is **self-applied** — does it concern your tech stack, app portfolio, or any of your active projects?

- **Self-applied** (most ag, dev-stack, security, or "how should I" questions): keep the context active. Use it to tailor recommendations to his actual stack, surface non-exposure where relevant, and apply his decision preferences (concrete options, evidence over hedging, etc.).
- **Generic** (a topic he's researching for someone else, a domain he doesn't operate in, an explainer not tied to his work): note that the topic is generic, lean lightly on the context, and don't over-anchor. The communication-style preferences still apply; the stack-specific ones don't.

If the context file is missing, note it in the output's "gaps" frontmatter field and proceed generically.

## Step 0.75: CLARIFY if underspecified (gate)

Before searching, check whether the invocation is specific enough to run. Read the shared gate logic:

```bash
cat ~/.claude/skills/_research-lib/clarify-template.md
```

Apply the **full gate** (5 dimensions) for `/research`:
- Topic specificity
- Mode (How-to / Comparison / Explainer / Landscape / Pulse)
- Audience (self / specific client / general reference)
- Deliverable (decision support / implementation prep / meeting prep / reference)
- Lens (the angle to emphasize)

**Skip the gate entirely** if:
- Invocation is >50 words
- Includes a specific URL or pasted article text
- Topic is explicitly tagged self-applied ("my stack", "my farm")
- Invocation says "go" or "just run"
- This is an obvious smoke test or follow-up

**If 3+ dimensions are unclear, trigger the gate.** Ask the 2-5 missing pieces in ONE numbered batch, including the "skip these and I'll just run with [default]" escape hatch.

After the gate (or when skipped), write `_context.md` to the output folder per the template's "Writing the answers to the run folder" section. Every run gets a `_context.md` — even if auto-derived.

## Step 1: CLASSIFY the question

Before searching, identify which of these five research modes the user is in. The mode shapes everything downstream:

| Mode | Trigger phrases | Output style |
|------|-----------------|--------------|
| **How-to / Guide** | "how do I", "how should I", "set up", "build", "implement" | Steps, patterns, tradeoffs, recommended tools |
| **Comparison** | "vs", "compare", "best X for Y", "which should I use", "alternatives to" | Matrix of options, scoring, recommendation |
| **Explainer** | "what is", "why does", "how does X work", "explain" | Background, mechanics, analogies, why it matters |
| **Landscape / Survey** | "state of", "current approaches to", "what's happening in", "trends" | Taxonomy of the space, who's doing what, open questions |
| **Pulse / Recency** | "what are people saying about", "lately", "recently", "last 30 days", "is X still worth it", "buzz around", "current sentiment" | Cross-platform sentiment synthesis over a recent window — consensus, controversy, pain points, excitement |

If ambiguous, pick the best fit and note it in output. If truly unclear, ask the user once.

**Pulse mode and the recency window.** Pulse is the ONLY mode that constrains by time. The other four apply no date filter — don't fence them in. Pulse activates only when the wording signals recency (the triggers above). When it does, resolve the window from the user's phrasing: "last week" → 7 days, "last few months" → 90 days, "this year" → year-to-date, an explicit "last N days" → N. Default to **30 days** only when recency is signaled but no span is named. Never apply a window to a non-Pulse run.

## Step 2: EXTRACT

Parse the user's input:
- Extract all URLs from pasted text
- Identify YouTube URLs (youtube.com, youtu.be)
- Identify PDF URLs
- Identify the core topic/keywords for search

## Step 3: DISCOVER

Use BOTH search APIs in parallel. Tailor search terms to the classified mode:

| Mode | Search augmentation |
|------|---------------------|
| How-to | Add "tutorial", "guide", "best practices", "2026" or current year |
| Comparison | Add "vs", "review", "pros cons", "compared", benchmark queries |
| Explainer | Add "explained", "introduction", "fundamentals", also look for canonical primary sources |
| Landscape | Add "state of", "survey", "2026 landscape", also hit industry analyst sites |
| Pulse | Recency-weighted: add the current year + "review"/"worth it"/"problems", and lead with the community sources below (Reddit + Hacker News) over evergreen docs |

**SerpAPI** (broader, supports YouTube):
```bash
curl -s "https://serpapi.com/search.json?q=QUERY&api_key=$SERPAPI_KEY&num=10"
```

For YouTube-specific (great for tutorials, conference talks, explainers):
```bash
curl -s "https://serpapi.com/search.json?engine=youtube&search_query=QUERY&api_key=$SERPAPI_KEY"
```

**Serper** (faster, Google-focused):
```bash
curl -s -X POST "https://google.serper.dev/search" \
  -H "X-API-KEY: $SERPER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"q": "QUERY", "num": 10}'
```

**Exa** — semantic search (skip if `EXA_API_KEY` empty).

When to use it:
- Topic is conceptually broad and keyword search will miss adjacent ideas (e.g., "regenerative agriculture economics" — keyword search finds papers with those words; Exa finds papers on soil-health ROI, carbon programs, transition-period yield drag — concepts the query didn't mention)
- Mode is Landscape, Explainer, or Comparison (broad-coverage modes benefit most)
- User asked "find me more like X" or "what else is being said about Y"
- Skip for narrow how-to questions where the canonical doc is already known

Call pattern:

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

Parse results for: `results[].url`, `results[].title`, `results[].highlights` (the relevant excerpts — these are token-efficient, often sufficient without a full Firecrawl fetch). For results where highlights alone are insufficient, surface the URL for Step 4 FETCH.

**Cost note:** Exa's `type: "deep"` runs multi-step search with synthesis — ~4-15 second latency, higher per-call cost than `auto`. For most agronomy/tech research the quality is worth it. If query volume becomes a concern, drop to `type: "auto"` (~1 second).

**OpenAlex** — academic literature discovery (skip if `OPENALEX_KEY` empty).

When to use it:
- Topic has a research/scientific dimension (agronomy, tech research, biology, medicine, etc.)
- Question asks "what does the research say" or implies peer-reviewed evidence
- A specific researcher, institution, or topic-ID is known
- Skip for pure how-to dev questions (no literature) or vendor comparisons

Two query types — prefer **list+filter** ($0.10/1000) over **search** ($1/1000):

```bash
# Filter — cheap, structured queries (preferred)
# By topic ID (find topic IDs via /topics endpoint):
curl -s "https://api.openalex.org/works?filter=topics.id:T10325,publication_year:2020-2026&per_page=25&sort=cited_by_count:desc&api_key=$OPENALEX_KEY" > _raw/openalex_topic.json

# By author ORCID:
curl -s "https://api.openalex.org/works?filter=author.orcid:0000-0000-0000-0000&per_page=25&api_key=$OPENALEX_KEY" > _raw/openalex_author.json

# Search — full-text keyword query (use sparingly):
curl -s "https://api.openalex.org/works?search=tissue+sampling+timing&per_page=25&api_key=$OPENALEX_KEY" > _raw/openalex_search.json

# Get-by-DOI (FREE, unlimited) — for resolving specific citations:
curl -s "https://api.openalex.org/works/doi:10.1234/example?api_key=$OPENALEX_KEY" > _raw/openalex_doi_lookup.json
```

Parse results for: `id`, `doi`, `title`, `abstract_inverted_index` (decode it), `open_access.is_oa`, `open_access.oa_url`, `cited_by_count`, `topics[].display_name`. Surface the most-cited and most-recent works as candidate sources. Extract DOIs for Unpaywall handoff (Step 4b).

**Source priority for academic-flavored topics:** OpenAlex results > Web search results from edu/gov/research domains > general web search. For pure dev/practical topics, web search results lead.

**GitHub Code Search** — real-world implementation patterns (skip if `GITHUB_TOKEN` empty).

When to use it:
- Mode is How-to and topic concerns code, libraries, frameworks, APIs, or implementation patterns
- User asks "how do real apps use X" or "show me a working example of Y"
- Library/framework documentation is thin or vague — production code fills the gap
- Skip for non-dev topics (no value for agronomy, business, security policy)

GitHub-authenticated requests run at 5,000/hour (vs 60/hour unauthed) — well above what a single research run needs.

```bash
# Code search across all public repos (returns ranked results with snippets):
Q_ENCODED=$(echo "QUERY language:typescript" | python -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))")
curl -s "https://api.github.com/search/code?q=${Q_ENCODED}&per_page=20" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_code.json

# Repo search (find repos by topic — useful for "best libraries for X"):
curl -s "https://api.github.com/search/repositories?q=TOPIC+stars:>500&sort=stars&order=desc&per_page=20" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_repos.json
```

Parse for: `items[].repository.full_name`, `items[].path` (file path), `items[].text_matches[].fragment` (code snippet with the match), `items[].html_url` (link to the source file on GitHub). Surface the most-starred repositories first — these are the patterns people have validated in production.

**Cost tip:** prefer `search/repositories` for landscape mode (cheap, returns top repos by stars), `search/code` for how-to mode (find exact implementation patterns).

**Listen Notes** — podcast discovery (skip if `LISTEN_API_KEY` empty).

When to use it:
- Topic likely has substantial podcast coverage (business strategy, dev tools, agriculture, health, politics, popular tech)
- Mode is Landscape, Explainer, or Comparison
- User asks "what are people saying" or wants current practitioner discourse
- Skip for narrow technical how-to questions — podcasts rarely cover those at useful depth

Free-tier quirks:
- Rate limit 2 req/sec (throttle parallel queries — sleep 0.6s between)
- 10 results per query default
- Full transcripts are PRO-only, but `transcripts_highlighted` snippets returned for free on search hits where keywords are in audio
- Header is `X-ListenAPI-Key`, NOT `Authorization: Bearer`

```bash
Q_ENCODED=$(echo "QUERY" | python -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))")
curl -s "https://listen-api.listennotes.com/api/v2/search?q=${Q_ENCODED}&type=episode&language=English" \
  -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/listennotes_search.json
sleep 0.6
```

Parse for: `results[].title_original`, `results[].audio` (URL — for Whisper fallback if transcript needed), `results[].audio_length_sec`, `results[].pub_date_ms`, `results[].podcast.title_original`, `results[].transcripts_highlighted` (real verbatim quotes — usable as primary-source content even without PRO).

**Pattern for substantive coverage:** fire 3-5 angled queries (broad term, critique variant, current-state variant, named-expert) to get range. Throttle ≥600ms between.

**When snippets aren't enough:** download audio via Python urllib (bash curl-in-loops fails on Windows), run faster-whisper locally (~18x realtime on modern GPU). Full pattern documented in `/content-research`.

**Hacker News + Reddit** — community sentiment. Use for Pulse mode, and optionally for Landscape/Comparison when "what do real users actually think" matters. These are the community-discussion sources the rest of the stack misses.

**Hacker News (primary — open API, verified working).** Algolia search is public JSON, no key. In Pulse mode, filter to the resolved window:

```bash
# stories + comments since (now - window). TIMESTAMP = Unix epoch:
#   bash:   date -d '30 days ago' +%s
#   python: int((datetime.now() - timedelta(days=30)).timestamp())
curl -s "https://hn.algolia.com/api/v1/search?query=QUERY&tags=story&numericFilters=created_at_i>TIMESTAMP&hitsPerPage=20"
curl -s "https://hn.algolia.com/api/v1/search?query=QUERY&tags=comment&numericFilters=created_at_i>TIMESTAMP&hitsPerPage=15"
```
Extract per hit: title, url, points, num_comments, author, created_at, objectID. HN skews technical/builder — note that lens when you synthesize.

**Reddit (OAuth — public JSON is blocked).** Reddit's public `*.json` endpoints return HTTP 403 to datacenter/programmatic requests regardless of User-Agent (verified: curl and WebFetch, on `www`, `old`, and subreddit-scoped paths alike). The authenticated API works, though. If `REDDIT_CLIENT_ID` and `REDDIT_CLIENT_SECRET` are set, get a userless token and query `oauth.reddit.com`:

```bash
# 1. Fetch a read-only (client-credentials) token — fetch fresh per run:
TOKEN=$(curl -s -X POST "https://www.reddit.com/api/v1/access_token" \
  -u "$REDDIT_CLIENT_ID:$REDDIT_CLIENT_SECRET" \
  -A "research-skills/3.3 (Claude Code)" \
  -d "grant_type=client_credentials" | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Query oauth.reddit.com (mirrors the public paths; the UA header is mandatory).
#    t = hour|day|week|month|year|all — set from the resolved window in Pulse mode.
curl -s -H "Authorization: bearer $TOKEN" -A "research-skills/3.3 (Claude Code)" \
  "https://oauth.reddit.com/search?q=QUERY&sort=top&t=month&limit=25&type=link"

# 3. For the top 3-5 threads by score, pull comments (the gold is in the comments):
curl -s -H "Authorization: bearer $TOKEN" -A "research-skills/3.3 (Claude Code)" \
  "https://oauth.reddit.com/r/SUBREDDIT/comments/POST_ID?sort=top&limit=10"
```
Extract per post: title, subreddit, score, num_comments, created_utc, permalink. From comment threads: recurring complaints, praise, and unanswered questions.

**Fallback if the creds aren't set:** surface Reddit threads through SerpAPI/Serper (`site:reddit.com QUERY`) and use the snippets — note in the report's "gaps" field that Reddit was snippet-only. To enable the full path: create a **script** app at https://www.reddit.com/prefs/apps, then add `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` to `~/.claude/skills/deep-research/.env`.

If HN returns nothing, broaden the query or drop the timestamp to check whether the topic is simply older than the window.

**Out of scope (deliberate):** X/Twitter sentiment is NOT fetched here. Pulling it means driving Grok through a browser, which this skill's tool set (`Bash, WebSearch, WebFetch, Agent`) doesn't include. Web search already surfaces news/analysis; Reddit + HN cover the community signal. If X sentiment is ever genuinely needed, run it separately in a browser-capable context.

Source bias for general research: favor primary sources, canonical documentation, authoritative practitioners, recent high-quality blog posts. Deprioritize SEO spam, listicles, AI-generated summary sites. When you see a source cited repeatedly across other sources, that's a signal to fetch the original. **In Pulse mode, invert this slightly:** the community threads ARE the primary source — you're measuring sentiment, not finding canonical docs.

Deduplicate URLs across all sources (SerpAPI / Serper / OpenAlex / Listen Notes / Reddit / Hacker News).

## Step 3b: RESOLVE OA full-text via Unpaywall (when DOIs are present)

If Step 3 OpenAlex queries surfaced papers with DOIs but `open_access.is_oa:false` OR no `oa_url`, try Unpaywall for the legal free PDF before treating it as paywalled.

Skip if `UNPAYWALL_EMAIL` is empty.

```bash
# For each DOI from OpenAlex results:
curl -s "https://api.unpaywall.org/v2/$DOI?email=$UNPAYWALL_EMAIL" > _raw/unpaywall_${DOI_SLUG}.json
```

Parse the response:
- `is_oa` — boolean, is there a free OA version somewhere?
- `best_oa_location.url_for_pdf` — direct PDF link (preferred)
- `best_oa_location.url` — landing page if no direct PDF
- `oa_locations[]` — all OA copies (institutional repositories, preprints, OA mirrors)

If a free PDF URL is found, route through Firecrawl in Step 4 like any other PDF source. If not, note in the report's "gaps" section: "Paper X is paywalled (Wiley/Elsevier/etc.); no OA version found via Unpaywall."

**Hit rate notes:**
- Open-access journals (PLoS, MDPI, Frontiers): nearly 100%
- Hybrid OA in mainstream journals: 30-50%
- Pure paywalled (Elsevier/Wiley behind subscription): often nothing legal
- Don't pursue Sci-Hub or shadow libraries. Stay legal.

## Step 4: FETCH

Scrape discovered URLs. Parallelize with Agent subagents (up to 5 concurrent).

**Fetch tier strategy — try the cheapest tool that works.** Firecrawl has only 500 lifetime credits; squander them and they're gone. Static pages don't need Firecrawl. Default order:

| Tier | Tool | Cost | Use for |
|---|---|---|---|
| 1 | **WebFetch** (Claude built-in) | Free | Static blog posts, news, Wikipedia, .edu/.gov pages, simple HTML — most cases |
| 2 | **Firecrawl** | 1 credit / page | JS-heavy SPAs, modern marketing sites, PDFs (native handling), sites that block WebFetch |
| 3 | **Playwright** | Free, slower | Sites that block both above; auth-walled with cookies |

**Default to WebFetch first.** Try it on the URL. If you get back near-empty content, a captcha-style blob, or a "JavaScript required" message — fall back to Firecrawl. Anywhere this happens reliably (e.g., known SPA domains), document the pattern locally and skip WebFetch for that domain next time.

**Pre-flight Firecrawl credit check** (run once at start of substantive runs):
```bash
curl -s "https://api.firecrawl.dev/v1/team/credit-usage" -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
If remaining credits < 50, warn the user and bias more aggressively toward WebFetch.

**Articles / blog posts / docs — Firecrawl (tier 2):**
```bash
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "TARGET_URL", "formats": ["markdown"]}'
```
Content is at `.data.markdown`.

**YouTube videos — yt-dlp:**
```bash
python -m yt_dlp --skip-download --write-auto-subs --write-subs --sub-lang en --convert-subs srt -o "%(title)s.%(ext)s" "YOUTUBE_URL"
```

Strip SRT timestamps:
```bash
python -c "
import re, glob
for f in glob.glob('*.srt'):
    with open(f) as fh:
        text = fh.read()
    lines = [l for l in text.split('\n') if l.strip() and not re.match(r'^\d+$', l.strip()) and not re.match(r'^\d{2}:\d{2}', l.strip())]
    seen = set()
    deduped = [l for l in lines if l not in seen and not seen.add(l)]
    print('\n'.join(deduped))
"
```

**PDFs — Firecrawl handles natively:**
```bash
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
  -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "PDF_URL", "formats": ["markdown"]}'
```

**Fallback chain:**
1. WebFetch (built-in)
2. Playwright (`playwright-cli goto URL` → `playwright-cli snapshot`)
3. Note "Source unavailable, analysis based on available context"

## Step 5: SYNTHESIZE (mode-dependent)

Pick the analysis skeleton matching the classified mode. Do NOT use the /deep-research "your exposure" mapping — that's for security work only.

### Mode: How-to / Guide

Synthesize around:
1. **Core concepts** — what does the user need to understand first?
2. **Canonical approaches** — the 2-4 patterns that show up repeatedly across sources
3. **Decision points** — what choices does the user face, and what's the tradeoff at each?
4. **Tools / stack** — what people actually use to do this today
5. **Common mistakes** — what do practitioners warn against?
6. **Recommended path** — given what the user said about their context, what's the best-fit approach?

### Mode: Comparison

Synthesize around:
1. **Contenders** — what are the real options (drop anything obscure or discontinued)?
2. **Evaluation axes** — what dimensions actually matter for this decision?
3. **Matrix** — score each option on each axis, with evidence from sources
4. **Tradeoffs** — what does each option optimize for, and what does it sacrifice?
5. **Recommendation** — given the user's context, which one and why?

### Mode: Explainer

Synthesize around:
1. **The question** — what is the user really asking?
2. **Background** — what do you need to know to understand the answer?
3. **The mechanism** — how does it actually work, step by step?
4. **Why it matters** — what are the implications or use cases?
5. **Misconceptions** — what do people commonly get wrong?
6. **Further reading** — canonical sources for going deeper

### Mode: Landscape / Survey

Synthesize around:
1. **The space** — what problem are all these people trying to solve?
2. **Taxonomy** — how do the current approaches cluster?
3. **Players** — who's doing what, with evidence
4. **Trends** — where is this heading, and why?
5. **Open questions** — what hasn't been solved yet?

### Mode: Pulse / Recency

Synthesize what people are actually saying over the window. Cross-platform convergence is the strongest signal — if it shows up on Reddit AND Hacker News AND the web, it's real. Synthesize around:
1. **TL;DR** — the one thing to know about current sentiment, in 2-3 sentences
2. **Consensus** — what do people broadly agree on across sources?
3. **Controversy** — where's the real disagreement or debate?
4. **Pain points** — what frustrations keep surfacing?
5. **Excitement** — what are people genuinely enthusiastic about?
6. **Emerging vs settled** — what's new or gaining momentum vs. accepted wisdom?
7. **Gaps** — what questions aren't being answered well anywhere?

State the window explicitly ("past 30 days") and lead each source's findings with its engagement signal (upvotes / points / comment counts) so the reader can weight them. Cite real threads with links.

## Step 6: OUTPUT

Default output is a markdown report in the mode-appropriate skeleton. Ask the user ONLY if it matters:

- If they gave a specific question, just answer it with the mode-appropriate structure.
- If the research is broad, offer: "Long-form report or TL;DR first?"

**Report template (adapt sections to mode). Frontmatter is REQUIRED per `CONVENTIONS.md` Rule 2:**

```markdown
---
target: "[Topic]"
slug: [slug-form-of-topic]
canonical_entity_id: [slug-form-of-topic]   # NEW v3.0.3: stable across renames. Default = slug on first run.
topic_area: [TopicArea or null]              # NEW v3.0.3
type: research
skill_version: "3.3.0"                       # NEW v3.0.3
mode: [how-to | comparison | explainer | landscape | pulse]
window: null                                 # NEW v3.3.0: Pulse mode only — e.g. "last 30 days"; null otherwise
run_date: YYYY-MM-DD
status: complete
apis_used: [serpapi, serper, firecrawl, yt-dlp]
sources_count: [N]
gaps:
  - "[any sources unavailable / paywalled / blocked]"
supersedes: null
tags:
  domain: [agronomy | tech | security | business | personal]
  artifact_type: topic-synthesis
---

# Research: [Topic]
Date: YYYY-MM-DD
Mode: [How-to / Comparison / Explainer / Landscape]

## TL;DR
[3-4 sentence synthesis — the answer if the user reads nothing else]

## [Mode-specific sections — see Step 5]

## Sources Used
| # | Source | Type | Key Contribution |
|---|--------|------|------------------|
| 1 | [title](url) | article/video/pdf/docs | ... |

## Sources Considered but Dropped
[Only include if you dropped notable sources. Brief note why — outdated, low quality, duplicate, etc.]
```

## Step 7: SAVE (mandatory, automatic — do NOT ask permission)

Every run saves to disk. Path resolution per `CONVENTIONS.md`:

1. **Resolve topic-area** (per `CONVENTIONS.md` Rule 11). Track which resolution path was used; you'll disclose it in step 6.
   - **(a) Arg:** If caller passed `--topic-area=Foo` or named one in the prompt, use it. Create `~/Documents/AI\Content extraction\topics\Foo\` (with a `README.md` stub) if it doesn't exist. Source = `arg`.
   - **(b) Infer:** Otherwise, list existing topic-areas. On bash: `ls -d ~/Documents/AI/Content\ extraction/topics/*/ 2>/dev/null`. If listing fails, fall back to asking (skip to step c). **Only auto-route if you are ≥90% confident the target fits an existing topic-area** — e.g., the target name matches an existing folder, or the target is a well-known figure in that area's NAMES list. Borderline cases must ask. Source = `inferred`.
   - **(c) Ask:** If ambiguous or listing failed, ask the user once: `"Which topic-area? (Existing: <list>. Or 'new:Foo' to create one. Or 'ungrouped' to keep at topics/ root.)"` Source = `asked`.
   - **(d) Ungrouped:** If user picks `ungrouped` or no topic-area is appropriate, set `TopicArea` to empty and skip the `{TopicArea}\` segment everywhere below (no double slashes, no literal `{TopicArea}` in paths or links).

2. **Output path:**
   - With topic-area: `~/Documents/AI\Content extraction\topics\{TopicArea}\{slug}-YYYY-MM-DD\`
   - Ungrouped: `~/Documents/AI\Content extraction\topics\{slug}-YYYY-MM-DD\`
   - Slug: lowercase, hyphenated, max 50 chars, stopwords stripped (see `CONVENTIONS.md` Rule 3)
   - Date: ISO 8601, today's date
   - If folder already exists (same-day re-run), append `-v2`, `-v3`, etc.

3. **Files written:**
   - `REPORT.md` — the synthesis (with YAML frontmatter per Step 6 template)
   - `_raw/` subfolder — raw SerpAPI/Serper/Firecrawl JSON responses for reproducibility (preserve untouched per `CONVENTIONS.md` Rule 5)

4. **Append to master INDEX** — final step, mandatory. Add one line to `~/Documents/AI\INDEX.md` under "Topic syntheses". Path matches the output path resolution above:
   - With topic-area: `- YYYY-MM-DD [topic] [{Target}](Content%20extraction/topics/{TopicArea}/{slug}-YYYY-MM-DD/) — {one-line description}`
   - Ungrouped: `- YYYY-MM-DD [topic] [{Target}](Content%20extraction/topics/{slug}-YYYY-MM-DD/) — {one-line description}`

5. **Append to entity catalog** — also add a row to `~/Documents/AI\Content extraction\INDEX.md` under the appropriate topic-area's "Topic syntheses" table (or under the "Other topic syntheses (ungrouped)" section if ungrouped). Read the existing rows in the target table and match their column structure exactly — don't invent a new format. The link is relative to `Content extraction/`, so it includes the `topics/{TopicArea}/` prefix when topic-grouped, or just `topics/` when ungrouped:
   - With topic-area row link: `[{slug}-YYYY-MM-DD](topics/{TopicArea}/{slug}-YYYY-MM-DD/)`
   - Ungrouped row link: `[{slug}-YYYY-MM-DD](topics/{slug}-YYYY-MM-DD/)`
   - If the target topic-area has no "Topic syntheses" table yet, add one with a header that matches the style of sibling topic-areas' tables.

6. **WRITE `recipe.yaml` to the archive root + UPDATE topic-area `MANIFEST.yaml`** (NEW in v3.0.3 — mandatory). See `~/.claude/skills/_research-lib/SCHEMAS.md` for full schemas, identity resolution, `source_key` derivation, and merge-key precedence. Summary:
   - **Resolve `canonical_entity_id` first** per SCHEMAS.md "Identity resolution procedure": if the archive folder already exists, READ existing recipe.yaml and reuse its `canonical_entity_id` verbatim — never change it on a re-run. Only set it (= slug) on first creation. Renames go to `aliases[]`, not to `canonical_entity_id`.
   - **`recipe.yaml`** in the archive folder with `schema_version: 1`, `skill_version: "3.3.0"`, `skill_name: research`, `generated_at` + `last_updated_at` (UTC ISO-8601), `target` block (with `canonical_entity_id` from above, `topic_area` as string name OR YAML null if ungrouped — NOT the string "ungrouped"), `sources[]` array. Each source MUST have: `source_key` (per SCHEMAS.md rules — e.g., `website_{domain}`, `youtube_{handle}`, `podcast_listen-notes_{id}`), `type`, `discovery_method`, `api_used`, `captured_count`, `last_run_at_utc`, `resumable`. **Skill-specific top-level fields allowed**: `mode` (the research mode classified in Step 1).
   - **For every resumable source, write a captured-IDs file in `_raw/`** with stable item IDs (one per line). Counts alone aren't enough — v3.1 tombstone detection needs stable IDs.
   - **`topics/{TopicArea}/MANIFEST.yaml`** (or `topics/MANIFEST.yaml` if topic_area is null). **Merge key precedence**: match by `canonical_entity_id` first, `path` second (legacy fallback). NEVER use `slug` alone — slug can change on rename. Entry fields: `slug`, `canonical_entity_id`, `path`, `created_at_utc` (first run only), `last_updated_at_utc`, `skill_version_at_creation` (first only), `skill_version_at_last_update`, `has_recipe_yaml: true`, `sources_summary` keyed by `source_key`.
   - **Use UTC timestamps everywhere** (`date -u +%Y-%m-%dT%H:%M:%SZ` in bash, `datetime.now(timezone.utc).isoformat().replace('+00:00','Z')` in Python). Never local time.
   - Without this metadata, this archive cannot be updated incrementally by `/content-update` — only re-created from scratch as a new dated snapshot.

7. **Tell the user the exact path saved AND the topic-area resolution.** Two-line format, mandatory on every run:
   ```
   TopicArea: <Name or "ungrouped"> (source: arg|inferred|asked)
   Saved: <full path>
   ```
   If versioning was applied, append `(v{N})` to the path. If a new topic-area was created, append `(new topic-area created)`.

**Never overwrite an existing report.** The prior run may be referenced elsewhere.

## Parallelization

Use Agent subagents for:
- SerpAPI + Serper searches in parallel
- Up to 5 concurrent URL scrapes
- YouTube transcript extraction as a separate agent
- Main thread synthesizes once all fetches return

## Error Handling

| Error | Action |
|-------|--------|
| API key missing | Tell user which key, point to `~/.claude/skills/deep-research/.env` |
| Firecrawl 402 (credits exhausted) | Fall back to WebFetch, then Playwright |
| Firecrawl 429 (rate limit) | Wait 5s, retry once, then fall back |
| yt-dlp no subtitles | Note "No transcript available" in output |
| SerpAPI 429 | Use Serper results only |
| Serper 429 | Use SerpAPI results only |
| URL 403/404 | Try Playwright, note if still inaccessible |
| Paywall detected | Note it, summarize from snippets |

## When to Use This vs /deep-research

| Use `/research` | Use `/deep-research` |
|-----------------|----------------------|
| How-to guides | CVEs and security advisories |
| Product / tool comparisons | Vulnerability disclosures |
| Explaining concepts | "Does this affect my apps?" exposure analysis |
| Landscape surveys | Vendor security response tracking |
| Any non-security research | AI/tech news with security angle |

If a question could go either way (e.g. "best practices for storing API keys"), pick based on whether the user wants *how-to guidance* (this skill) or *threat analysis for their stack* (deep-research).

## Usage Examples

```
/research How should I structure a knowledge base for a software project?
```

```
/research Compare vector databases for a small app — Pinecone vs Weaviate vs pgvector
```

```
/research What is MCP and why does it matter?
```

```
/research State of AI coding agents in 2026
```

```
/research What are people saying about Supabase vs Firebase lately?
```

```
/research https://blog.example.com/post-about-X
```

## Notes

- All API calls go to US-based services (SerpAPI, Serper, Firecrawl). No data leaves to non-US servers.
- yt-dlp runs locally.
- Output is saved automatically per Step 7 — see `~/Documents/AI\CONVENTIONS.md` for canonical rules (including Rule 11 on topic-area subfolders). Default path: `Documents\AI\Content extraction\topics\{TopicArea}\{slug}-YYYY-MM-DD\` (or `Documents\AI\Content extraction\topics\{slug}-YYYY-MM-DD\` if `ungrouped` — no `{TopicArea}` segment, no double slash).
