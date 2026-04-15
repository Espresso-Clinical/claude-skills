#!/usr/bin/env bash
# sync-to-cache.sh — Sync the protocol-kri-extractor skill from skills-repo
# to the plugin cache so that Claude Code actually loads the latest version
# at runtime.
#
# Why this exists:
#   Claude Code loads the skill from ~/.claude/plugins/cache/<plugin>/<version>/
#   at runtime, NOT from ~/.claude/skills-repo/. Without syncing, edits to the
#   skills-repo never take effect when the skill runs.
#
# Invocation — three ways:
#   1. Manually:
#        ~/.claude/skills-repo/protocol-kri-extractor/scripts/sync-to-cache.sh
#   2. Automatically via git hooks (see install-hooks.sh)
#   3. From another script (returns non-zero on failure)
#
# Behavior:
#   - rsync --delete from skills-repo → plugin cache (mirror exactly)
#   - Back up the previous cache to .previous before overwriting
#   - Append a line to ~/.claude/logs/plugin-cache-sync.log
#   - Never fail silently: exits non-zero if the source is missing

set -euo pipefail

SKILL_NAME="protocol-kri-extractor"
SRC_ROOT="$HOME/.claude/skills-repo/$SKILL_NAME"
CACHE_ROOT="$HOME/.claude/plugins/cache/espresso-skills/$SKILL_NAME/1.0.0/skills/$SKILL_NAME"
LOG_FILE="$HOME/.claude/logs/plugin-cache-sync.log"

if [ ! -d "$SRC_ROOT" ]; then
    echo "✗ sync-to-cache: source does not exist: $SRC_ROOT" >&2
    exit 1
fi

# Make sure the cache parent dir exists
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

# Get current git commit for the log line (if we're in a git repo)
COMMIT="no-git"
GIT_ROOT="$HOME/.claude/skills-repo"
if [ -d "$GIT_ROOT/.git" ]; then
    COMMIT=$(git -C "$GIT_ROOT" rev-parse --short HEAD 2>/dev/null || echo "no-git")
fi

echo "$(date -Iseconds)  sync  $SKILL_NAME  @$COMMIT" >> "$LOG_FILE"

echo "✓ sync-to-cache: $SKILL_NAME synced to plugin cache (@$COMMIT)"
