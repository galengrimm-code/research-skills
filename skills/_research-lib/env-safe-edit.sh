#!/bin/bash
# Safe .env modification helper
# USAGE: bash ~/.claude/skills/_research-lib/env-safe-edit.sh
# Creates a timestamped backup of .env in .env-backups/
# REFUSES to back up an empty file (defense against earlier failure mode where
# a broken grep+mv chain destroyed .env then ran a "backup" of the empty result)
set -e

ENV_FILE="${1:-$HOME/.claude/skills/deep-research/.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE does not exist."
  echo "Cannot back up a file that isn't there. ABORTING."
  exit 1
fi

SIZE=$(wc -c < "$ENV_FILE")
if [ "$SIZE" -lt 100 ]; then
  echo "REFUSING TO BACK UP: $ENV_FILE is only $SIZE bytes."
  echo "Likely empty or broken. Aborting to prevent destroying a good backup with a bad one."
  echo ""
  echo "If you intentionally have a tiny .env, override with --force:"
  echo "  bash $0 $ENV_FILE --force"
  if [ "$2" != "--force" ]; then
    exit 1
  fi
fi

BAK_DIR="$(dirname "$ENV_FILE")/.env-backups"
mkdir -p "$BAK_DIR"

TS=$(date +%Y%m%d-%H%M%S)
DEST="$BAK_DIR/.env.bak.$TS"

cp "$ENV_FILE" "$DEST"
echo "Backed up: $DEST ($SIZE bytes)"

# Prune: keep last 10 backups
COUNT=$(ls -1 "$BAK_DIR"/.env.bak.* 2>/dev/null | wc -l)
if [ "$COUNT" -gt 10 ]; then
  ls -t "$BAK_DIR"/.env.bak.* | tail -n +11 | xargs -r rm
  echo "Pruned older backups (kept last 10)"
fi
