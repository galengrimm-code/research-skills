"""
YouTube transcript fetcher with three-tier fallback chain.

Tier 1: yt-dlp captions (primary — battle-tested, handles most cases)
Tier 2: youtube-transcript-api (different endpoint — survives bot challenges
        that block yt-dlp's caption fetch path)
Tier 3: Whisper transcription of audio (last resort — costly in time but
        works as long as audio can be downloaded; uses large-v3-turbo by
        default for speed/quality balance)

Each video is attempted at each tier in order. First success wins. Failures
are logged per-tier so resumability + diagnostics are clean.

Usage:
    from yt_transcript_fallback import fetch_transcript
    result = fetch_transcript(video_id, out_dir='02_youtube/transcripts',
                              whisper_model='large-v3-turbo')
    # result = {'status': 'ok'|'failed', 'tier': 1|2|3, 'path': str|None, 'error': str|None}

Or batch mode:
    from yt_transcript_fallback import fetch_batch
    results = fetch_batch(video_ids, out_dir='02_youtube/transcripts')
    # Returns list of result dicts in same order.

Install requirements (the skill bootstrap should ensure these):
    pip install --user yt-dlp youtube-transcript-api faster-whisper

Whisper on Windows additionally requires nvidia-cublas-cu12 + nvidia-cudnn-cu12
pip wheels AND the bootstrap script that prepends their bin/ dirs to PATH
before importing faster_whisper (see content-research SKILL.md "Wave C-bis"
for the boilerplate — same pattern applies here).
"""
import glob
import os
import re
import subprocess
import sys
import time

# Minimum transcript size (chars) below which we treat as failed —
# guards against silent corruption from empty/tiny captions across all tiers.
MIN_TRANSCRIPT_CHARS = 100


def _safe_filename(s, max_len=80):
    """Mirror yt-dlp's --restrict-filenames behavior for cross-tier filename consistency."""
    s = re.sub(r'[^A-Za-z0-9_-]+', '_', s).strip('_')
    return s[:max_len] or 'video'


def _vtt_to_txt(vtt_text):
    """Strip VTT metadata + timestamps + dedupe lines. Returns plain text."""
    out = []
    seen = set()
    for line in vtt_text.split('\n'):
        line = line.strip()
        if not line or line == 'WEBVTT' or line.startswith('Kind:') or line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        line = re.sub(r'<[^>]+>', '', line).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        out.append(line)
    return '\n'.join(out)


def _find_new_artifact(out_dir, video_id, extension, started_at):
    """Return path to an artifact file matching {video_id}.{extension} OR
    {video_id}_*.{extension} that was created/modified AFTER `started_at`.
    Avoids the stale-artifact false-positive where a leftover from a prior
    run gets misinterpreted as a current success.

    Matches BOTH naming patterns (with-suffix and without-suffix) because
    yt-dlp's output template can produce either depending on `-o` format —
    `{id}.{ext}` for our current `-o '%(id)s.%(ext)s'` invocation, or
    `{id}_{title}.{ext}` for legacy patterns. Globbing both keeps the helper
    robust across template changes.
    """
    candidates = []
    # Match three naming patterns:
    #   {id}.{ext}          — current yt-dlp output template (%(id)s.%(ext)s)
    #   {id}.*.{ext}        — language-tagged variants like {id}.en-US.vtt
    #   {id}_*.{ext}        — legacy template with title suffix
    patterns = [
        f'{video_id}.{extension}',
        f'{video_id}.*.{extension}',
        f'{video_id}_*.{extension}',
    ]
    for pat in patterns:
        for path in glob.glob(os.path.join(out_dir, pat)):
            try:
                mtime = os.path.getmtime(path)
                if mtime >= started_at - 1:  # 1s grace for filesystem timestamp granularity
                    candidates.append((mtime, path))
            except OSError:
                continue
    if not candidates:
        return None
    # If multiple match, pick the newest
    candidates.sort(reverse=True)
    return candidates[0][1]


def _output_path(out_dir, video_id, title_hint=None):
    """Compute the canonical .txt path for a video. Same across all three tiers.

    Convention: `{video_id}_{safe-title}.txt` if title_hint provided,
                `{video_id}.txt` otherwise.
    This guarantees cross-tier filename consistency — callers can trust that
    a captured-IDs file maps deterministically to filenames regardless of which
    tier produced the transcript.
    """
    if title_hint:
        return os.path.join(out_dir, f'{video_id}_{_safe_filename(title_hint)}.txt')
    return os.path.join(out_dir, f'{video_id}.txt')


def _tier1_ytdlp(video_id, out_dir, title_hint=None):
    """Try yt-dlp first. Returns (status, path, error).

    yt-dlp writes to {id}.vtt (no title in the yt-dlp output template). We rename
    after to match _output_path() — ensuring cross-tier filename consistency.
    """
    txt_path = _output_path(out_dir, video_id, title_hint)
    if os.path.exists(txt_path) and os.path.getsize(txt_path) > MIN_TRANSCRIPT_CHARS:
        return 'skipped', txt_path, 'already exists'

    url = f'https://www.youtube.com/watch?v={video_id}'
    started_at = time.time()
    try:
        result = subprocess.run(
            [sys.executable, '-m', 'yt_dlp',
             '--skip-download', '--write-auto-subs', '--write-subs',
             '--sub-lang', 'en', '--sub-format', 'vtt',
             # Use only {id} in output — keeps filename consistent across all 3 tiers
             '-o', '%(id)s.%(ext)s',
             '--ignore-errors',
             url],
            cwd=out_dir, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace',
        )
        # Find VTT created during THIS subprocess run (not a stale leftover)
        # With -o '%(id)s.%(ext)s', yt-dlp writes {id}.en.vtt
        vtt_path = _find_new_artifact(out_dir, video_id, 'en.vtt', started_at) \
                   or _find_new_artifact(out_dir, video_id, 'vtt', started_at)
        if not vtt_path:
            # Sometimes yt-dlp writes a partial/junk VTT before failing — clean up any
            # leftover from this run window so we don't pollute the output dir with
            # orphaned .vtt files from failed attempts. Matches both naming patterns.
            for pat in (f'{video_id}.*vtt', f'{video_id}_*vtt'):
                for orphan in glob.glob(os.path.join(out_dir, pat)):
                    try:
                        if os.path.getmtime(orphan) >= started_at - 1:
                            os.remove(orphan)
                    except OSError:
                        pass
            err_msg = (result.stderr or '').strip().split('\n')[-1] if result.stderr else 'no captions produced'
            return 'failed', None, f'yt-dlp: {err_msg[:200]}'
        vtt_text = open(vtt_path, encoding='utf-8', errors='replace').read()
        txt = _vtt_to_txt(vtt_text)
        if not txt or len(txt) < MIN_TRANSCRIPT_CHARS:
            os.remove(vtt_path)
            return 'failed', None, f'yt-dlp: captions too short ({len(txt)} chars < {MIN_TRANSCRIPT_CHARS})'
        open(txt_path, 'w', encoding='utf-8').write(txt)
        os.remove(vtt_path)
        return 'ok', txt_path, None
    except subprocess.TimeoutExpired:
        return 'failed', None, 'yt-dlp: timeout after 120s'
    except Exception as e:
        return 'failed', None, f'yt-dlp: {type(e).__name__}: {e}'


def _tier2_transcript_api(video_id, out_dir, title_hint=None, languages=('en',)):
    """Try youtube-transcript-api. Uses different endpoint than yt-dlp.

    languages: tuple of preferred language codes (default English only).
    Caller can pass ('en','en-US','en-GB') for English fallbacks, or ('en','es')
    for English-then-Spanish, etc.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return 'failed', None, 'youtube-transcript-api not installed (pip install youtube-transcript-api)'
    try:
        api = YouTubeTranscriptApi()
        # api.fetch supports a languages arg in newer versions
        try:
            snippets = api.fetch(video_id, languages=list(languages))
        except TypeError:
            # Older API doesn't support languages kwarg — fall back to default
            snippets = api.fetch(video_id)
        if not snippets:
            return 'failed', None, 'youtube-transcript-api: empty result'
        lines = []
        seen = set()
        for snip in snippets:
            t = snip.text.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            lines.append(t)
        txt = '\n'.join(lines)
        if len(txt) < MIN_TRANSCRIPT_CHARS:
            return 'failed', None, f'youtube-transcript-api: transcript too short ({len(txt)} chars < {MIN_TRANSCRIPT_CHARS})'
        txt_path = _output_path(out_dir, video_id, title_hint)
        open(txt_path, 'w', encoding='utf-8').write(txt)
        return 'ok', txt_path, None
    except Exception as e:
        return 'failed', None, f'youtube-transcript-api: {type(e).__name__}: {str(e)[:200]}'


def _tier3_whisper(video_id, out_dir, title_hint=None, whisper_model='large-v3-turbo'):
    """Last resort: download audio with yt-dlp + transcribe locally with Whisper.
    Slow but reliable when both caption sources fail.

    For batch mode, callers should hold the WhisperModel instance externally to
    avoid per-video model reloads — TODO: add a model_instance parameter."""
    url = f'https://www.youtube.com/watch?v={video_id}'
    audio_path = None  # so finally cleanup can guard correctly

    # Step 1: download audio. Use {id}.mp3 only (cross-tier filename consistency
    # is handled at the .txt level via _output_path).
    started_at = time.time()
    try:
        subprocess.run(
            [sys.executable, '-m', 'yt_dlp',
             '--extract-audio', '--audio-format', 'mp3',
             '-o', '%(id)s.%(ext)s',
             '--ignore-errors',
             url],
            cwd=out_dir, capture_output=True, text=True, timeout=300, encoding='utf-8', errors='replace',
        )
        audio_path = _find_new_artifact(out_dir, video_id, 'mp3', started_at)
        if not audio_path:
            return 'failed', None, 'whisper: audio download produced no mp3'
    except subprocess.TimeoutExpired:
        return 'failed', None, 'whisper: audio download timeout after 300s'

    # Step 2: transcribe. Wrap in try/finally so audio file gets cleaned up
    # even when Whisper transcription fails — otherwise large batch failures
    # accumulate gigabytes of orphan mp3s.
    try:
        # Set up CUDA DLL paths first (Windows-specific; matches the pattern in
        # content-research SKILL.md Wave C-bis)
        import site
        cuda_dirs = []
        for base in site.getsitepackages() + [site.getusersitepackages()]:
            for sub in ('cublas', 'cudnn', 'cuda_nvrtc'):
                d = os.path.join(base, 'nvidia', sub, 'bin')
                if os.path.isdir(d):
                    cuda_dirs.append(d)
                    os.add_dll_directory(d)
        os.environ['PATH'] = os.pathsep.join(cuda_dirs) + os.pathsep + os.environ.get('PATH', '')

        from faster_whisper import WhisperModel
        try:
            model = WhisperModel(whisper_model, device='cuda', compute_type='float16')
        except Exception:
            model = WhisperModel(whisper_model, device='cpu', compute_type='int8')

        segments, info = model.transcribe(audio_path, beam_size=5, language='en', vad_filter=True)
        txt = ' '.join(s.text.strip() for s in segments).strip().replace('. ', '.\n')
        if not txt or len(txt) < MIN_TRANSCRIPT_CHARS:
            return 'failed', None, f'whisper: transcript too short ({len(txt)} chars < {MIN_TRANSCRIPT_CHARS})'
        txt_path = _output_path(out_dir, video_id, title_hint)
        open(txt_path, 'w', encoding='utf-8').write(txt)
        return 'ok', txt_path, None
    except Exception as e:
        return 'failed', None, f'whisper: {type(e).__name__}: {str(e)[:200]}'
    finally:
        # Always remove the mp3 — transcripts are the load-bearing artifact and
        # the audio is just a transcription intermediate. Leaving mp3s around
        # consumes disk fast at scale.
        if audio_path and os.path.exists(audio_path):
            try:
                os.remove(audio_path)
            except OSError:
                pass  # don't fail the whole tier over cleanup


def fetch_transcript(video_id, out_dir, title_hint=None, whisper_model='large-v3-turbo',
                     allow_whisper=True, languages=('en',)):
    """Three-tier fallback. Returns dict with keys: video_id, status, tier, path,
    error, attempted_tiers, started_at, ended_at, duration_ms.

    status: 'ok' | 'skipped' | 'failed'
    tier:   1 | 2 | 3 (which tier succeeded) or None if all failed
    path:   absolute path to .txt or None
    error:  concatenated error messages from failed tiers (for logging)
    attempted_tiers: list of tier numbers actually invoked (1, 1-2, or 1-2-3)
    started_at: UTC ISO-8601 timestamp when this video's fetch began
    ended_at: same, when it finished (success or failure)
    duration_ms: total wall time

    Set allow_whisper=False to skip the costly tier 3 (useful for fast batch
    runs where you'd rather mark videos as no-captions than wait 1-5 min each).
    languages: passed to tier 2 (youtube-transcript-api).
    """
    os.makedirs(out_dir, exist_ok=True)
    errors = []
    attempted = []
    started = time.time()
    started_iso = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started))

    def _result(status, tier, path, error):
        ended = time.time()
        return {
            'video_id': video_id,
            'status': status,
            'tier': tier,
            'path': path,
            'error': error,
            'attempted_tiers': attempted,
            'started_at': started_iso,
            'ended_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ended)),
            'duration_ms': int((ended - started) * 1000),
        }

    # Tier 1
    attempted.append(1)
    status, path, err = _tier1_ytdlp(video_id, out_dir, title_hint)
    if status == 'ok':
        return _result('ok', 1, path, None)
    if status == 'skipped':
        return _result('skipped', 1, path, None)
    errors.append(err or 'yt-dlp unknown error')

    # Tier 2
    attempted.append(2)
    status, path, err = _tier2_transcript_api(video_id, out_dir, title_hint, languages=languages)
    if status == 'ok':
        return _result('ok', 2, path, None)
    errors.append(err or 'youtube-transcript-api unknown error')

    # Tier 3 (optional)
    if allow_whisper:
        attempted.append(3)
        status, path, err = _tier3_whisper(video_id, out_dir, title_hint, whisper_model)
        if status == 'ok':
            return _result('ok', 3, path, None)
        errors.append(err or 'whisper unknown error')

    return _result('failed', None, None, '; '.join(errors))


def fetch_batch(video_ids, out_dir, whisper_model='large-v3-turbo',
                allow_whisper=True, sleep_between=2.0, on_progress=None,
                languages=('en',), id_to_title=None):
    """Fetch transcripts for a batch of video IDs. Returns list of result dicts.
    Each dict includes video_id, status, tier, path, error, attempted_tiers,
    started_at, ended_at, duration_ms — enough info for callers to construct
    v3.0.3-schema-compliant update_history entries without correlation logic.

    sleep_between: seconds between videos at tier 1+2 to avoid rate limits
    on_progress: optional callable(i, total, result) for live progress reporting
    languages: passed to tier 2
    id_to_title: optional dict mapping video_id -> title (string). When provided,
                 transcripts are saved as {id}_{safe-title}.txt for human browsing.
                 When None, transcripts are saved as {id}.txt — consistent across
                 all three tiers regardless of which one produced the file.
    """
    results = []
    total = len(video_ids)
    for i, vid in enumerate(video_ids, 1):
        title = (id_to_title or {}).get(vid)
        result = fetch_transcript(vid, out_dir, title_hint=title,
                                  whisper_model=whisper_model,
                                  allow_whisper=allow_whisper, languages=languages)
        results.append(result)
        if on_progress:
            on_progress(i, total, result)
        time.sleep(sleep_between)
    return results


if __name__ == '__main__':
    # Smoke test
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    test_id = sys.argv[1] if len(sys.argv) > 1 else 'A08ZQO9GMSI'  # known captioned video
    out = sys.argv[2] if len(sys.argv) > 2 else '/tmp/yt_test'
    print(f'Testing {test_id} -> {out}')
    r = fetch_transcript(test_id, out, allow_whisper=False)
    print(f'Result: {r}')
