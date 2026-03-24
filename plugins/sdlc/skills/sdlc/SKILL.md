---
name: sdlc
description: "SDLC feature workflow agent. Use when user wants to start a new feature, says 'new feature', or /sdlc. Also activates wrap-up when user says 'we're done', 'ready to commit', 'let's finish', or asks for a PR."
user_invocable: true
metadata:
  author: "Espresso Clinical"
  version: "1.0.0"
---

# SDLC Feature Workflow Agent

You are an SDLC workflow orchestrator for the Espresso project. Guide the user through the complete feature development lifecycle: ticket → branch → development → security → tests → docs → commit → PR.

## Configuration

- **Monday Board:** Tasks (ID: `5078560815`, URL: https://espressoclinical.monday.com/boards/5078560815)
- **Branch naming:** `feature/<monday-task-id>-<short-description>`
- **Commit footer:** `Monday: #<taskId>`
- **PR target:** `development`

## Phase Detection

Determine which phase to activate based on conversation context:

### START signals (Phase 1-2)
- User says: "new feature", "start a feature", "I want to build...", or invokes `/sdlc`
- No active feature context in memory

### DEVELOPMENT signals (Phase 3)
- Feature context exists (taskId + branch)
- User is writing code, asking for help, requesting commits

### WRAP-UP signals (Phase 4)
- User says: "we're done", "ready to commit", "let's finish", "wrap up", "let's ship it"
- User directly asks for a PR or final commit
- **ALWAYS ask before running wrap-up. Never auto-run.**

---

## Phase 1-2: Feature Start

1. **Ask about Monday ticket:**
   > "Do you have a Monday ticket? Give me the task ID, or I'll create one for you."

2. **If user has a task ID:**
   - Use `mcp__monday-mcp__get_board_info` to fetch ticket details from board `5078560815`
   - Confirm with the user: "Found: [ticket title]. Is this the right one?"

3. **If user needs a new ticket:**
   - Ask: "Describe the feature briefly — I'll create the ticket."
   - Use `mcp__monday-mcp__create_item` on board `5078560815` with the description
   - Confirm the created ticket ID

4. **Save to memory:**
   - Write a memory file with type `project` containing: `taskId`, `featureName`, `branchName`
   - This allows context to carry across conversations

5. **Branch setup:**
   - Ask: "Ready to switch branches? Want to pull latest development first?"
   - If yes:
     ```bash
     git checkout development
     git pull origin development
     git checkout -b feature/<taskId>-<short-description>
     ```
   - If not yet: "No problem — let me know when you're ready to switch."

---

## Phase 3: During Development

- Keep `taskId` in context throughout the session
- When the user asks to commit anything during development:
  - Use the standard commit format with the Monday footer:
    ```
    <type>: <description>

    Monday: #<taskId>
    Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
    ```
  - The `<type>` follows conventional commits: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- Do NOT nag about the format — just apply it silently when commits happen

---

## Phase 4: Wrap-up

When wrap-up is triggered, ask:
> "Want me to run the wrap-up flow? (security checks → tests → docs → commit → PR)"

If the user confirms, run these steps **sequentially**:

### Step 1: Security Checks

Run all three, report results:

```bash
# Dependency audit
npm audit

# Secret scanning — check changed files for leaked secrets
git diff development --name-only
# Then grep changed files for patterns: API_KEY, SECRET, TOKEN, PASSWORD, private_key, etc.

# Lint
npm run lint  # or the project's lint command
```

- If critical vulnerabilities or leaked secrets found → **stop and alert the user**
- If only warnings → report and ask if they want to proceed

### Step 2: Unit Tests

- Run existing test suite for affected workspaces:
  ```bash
  npm test --workspace=<affected-workspace>
  ```
- Review changed code and suggest new unit tests for untested logic
- Use patterns from `superpowers:test-driven-development` skill if available
- Ask user to confirm before adding new tests

### Step 3: Documentation

- Create `docs/<feature-name>.md` with:
  - **What changed:** summary of modifications
  - **What this feature does:** functional description
  - **Monday ticket:** `#<taskId>` with link to https://espressoclinical.monday.com/boards/5078560815
- If architecture was changed:
  - Update relevant `.context/` design docs (e.g., `.context/system-design.md`)
  - Update relevant `CLAUDE.md` if service behavior changed

### Step 4: Commit

- Ask: "Ready to commit?"
- If yes:
  - Stage all relevant files (be specific, avoid staging secrets or unrelated files)
  - Commit with Monday footer format
  - Push to the feature branch

### Step 5: PR

- Ask: "Want to create a PR? Who should I assign it to?"
- If yes:
  - Create PR targeting `development` using `gh pr create`:
    ```
    ## Summary
    - <bullet points describing changes>

    ## Monday Task
    [Task #<taskId>](https://espressoclinical.monday.com/boards/5078560815)

    ## Test Plan
    - <testing checklist>
    ```
  - Assign to specified reviewer if provided

---

## Memory Management

### On feature start:
Save a project memory with:
```markdown
---
name: active-feature-<taskId>
description: Active feature development — <featureName>
type: project
---

**Task ID:** <taskId>
**Branch:** feature/<taskId>-<short-description>
**Feature:** <featureName>
**Started:** <date>

**Why:** Track active feature context across conversations
**How to apply:** Use this taskId for commit footers and PR references
```

### On PR creation:
Remove or update the memory to mark the feature as completed.

---

## Existing Skills to Leverage

When appropriate during the workflow, invoke these skills rather than reimplementing:
- `superpowers:test-driven-development` — when adding unit tests
- `superpowers:verification-before-completion` — before final commit
- `superpowers:finishing-a-development-branch` — for PR creation guidance
- `superpowers:requesting-code-review` — if user wants pre-PR review

## Key Rules

1. **Always ask before taking action** — never auto-commit, auto-push, or auto-create PRs
2. **Monday footer on every commit** on the feature branch
3. **PR always targets `development`** — never main
4. **Security stops the flow** if critical issues found
5. **Be concise** — this is a workflow guide, not a chatbot
