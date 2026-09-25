# Local Hands

Local Hands is a local execution runtime for Codex-style computer work from ChatGPT. It exposes project inspection, patch-oriented editing, filesystem work, Git, long-running jobs, persistent terminals, SSH, screenshots, windows, mouse/keyboard control, project memory, and safe Agent Skill acquisition.

## v0.6: ordinary ChatGPT browser bridge

v0.6 adds a separate **Local Hands Companion** for Chrome/Edge. It lets an ordinary ChatGPT browser conversation exchange structured Local Hands tool requests with the loopback runtime without relying on a custom MCP write surface.

Architecture:

```text
ChatGPT in Chrome / Edge
        |
        | companion extension (DOM bridge)
        v
127.0.0.1:8766-8770
Local Hands Browser Bridge
        |
        v
same Local Hands tool dispatcher
        |
        +-- files / patch / Git
        +-- process / PTY / ConPTY
        +-- SSH / Skills / desktop
```

The browser companion is an **unofficial UI integration**, not a public ChatGPT automation API. It observes the current ChatGPT page and can submit tool-result messages on the user's behalf while that tab is enabled. Provider terms, account limits, safety decisions, and workspace rules still apply. Do not use the bridge to evade a provider restriction or safety decision.

### Browser bridge quick start (Windows)

1. Clone or update Local Hands locally.
2. In PowerShell from the repository root, run:

```powershell
.\scripts\start-bridge.ps1
```

The bridge binds only to loopback, chooses the first free port from 8766-8770, and prints a six-digit pairing code.

3. Open `chrome://extensions` or `edge://extensions`.
4. Enable **Developer mode**.
5. Choose **Load unpacked** and select the repository's `extension` folder.
6. Open `https://chatgpt.com/` in that browser.
7. Open the **Local Hands Companion** extension popup, enter the six-digit code once, then click **Enable this ChatGPT tab** and **Initialize this chat**.
8. After ChatGPT acknowledges initialization, send a normal task such as: `Inspect this project, fix the failing tests, run verification, and keep going until it passes.`

The bridge token is generated locally and stored under Local Hands' data directory. It is never printed. A new six-digit pairing code is generated each time the bridge starts; successful pairing rotates the in-memory code.

### Safety boundaries

- The browser bridge binds to `127.0.0.1` only and refuses non-loopback startup.
- Operational endpoints require a random persistent bearer token obtained through one-time local pairing.
- CORS is granted only to browser-extension origins carrying the Local Hands extension header.
- Each ChatGPT tab is disabled by default. Enable it explicitly from the extension popup.
- A visible badge shows `ACTIVE`, `RUNNING`, `PAUSED`, or `ERROR`; clicking it pauses that tab immediately.
- The companion stops automatically after 80 automatic tool-result turns in one page session to catch accidental loops.
- The Local Hands runtime still enforces authorized filesystem roots and its high-risk command approval checks.
- Browser integration has no separate route for raw filesystem access; it can only invoke the existing Local Hands tool dispatcher after pairing.

### Bridge protocol

After **Initialize this chat**, the extension sends a one-time visible bootstrap instruction. When ChatGPT needs a local action it emits one `local-hands` fenced JSON block:

```json
{"local_hands":1,"id":"unique-id","calls":[{"tool":"project_inspect","arguments":{}}],"stop_on_error":true}
```

The extension executes up to 8 calls through the loopback bridge and submits a structured `[LOCAL_HANDS_RESULT]` message back into the same conversation. ChatGPT can then request the next tool call or give its final answer. Screenshot image results are attached to the ChatGPT composer on a best-effort basis.

## Existing runtime transports

The same runtime remains available through:

1. local plugin transport (`stdio`) for clients that support local MCP subprocesses;
2. Streamable HTTP companion (`server/http_agent.py`) for supported remote MCP configurations;
3. the v0.6 browser bridge (`server/browser_bridge.py`) for ordinary ChatGPT browser conversations.

## v0.4: project memory and self-service Skills

- `resume_context` returns workspace, task/project memory, Git state, live sessions, recent workspaces, and installed Skills.
- Task state is isolated per workspace.
- `project_context_get/set` persists stable build/test/lint commands and project notes.
- Skill acquisition is review-first: shallow metadata discovery, sparse checkout, static audit, provenance/hash, then install. Review/install does not execute downloaded scripts.

## v0.5: terminal and verification efficiency

- Windows terminals prefer native ConPTY and automatically fall back to a pipe shell if unavailable.
- POSIX uses a real PTY.
- `project_inspect` suggests common verification commands.
- `project_verify` runs stored or explicit lint/test/build commands in one bounded pass.

## Access model

The user's home directory is authorized by default. Additional roots must be explicitly authorized with `authorize_root`. Workspace, SSH target metadata, project memory, and task state are persisted under `PLUGIN_DATA` when provided, otherwise under `~/.local-hands/`.

Remote tools use the system `ssh` executable and never store passwords. Git is optional but recommended. High-risk command patterns require explicit user approval plus `risk_acknowledged=true`.
