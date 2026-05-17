#!/usr/bin/env python3
"""
check_repo_structure.py — validate the espresso-skills marketplace repo layout.

Run via:
    scripts/check_repo_structure.py

Exits 0 if everything is consistent, 1 with a list of problems otherwise.
Wire into CI / pre-commit to prevent the kind of drift that prompted
fix_repo_structure (skill dirs at repo root, plugins/marketplace
mismatches, missing plugin.json, etc.).
"""

from __future__ import annotations
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"
PLUGINS_DIR = REPO_ROOT / "plugins"

# Top-level dirs that are allowed to NOT look like plugins.
ALLOWED_ROOT_DIRS = {".git", ".claude-plugin", "plugins", "scripts", "_archive"}


def main() -> int:
    problems: list[str] = []

    if not MARKETPLACE.exists():
        print(f"✗ missing {MARKETPLACE.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 1

    marketplace = json.loads(MARKETPLACE.read_text())
    registered: dict[str, dict] = {p["name"]: p for p in marketplace.get("plugins", [])}

    # 1. No skill-shaped directories at repo root.
    for child in REPO_ROOT.iterdir():
        if not child.is_dir() or child.name in ALLOWED_ROOT_DIRS or child.name.startswith("."):
            continue
        if (child / "SKILL.md").exists() or (child / ".claude-plugin").exists():
            problems.append(
                f"top-level skill dir '{child.name}/' — move under plugins/ "
                f"(skills must live at plugins/<name>/)"
            )

    # 2. Every plugin dir must be registered + well-formed.
    on_disk: set[str] = set()
    if PLUGINS_DIR.exists():
        for plugin_dir in sorted(PLUGINS_DIR.iterdir()):
            if not plugin_dir.is_dir():
                continue
            name = plugin_dir.name
            on_disk.add(name)

            # 2a. directory registered in marketplace?
            if name not in registered:
                problems.append(
                    f"plugins/{name}/ exists but is NOT in marketplace.json "
                    f"— won't appear in /plugin browse"
                )

            # 2b. plugin.json present and name matches dir name
            plugin_json = plugin_dir / ".claude-plugin" / "plugin.json"
            if not plugin_json.exists():
                problems.append(f"plugins/{name}/ missing .claude-plugin/plugin.json")
            else:
                try:
                    data = json.loads(plugin_json.read_text())
                except json.JSONDecodeError as exc:
                    problems.append(f"plugins/{name}/.claude-plugin/plugin.json invalid JSON: {exc}")
                    data = None
                if data and data.get("name") != name:
                    problems.append(
                        f"plugins/{name}/.claude-plugin/plugin.json declares name="
                        f"'{data.get('name')}' but dir is '{name}'"
                    )

            # 2c. SKILL.md present at the conventional path
            skill_md = plugin_dir / "skills" / name / "SKILL.md"
            if not skill_md.exists():
                problems.append(f"plugins/{name}/ missing skills/{name}/SKILL.md")

    # 3. Every marketplace entry has a backing dir + sane source path
    for name, entry in registered.items():
        if name not in on_disk:
            problems.append(
                f"marketplace.json registers '{name}' but plugins/{name}/ does not exist"
            )
        expected_source = f"./plugins/{name}"
        if entry.get("source") != expected_source:
            problems.append(
                f"marketplace.json entry '{name}' has source='{entry.get('source')}' "
                f"— expected '{expected_source}'"
            )

    if problems:
        print(f"✗ {len(problems)} problem(s) found:\n", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    print(f"✓ repo structure OK ({len(on_disk)} plugins, all registered and well-formed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
