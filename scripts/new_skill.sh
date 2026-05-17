#!/usr/bin/env bash
# Scaffold a new skill in this repo.
#
# Usage:  scripts/new_skill.sh <skill-name> [version]
#
# Creates:
#   plugins/<name>/.claude-plugin/plugin.json
#   plugins/<name>/skills/<name>/SKILL.md
#   plugins/<name>/{scripts,references}/
# Registers in:
#   .claude-plugin/marketplace.json
#   ~/.claude/plugins/installed_plugins.json
# Creates symlink:
#   ~/.claude/plugins/cache/espresso-skills/<name>/<version>/ → plugins/<name>/

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "Usage: $0 <skill-name> [version]" >&2
  exit 1
fi

NAME="$1"
VERSION="${2:-1.0.0}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLUGIN_DIR="$REPO_ROOT/plugins/$NAME"
CACHE_DIR="$HOME/.claude/plugins/cache/espresso-skills/$NAME/$VERSION"

if [ -e "$PLUGIN_DIR" ]; then
  echo "✗ $PLUGIN_DIR already exists" >&2
  exit 1
fi

# 1. directory scaffold
mkdir -p "$PLUGIN_DIR/.claude-plugin" "$PLUGIN_DIR/skills/$NAME" "$PLUGIN_DIR/scripts" "$PLUGIN_DIR/references"

# 2. plugin.json
cat > "$PLUGIN_DIR/.claude-plugin/plugin.json" <<EOF
{
  "name": "$NAME",
  "version": "$VERSION",
  "description": "TODO: one-line description",
  "author": {
    "name": "Espresso Clinical",
    "email": "eng@espressoclinical.com"
  },
  "license": "UNLICENSED",
  "keywords": ["clinical", "espresso"]
}
EOF

# 3. SKILL.md stub
cat > "$PLUGIN_DIR/skills/$NAME/SKILL.md" <<EOF
---
name: $NAME
description: >
  TODO: describe what this skill does, when to use it, and any required inputs.
  Be specific — this description is how Claude Code decides when to invoke it.
---

# $NAME

TODO: skill body.
EOF

# 4. register in marketplace.json
python3 - "$REPO_ROOT" "$NAME" "$VERSION" <<'PY'
import json, sys
repo, name, version = sys.argv[1], sys.argv[2], sys.argv[3]
mpath = f"{repo}/.claude-plugin/marketplace.json"
with open(mpath) as f:
    data = json.load(f)
if any(p["name"] == name for p in data["plugins"]):
    sys.exit(f"✗ {name} already in marketplace.json")
data["plugins"].append({
    "name": name,
    "description": "TODO: one-line description",
    "version": version,
    "author": {"name": "Espresso Clinical"},
    "source": f"./plugins/{name}",
    "category": "clinical",
    "keywords": ["clinical", "espresso"],
})
with open(mpath, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

# 5. cache symlink
mkdir -p "$(dirname "$CACHE_DIR")"
ln -s "$PLUGIN_DIR" "$CACHE_DIR"

# 6. register in installed_plugins.json + enable in settings.json
python3 - "$NAME" "$VERSION" "$CACHE_DIR" <<'PY'
import json, os, sys
from datetime import datetime, timezone
name, version, cache_dir = sys.argv[1], sys.argv[2], sys.argv[3]
home = os.path.expanduser("~")
now = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

# installed_plugins.json
ipath = f"{home}/.claude/plugins/installed_plugins.json"
with open(ipath) as f:
    ip = json.load(f)
ip.setdefault("plugins", {})[f"{name}@espresso-skills"] = [{
    "scope": "user",
    "installPath": cache_dir,
    "version": version,
    "installedAt": now,
    "lastUpdated": now,
    "gitCommitSha": "local",
}]
with open(ipath, "w") as f:
    json.dump(ip, f, indent=2); f.write("\n")

# settings.json — enabledPlugins
spath = f"{home}/.claude/settings.json"
with open(spath) as f:
    s = json.load(f)
s.setdefault("enabledPlugins", {})[f"{name}@espresso-skills"] = True
with open(spath, "w") as f:
    json.dump(s, f, indent=2); f.write("\n")
PY

echo "✓ created plugins/$NAME/ (version $VERSION)"
echo "✓ registered in marketplace.json + installed_plugins.json"
echo "✓ symlinked cache: $CACHE_DIR → $PLUGIN_DIR"
echo
echo "Next:"
echo "  1. Edit plugins/$NAME/skills/$NAME/SKILL.md"
echo "  2. Fill in the description in plugins/$NAME/.claude-plugin/plugin.json and marketplace.json"
echo "  3. Restart Claude Code so the new skill is discovered"
