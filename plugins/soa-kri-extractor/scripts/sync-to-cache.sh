#!/usr/bin/env bash
# sync-to-cache.sh — Sync the soa-kri-extractor skill from skills-repo
# to the plugin cache so Claude Code loads the latest version at runtime.
set -euo pipefail

SKILL_NAME="soa-kri-extractor"
SRC_ROOT="$HOME/.claude/skills-repo/$SKILL_NAME"
CACHE_ROOT="$HOME/.claude/plugins/cache/espresso-skills/$SKILL_NAME/1.0.0/skills/$SKILL_NAME"
LOG_FILE="$HOME/.claude/logs/plugin-cache-sync.log"

if [ ! -d "$SRC_ROOT" ]; then
    echo "✗ sync-to-cache: source does not exist: $SRC_ROOT" >&2
    exit 1
fi

mkdir -p "$(dirname "$CACHE_ROOT")"
mkdir -p "$(dirname "$LOG_FILE")"

# Single-slot backup of the current cache (last known good)
if [ -d "$CACHE_ROOT" ]; then
    BACKUP="$CACHE_ROOT.previous"
    rm -rf "$BACKUP"
    cp -a "$CACHE_ROOT" "$BACKUP"
fi

# Mirror
rsync -a --delete "$SRC_ROOT/" "$CACHE_ROOT/"

COMMIT="no-git"
GIT_ROOT="$HOME/.claude/skills-repo"
if [ -d "$GIT_ROOT/.git" ]; then
    COMMIT=$(git -C "$GIT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "no-git")
fi

echo "$(date -Iseconds)  sync  $SKILL_NAME  @$COMMIT" >> "$LOG_FILE"
echo "✓ sync-to-cache: $SKILL_NAME synced to plugin cache (@$COMMIT)"
