---
name: content-update
version: "1.1.0"
description: Detect new content for an existing entity archive (or all archives in a topic-area) and append-only update without re-fetching what's already captured. Reads recipe.yaml + MANIFEST.yaml written by /research, /deep-research, and /content-research (v3.0.3+). Use when you want to refresh an existing archive's coverage of a target — new YouTube videos, new blog posts, new podcast episodes — without burning API quota on what you already have. Invoke with `/content-update <path-to-archive>` or `/content-update --topic-area=<Name>`. Trigger phrases: "update X", "refresh X", "pull new content for X".
allowed-tools: Bash, WebSearch, WebFetch, Agent
---

# Content Update Skill

Append-only delta refresh for archives previously built by `/research`, `/deep-research`, or `/content-research`. Reads the v3.0.3+ metadata (recipe.yaml + topic-area MANIFEST.yaml), re-enumerates each resumable source, identifies new items by set-diff against captured-IDs files, and pulls only deltas. Never deletes, never modifies existing captured content.

**When to use this vs. other skills:**

| Skill | When |
|---|---|
| `/content-update` (this one) | Existing archive exists, you want to pull what's NEW since last run |
| `/content-research` | New entity, no archive exists yet — full fresh extraction |
| `/research`, `/deep-research` | Topic synthesis or security analysis (one-shot, not incremental) |

---

## Step 0: BOOTSTRAP (run every session)

Reuse the deep-research skill's API keys.

```bash
source ~/.claude/skills/deep-research/.env && echo "Keys: SERPAPI=${SERPAPI_KEY:+OK} SERPER=${SERPER_API_KEY:+OK} FIRECRAWL=${FIRECRAWL_API_KEY:+OK} OPENALEX=${OPENALEX_KEY:+OK} UNPAYWALL=${UNPAYWALL_EMAIL:+OK} GITHUB=${GITHUB_TOKEN:+OK} EXA=${EXA_API_KEY:+OK} LISTEN=${LISTEN_API_KEY:+OK}"
python -m yt_dlp --version 2>&1 || python -m pip install yt-dlp $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
python -c "import youtube_transcript_api" 2>&1 || python -m pip install youtube-transcript-api $([ -z "$VIRTUAL_ENV" ] && echo "--user") 2>&1 | tail -3
```

**Schema reference:** all schema details live at `~/.claude/skills/_research-lib/SCHEMAS.md`. Read it if anything below is ambiguous.

**YouTube transcript fetching (v1.1.0+):** when this skill fetches deltas for a youtube_channel source, use the shared helper at `~/.claude/skills/_research-lib/yt_transcript_fallback.py` for the actual transcript retrieval (Step 4). It runs a three-tier chain per video (yt-dlp → youtube-transcript-api → Whisper) so a single YouTube rate-limit doesn't abandon the delta-fetch mid-run. Default Whisper model: `large-v3-turbo`.

---

## Step 1: PARSE invocation + select archives

Three invocation modes:

1. **Single archive (path):** `/content-update topics/Leadership/henry-cloud-research-2026-05-21/`
   - Verify the path exists and contains `recipe.yaml`. If no recipe.yaml, the archive predates v3.0.3 metadata — run the backfill script first (`Documents/AI/Content extraction/_BACKFILL.py`), then retry.
   - Single archive to process.

2. **Topic-area (flag):** `/content-update --topic-area=Leadership`
   - Read `Documents/AI/Content extraction/topics/{TopicArea}/MANIFEST.yaml`.
   - For each archive in `archives[]`, get its `path` and append to processing list.
   - Filter: only archives with `has_recipe_yaml: true` (skip un-backfilled archives with a warning).

3. **Trigger phrase parsing:** if the user said something like "update Henry Cloud" or "refresh the Leadership topic" without an explicit path/flag:
   - Try matching against canonical_entity_id values in the relevant manifests.
   - If multiple matches, ask the user once which one.
   - If "the Leadership topic" / "all Leadership archives" — use topic-area mode.

For each archive selected, run Steps 2-6 in sequence. Don't parallelize across archives — keeps log output sane and API quota predictable.

---

## Step 2: READ recipe + identify resumable sources

```python
import yaml, os
recipe = yaml.safe_load(open(os.path.join(archive_path, 'recipe.yaml'), encoding='utf-8'))
sources = [s for s in recipe.get('sources', []) if s.get('resumable')]
```

**Backfilled archives caveat:** v3.0.3 `_BACKFILL.py` is REQUIRED to materialize captured-IDs files (one per resumable source) at backfill time — `/content-update` does NOT attempt filename-to-URL inversion or guess captured sets from folder contents at runtime (that approach was rejected as too lossy: slug collisions, URL encoding normalization, and truncation produce silent false-diffs).

If a source entry is `backfilled: true` but its `*_file` field is missing or the file doesn't exist on disk, **the skill MUST skip that source** with a clear message:

```
SKIPPING source {source_key} on {archive_slug}:
  Backfilled entry has no captured-IDs file. Re-run _BACKFILL.py (which now
  materializes captured-IDs files for all resumable sources) before updating.
```

Do NOT attempt to reconstruct the captured set from filenames or transcript paths at update time — that's the backfill script's job, run once, in cold-headed batch mode, with explicit logging of how each ID was derived.

Print one line per archive: `Processing: {slug} ({skill_name}, last updated {last_updated_at})`.

---

## Step 3: ENUMERATE current state per source

For each resumable source in `recipe.sources[]`, re-run the discovery query and emit the current full set. Per-source method:

### youtube_channel

```bash
python -m yt_dlp --flat-playlist --print "%(id)s" \
  "https://www.youtube.com/@${CHANNEL_HANDLE}/videos" > /tmp/yt_current.txt
```

Read current IDs into a set. Read captured IDs from `_raw/yt_captured_ids.txt`. If that file doesn't exist, this source was not properly materialized at backfill time — skip per Step 2 policy; do NOT attempt to derive captured IDs from filenames at runtime. `new_ids = current - captured`.

**Fetching the new transcripts** (Step 4) uses `~/.claude/skills/_research-lib/yt_transcript_fallback.py` (`fetch_batch(new_ids, out_dir='02_youtube/transcripts')`) — the three-tier chain (yt-dlp → youtube-transcript-api → Whisper) handles bot challenges automatically by trying tier 2 when tier 1 fails. If yt-dlp at tier 1 hits "Sign in to confirm you're not a bot" on ALL videos AND tier 2 also fails consistently (rare), log this source as `interrupted_by: youtube-bot-challenge-all-tiers` in the updated recipe and move on. Per-video tier outcomes are returned in `results[].tier` for the update history log.

### website (sitemap)

```bash
curl -s "https://${DOMAIN}/sitemap.xml" > /tmp/sitemap_current.xml
# Parse for <loc> tags, get full URL list
```

Apply the same `filter` from recipe.sources[].filter if defined (e.g., trust-keyword filter for boundaries.me). Read captured URLs from the captured-URLs file. If that file doesn't exist (e.g., backfilled archive where website URLs couldn't be reliably reconstructed), this source is `resumable: false` in the recipe and Step 2 will have already skipped it; do NOT attempt runtime URL reconstruction here. `new_urls = current_filtered - captured`.

### website (google-site-query)

```bash
curl -s "https://serpapi.com/search.json?q=site:${DOMAIN}&api_key=${SERPAPI_KEY}&num=100"
```

Same diff logic. Note: SerpAPI returns at most 100 results — for sites with more, page through (`start=100`, `start=200`, etc.) until exhausted.

### podcast (listen-notes)

```bash
curl -s "https://listen-api.listennotes.com/api/v2/podcasts/${PODCAST_ID}?sort=recent_first" \
  -H "X-ListenAPI-Key: ${LISTEN_API_KEY}"
```

Read `last_seen_episode_pub_date_ms` from recipe. New episodes are those with `pub_date_ms > last_seen_episode_pub_date_ms`. Also do a set-diff on episode IDs as a safety net (catches backfilled/edited episodes that don't have a strictly-newer pub_date).

**Free-tier rate limit:** 2 req/sec, ~10K req/month. With long sleeps (3-5s between paginated calls), update runs usually fit. If 429ed, log `interrupted_by: free-tier-quota` and continue.

### press_search / social_search

Re-run the same `queries` from recipe.sources[].queries. Dedupe results by URL (strip `?utm_*` tracking params first) against the existing snippet list. `new_snippets = current - captured`.

### topic-synthesis (research / deep-research output)

Not incrementally updateable. Skip with note: "Topic syntheses are one-shot — to refresh, run `/research` or `/deep-research` again to produce a new dated archive."

---

## Step 4: FETCH deltas

For each source with `new_ids` / `new_urls` / `new_snippets`:

- Use the same fetch logic as the original skill (`/content-research` for entity archives — see its SKILL.md Wave A/B/C/D).
- Save new files alongside existing ones (append-only). No overwrite of existing files.
- For YouTube: pull captions via yt-dlp with `--sleep-requests 2 --sleep-interval 1` to avoid rate limits.
- For website: Firecrawl scrape per URL.
- For podcast (Listen Notes): metadata is enough for the update log; audio MP3 + Whisper transcription on demand only (ask user if they want it).
- For SerpAPI: write NEW snippets to a NEW dated file alongside the existing one — `05_social/social-snippets-updates-{run_date}.md` or `04_press/press-list-updates-{run_date}.md`. Do NOT modify the original `social-snippets.md` / `press-list.md`. Append-only contract (Step 7) applies — existing captured files are immutable history.

**Budget check before fetching:** Firecrawl credit balance check (`/v1/team/credit-usage`). If estimated cost > 20% of remaining credits, ask the user to confirm before proceeding.

---

## Step 5: UPDATE captured-IDs files + recipe.yaml + MANIFEST

Run this step **after every source attempt** — success, partial interruption, or skipped. Update history (`update_history[]`) is always appended, regardless of outcome. Counts and `last_seen_*` anchors only advance for sources that actually fetched new items successfully.

1. **Append new IDs to captured-IDs file** (one per line):
   ```bash
   echo "$NEW_YT_ID" >> _raw/yt_captured_ids.txt
   ```

2. **Update `recipe.yaml`** (this file IS allowed to be modified — it's metadata, not captured content):
   - `last_updated_at: <now UTC>`
   - Per source: increment `captured_count` by deltas, refresh `last_run_at_utc`, update `last_seen_*` anchors (e.g., `last_seen_episode_pub_date_ms` for podcasts, latest YouTube ID for channels).
   - Always append to source's `update_history[]` array (create if missing), regardless of success: `{run_at_utc, new_items_count, status: "success" | "interrupted" | "skipped", interrupted_by: <reason or null>}`. Never drop the audit trail — partial failures must show in history.
   - **Do NOT modify `skill_version`** in recipe.yaml. That field is the version of the *creating* skill that originally produced the archive. The /content-update skill records its own version in a separate `last_updated_by` field: `last_updated_by: "content-update/1.0.0"`.

3. **Update topic-area `MANIFEST.yaml`** for the matching archive entry:
   - `last_updated_at_utc: <now>`
   - `last_updated_by_skill: "content-update/1.0.0"` (new field, distinct from `skill_version_at_last_update` which still tracks the creating skill's version)
   - Refresh `sources_summary` counts.
   - Use merge key precedence per SCHEMAS.md: `canonical_entity_id` → `path` → never `slug` alone.

4. **Append `## Updates {YYYY-MM-DD}` section to archive's `INDEX.md`** — use the actual current date, never a placeholder. Don't modify existing INDEX.md sections:
   ```markdown
   ## Updates {YYYY-MM-DD}
   
   - YouTube: +N new videos (was X, now Y)
   - Boundaries.me blog: +N new trust-filtered posts (was X, now Y)
   - Listen Notes podcast: +N new episodes captured (was X, now Y)
   - Press: +N new mentions
   
   Sources skipped: list each with reason
   
   Run by /content-update v1.0.0 at {YYYY-MM-DD HH:MM:SS UTC}.
   ```

---

## Step 6: REPORT back to user

**Per-archive block (MANDATORY format for every archive processed — single or topic-area mode):**

```
=== Archive: <slug> (<canonical_entity_id>) ===
Path: <full path>
Updated: <YYYY-MM-DD HH:MM:SS UTC>
Result: COMPLETE | PARTIAL | SKIPPED

Deltas (per source):
- youtube_DrHenryCloud: +N new videos (was X, now Y)
- website_drcloud.com: +M new pages
- podcast_listen-notes_{id}: +J new episodes
- ... etc

Sources skipped/interrupted:
- <source_key>: <reason — e.g., backfilled archive missing captured-IDs file, or free-tier-quota>

API budget consumed for this archive: <details>
```

**Result determination:**
- COMPLETE: every resumable source ran end-to-end, regardless of whether deltas were 0 or many
- PARTIAL: at least one source was interrupted (rate limit, network failure) but others completed
- SKIPPED: zero sources processed (e.g., archive missing recipe.yaml, all sources backfilled without captured-IDs files)

**Topic-area mode wrap-up (after all per-archive blocks):**

```
=== Topic-area summary: <Name> ===
Archives processed: N
  - COMPLETE: A
  - PARTIAL: B (list each with the source(s) that failed)
  - SKIPPED: C (list each with reason)

Total deltas across all archives:
  - YouTube: +<sum>
  - Website: +<sum>
  - etc.

Total API budget consumed:
  - Firecrawl: ~N credits (X% of starting balance)
  - SerpAPI: N searches
  - Listen Notes: N requests

Failed sources requiring user action (e.g., re-auth, cookie extraction, manual rename alias): list each with the recommended next step.
```

This format is non-negotiable. The user needs to know exactly which archives succeeded and which need follow-up — a single-line "done" message is forbidden.

---

## Step 7: APPEND-ONLY contract (non-negotiable)

This skill **must not**:
- Delete any captured file
- Modify any existing captured file
- Re-fetch any item already in the captured-IDs file
- Change `canonical_entity_id` (read existing recipe and reuse — never derive a new one)
- Bump `schema_version` (any breaking schema change requires a versioned migration, not silent rewrites)

This skill **must**:
- Treat the existing archive as immutable history
- Append new content alongside existing content
- Update only the metadata files (recipe.yaml, MANIFEST.yaml, INDEX.md updates section)
- Log every action — silent failures are forbidden

If something needs deletion or modification (e.g., a URL changed at origin and the old content is now misleading), record a `tombstone` entry in recipe.yaml's `tombstones[]` array (new in v1.0.0 of this skill): `{item_id, source_key, observed_missing_at_utc, action: "noted" | "redirected"}`. Tombstone schema is intentionally minimal in MVP — extend when real cases appear.

---

## Edge cases handled

- **Backfilled archives:** sources whose captured-IDs files were materialized by `_BACKFILL.py` (YouTube, podcast where original `_raw/listennotes_*.json` exists) are fully resumable. Sources where backfill couldn't reliably reconstruct captured state (websites, press_search, social_search) are marked `resumable: false` in the recipe with an explanatory note; this skill skips them with a clear message recommending `/content-research` to produce a fresh dated archive. NO runtime reconstruction by this skill — that's a hard policy.
- **Source migration (channel renamed, podcast moved):** check recipe.aliases[] before re-enumerating. If no alias defined and the original source ID/URL fails, prompt the user to add an alias to recipe.aliases[] manually, then retry.
- **Partial failure:** per-source state in MANIFEST means the update is restartable. If YouTube rate-limits mid-run, MANIFEST records the YouTube source as `interrupted_by: youtube-bot-challenge` but other sources complete normally.
- **Concurrent updates:** not supported in MVP — assume one update at a time per archive.

## Edge cases deferred to v1.1+

- **URL-stable content edits:** same URL, different content. MVP treats URL as identity. v1.1 may add content-hash diffing.
- **Backfilled old content discovery:** APIs sometimes surface older items not in original enumeration. MVP detects via set-diff anyway (any new ID = new item).
- **Cross-archive merging:** if a podcast moves from one entity to another, MVP doesn't handle. Manual recipe.aliases[] is the workaround.
- **Snapshot triggers:** when a parser change makes existing data incompatible, MVP doesn't auto-snapshot before continuing. Manual `cp -r {archive} {archive}-snapshot-DATE/` is the workaround.

---

## Usage examples

```bash
# Single archive
/content-update topics/Leadership/henry-cloud-research-2026-05-21/

# Topic-area wide
/content-update --topic-area=Leadership

# Trigger phrase (LLM parses)
"Update the henry cloud archive"
"Refresh Leadership topic"
"Pull any new content for John Kempf"
```

The CONVENTIONS.md Rule 12 contract underpins this skill. If the user has archives that predate v3.0.3 metadata, route them through `_BACKFILL.py` first.
