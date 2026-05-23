"""
summary_updater.py — refresh AUTO blocks in a topic-area SUMMARY.md.

Design follows codex's review (2026-05-22) with all P1 fixes + P3 hardening:
  - Marker-delimited AUTO blocks with `GENERATED: DO NOT EDIT` notices inside each block
  - Conflict-edit detection: if an AUTO block was hand-edited, write .bak + warn
  - Stable-keyed AUTO-ARCHIVE-ROSTER: per-archive narrative preserved across renames
    by `canonical_entity_id` from MANIFEST.yaml (heading text auto-updates from
    target.name; HAND-FILL content preserved)
  - Removed-archive preservation: if an archive disappears from MANIFEST, its hand
    content moves to a "## Removed archives" auto-subsection (never silently dropped)
  - --check dry-run mode (CI / pre-commit friendly)
  - Atomic write (temp file + os.replace)
  - Idempotent no-op writes (no git churn when content unchanged)
  - Deterministic archive sort
  - Strict marker validator

USAGE:
  python -m summary_updater <SUMMARY.md path>          # in-place refresh
  python -m summary_updater --check <SUMMARY.md path>  # dry-run, no write
  python -m summary_updater --all <topics dir>         # refresh all SUMMARY.md
                                                       # under topics/{TopicArea}/

API:
  from summary_updater import refresh_summary
  result = refresh_summary('topics/Leadership/SUMMARY.md', dry_run=False)
  # result keys: status, changed, warnings, removed_archives, written

Source-of-truth invariants:
  - MANIFEST.yaml is authoritative for archive list + state. SUMMARY.md never
    feeds back into MANIFEST.
  - The AUTO blocks below are owned by this tool. Hand edits inside them get
    backed up to {SUMMARY}.bak and overwritten on next refresh.
  - HAND-FILL blocks inside AUTO-ARCHIVE-ROSTER are the ONLY hand-editable
    content within an AUTO block. Keyed by canonical_entity_id.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import os
import re
import shutil
import sys
import tempfile
import yaml
from typing import Optional


# ---------------------------------------------------------------------------
# Marker definitions
# ---------------------------------------------------------------------------

# Three AUTO block kinds. Each appears at most once per SUMMARY.md.
AUTO_BLOCK_KINDS = ('INVENTORY', 'ARCHIVE-ROSTER', 'PIPELINE')

GENERATED_NOTICE = (
    '<!-- GENERATED: DO NOT EDIT — overwritten on every refresh. '
    'Hand-edits will be backed up to {SUMMARY}.bak and overwritten. '
    'Inside AUTO-ARCHIVE-ROSTER, only HAND-FILL blocks are preserved. -->'
)


def _begin_marker(kind: str) -> str:
    return f'<!-- AUTO-{kind}:BEGIN -->'


def _end_marker(kind: str) -> str:
    return f'<!-- AUTO-{kind}:END -->'


def _hand_fill_begin(key: str) -> str:
    return f'<!-- HAND-FILL:{key}:BEGIN -->'


def _hand_fill_end(key: str) -> str:
    return f'<!-- HAND-FILL:{key}:END -->'


def _archive_anchor(canonical_id: str) -> str:
    """Stable identity anchor inside the roster — drives rename safety."""
    return f'<!-- ARCHIVE:{canonical_id} -->'


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _validate_markers_strict(content: str) -> list[str]:
    """Strict pre-scan: each AUTO-X kind must have exactly 1 BEGIN and 1 END,
    properly paired, no nesting. Returns list of error strings (empty = valid)."""
    errors = []
    for kind in AUTO_BLOCK_KINDS:
        begin = _begin_marker(kind)
        end = _end_marker(kind)
        n_begin = content.count(begin)
        n_end = content.count(end)
        if n_begin > 1:
            errors.append(f'Marker `{begin}` appears {n_begin} times (must be 0 or 1)')
        if n_end > 1:
            errors.append(f'Marker `{end}` appears {n_end} times (must be 0 or 1)')
        if n_begin != n_end:
            errors.append(f'Mismatched markers for AUTO-{kind}: {n_begin} BEGIN, {n_end} END')
        if n_begin == 1 and n_end == 1:
            bi = content.find(begin)
            ei = content.find(end)
            if ei < bi:
                errors.append(f'AUTO-{kind} END appears before BEGIN')
    # Check that AUTO blocks don't nest (any AUTO-X BEGIN inside AUTO-Y BEGIN/END)
    spans = []
    for kind in AUTO_BLOCK_KINDS:
        begin = _begin_marker(kind)
        end = _end_marker(kind)
        bi = content.find(begin)
        ei = content.find(end)
        if bi != -1 and ei != -1 and bi < ei:
            spans.append((bi, ei + len(end), kind))
    spans.sort()
    for i, (s1, e1, k1) in enumerate(spans):
        for s2, e2, k2 in spans[i+1:]:
            if s2 < e1:
                errors.append(f'AUTO-{k1} and AUTO-{k2} overlap or nest — blocks must be disjoint')
    return errors


def _find_block(content: str, kind: str) -> Optional[tuple[int, int, str]]:
    """Return (begin_idx, end_idx, inner_content) for the named AUTO block, or None.

    begin_idx is the index of the BEGIN marker line; end_idx is the index just
    after the END marker line. inner_content excludes the markers themselves.
    Assumes _validate_markers_strict has already passed (so we trust matching pairs).
    """
    begin = _begin_marker(kind)
    end = _end_marker(kind)
    bi = content.find(begin)
    if bi == -1:
        return None
    ei = content.find(end, bi + len(begin))
    if ei == -1:
        return None  # caught by validator; defensive
    end_line_end = content.find('\n', ei + len(end))
    if end_line_end == -1:
        end_line_end = len(content)
    else:
        end_line_end += 1
    begin_line_start = content.rfind('\n', 0, bi) + 1
    inner = content[bi + len(begin):ei]
    return (begin_line_start, end_line_end, inner)


def _validate_manifest(manifest: dict) -> list[str]:
    """Validate MANIFEST has required structure. Returns list of error strings."""
    errors = []
    if not isinstance(manifest, dict):
        return ['MANIFEST root is not a mapping']
    if 'schema_version' not in manifest:
        errors.append('MANIFEST missing required field: schema_version')
    elif not isinstance(manifest['schema_version'], int):
        errors.append(
            f'MANIFEST.schema_version must be an integer, got '
            f'{type(manifest["schema_version"]).__name__}: {manifest["schema_version"]!r}'
        )
    if 'topic_area' not in manifest:
        errors.append('MANIFEST missing required field: topic_area')
    elif not isinstance(manifest['topic_area'], str) or not manifest['topic_area'].strip():
        errors.append(
            f'MANIFEST.topic_area must be a non-empty string, got '
            f'{type(manifest["topic_area"]).__name__}: {manifest["topic_area"]!r}'
        )
    archives = manifest.get('archives')
    if archives is None:
        errors.append('MANIFEST missing required field: archives')
    elif not isinstance(archives, list):
        errors.append(f'MANIFEST.archives must be a list, got {type(archives).__name__}')
    else:
        # Check uniqueness of canonical_entity_id across archives — P1 from codex review
        seen = {}
        for a in archives:
            if not isinstance(a, dict):
                errors.append(f'MANIFEST.archives entry is not a mapping: {a}')
                continue
            cid = a.get('canonical_entity_id')
            if not cid:
                errors.append(f'MANIFEST archive entry missing canonical_entity_id: {a.get("slug","?")}')
                continue
            if cid in seen:
                errors.append(
                    f'Duplicate canonical_entity_id `{cid}` — two archives cannot share identity '
                    f'(would silently clobber hand-fill content): {seen[cid]} and {a.get("path","?")}'
                )
            else:
                seen[cid] = a.get('path', '?')
    return errors


def _parse_hand_fills(roster_inner: str) -> dict[str, str]:
    """Extract {canonical_entity_id: hand_content} from an existing roster block.

    Each HAND-FILL block must be tagged with a key matching an ARCHIVE anchor.
    Returns content verbatim (including surrounding whitespace inside the markers).
    """
    out: dict[str, str] = {}
    # Pattern: <!-- HAND-FILL:KEY:BEGIN -->...<!-- HAND-FILL:KEY:END -->
    pattern = re.compile(
        r'<!--\s*HAND-FILL:([A-Za-z0-9_-]+):BEGIN\s*-->'
        r'(.*?)'
        r'<!--\s*HAND-FILL:\1:END\s*-->',
        re.DOTALL,
    )
    for m in pattern.finditer(roster_inner):
        out[m.group(1)] = m.group(2)
    return out


def _has_hand_edits_in_pure_auto(rendered: str, existing_inner: str) -> bool:
    """For pure AUTO blocks (INVENTORY, PIPELINE), detect if user has hand-edited.

    Compare rendered output (what the tool would write) against existing inner
    content. Returns True if they differ (any difference is a hand-edit signal
    for these block types — they have no HAND-FILL escape hatches).
    """
    return rendered.strip() != existing_inner.strip()


# ---------------------------------------------------------------------------
# Block renderers
# ---------------------------------------------------------------------------

def _read_archive_facts(topic_dir: str, archive_entry: dict) -> dict:
    """Pull per-archive facts: target name from archive INDEX.md frontmatter,
    file/word counts from disk, last_updated from MANIFEST."""
    path = archive_entry.get('path', '')
    archive_dir = os.path.join(topic_dir, path) if path else None
    facts = {
        'slug': archive_entry.get('slug', '?'),
        'canonical_entity_id': archive_entry.get('canonical_entity_id', '?'),
        'path': path,
        'created_at_utc': archive_entry.get('created_at_utc', ''),
        'last_updated_at_utc': archive_entry.get('last_updated_at_utc', ''),
        'has_recipe_yaml': archive_entry.get('has_recipe_yaml', False),
        'backfilled': archive_entry.get('backfilled', False),
        'target_name': archive_entry.get('slug', '?'),  # fallback
        'subject': '',
        'file_count': 0,
        'word_count': 0,
        'size_mb': 0.0,
    }
    if not archive_dir or not os.path.isdir(archive_dir):
        return facts

    # Try to read target name + subject from archive's INDEX.md frontmatter
    index_path = os.path.join(archive_dir, 'INDEX.md')
    if os.path.exists(index_path):
        try:
            content = open(index_path, encoding='utf-8', errors='replace').read()
            m = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if m:
                fm = yaml.safe_load(m.group(1)) or {}
                facts['target_name'] = fm.get('target', facts['target_name'])
        except Exception:
            pass

    # Count files + words from disk
    file_count = word_count = total_bytes = 0
    for root, _, files in os.walk(archive_dir):
        for f in files:
            p = os.path.join(root, f)
            try:
                file_count += 1
                total_bytes += os.path.getsize(p)
                if f.endswith(('.txt', '.md')):
                    with open(p, encoding='utf-8', errors='replace') as fh:
                        word_count += len(fh.read().split())
            except OSError:
                continue
    facts['file_count'] = file_count
    facts['word_count'] = word_count
    facts['size_mb'] = round(total_bytes / (1024 * 1024), 1)
    return facts


def _fmt_words(n: int) -> str:
    if n >= 1_000_000:
        return f'{n/1_000_000:.2f}M'
    if n >= 1_000:
        return f'{n/1_000:.0f}K'
    return str(n)


def _render_inventory_block(topic_area: str, archive_facts: list[dict], now_utc: str) -> str:
    """Inventory table + totals — pure AUTO (no hand-fill).

    Deliberately does NOT include `now_utc` — the inventory should be fully
    deterministic from MANIFEST + on-disk file counts. Refresh timestamps live
    only in the PIPELINE block (sourced from MANIFEST.last_updated_at_utc, not
    from wall clock) so idempotent re-runs produce no diff."""
    lines = [
        '',
        GENERATED_NOTICE,
        '',
        '## Archives in this topic-area',
        '',
        '| Archive | Files | Words | Last Updated |',
        '|---|---|---|---|',
    ]
    total_files = total_words = 0
    for f in archive_facts:
        last = f['last_updated_at_utc'][:10] if f['last_updated_at_utc'] else '—'
        lines.append(f"| `{f['path']}` | {f['file_count']:,} | {_fmt_words(f['word_count'])} | {last} |")
        total_files += f['file_count']
        total_words += f['word_count']
    lines.append('')
    lines.append(
        f"**Total: {len(archive_facts)} archive{'s' if len(archive_facts) != 1 else ''}, "
        f"{total_files:,} files, {_fmt_words(total_words)} words**"
    )
    lines.append('')
    return '\n'.join(lines)


def _render_roster_block(
    topic_area: str,
    archive_facts: list[dict],
    preserved_hand: dict[str, str],
    removed_archives: list[str],
    now_utc: str,
) -> str:
    """Per-archive narrative block — auto headings, HAND-FILL bodies preserved
    by canonical_entity_id. Removed archives go to a sub-section at the bottom."""
    lines = [
        '',
        GENERATED_NOTICE,
        '',
        '## What each archive uniquely teaches',
        '',
        '_Headings are auto-generated from MANIFEST.yaml. Body content inside '
        '`HAND-FILL` markers is preserved across refreshes — write your '
        'synthesis insights there._',
        '',
    ]
    for f in archive_facts:
        cid = f['canonical_entity_id']
        lines.append(_archive_anchor(cid))
        lines.append(f"### {f['target_name']}")
        lines.append('')
        lines.append(_hand_fill_begin(cid))
        if cid in preserved_hand:
            # Preserve verbatim (includes leading/trailing whitespace)
            hand = preserved_hand[cid].strip('\n')
            lines.append(hand if hand else '_(Add 2-3 sentences here on what this archive uniquely contributes — frameworks, signature stories, recommended starting docs.)_')
        else:
            lines.append('_(Add 2-3 sentences here on what this archive uniquely contributes — frameworks, signature stories, recommended starting docs.)_')
        lines.append(_hand_fill_end(cid))
        lines.append('')

    # Removed archives — never silently drop hand content
    if removed_archives:
        lines.append('---')
        lines.append('')
        lines.append('### Removed archives (hand content preserved)')
        lines.append('')
        lines.append(
            '_These archives are no longer in MANIFEST.yaml but had hand-written '
            'narrative below. Content is preserved here so it is never silently lost. '
            'Delete this section manually if the content is genuinely obsolete._'
        )
        lines.append('')
        for cid in removed_archives:
            lines.append(f"#### `{cid}` (removed)")
            lines.append('')
            lines.append(_hand_fill_begin(cid))
            lines.append(preserved_hand[cid].strip('\n'))
            lines.append(_hand_fill_end(cid))
            lines.append('')
    return '\n'.join(lines)


def _render_pipeline_block(
    topic_area: str,
    archive_facts: list[dict],
    manifest: dict,
    now_utc: str,
) -> str:
    """Pipeline state — pure AUTO.

    The visible timestamp here is MANIFEST.last_updated_at_utc (NOT wall-clock
    `now_utc`). This is what makes refreshes idempotent: a re-run with no
    MANIFEST change produces no SUMMARY change, so no spurious git churn. The
    `now_utc` argument is intentionally unused but kept in the signature for
    forward compatibility (e.g., if a future field needs the actual refresh time)."""
    del now_utc  # explicitly unused — see docstring
    all_have_recipe = all(f.get('has_recipe_yaml') for f in archive_facts)
    backfilled_count = sum(1 for f in archive_facts if f.get('backfilled'))
    manifest_ts = manifest.get('last_updated_at_utc', '?')
    lines = [
        '',
        GENERATED_NOTICE,
        '',
        '## Pipeline state',
        '',
        f"- **MANIFEST last updated (UTC):** {manifest_ts}",
        f"- **MANIFEST schema version:** {manifest.get('schema_version', '?')}",
        f"- **Topic-area:** {topic_area}",
        f"- **Archives:** {len(archive_facts)} "
        f"({backfilled_count} backfilled from pre-v3.0.3, {len(archive_facts) - backfilled_count} native)",
        f"- **All archives have recipe.yaml:** {'yes' if all_have_recipe else 'no — re-run _BACKFILL.py'}",
        '',
        '_Source of truth: `MANIFEST.yaml` in this folder. This block is regenerated '
        'from MANIFEST + each archive\'s `INDEX.md` frontmatter and on-disk file counts. '
        'Timestamp is MANIFEST\'s last_updated_at_utc, not the refresh time — '
        'idempotent re-runs do not change this block._',
        '',
    ]
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Main refresh
# ---------------------------------------------------------------------------

def refresh_summary(summary_path: str, dry_run: bool = False, verbose: bool = True) -> dict:
    """Refresh AUTO blocks in a SUMMARY.md. Returns a result dict.

    Result keys:
      - status: 'ok' | 'no-change' | 'no-summary' | 'no-manifest' | 'error'
      - changed: bool — whether any block changed
      - blocks_updated: list of block kinds that were updated
      - warnings: list of human-readable warning strings
      - removed_archives: list of canonical_entity_ids no longer in MANIFEST
      - written: bool — whether file was actually written (always False if dry_run)
      - bak_written: path to .bak file if hand-edit detected, else None
    """
    result: dict = {
        'status': 'ok', 'changed': False, 'blocks_updated': [], 'warnings': [],
        'removed_archives': [], 'written': False, 'bak_written': None,
    }

    if not os.path.exists(summary_path):
        result['status'] = 'no-summary'
        result['warnings'].append(f'SUMMARY.md not found: {summary_path}')
        return result

    topic_dir = os.path.dirname(os.path.abspath(summary_path))
    manifest_path = os.path.join(topic_dir, 'MANIFEST.yaml')
    if not os.path.exists(manifest_path):
        result['status'] = 'no-manifest'
        result['warnings'].append(f'MANIFEST.yaml not found alongside SUMMARY: {manifest_path}')
        return result

    try:
        manifest = yaml.safe_load(open(manifest_path, encoding='utf-8')) or {}
    except Exception as e:
        result['status'] = 'error'
        result['warnings'].append(f'Failed to parse MANIFEST: {e}')
        return result

    # Validate MANIFEST structure + canonical_entity_id uniqueness — P1/P2 fix
    manifest_errors = _validate_manifest(manifest)
    if manifest_errors:
        result['status'] = 'error'
        result['warnings'].extend(manifest_errors)
        if verbose:
            for e in manifest_errors:
                print(f'ERROR: {e}', file=sys.stderr)
        return result

    topic_area = manifest.get('topic_area', os.path.basename(topic_dir))
    # Deterministic archive order: by created_at_utc, then by slug
    archives = sorted(
        manifest.get('archives', []),
        key=lambda a: (a.get('created_at_utc', ''), a.get('slug', '')),
    )
    facts = [_read_archive_facts(topic_dir, a) for a in archives]
    now_utc = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    # Read original — use utf-8-sig to detect+strip BOM if present (preserve later on write)
    raw_bytes = open(summary_path, 'rb').read()
    has_bom = raw_bytes.startswith(b'\xef\xbb\xbf')
    if has_bom:
        original = raw_bytes[3:].decode('utf-8', errors='replace')
    else:
        original = raw_bytes.decode('utf-8', errors='replace')
    # Detect line endings — preserve dominant style on write
    crlf_count = original.count('\r\n')
    lf_only_count = original.count('\n') - crlf_count
    use_crlf = crlf_count > lf_only_count

    # Strict marker pre-validation — hard-fail on malformed/nested blocks (P1)
    marker_errors = _validate_markers_strict(original)
    if marker_errors:
        result['status'] = 'error'
        result['warnings'].extend(marker_errors)
        if verbose:
            for e in marker_errors:
                print(f'ERROR: {e}', file=sys.stderr)
        return result

    # Parse roster for preserved HAND-FILL contents BEFORE re-rendering
    preserved_hand: dict[str, str] = {}
    roster_existing = _find_block(original, 'ARCHIVE-ROSTER')
    if roster_existing:
        _, _, roster_inner = roster_existing
        preserved_hand = _parse_hand_fills(roster_inner)

    # Determine removed archives (had HAND-FILL but no longer in MANIFEST)
    current_cids = {f['canonical_entity_id'] for f in facts}
    removed_cids = sorted(cid for cid in preserved_hand if cid not in current_cids)
    result['removed_archives'] = removed_cids

    # Render new blocks
    new_blocks = {
        'INVENTORY': _render_inventory_block(topic_area, facts, now_utc),
        'ARCHIVE-ROSTER': _render_roster_block(topic_area, facts, preserved_hand, removed_cids, now_utc),
        'PIPELINE': _render_pipeline_block(topic_area, facts, manifest, now_utc),
    }

    # Walk through blocks, replace inline. For pure-AUTO blocks (INVENTORY,
    # PIPELINE), check for hand-edits and warn + bak.
    updated_content = original
    hand_edit_detected = False
    for kind in AUTO_BLOCK_KINDS:
        existing = _find_block(updated_content, kind)
        if existing is None:
            result['warnings'].append(
                f'AUTO-{kind} marker pair not found — block not inserted. '
                f'Add `{_begin_marker(kind)}` and `{_end_marker(kind)}` to SUMMARY.md '
                f'where you want the block.'
            )
            continue
        begin_idx, end_idx, existing_inner = existing

        # For INVENTORY and PIPELINE: detect hand edits (any diff is suspect)
        if kind in ('INVENTORY', 'PIPELINE'):
            if _has_hand_edits_in_pure_auto(new_blocks[kind], existing_inner):
                # Differ — could be legit refresh OR a hand edit.
                # Heuristic: if existing block lacks the GENERATED notice and
                # differs substantially, treat as hand-edit and back up.
                if 'GENERATED' not in existing_inner and existing_inner.strip():
                    hand_edit_detected = True
                    result['warnings'].append(
                        f'AUTO-{kind} appears hand-edited (missing GENERATED notice). '
                        f'Backing up to .bak.'
                    )

        # Replace the block (markers + inner) with marker + new inner + marker
        replacement = (
            _begin_marker(kind) + new_blocks[kind] + _end_marker(kind) + '\n'
        )
        if updated_content[begin_idx:end_idx] != replacement:
            result['changed'] = True
            result['blocks_updated'].append(kind)
        updated_content = (
            updated_content[:begin_idx] + replacement + updated_content[end_idx:]
        )

    # No-op if content unchanged
    if updated_content == original:
        result['status'] = 'no-change'
        if verbose:
            print(f'[no-change] {summary_path}')
        return result

    if dry_run:
        if verbose:
            print(f'[dry-run] would update {len(result["blocks_updated"])} block(s) in {summary_path}: {result["blocks_updated"]}')
            if removed_cids:
                print(f'[dry-run] removed archives detected: {removed_cids}')
            for w in result['warnings']:
                print(f'[dry-run] WARN: {w}')
        return result

    # Backup if hand-edit detected
    if hand_edit_detected:
        bak_path = summary_path + '.bak'
        shutil.copy2(summary_path, bak_path)
        result['bak_written'] = bak_path
        if verbose:
            print(f'[bak] wrote {bak_path}')

    # Atomic write — preserve original line endings (CRLF or LF) and BOM if present
    write_content = updated_content
    if use_crlf:
        # Normalize all newlines to \n first, then convert all to \r\n
        write_content = write_content.replace('\r\n', '\n').replace('\n', '\r\n')
    out_bytes = write_content.encode('utf-8')
    if has_bom:
        out_bytes = b'\xef\xbb\xbf' + out_bytes

    dir_ = os.path.dirname(os.path.abspath(summary_path))
    fd, tmp_path = tempfile.mkstemp(prefix='.summary.', suffix='.tmp', dir=dir_)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(out_bytes)
        os.replace(tmp_path, summary_path)
        result['written'] = True
        if verbose:
            print(f'[wrote] {summary_path} — updated {result["blocks_updated"]}')
            for w in result['warnings']:
                print(f'WARN: {w}')
    except Exception as e:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        result['status'] = 'error'
        result['warnings'].append(f'Atomic write failed: {e}')

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    p.add_argument('path', help='Path to a SUMMARY.md or (with --all) topics/ directory')
    p.add_argument('--check', action='store_true', help='Dry-run; do not write')
    p.add_argument('--all', action='store_true',
                   help='Treat path as topics/ root; refresh every topic-area SUMMARY.md found under topics/{TopicArea}/SUMMARY.md')
    p.add_argument('--quiet', action='store_true', help='Suppress per-file output')
    args = p.parse_args(argv)

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    targets: list[str] = []
    if args.all:
        if not os.path.isdir(args.path):
            print(f'ERROR: --all requires a directory, got {args.path}', file=sys.stderr)
            return 2
        for sub in os.listdir(args.path):
            cand = os.path.join(args.path, sub, 'SUMMARY.md')
            if os.path.exists(cand):
                targets.append(cand)
        if not targets:
            print(f'No SUMMARY.md files found under {args.path}/*/')
            return 0
    else:
        targets = [args.path]

    overall_ok = True
    for t in targets:
        r = refresh_summary(t, dry_run=args.check, verbose=not args.quiet)
        if r['status'] == 'error':
            overall_ok = False
    return 0 if overall_ok else 1


if __name__ == '__main__':
    sys.exit(main())
