"""
claude_max.py — Anthropic-side LLM dispatch via the Claude Code CLI.

Routes Claude calls through `claude -p` (headless mode), which uses the user's
Claude Max session for billing. This avoids depending on `ANTHROPIC_API_KEY` /
the developer-API account.

Drop-in replacement for `anthropic.Anthropic().messages.create()`. Returns an
object with `.content[0].text` and `.usage` so existing call sites work without
restructuring.

Notes:
  * Each call spawns a new `claude` subprocess. Slow per-call (~2–10s of overhead),
    so use sparingly inside tight loops.
  * Long prompts are passed via stdin to avoid argv length limits.
  * Gemini calls stay on their existing API key (separate provider) — only the
    Anthropic-side calls move to Max.
"""
import json
import os
import re
import subprocess
import sys


CLAUDE_BIN = os.environ.get("CLAUDE_BIN", "claude")


class _Usage:
    def __init__(self, input_tokens=0, output_tokens=0):
        self.input_tokens = int(input_tokens or 0)
        self.output_tokens = int(output_tokens or 0)


class _ContentBlock:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, text, usage=None, raw=None):
        self.content = [_ContentBlock(text)]
        self.usage = usage or _Usage()
        self.raw = raw  # full JSON dict from `claude -p` for diagnostics


def _format_messages_to_prompt(messages, system=None):
    """Compose a single prompt string from a `messages` list + optional system.

    `claude -p` accepts a single prompt input; we serialize the list into a
    natural conversation block. For our use cases (single-turn extraction or
    judging) the messages list typically has length 1, so this is essentially
    just the user content.
    """
    parts = []
    if system:
        parts.append(f"[SYSTEM]\n{system.strip()}")
    for m in messages or []:
        role = (m.get("role") or "user").upper()
        content = m.get("content") or ""
        if isinstance(content, list):
            content = "\n".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
        parts.append(f"[{role}]\n{str(content).strip()}")
    return "\n\n".join(parts).strip()


def messages_create(messages=None, system=None, max_tokens=4096, model=None,
                    timeout=600, _retries=1):
    """Drop-in replacement for anthropic.Anthropic().messages.create().

    Returns a _Response object with .content[0].text and .usage.

    Args:
        messages: list of {"role": "user"|"assistant", "content": str}
        system: optional system prompt string
        max_tokens: ignored by `claude -p` (it has its own caps); kept for
            interface compatibility
        model: optional model override (e.g. "claude-sonnet-4-20250514"). Falls
            back to the CLI's default if None.
        timeout: subprocess timeout in seconds
        _retries: number of retries on transient failures

    Raises:
        RuntimeError on non-zero exit, missing JSON, or empty result
    """
    prompt = _format_messages_to_prompt(messages, system)
    cmd = [CLAUDE_BIN, "-p", "--output-format", "json"]
    if model:
        cmd.extend(["--model", model])

    # Pass through the calling environment but ALSO ensure that an empty
    # ANTHROPIC_API_KEY env var (set as a sandbox safeguard by some launchers)
    # is removed entirely — claude -p prefers Max OAuth when logged in, but an
    # empty-string API key var has been observed to confuse its auth detection.
    env = os.environ.copy()
    if env.get("ANTHROPIC_API_KEY") == "":
        del env["ANTHROPIC_API_KEY"]

    last_err = None
    for attempt in range(max(1, _retries) + 1):
        try:
            proc = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
            if proc.returncode != 0:
                last_err = f"claude -p exited {proc.returncode}: {proc.stderr[-400:]}"
                continue
            stdout = (proc.stdout or "").strip()
            if not stdout:
                last_err = "claude -p produced empty stdout"
                continue
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                # Some Claude Code versions stream multiple JSON objects; take the last one
                m = re.findall(r"\{[\s\S]*?\}\s*$", stdout)
                if m:
                    payload = json.loads(m[-1])
                else:
                    last_err = f"claude -p stdout was not JSON: {stdout[:300]}"
                    continue
            if payload.get("is_error"):
                last_err = f"claude -p reported error: {payload.get('result', '')[:400]}"
                continue
            text = (payload.get("result", "") or "").strip()
            if not text:
                # Empty result — retry once. This sometimes happens when claude -p
                # produces a 'thinking' response without final text (rare). On
                # repeat failure surface it loudly so the caller knows.
                last_err = (
                    f"claude -p returned empty result (subtype={payload.get('subtype')!r}, "
                    f"stop_reason={payload.get('stop_reason')!r}, num_turns={payload.get('num_turns')})"
                )
                continue
            usage_dict = payload.get("usage") or {}
            usage = _Usage(
                input_tokens=usage_dict.get("input_tokens", 0),
                output_tokens=usage_dict.get("output_tokens", 0),
            )
            return _Response(text=text, usage=usage, raw=payload)
        except subprocess.TimeoutExpired:
            last_err = f"claude -p timeout after {timeout}s"
            continue
        except Exception as e:
            last_err = f"claude -p exception: {e}"
            continue
    raise RuntimeError(f"claude -p failed after retries: {last_err}")


# ─── Anthropic SDK shape (so existing code can do `client = Anthropic()` etc.) ─
class Anthropic:
    """Drop-in shim for `anthropic.Anthropic()` that routes through `claude -p`.

    Existing code:
        client = anthropic.Anthropic()
        response = client.messages.create(model=..., max_tokens=..., messages=[...], system=...)

    Becomes (with this shim):
        from claude_max import Anthropic
        client = Anthropic()
        response = client.messages.create(...)   # unchanged

    No API key consumed. Uses the Claude Code Max session.
    """
    def __init__(self, *args, **kwargs):
        self.messages = _MessagesNamespace()


class _MessagesNamespace:
    def create(self, model=None, max_tokens=4096, messages=None, system=None, **kw):
        return messages_create(
            messages=messages, system=system, max_tokens=max_tokens, model=model,
            timeout=kw.get("timeout", 600),
        )


# ─── Self-test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    r = messages_create(
        messages=[{"role": "user", "content": "Reply with exactly one word: OK"}],
        max_tokens=20,
    )
    print(f"Result text: {r.content[0].text!r}")
    print(f"Tokens: in={r.usage.input_tokens} out={r.usage.output_tokens}")
    print("✓ self-test passed" if "OK" in r.content[0].text.upper() else "✗ unexpected response")
