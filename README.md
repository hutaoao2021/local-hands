# Local Hands

Local Hands is a local execution runtime for Codex-style computer work from ordinary ChatGPT browser conversations. It exposes project inspection, patch-oriented editing, filesystem work, Git, long-running jobs, persistent terminals, SSH, screenshots, windows, mouse/keyboard control, project memory, and safe Agent Skill acquisition.

## v0.6.1: zero-click-after-reboot Windows flow

v0.6.1 keeps the v0.6 Chrome/Edge loopback bridge and adds two optional convenience features:

- **Windows login autostart** for the Local Hands Browser Bridge, installed only for the current user and without administrator rights.
- **Hands-free ChatGPT tabs** in the extension. When enabled once, new/reloaded `chatgpt.com` tabs automatically enable Local Hands and send the bridge bootstrap for the active chat. Any tab can still be paused immediately from the visible Local Hands badge.

The intended one-time setup is:

```text
visible bridge start -> pair extension once -> install autostart once
-> enable Hands-free mode once
```

After that, a normal reboot flow is:

```text
Windows sign-in -> hidden Local Hands bridge starts
-> Chrome/Edge opens -> extension reconnects with the persisted token
-> ChatGPT tab auto-enables/initializes -> give ChatGPT the task
```

### One-time Windows setup

From the repository root:

```powershell
.\scripts\start-bridge.ps1
```

Load `extension/` as an unpacked Chrome/Edge extension, open `chatgpt.com`, and pair with the six-digit code printed by the bridge.

After pairing, install autostart:

```powershell
.\scripts\install-autostart.ps1
```

This creates one shortcut in the **current user's Startup folder**. It launches the bridge through `wscript.exe`, so there is no persistent PowerShell window after Windows sign-in. The startup launcher also uses the regular `start-bridge.ps1`, which avoids starting a duplicate bridge if one is already running.

Then open the Local Hands Companion popup and enable:

```text
Hands-free ChatGPT tabs
```

This setting and the pairing token are stored by the extension and survive normal browser/Windows restarts.

To remove Windows autostart:

```powershell
.\scripts\uninstall-autostart.ps1
```

This removes only the Startup shortcut. It does not terminate an already-running bridge and does not delete Local Hands state or pairing tokens.

## v0.6 browser bridge

Architecture:

```text
ChatGPT in Chrome / Edge
        |
        | Local Hands Companion extension
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

The browser companion is an **unofficial UI integration**, not a public ChatGPT automation API. It observes the current ChatGPT page and can submit tool-result messages on the user's behalf while enabled. Provider terms, account limits, safety decisions, and workspace rules still apply.

### Safety boundaries

- The browser bridge binds to `127.0.0.1` only.
- Operational endpoints require a persistent random bearer token obtained through one-time local pairing.
- CORS is granted only to Chrome/Edge extension origins carrying the Local Hands extension header.
- Hands-free mode is opt-in. A visible page badge always shows Local Hands state and can pause the current tab immediately.
- Per-tab pause is an explicit override even while Hands-free mode is enabled.
- The companion pauses after 80 automatic tool-result turns in one page session as a loop guard.
- The existing Local Hands authorized-root and high-risk-command approval checks remain in force.
- Browser integration has no separate raw-filesystem route; it invokes the existing Local Hands tool dispatcher only after pairing.

### Bridge protocol

When initialized, the extension gives ChatGPT the Local Hands bridge protocol. When ChatGPT needs a local action it emits a `local-hands` fenced JSON block:

```json
{"local_hands":1,"id":"unique-id","calls":[{"tool":"project_inspect","arguments":{}}],"stop_on_error":true}
```

The extension executes up to 8 calls through the loopback bridge and sends a structured `[LOCAL_HANDS_RESULT]` message back into the same conversation. ChatGPT can then request the next tool call or give its final answer. Screenshot image results are attached on a best-effort basis.

## Existing runtime transports

The same runtime also remains available through:

1. local plugin transport (`stdio`) for clients that support local MCP subprocesses;
2. Streamable HTTP companion (`server/http_agent.py`) for supported remote MCP configurations;
3. browser bridge (`server/browser_bridge.py`) for ordinary ChatGPT browser conversations.

## Existing v0.4-v0.5 capabilities

- Workspace/project memory and `resume_context`.
- Review-first Agent Skill discovery/install with provenance.
- Patch-oriented editing and Git inspection.
- Long-running process sessions and polling.
- Native Windows ConPTY with fallback; real POSIX PTY.
- SSH commands, remote jobs, and interactive terminals.
- `project_verify` for bounded lint/test/build verification.
- Authorized filesystem roots plus explicit high-risk command approval.

## Access model

The user's home directory is authorized by default. Additional roots must be explicitly authorized with `authorize_root`. Runtime state is stored under `PLUGIN_DATA` when provided, otherwise under `~/.local-hands/`.

Remote tools use the system `ssh` executable and never store passwords. Git is optional but recommended.
