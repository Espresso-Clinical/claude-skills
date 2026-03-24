# SDLC Feature Workflow Agent

Conversational SDLC orchestrator that guides feature development from Monday ticket through PR submission.

## What it does

- **Start:** Asks for Monday ticket (or creates one), sets up feature branch
- **Develop:** Enforces commit format with Monday task ID footer
- **Finish:** Runs security checks, tests, docs, commit, and PR creation

## Triggers

| You say | What happens |
|---------|-------------|
| `/sdlc` or "new feature" | Kicks off ticket + branch setup |
| "commit" (during dev) | Commits with `Monday: #<taskId>` footer |
| "we're done" / "let's finish" | Wrap-up flow: security → tests → docs → commit → PR |

## Configuration

| Setting | Value |
|---------|-------|
| Monday Board | Tasks (ID: `5078560815`) |
| Branch naming | `feature/<task-id>-<short-desc>` |
| PR target | `development` |

## Requirements

- Monday MCP server configured (`mcp__monday-mcp__*` tools)
- GitHub CLI (`gh`) for PR creation
- Git access
