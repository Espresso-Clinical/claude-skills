# skills-repo — conventions

Working notes for anyone (human or agent) editing this repo.

## Layout

Every skill lives at exactly one place: `plugins/<name>/`. The structure inside is:

```
plugins/<name>/
├── .claude-plugin/plugin.json     # plugin manifest (required)
├── skills/<name>/SKILL.md         # skill body (required)
├── scripts/                       # python/shell helpers
├── references/                    # markdown reference material
└── README.md                      # optional, plugin overview
```

**Do not create skill directories at the repo root.** Drift between root and `plugins/` is what motivated this cleanup — don't bring it back.

## How edits reach Claude Code

Each installed plugin has a cache directory at
`~/.claude/plugins/cache/espresso-skills/<name>/<version>/` which is a **symlink** pointing back at this repo's `plugins/<name>/`. That means any edit you save here is visible to Claude Code immediately — **no commit, no sync script, no re-install**.

If a symlink ever gets clobbered (e.g. by `/plugin update`), restore it with:

```bash
ln -sfn ~/.claude/skills-repo/plugins/<name> \
        ~/.claude/plugins/cache/espresso-skills/<name>/<version>
```

## Creating a new skill

Use the scaffolder — it creates the dir tree, writes a plugin.json stub, registers in `marketplace.json` and `installed_plugins.json`, and creates the cache symlink in one shot:

```bash
scripts/new_skill.sh <skill-name>
```

Then edit `plugins/<name>/skills/<name>/SKILL.md` and the description in `plugin.json` / `marketplace.json`. Restart Claude Code to pick up the new skill.

## Registration files (do not edit by hand unless you know why)

A plugin needs **three** things to show up in `/`:

1. **Declared** in `.claude-plugin/marketplace.json` (the marketplace's `plugins[]` array)
2. **Installed** in `~/.claude/plugins/installed_plugins.json` (with a valid `installPath` — which for us is a symlink into this repo)
3. **Enabled** in `~/.claude/settings.json` under `enabledPlugins` (`"<name>@espresso-skills": true`)

Missing any one of those = the skill won't appear. The scaffolder handles all three for new skills; `/plugin install` handles #2 and #3 if you're adding an existing entry.

## Branching

Use **git branches**, not git worktrees. Worktrees produce stale leftover directories (`prunable` entries) and confuse the symlink model since the linked cache only ever points at the main checkout. Branch in-place:

```bash
git checkout -b feature/<short-name>
```

## What got removed in fix_repo_structure

For context if you're confused by missing things:

- `protocol-kri-extractor/scripts/sync-to-cache.sh`, `install-hooks.sh` — gone. Symlinks replaced the need.
- `plugins/soa-kri-extractor/scripts/sync-to-cache.sh` — gone, same reason.
- `.git/hooks/post-commit` — gone. No longer needed.
- Top-level duplicates of `protocol-kri-extractor`, `kri-regression-tester`, `amendment-sync` — gone. Plugin tree is the single source of truth.
