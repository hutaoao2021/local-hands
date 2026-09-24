# Local Hands

Local Hands is a private Agent Plugin runtime for Codex-style execution from ChatGPT. It exposes project inspection, patch-oriented code editing, filesystem work, Git, long-running jobs, persistent terminals, SSH targets, screenshots, windows, mouse, and keyboard actions.

## v0.5 architecture

Local Hands now has two transports over the same 55-tool runtime:

1. **Local plugin transport (`stdio`)** — used by Agent Plugin clients that can launch local MCP subprocesses.
2. **Web companion transport (Streamable HTTP)** — a loopback-only MCP server that can be placed behind an HTTPS tunnel and connected to ChatGPT as a custom MCP app.

This separation matters because Agent Plugins do not expand environment variables inside remote MCP URLs. A changing per-user tunnel URL therefore cannot safely be hard-coded into `mcp.json`.

## v0.4: project memory and self-service Skills

- `resume_context` returns one compact continuation snapshot: workspace, project/task memory, Git status, live process/terminal sessions, recent workspaces, and installed Skills.
- Task state is isolated per workspace, so switching projects no longer carries the previous project's goal into the next one.
- `project_context_get/set` persists stable build/test/lint commands, summaries, important files, and notes for future turns.
- `workspace_list` makes recent authorized projects cheap to resume.
- Local Hands can now list/read installed Agent Skills and safely acquire new ones from Git repositories.
- Skill acquisition is review-first: metadata-only shallow clone, candidate discovery from the Git tree, sparse checkout of the selected Skill, static audit, content hash/provenance, then installation. Downloaded code is never executed as part of review or installation.
- GitHub HTTPS is the default automatic source. Non-GitHub hosts, binaries, and overwrites require stronger explicit intent.

## v0.5: terminal and verification efficiency

- Windows terminals now prefer the native Windows 10/11 ConPTY API through a dependency-free `ctypes` implementation. This improves interactive CLI, ANSI/TUI, SSH, stdin, and resize behavior; older/unsupported Windows builds automatically fall back to the existing pipe shell.
- POSIX still uses a real PTY and was regression-tested for input, incremental output, resize, and termination.
- `project_inspect` suggests likely lint/test/build commands from common project descriptors.
- `project_verify` runs stored or explicit lint/test/build commands in one bounded pass and stops on first failure by default, reducing agent/tool round-trips.

## Codex-style runtime

- `project_inspect` plus persistent workspace/task state.
- `apply_patch` with structured multi-file edits and unified diffs; structured edits are preflighted and use best-effort rollback if an apply step fails.
- Long-running process sessions with incremental output, session listing, and poll waits up to 300 seconds.
- Persistent interactive terminals: real PTY on POSIX; persistent pipe-backed shell fallback on Windows.
- Named key-based SSH targets with synchronous commands, long-running remote jobs, and interactive SSH terminals.
- Windows desktop control: screen geometry, full/region screenshots, visible-window enumeration/activation, mouse movement/click/scroll, Unicode typing, and key chords.
- Agent skill that instructs ChatGPT to keep executing inspect -> patch -> run -> observe -> verify rather than stopping at intermediate states.

## Local stdio mode

The client must support local `stdio` MCP servers and have Python 3 available as `python` on PATH. The local agent uses only the Python standard library.

Git is optional but recommended. Unified-diff patch mode and Git tools require `git` on PATH; structured `apply_patch` edits do not. Remote tools use the system `ssh` executable and never store passwords.

## Web ChatGPT companion

Start the loopback MCP server:

### Windows

```powershell
.\scripts\start-http.ps1
```

### macOS/Linux

```sh
./scripts/start-http.sh
```

It prints a URL similar to:

```text
http://127.0.0.1:8765/mcp/<high-entropy-secret>
```

The server binds to `127.0.0.1` by default, validates non-empty Origin headers, limits request bodies, and uses the unguessable path as an access secret. Keep the complete MCP URL private.

To make it reachable from web ChatGPT, place an HTTPS tunnel in front of the loopback origin and append the same `/mcp/<secret>` path to the public origin. Then add that complete HTTPS URL as a Streamable HTTP custom MCP app in ChatGPT Developer mode.

If `cloudflared` is already installed, Local Hands can launch a Cloudflare quick tunnel for you:

```powershell
.\scripts\start-cloudflare.ps1
```

or:

```sh
./scripts/start-cloudflare.sh
```

The launcher prints `PUBLIC MCP URL: ...`; use that complete secret URL for the custom MCP app. Quick-tunnel public origins change on restart.

## Windows notes

Screenshot and GUI input use Windows PowerShell/.NET and the Win32 API. v0.5 prefers the native Windows ConPTY API and falls back to the older pipe-backed terminal only when the API is unavailable or initialization fails. The fallback reason is returned to the agent so it can adapt.

## Access model

The user's home directory is authorized by default. Additional roots must be explicitly authorized with `authorize_root`. Workspace, SSH target metadata, and task state are persisted under `PLUGIN_DATA` when provided, otherwise under `~/.local-hands/state.json`.

The HTTP path secret is generated locally and stored separately under the same data directory. It is not packaged into the plugin and is not included in normal tool results.

High-risk command patterns require `risk_acknowledged=true` after explicit user approval. The agent skill instructs ChatGPT to preserve unrelated changes and verify work before declaring success.
