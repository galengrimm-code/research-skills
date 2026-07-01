---
name: content-research
version: "3.2.0"
description: Extract EVERYTHING a company, person, or domain has published into an organized local archive. Not a synthesized report — an indexed content dossier with all website pages, YouTube transcripts, podcast audio transcribed via local Whisper (faster-whisper on GPU), press coverage, and social snippets. Use when the user wants a complete "give me everything this target has ever put out" pull, not a research answer. Invoke with /content-research followed by a company name, person name, or URL.
allowed-tools: Bash, WebSearch, WebFetch, Agent
---

# Content Research Skill

Builds a complete local content archive for a target (company, person, or domain). Unlike `/research` and `/deep-research` which produce synthesized reports, this skill produces a **folder of extracted content** with a master INDEX.md and honest gap accounting.

**When to use this vs. other research skills:**

| Skill | When |
|---|---|
| `/content-research` (this one) | "Get me everything X has published" — competitive intelligence, company dossier, content archaeology, building a corpus to reference later |
| `/research` | "How does X work / what should I use / compare these" — synthesized answer |
| `/deep-research` | Security / CVE / stack-exposure analysis |

---

## Step 0: BOOTSTRAP (run every session)

Reuse the deep-research skill's keys — single source of truth.

```bash
source ~/.claude/skills/deep-research/.env && echo "Keys: SERPAPI=${SERPAPI_KEY:+OK} SERPER=${SERPER_API_KEY:+OK} FIRECRAWL=${FIRECRAWL_API_KEY:+OK} OPENALEX=${OPENALEX_KEY:+OK} UNPAYWALL=${UNPAYWALL_EMAIL:+OK} GITHUB=${GITHUB_TOKEN:+OK} EXA=${EXA_API_KEY:+OK} LISTEN=${LISTEN_API_KEY:+OK}"
python -m yt_dlp --version 2>&1 || python -m pip install yt-dlp $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
python -c "import youtube_transcript_api" 2>&1 || python -m pip install youtube-transcript-api $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
```

**Graceful degradation:** Wayback Machine CDX needs no auth. OpenAlex and Unpaywall enrich academic discovery when the target has publications, but aren't required. If `OPENALEX_KEY` is empty, skip the author-works lookup and note in the archive's INDEX.md gaps section.

**Output conventions live at** `~/Documents/AI\CONVENTIONS.md`. That doc defines slug format, frontmatter schema, output paths, and the master INDEX append protocol. Skills MUST follow it. If the file is missing, alert the user — don't improvise.

Signup links if keys missing:
- SerpAPI: https://serpapi.com (100 free/month)
- Serper: https://serper.dev (2,500 free signup)
- Firecrawl: https://firecrawl.dev (500 free lifetime — tight budget, use sparingly)

---

## Step 1: IDENTIFY the target

User gives you a name (possibly misspelled), a URL, or a description. Before scraping anything, confirm the target:

1. **Two-query identification:** run a SerpAPI and a Serper search for the user's exact input. Look for:
   - Official website (usually position 1-2)
   - LinkedIn company / personal page
   - Social accounts (Facebook, Instagram, YouTube, LinkedIn)
   - Alternate spellings / canonical name
2. **If the user's spelling is off** (e.g., "Ravensberg" → "Rabenberg"), state the correction clearly in one sentence and proceed. Don't ask for confirmation in auto mode.
3. **If the target is ambiguous** (two companies with same name), show the top 2-3 candidates and ask which one.

Before scraping, output one line: `Target identified: [official name] — [primary domain] — [key people]`. This gives the user a chance to course-correct.

---

## Step 1.5: CAPTURE engagement context (MANDATORY — full gate)

`/content-research`'s gate is the full target-context capture — entity
archives ALWAYS need engagement context, no skip path. Read both:

```bash
cat ~/.claude/skills/_research-lib/clarify-template.md
cat ~/.claude/skills/_research-lib/contexts/_target-template.md
```

Collect from the user (or extract from the initial invocation):

- **engagement_for** — who is the research for? (name or 'self')
- **relationship** — employee, client, partner, competitor, friend, self, other
- **deliverable** — what they need (meeting prep, sales playbook, dossier, competitive analysis, reference archive, etc.)
- **deadline** — ISO date or 'no deadline'
- **sensitivity** — public, internal, confidential
- **lens** — what angle to emphasize (methodology, products, competitive position, talent, technology, market, etc.)
- **Why this target?** — one paragraph
- **What outcome does the requester need?** — specific
- **What should NOT be in scope?** — explicit bounds
- **Sensitivities or constraints** — diplomatic framing? working relationship?

**Follow the shared gate's question format** (single numbered batch, never serialized) per `clarify-template.md`. If the initial invocation contains a multi-line context blob with these elements, extract from it and proceed without asking. Otherwise prompt the user once.

**Lightweight mode:** if the user says "for self / general reference," fill `engagement_for: self` and skip the prose sections. A one-paragraph "why this target" still required.

This context goes into `_context.md` inside the archive folder (Step 2 will create the folder; this step prepares the content).

---

## Step 2: CREATE the archive folder

**Step 2a: Resolve topic-area** (per `CONVENTIONS.md` Rule 11). Track which resolution path was used; you'll disclose it at the end of the run (Step 6).
- **(a) Arg:** If caller passed `--topic-area=Foo` or named one in the prompt, use it. Create `~/Documents/AI\Content extraction\topics\Foo\` (with a `README.md` stub) if it doesn't exist. Source = `arg`.
- **(b) Infer:** Otherwise, list existing topic-areas. On bash: `ls -d ~/Documents/AI/Content\ extraction/topics/*/ 2>/dev/null`. If listing fails, fall back to asking (skip to step c). **Only auto-route if you are ≥90% confident** the target fits an existing topic-area — e.g., target name matches an existing folder, or target is a well-known figure in that area's NAMES list. Borderline cases must ask. Source = `inferred`.
- **(c) Ask:** If ambiguous or listing failed, ask the user once: `"Which topic-area? (Existing: <list>. Or 'new:Foo' to create one. Or 'ungrouped' to keep at topics/ root.)"` Source = `asked`.
- **(d) Ungrouped:** If user picks `ungrouped` or no topic-area is appropriate, set `TopicArea` to empty and skip the `{TopicArea}\` segment everywhere below (no double slashes, no literal `{TopicArea}` in paths or links).

**Step 2b: Compute path.**

**Default location** per `CONVENTIONS.md` Rules 1 + 11:
- With topic-area: `~/Documents/AI\Content extraction\topics\{TopicArea}\{slug}-research-YYYY-MM-DD\`
- Ungrouped: `~/Documents/AI\Content extraction\topics\{slug}-research-YYYY-MM-DD\`

- Slug: lowercase, hyphenated, max 50 chars, stopwords stripped. Examples: "Soil Works LLC" → `soilworks`, "Calibrated Agronomy" → `calibrated-agronomy`, "Glen Rabenberg" → `glen-rabenberg`.
- Date: ISO 8601, today's date (the day the skill runs).
- If folder already exists (same-day re-run), append `-v2`, `-v3`, etc. **Never overwrite.**

**Legacy note:** Entity archives created before 2026-05-15 use the date-less form `{slug}-research/` and live at `Content extraction\topics\{TopicArea}\` (after the 2026-05-20 topic-area restructure) or directly at `Content extraction\` root (oldest, never moved). Don't retro-rename them — new convention only applies to new runs.

Standard folder structure (create all up front — empty folders get removed at the end):

```
{slug}-research-YYYY-MM-DD/
├── _context.md              # Engagement context (filled per Step 1.5) — write FIRST
├── 01_website/              # All pages from the primary domain
│   └── products/            # Sub-folder if the site has distinct product pages
├── 02_youtube/
│   ├── channel-index.md     # Table of every video
│   └── transcripts/         # One .txt per video
├── 03_podcast/              # Spotify/Apple listings + host-site pages
├── 04_press/                # External articles, trade pubs, interviews
├── 05_social/               # social-snippets.md (Google-indexed FB/IG/LI)
├── 06_parent_or_related/    # Sister brands, parent companies, retail listings
├── _raw/                    # Sitemaps, URL lists, raw API JSONs (for reproducibility)
│   └── search/              # Raw SerpAPI/Serper responses
└── INDEX.md                 # Master navigation + key facts + gap accounting
```

Adapt to the target. A manufacturer needs `06_retail_listings/`; a person needs less product focus. Don't force empty folders.

---

## Step 3: DISCOVER URLs

Run these in parallel:

```bash
# 1. Sitemap discovery — most WordPress sites have one
curl -s "https://DOMAIN/sitemap.xml" > _raw/sitemap.xml
curl -s "https://DOMAIN/sitemap_index.xml" > _raw/sitemap_index.xml
curl -s "https://DOMAIN/robots.txt" > _raw/robots.txt  # often has sitemap URL

# 2. Google site: queries for URL discovery (fallback if no sitemap)
curl -s "https://serpapi.com/search.json?q=site:DOMAIN&api_key=$SERPAPI_KEY&num=100" > _raw/search/site.json

# 3. YouTube channel discovery — the channel handle is the key
curl -s "https://serpapi.com/search.json?engine=youtube&search_query=TARGET&api_key=$SERPAPI_KEY" > _raw/search/yt.json
# Then for the found handle:
python -m yt_dlp --flat-playlist --print "%(id)s|%(title)s|%(duration)s|%(view_count)s|%(upload_date)s" "https://www.youtube.com/@HANDLE/videos" > _raw/youtube_videos.txt

# 4. Podcast discovery — Listen Notes API (replaces SerpAPI Spotify/Apple scraping)
# Skip if LISTEN_API_KEY empty.
# Free tier: 2 req/sec rate limit, 10 results per query. Throttle ≥600ms between calls.
TARGET_ENC=$(echo "TARGET" | python -c "import sys,urllib.parse; print(urllib.parse.quote(sys.stdin.read().strip()))")

# a. Find podcasts BY the target (target hosts a show under their name):
curl -s "https://listen-api.listennotes.com/api/v2/search?q=${TARGET_ENC}&type=podcast&language=English" \
  -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/listennotes_podcasts_by.json
sleep 0.6

# b. Find episodes WHERE the target appears (guest spots, topical mentions):
curl -s "https://listen-api.listennotes.com/api/v2/search?q=${TARGET_ENC}&type=episode&language=English" \
  -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/listennotes_episodes_about.json
sleep 0.6

# c. If target has its own podcast domain (e.g., podcast.targetsite.com), one-shot all their episodes:
# curl -s "https://listen-api.listennotes.com/api/v2/podcasts/domains/podcast.targetsite.com" \
#   -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/listennotes_domain.json

# d. Once you've ID'd a specific podcast worth full enumeration, fetch full episode list:
# curl -s "https://listen-api.listennotes.com/api/v2/podcasts/PODCAST_ID?sort=recent_first" \
#   -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/listennotes_podcast_full.json

# 5. Press / social discovery
curl -s "https://serpapi.com/search.json?q=TARGET+interview+OR+podcast+OR+article&api_key=$SERPAPI_KEY&num=20" > _raw/search/press.json
curl -s "https://serpapi.com/search.json?q=TARGET+facebook+OR+instagram+OR+linkedin&api_key=$SERPAPI_KEY&num=20" > _raw/search/social.json

# 6. Wayback Machine CDX — historical captures (catches deleted pages)
curl -s "http://web.archive.org/cdx/search/cdx?url=DOMAIN&output=json&fl=timestamp,original,statuscode&filter=statuscode:200&collapse=urlkey&limit=500" > _raw/wayback_cdx.json
# Output format: [["timestamp","original","statuscode"], ["20230101120000","https://DOMAIN/page1","200"], ...]
# First row is headers. collapse=urlkey returns one row per unique URL (latest capture).

# 7. OpenAlex — academic publications (when target is a researcher, professor, or lab; skip if OPENALEX_KEY empty)
# Decide: does the target have peer-reviewed publications? Signals: "Dr." prefix, university affiliation, journal-style content on their site, ORCID link, Google Scholar profile.
# If yes:
curl -s "https://api.openalex.org/authors?search=TARGET_NAME&per_page=5&api_key=$OPENALEX_KEY" > _raw/openalex_author_lookup.json
# Pick the right author from results (disambiguate by institution, ORCID, work count). Then:
curl -s "https://api.openalex.org/works?filter=author.id:AXXXXXXXX&per_page=100&sort=publication_date:desc&api_key=$OPENALEX_KEY" > _raw/openalex_author_works.json

# 8. GitHub — when target has a GitHub presence (developers, devtools companies, OSS projects; skip if GITHUB_TOKEN empty)
# Decide: does the target have a GitHub username/org? Signals: GitHub link on their site, "Open source" mentions, dev-tool company, or known username.
# If yes:
GH_USER="TARGET_GITHUB_USERNAME_OR_ORG"
# List repos (public only, no scope needed beyond auth):
curl -s "https://api.github.com/users/$GH_USER/repos?per_page=100&sort=updated" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_repos.json
# Get user profile metadata:
curl -s "https://api.github.com/users/$GH_USER" \
  -H "Authorization: Bearer $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github+json" > _raw/github_user.json
# For top repos by stars or recent activity, pull README via raw content URL:
# curl -sL "https://raw.githubusercontent.com/$GH_USER/REPO/HEAD/README.md" -H "Authorization: Bearer $GITHUB_TOKEN" > "_raw/github_readme_REPO.md"
```

**If the sitemap has branches** (`sitemap_index.xml` points to `page-sitemap.xml`, `post-sitemap.xml`, etc.), fetch each branch.

**Extract URLs** from all discovered sources and deduplicate. Cap at ~50 pages for the first pass — if there are more, note it and let the user decide whether to go deeper.

**Wayback handling:**
- Parse `wayback_cdx.json` to extract historical URLs not present in the live sitemap. These are deleted pages worth capturing.
- For each historical URL not in live discovery, fetch via `http://web.archive.org/web/{timestamp}id_/{original_url}` (the `id_` modifier returns the raw archived content without Wayback's frame).
- Wayback captures via Firecrawl work fine — same pattern as live scraping.
- Cap historical fetches at 10-20 pages. Note in INDEX.md gaps: "Pulled N historical pages from Wayback; M additional captures available but capped."

**OpenAlex handling (when target has academic publications):**
- Parse `openalex_author_lookup.json` to disambiguate the right author. Multiple "John Kempf" entries exist; pick by institution affiliation, work count, or topic overlap with the target's domain.
- For the disambiguated author ID, the `openalex_author_works.json` response lists all their works. Add a new archive folder `09_academic/` and write:
  - `09_academic/works-index.md` — table of papers (title, journal, year, DOI, citations, OA URL)
  - `09_academic/abstracts/` — one `.md` per work with decoded abstract (the inverted-index format)
- Extract all DOIs for Unpaywall handoff (below) to get free PDF URLs where available.
- Skip the section entirely if target has no academic publications. Don't force it. Most consultants/companies have zero peer-reviewed work; that's fine.

**Unpaywall handling (companion to OpenAlex, when DOIs surfaced):**

For each DOI from OpenAlex results, query Unpaywall to find free legal full-text:

```bash
# Skip entirely if UNPAYWALL_EMAIL is empty
for DOI in $(cat _raw/openalex_dois.txt); do
  DOI_SLUG=$(echo "$DOI" | sed 's|/|_|g' | sed 's|[^a-zA-Z0-9_.-]||g')
  curl -s "https://api.unpaywall.org/v2/$DOI?email=$UNPAYWALL_EMAIL" > "_raw/unpaywall_${DOI_SLUG}.json"
done
```

Parse each response for `best_oa_location.url_for_pdf` (direct PDF) or `best_oa_location.url` (landing page). When a free PDF is found:
- Download into `09_academic/pdfs/` via Firecrawl
- Add the OA URL to the corresponding row in `09_academic/works-index.md`

For paywalled works with no OA version, note in `09_academic/works-index.md` as "PAYWALLED" — still cite the abstract from OpenAlex, just flag that full-text wasn't pulled. Don't pursue Sci-Hub or shadow libraries.

**GitHub handling (when target has a GitHub presence):**

If the target is a developer, OSS project, or dev-tool company with a meaningful GitHub footprint, create archive folder `10_github/` and write:
- `10_github/repos.md` — table of repos (name, description, stars, last-updated, primary language, topics)
- `10_github/profile.md` — user/org profile metadata (bio, location, hireable, member-since, follower count)
- `10_github/readmes/{repo-slug}.md` — pulled READMEs of the top 5-10 repos by stars or recent activity

Signals to consider for the "is this worth pulling" decision:
- Target's website links to a GitHub profile
- Target operates an OSS project (`/projects` page, "view source" links)
- Target is a dev-tool company (e.g., builds an SDK, library, or developer-facing platform)
- Skip if target has no GitHub presence or only a tiny placeholder profile.

Authenticated GitHub calls run at 5,000 req/hour — well above what a single archive run needs. No risk of rate-limiting during normal usage.

**Common Wayback gotchas:**
- Subdomains aren't auto-included. If the target uses `shop.DOMAIN.com`, query CDX separately for that subdomain.
- Some sites have years of duplicate captures of the same URL. `collapse=urlkey` dedupes correctly.
- Wayback occasionally returns HTML wrapped in archive.org chrome — verify the first scrape, then trust the pattern.

---

## Step 4: SCRAPE in parallel waves

**Firecrawl budget management.** Entity archives are credit-heavy by nature (often 30-80 pages per run). Pre-flight check before starting:
```bash
curl -s "https://api.firecrawl.dev/v1/team/credit-usage" -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```
If <100 credits remaining and the archive will need 30+ pages, warn the user before proceeding — either upgrade Firecrawl, use WebFetch fallback (slower fidelity), or scope down the archive (skip retail pages, skip parent-entity sites). The skill should not silently burn through the last 100 credits.

**WebFetch tier (Claude built-in, free) is useful for:** Wikipedia entries, .edu/.gov pages about the target, simple blog posts the target is referenced in. Reserve Firecrawl for the target's own marketing site (typically JS-heavy), shop pages, complex modern WordPress sites.



### Wave A: Website pages
Fire off parallel Firecrawl scrapes for every discovered sitemap URL. **Bash `&` + `wait` pattern** runs up to 20 concurrent.

```bash
for url in "${urls[@]}"; do
  slug=$(echo "$url" | sed 's|https://DOMAIN/||' | sed 's|/$||' | sed 's|/|_|g')
  [ -z "$slug" ] && slug="home"
  curl -s -X POST "https://api.firecrawl.dev/v1/scrape" \
    -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"url\": \"$url\", \"formats\": [\"markdown\"]}" > "/tmp/scrape_${slug}.json" &
done
wait
```

Then convert each JSON to `{slug}.md` and drop in `01_website/`.

**Pitfall:** Firecrawl blocks Meta (Facebook, Instagram) and LinkedIn. Don't waste credits scraping them directly — use social snippets (Step 6) instead.

### Wave B: YouTube transcripts (three-tier fallback chain, v3.2.0+)

Use the shared helper at `~/.claude/skills/_research-lib/yt_transcript_fallback.py` — it handles three tiers automatically per video:

1. **yt-dlp captions** (primary — fastest, battle-tested)
2. **youtube-transcript-api** (different endpoint — bypasses bot challenges that block yt-dlp)
3. **Whisper transcription of audio** (last resort — slow but reliable; uses `large-v3-turbo` by default — ~4x faster than `large-v3` (non-turbo) with ~90% of its quality, and markedly more accurate on proper nouns than `medium` despite being slightly slower)

Each video is attempted at each tier in order. First success wins. The helper writes the same `{id}_{title}.txt` filename regardless of which tier produced it, so the downstream channel-index logic is unchanged.

**Bootstrap requirements** (already covered in Step 0 of v3.2.0+):

```bash
python -m yt_dlp --version 2>&1 || python -m pip install yt-dlp $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1
python -c "import youtube_transcript_api" 2>&1 || python -m pip install youtube-transcript-api $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1
# faster-whisper + CUDA wheels are required only if tier 3 is allowed (see content-research Wave C-bis for setup)
```

**Batch usage from a research run:**

```python
import sys, os
sys.path.insert(0, os.path.expanduser('~/.claude/skills/_research-lib'))  # portable: works on Win/Mac/Linux. The POSIX-form '/c/Users/...' DOES NOT work because Python on Windows reads paths literally.
from yt_transcript_fallback import fetch_batch

video_ids = open('_raw/yt_video_ids.txt', encoding='utf-8').read().split()
results = fetch_batch(
    video_ids,
    out_dir='02_youtube/transcripts',
    whisper_model='large-v3-turbo',  # large-v3-turbo for speed; large-v3 for max quality (slower)
    allow_whisper=True,              # False for fast runs that accept some missing transcripts
    sleep_between=2.0,               # rate-limit-friendly default
    on_progress=lambda i, total, r: print(f'  {i}/{total} {r["status"]} (tier {r["tier"]})') if i % 25 == 0 or r['status'] == 'failed' else None,
)
ok = sum(1 for r in results if r['status'] in ('ok', 'skipped'))
print(f'\nDone: {ok}/{len(results)} transcripts captured')
print(f'Failed: {len(results) - ok} — see results[].error for per-video details')
```

**Single-video usage:**

```python
from yt_transcript_fallback import fetch_transcript
r = fetch_transcript('VIDEO_ID', out_dir='02_youtube/transcripts', whisper_model='large-v3-turbo')
# r = {'status': 'ok'|'failed', 'tier': 1|2|3, 'path': '...', 'error': '...'}
```

**Why the chain matters:** today's session caught YouTube rate-limiting yt-dlp at video 367 of 690. The same session would have continued cleanly via tier 2 (youtube-transcript-api uses a different endpoint and wasn't blocked) for the remaining 323. Verified on a specific failed video: tier 2 returned 417 caption segments where tier 1 returned "Sign in to confirm you're not a bot."

**Expect ~5-15% of videos to still have no captions at any tier** — shorts, very new uploads, music-only content, age-gated videos. Note them in the channel index with `transcript: missing`. If you need transcripts for those, tier 3 (Whisper) will catch them as long as audio is downloadable.

**Background mode for big channels:** wrap the batch call in a background script so it doesn't block the rest of the research run:

```bash
nohup python -c "
import sys, os; sys.path.insert(0, os.path.expanduser('~/.claude/skills/_research-lib'))
from yt_transcript_fallback import fetch_batch
ids = open('_raw/yt_video_ids.txt').read().split()
fetch_batch(ids, out_dir='02_youtube/transcripts')
" > _raw/yt_fetch_log.txt 2>&1 &
```

### Wave C: Podcast metadata + audio (Listen Notes primary, page-scrape fallback)

**Default path: Listen Notes API** (replaces SerpAPI-discovery + Firecrawl-page-scraping of Spotify/Apple/SoundCloud/Podbean).

Parse `_raw/listennotes_podcasts_by.json` and `_raw/listennotes_episodes_about.json` from Step 3. For each relevant podcast/episode:

1. **Audio URL is returned directly** as `audio` field — no page scraping needed. Listen Notes proxies to the publisher CDN (Megaphone, Libsyn, Buzzsprout, etc.) and follows redirects to the actual MP3.

2. **Episode metadata is structured** — title, description, duration (`audio_length_sec`), pub date (`pub_date_ms`), full podcast metadata via `podcast` field. No HTML parsing.

3. **Free-tier transcript snippets** available when search terms hit indexed transcripts via the `transcripts_highlighted` array on search results. Pull these as primary-source verbatim quotes even without a full Whisper transcription run.

4. **For deeper episode detail**, fetch by ID:
   ```bash
   curl -s "https://listen-api.listennotes.com/api/v2/episodes/EPISODE_ID" \
     -H "X-ListenAPI-Key: $LISTEN_API_KEY" > _raw/episodes/ep_SLUG.json
   sleep 0.6
   ```
   Note: full transcript field is PRO-tier; free tier returns the upgrade message. For full transcripts, download audio + Whisper (Wave C-bis).

**Fallback path: Page scraping (only when Listen Notes doesn't index the show).** Some niche podcasts don't appear in Listen Notes — for those, fall back to the legacy Firecrawl approach:

```bash
# LEGACY: only when Listen Notes returns no results for the target
curl -s -X POST "https://api.firecrawl.dev/v1/scrape" -H "Authorization: Bearer $FIRECRAWL_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"url": "URL", "formats": ["markdown"]}' > /tmp/pod.json
```

Notes on the page-scrape fallback (legacy):
- **Spotify** often returns reCAPTCHA. Skip — Listen Notes covers Spotify-distributed shows.
- **Apple Podcasts** region-locks frequently. Skip — Listen Notes is better.
- **SoundCloud** works via Firecrawl if needed.
- **Podbean** — scrape `/e/<slug>/` episode URL, not the player-v2 embed (yt-dlp fails on player-v2).

### Wave C-bis: Audio transcription via Whisper (when captions don't exist)

If the podcast is audio-only and has no external captions source, **transcribe it locally via faster-whisper** rather than noting a gap. Setup is already done on your machine (see "Environment Preflight" below). For any new machine:

**One-time setup:**
```bash
# ffmpeg (no admin required — drop into a PATH-visible user dir)
mkdir -p ~/bin && cd ~/bin
curl -sL "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -o ffmpeg.zip
unzip -q ffmpeg.zip
cp ffmpeg-*/bin/*.exe ~/bin/
rm -rf ffmpeg.zip ffmpeg-*/

# faster-whisper + CUDA runtime wheels (pip does NOT need admin)
pip install --user faster-whisper nvidia-cublas-cu12 nvidia-cudnn-cu12
```

**Environment preflight** — verify before transcribing:
```bash
ffmpeg -version 2>&1 | head -1
python -c "from faster_whisper import WhisperModel; print('faster-whisper ready')"
nvidia-smi 2>&1 | grep "CUDA Version" | head -1
```

**Step 1 — get direct MP3 URLs.** TWO paths:

**Path A (preferred, when Listen Notes indexed the episode):** parse the `audio` field directly from `_raw/listennotes_*.json` responses. The URL is already a CDN-redirecting proxy that resolves to the actual MP3. No HTML parsing needed.

```python
import json
data = json.load(open('_raw/listennotes_episodes_about.json'))
for ep in data['results']:
    print(f"{ep['title_original']}: {ep['audio']}")  # ep['audio'] is the URL to download
```

**Path B (fallback, only for episodes Listen Notes doesn't index):** extract from episode pages. Podbean, Libsyn, Buzzsprout, and most Simplecast/Megaphone pages embed the MP3 URL as JSON-LD `contentUrl`. Regex that:

```python
import re, urllib.request
def get_mp3(episode_url):
    req = urllib.request.Request(episode_url, headers={'User-Agent':'Mozilla/5.0'})
    html = urllib.request.urlopen(req, timeout=30).read().decode('utf-8', errors='ignore')
    m = re.search(r'"contentUrl":"(https://[^"]+\.mp3[^"]*)"', html)
    return m.group(1) if m else None
```

**Step 2 — download MP3s via Python urllib**, NOT bash curl (bash `curl -sL` inside `while read` loops silently fails on Windows — Python is reliable):

```python
import urllib.request, os
def download(url, path):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=120) as r, open(path, 'wb') as f:
        f.write(r.read())
```

Save MP3s to `03_podcast/audio/` (or wherever the podcast folder is).

**Step 3 — transcribe** with this reusable script at `03_podcast/transcribe.py` (or the appropriate podcast folder):

```python
import os, sys, glob, time, site
sys.stdout.reconfigure(encoding='utf-8')

# CRITICAL on Windows: prepend NVIDIA DLL dirs to PATH AND call add_dll_directory
# BEFORE importing faster_whisper. os.add_dll_directory alone is NOT enough for CTranslate2.
cuda_dirs = []
for base in site.getsitepackages() + [site.getusersitepackages()]:
    for sub in ('cublas', 'cudnn', 'cuda_nvrtc'):
        d = os.path.join(base, 'nvidia', sub, 'bin')
        if os.path.isdir(d):
            cuda_dirs.append(d)
            os.add_dll_directory(d)
os.environ['PATH'] = os.pathsep.join(cuda_dirs) + os.pathsep + os.environ.get('PATH','')

from faster_whisper import WhisperModel

AUDIO_DIR = 'audio'
OUT_DIR = 'transcripts'
os.makedirs(OUT_DIR, exist_ok=True)

# large-v3-turbo = 809M params, distilled from large-v3. Best speed/quality balance
# as of 2026. ~4x faster than large-v3 with ~90% of the quality. Use 'large-v3' for
# absolute max quality on rare proper nouns (worth it for expert/academic interviews);
# use 'medium' if VRAM is tight (turbo fits in 6GB, medium in 4GB).
try:
    model = WhisperModel('large-v3-turbo', device='cuda', compute_type='float16')
    print('Loaded on CUDA (large-v3-turbo)')
except Exception as e:
    print(f'CUDA failed ({e}), falling back to CPU int8 (~10x slower)')
    model = WhisperModel('large-v3-turbo', device='cpu', compute_type='int8')

total_audio = total_time = total_words = 0
for mp3 in sorted(glob.glob(os.path.join(AUDIO_DIR, '*.mp3'))):
    name = os.path.splitext(os.path.basename(mp3))[0]
    out = os.path.join(OUT_DIR, f'{name}.txt')
    if os.path.exists(out) and os.path.getsize(out) > 500:
        continue
    t = time.time()
    segments, info = model.transcribe(mp3, beam_size=5, vad_filter=True, language='en')
    text = ' '.join(s.text.strip() for s in segments).strip().replace('. ', '.\n')
    open(out, 'w', encoding='utf-8').write(text)
    elapsed = time.time() - t
    total_audio += info.duration; total_time += elapsed; total_words += len(text.split())
    print(f'{name}: {info.duration:.0f}s -> {elapsed:.1f}s ({info.duration/elapsed:.1f}x RT)')

print(f'\nTOTAL: {total_audio/60:.1f} min audio -> {total_time/60:.1f} min wall, {total_words:,} words')
```

**Expected performance (default model = large-v3-turbo):**
- RTX 4060 (8GB VRAM), large-v3-turbo, float16: **~12-18× realtime** — 3 hours of audio in ~12-15 minutes
- For comparison: `medium` is faster (15-23× realtime) but less accurate; `large-v3` is slower (4-6× realtime) but catches more rare names
- CPU int8 fallback: **1-2× realtime** — 3 hours of audio in ~2-3 hours
- Kick off with `run_in_background: true`, monitor via output file

**When to transcribe automatically vs. ask:**
- ≤ 10 episodes, ≤ 5 hours total → just do it, ~15 min on GPU at large-v3-turbo
- 10-30 episodes or > 5 hours → estimate time, mention in response, then do it
- > 30 episodes → ask the user whether to proceed (could be 30+ min)

**Quality notes (v3.2.0+ defaults to large-v3-turbo):**
- `large-v3-turbo` handles technical jargon well and catches proper nouns markedly better than `medium`. Default for new runs.
- `large-v3` (non-turbo) is ~3× slower but the gold standard for rare proper nouns and accented speech — switch when transcribing expert interviews where every name matters.
- `medium` is a fallback when VRAM is constrained (<6 GB) or speed is paramount over quality.
- `vad_filter=True` skips silent sections and music intros — critical for clean output
- Always set `language='en'` if the podcast is English — skips the language detection step and saves time

### Wave D: Social snippets

Meta / LinkedIn block direct scraping. **Instead**, run multiple SerpAPI queries and aggregate Google-indexed snippets:

```bash
# Query variations
curl -s "https://serpapi.com/search.json?q=%22TARGET%22+facebook&api_key=$SERPAPI_KEY&num=30"
curl -s "https://serpapi.com/search.json?q=%22TARGET%22+linkedin&api_key=$SERPAPI_KEY&num=30"
curl -s "https://serpapi.com/search.json?q=%22TARGET%22+instagram&api_key=$SERPAPI_KEY&num=30"
curl -s "https://serpapi.com/search.json?q=%22TARGET%22+podcast+OR+interview&api_key=$SERPAPI_KEY&num=30"
```

Aggregate unique entries by URL into `05_social/social-snippets.md`:

```python
import json, os
search_dir = 'path/to/_raw/search'
out = ['# Social + Cross-Platform Snippets', '',
       'Facebook / Instagram / LinkedIn block direct scraping. Google-indexed excerpts below.', '']
seen = set()
for fname in os.listdir(search_dir):
    d = json.load(open(os.path.join(search_dir, fname), encoding='utf-8'))
    entries = d.get('organic_results') or d.get('organic') or []
    for r in entries:
        link = r.get('link','').strip()
        if not link or link in seen: continue
        seen.add(link)
        out.append(f'### {r.get("title","")}')
        out.append(f'- URL: {link}')
        if r.get('date'): out.append(f'- Date: {r["date"]}')
        if r.get('snippet'): out.append(f'- Snippet: {r["snippet"]}')
        out.append('')
# Write out
```

**Note:** Serper uses `organic`, SerpAPI uses `organic_results` — handle both.

**Note:** Don't waste Serper queries on `site:facebook.com/PAGE_ID` — it usually returns zero. Use `"TARGET" facebook` as a broader query instead.

---

## Step 5: BUILD index + statistics

### channel-index.md (YouTube)

```markdown
| # | Title | ID | Duration (s) | Views | Transcript |
|---|-------|----|----|-------|------------|
```

One row per video, cross-referenced to the `.txt` filename in `transcripts/` or `MISSING (no captions)`.

### Cross-references (when useful)

- **Product → video**: grep each transcript for product names, build a reverse index.
- **Episode → topic**: for a podcast, extract episode titles and synthesize theme tags.

### INDEX.md — the master navigation

**YAML frontmatter REQUIRED at top** per `CONVENTIONS.md` Rule 2:

```yaml
---
target: "[Company / Person Name]"
slug: [slug-form]
canonical_entity_id: [slug-form]   # NEW v3.0.3: stable across renames. Default = slug on first run. Never change once set.
topic_area: [TopicArea or null]    # NEW v3.0.3: which topics/{TopicArea}/ this lives in
type: content-research
skill_version: "3.2.0"             # NEW v3.0.3: pinned for forward compat with /content-update
run_date: YYYY-MM-DD
domains: [primary-domain.com, mirror-or-parent.com]
status: complete
file_count: [N]
total_size_mb: [N]
apis_used: [firecrawl, yt-dlp, serpapi, serper, listen-notes]
gaps:
  - "[real gap, e.g., 'Crunchbase paywalled']"
supersedes: null
tags:
  domain: [agronomy | tech | business | personal]
  artifact_type: entity-archive
---
```

Required sections (after frontmatter):

1. **Header:** Generated date, target, tools used (prose, complements the frontmatter)
2. **What's Here table:** folder-by-folder file counts
3. **Corpus stats:** total files, total size, transcript word count (if YouTube-heavy)
4. **Key Facts:** company/person details extracted from primary pages
   - Founded date, location, phone, email, founders, team, products, methodology
5. **Quick-Access Map:** most important files with one-line descriptions
6. **Honest gaps:** what couldn't be captured and why. Whisper transcription for audio-only podcasts is part of the normal flow (see Wave C-bis) — so don't list it as a gap unless you actively decided to skip it (e.g., >30 episodes, user declined, GPU unavailable). Typical real gaps:
   - "Firecrawl blocks Meta/LinkedIn — N snippets via Google index instead"
   - "X videos without captions (shorts or caption-less)"
   - "Crunchbase/PitchBook data paywalled"
   - "Member-only or auth-gated content not pulled"
   - "Some podbean `contentUrl` regex missed N/M episodes — fallback: manual inspection"
7. **Next actions** (optional): what could be extracted next at higher cost

Corpus stats calculation:

```python
import os, glob
trans_dir = '02_youtube/transcripts'
total_words = total_chars = files = 0
for f in glob.glob(os.path.join(trans_dir, '*.txt')):
    content = open(f, encoding='utf-8').read()
    total_words += len(content.split())
    total_chars += len(content)
    files += 1
print(f'Transcripts: {files} files, {total_words:,} words, {total_chars:,} chars')
```

---

## Step 6: APPEND to master indexes (mandatory, before reporting)

After the entity archive's own INDEX.md is written, append one line to EACH of:

1. **`~/Documents/AI\INDEX.md`** under "Entity archives" — path matches the output path resolution above:
   - With topic-area: `- YYYY-MM-DD [content] [{Target}](Content%20extraction/topics/{TopicArea}/{slug}-research-YYYY-MM-DD/) — {N} files, {one-line description}`
   - Ungrouped: `- YYYY-MM-DD [content] [{Target}](Content%20extraction/topics/{slug}-research-YYYY-MM-DD/) — {N} files, {one-line description}`

2. **`~/Documents/AI\Content extraction\INDEX.md`** under the topic-area section for `{TopicArea}` (add the row to its entity-archives table). The link is relative to `Content extraction/`, so it includes the `topics/{TopicArea}/` prefix:
   - With topic-area: `| [{slug}-research-YYYY-MM-DD](topics/{TopicArea}/{slug}-research-YYYY-MM-DD/) | {Target} — {one-line description} | {N} |`
   - Ungrouped (add under an "Ungrouped" section): `| [{slug}-research-YYYY-MM-DD](topics/{slug}-research-YYYY-MM-DD/) | {Target} — {one-line description} | {N} |`

If the topic-area section doesn't exist in the entity catalog yet (e.g., first run for a new topic-area), add it. Don't fall back to a flat "by date" section — that's the old convention.

**This is non-negotiable.** Per `CONVENTIONS.md` Rule 7, an archive that isn't indexed is an orphan and doesn't count as complete.

## Step 6.5: WRITE recipe.yaml + UPDATE MANIFEST.yaml (NEW in v3.0.3 — mandatory)

This step makes the archive **updateable** by a future `/content-update` skill (planned v3.1). Without it, the archive is a snapshot only — no delta detection possible.

See `~/.claude/skills/_research-lib/SCHEMAS.md` for full schemas, identity resolution rules, source_key derivation, and merge-key precedence. Summary:

1. **Resolve `canonical_entity_id` first.** Per SCHEMAS.md "Identity resolution procedure":
   - If this archive folder already exists on disk, read its existing `recipe.yaml` and REUSE the `target.canonical_entity_id` verbatim. Do not derive a new one.
   - If no existing archive but the topic-area MANIFEST has an entry with matching `path` or `slug`, reuse its `canonical_entity_id`.
   - Otherwise (first creation), set `canonical_entity_id` = the current run's slug.
   - **Never change `canonical_entity_id` on a re-run, even if the user used a different name/slug.** Add to `aliases[]` instead.

2. **Write `recipe.yaml` to the archive root** (alongside INDEX.md). Required structure:
   - `schema_version: 1`, `skill_version: "3.2.0"`, `skill_name: content-research`
   - `generated_at`, `last_updated_at` (UTC ISO-8601 `Z` format — see step 5 below)
   - `target` block: `name`, `slug`, `canonical_entity_id` (from step 1), `topic_area` (string name OR YAML null if ungrouped — do NOT use the string "ungrouped" or empty string)
   - `sources[]` array — one entry per source captured. Each entry MUST include: `source_key` (derived per SCHEMAS.md rules — e.g., `website_drcloud.com`, `youtube_DrHenryCloud`, `podcast_listen-notes_{id}`), `type`, `discovery_method`, `api_used`, `captured_count`, `last_run_at_utc`, `resumable: true|false`. Optional: `last_seen_*` anchors, `*_file` paths, `interrupted_by`.
   - `aliases: []`, `snapshot_triggers: []` (placeholders)

3. **For every source with `resumable: true`, write a captured-IDs file in `_raw/`** with **stable item IDs** (one per line):
   - YouTube: 11-char video IDs → `_raw/yt_captured_ids.txt`
   - Podcast (Listen Notes): hex episode IDs → `_raw/podcast_captured_episode_ids.txt`
   - Website: full URLs (strip `?utm_*` tracking params for normalization) → `_raw/{registrable-domain}_captured_urls.txt`
   - Press / social: full URLs
   - Counts alone are NOT enough — v3.1 tombstone detection needs to identify which specific items disappeared between runs.

4. **Update `topics/{TopicArea}/MANIFEST.yaml`** (or `topics/MANIFEST.yaml` if topic_area is null). **MANIFEST merge key precedence** (CRITICAL — see SCHEMAS.md):
   - First, search `archives[]` for entry where `canonical_entity_id` matches. If found, UPDATE that entry.
   - Otherwise, search for entry where `path` matches (legacy fallback). If found, UPDATE that entry AND populate its `canonical_entity_id` from the recipe.
   - Otherwise, APPEND a new entry.
   - **NEVER use `slug` alone as merge key** — slug can change on rename, but `canonical_entity_id` is stable. Matching on slug silently forks identity.
   - Entry fields: `slug`, `canonical_entity_id`, `path`, `created_at_utc` (only on first append), `last_updated_at_utc`, `skill_version_at_creation` (only on first append), `skill_version_at_last_update`, `has_recipe_yaml: true`, `sources_summary` (compact dict keyed by `source_key`).

5. **Use UTC timestamps everywhere.** Bash: `date -u +%Y-%m-%dT%H:%M:%SZ`. Python: `datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')`. Never use local time for `*_at_utc` fields — it breaks delta comparisons across timezones.

**Why this is mandatory:** without recipe.yaml + MANIFEST.yaml, the archive can never be updated incrementally — only re-created from scratch as a new dated snapshot. That works but burns API quota and loses provenance. With this metadata, a future `/content-update` can identify deltas (new YouTube videos, new blog posts, new podcast episodes) and pull only those.

## Step 7: REPORT back to user

In the final message, give a concise summary. The **first two lines are mandatory** so the user can verify the topic-area routing and exact save path without scrolling:

```
TopicArea: <Name or "ungrouped"> (source: arg|inferred|asked)
Saved: {full path}

**{N} files, {size}, {wordcount} transcribed words**

[One paragraph on folder contents — what's where]

[3-4 bullets of key facts surfaced — founders, founding date, signature product, methodology]

[Honest gaps block — what's NOT in there and why]

[API budget used for this run — Firecrawl credits, SerpAPI searches]

Want me to push further? Best next targets: [a], [b], [c].
```

If versioning was applied, append `(v{N})` to the Saved path. If a new topic-area was created, append `(new topic-area created)`.

---

(No storm-verify offer here: a content-research run is an extraction dossier — everything the target published — not a synthesized-claims report, so there is rarely a load-bearing claim to proof. The `/storm-verify` offer lives on `/research` and `/deep-research`, where synthesis actually happens. If a specific dossier's `INDEX.md` summary ever does warrant checking, run `/storm-verify <archive-folder>` standalone.)

---

## API Budget Guidance

Firecrawl is the tightest budget — 500 lifetime credits. Typical runs:

| Target type | Firecrawl | SerpAPI | Serper |
|-------------|-----------|---------|--------|
| Thin manufacturer site | 20-35 | 5-10 | 0 |
| Content-heavy consultant / expert | 40-60 | 10-15 | 0-5 |
| Large multi-brand company | 60-100 | 15-25 | 5-10 |

**To stretch Firecrawl**, bias toward:
- yt-dlp for transcripts (free, local)
- WebFetch for simple public pages
- Only use Firecrawl for JavaScript-heavy sites (Spotify, SoundCloud, Crunchbase, complex WordPress)

Check remaining credits any time:
```bash
curl -s "https://api.firecrawl.dev/v1/team/credit-usage" -H "Authorization: Bearer $FIRECRAWL_API_KEY"
```

---

## Common Pitfalls (learned from prior runs)

1. **`/tmp/` path mismatches between bash and Windows Python.** Bash `/tmp/` maps to MinGW's virtual tmp; Python on Windows reads `/tmp/` literally and fails. **Fix:** copy files to the research dir with `cp` before Python processes them.

2. **Serper queries with `site:` operators on Facebook/LinkedIn return zero results.** Don't waste Serper quota — use plain `"TARGET" facebook` instead.

3. **Serper rate limits at 25 queries/second and will 400 with `"Query not allowed"`** on unusual queries. Fall back to SerpAPI when Serper 400s.

4. **yt-dlp defaults to `.en.vtt`** — make sure your converter matches that extension, not `.srt`.

5. **Background `yt-dlp` on large channels takes 3-10 minutes.** Launch with `run_in_background: true` so you can proceed with page scraping in parallel.

6. **Homepage scrapes often reveal the canonical domain** (via `ogUrl` in metadata). If the user gives you `domain-a.com` but metadata points to `domain-b.com`, note both and prefer the canonical for display.

7. **Video IDs can contain underscores** (e.g., `_GlQA5EX7YE`). Don't split on first underscore to extract ID from filename — use `startswith(id + '_')` instead.

8. **Cleanup junk files from batched saves.** If you save all scrapes to `/tmp/` with a single prefix and then loop them into folders, non-page responses (search results, retry attempts) will end up misfiled. Validate before finalizing.

9. **Bash `curl -sL` inside a `while IFS=... read` loop silently fails on Windows** — the first download works, subsequent ones produce 0-byte files. Root cause unclear (possibly stdin interaction with the backgrounded curl). **Fix:** use Python `urllib.request` for any batched downloads. Confirmed reliable.

10. **Whisper CUDA loads the model but crashes on transcribe.** Classic symptom: `RuntimeError: Library cublas64_12.dll is not found or cannot be loaded` right after "Loaded on CUDA." On Windows, `os.add_dll_directory()` alone is NOT enough for CTranslate2's DLL loader — you MUST also prepend the DLL dirs to `os.environ['PATH']` **before** importing faster_whisper. Install `nvidia-cublas-cu12` + `nvidia-cudnn-cu12` pip wheels (user-level, no admin) and use the exact boilerplate in the Whisper script above.

11. **yt-dlp cannot extract Podbean MP3s from the `player-v2` embed** (returns "Unsupported URL"). Don't use yt-dlp for podbean — regex `"contentUrl":"...mp3"` directly from the episode page HTML instead. The JSON-LD block always has it.

12. **Research folders may get moved/reorganized mid-session** by the user. Before writing new content to a path, verify the folder still exists at the expected location. If the parent folder is gone, search `Downloads/` and parent dirs for a `Content extraction/` wrapper or similar before creating a new one.

---

## Edge Cases

- **Person with no company site** (e.g., author, academic, speaker): skip `01_website/`, emphasize YouTube, podcast appearances, press.
- **Company with shop subdomain** (e.g., shop.soilworksllc.com): check separately; Shopify sitemaps may be at `/sitemap.xml` on the subdomain.
- **Similar-handle collision** (e.g., @soilmender6310 is NOT Soil Mender Products, it's cooking content): verify channel ownership via the "About" page or recent video topics before downloading 50 unrelated transcripts.
- **Rebranded companies** (e.g., two entities merged): capture both parents + the merged entity's content. Use `06_parent_or_related/` for the upstream sites.

---

## Output Examples

For thin targets (~40 files): one INDEX.md, no cross-reference files.

For content-heavy targets (100+ files): add `02_youtube/channel-index.md`, `03_podcast/episode-index.md`, and a product-to-video cross-reference in `01_website/products/_cross-reference.md` if applicable.

Always finish with an explicit "Honest gaps" section in INDEX.md — resist the urge to hide what didn't work. The user's trust depends on accurate accounting.
