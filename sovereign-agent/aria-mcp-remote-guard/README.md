# aria-mcp-remote-guard — Safe remote access to Aria's MCP server (the claude.ai connector path)

> Lets a claude.ai custom connector or a remote Claude Code session reach Aria **without** exposing her.
> Local stdio use (Claude Desktop, local Claude Code) is unchanged. Staged; nothing is live until applied.

> **Targets Aria v6.5.0** (Erebo-Aria, 2026-09-29). Ported 2026-10-02: the edits were re-applied to v6.5.0's own `mcp_server.py` (+73/−13 lines plus the central gate), not copied from the old v0.4.0 snapshot, so none of v6.5's newer work is lost.

## Who it affects

- **Kevin:** remote access to Aria needs a token he keeps in his key vault. Local Claude Desktop and
  local Claude Code use is unchanged.
- **Aria:** her write tool and agent loop can't be driven by remote callers unless Kevin turns them on.
  Every refusal is recorded in her event log (`plane=control`, `mcp_guard.*`), so she can see who knocked.
- **Anyone who finds the URL:** gets 401 and nothing else.

## Why (measured on the live v0.4.0 server, 2026-10-02)

| Check against the current `sov-mcp --transport streamable-http` | Result |
|---|---|
| Request through a tunnel hostname (e.g. `aria.example.com`) | **421 rejected.** The MCP library only trusts `localhost`, so a connector cannot work today. |
| Request to `127.0.0.1` with no credentials at all | **200 accepted.** Anything that forwards to localhost exposes every tool, including `record_proof_of_value` (writes) and `ask_aria` (runs the full agent loop). |
| `--help` text | Suggested `--host 0.0.0.0`, which publishes the unauthenticated server to the whole network. |

## What it changes

- **Fails closed.** Any network transport needs `ARIA_MCP_TOKEN` (at least 32 characters), even on
  127.0.0.1, or `sov-mcp` refuses to start. The only opt-out, `ARIA_MCP_ALLOW_NO_TOKEN=1`, works on
  loopback alone, for local testing.
- **Default-deny for remote clients.**
  - Only the 14 tools listed as read-only in `REMOTE_READ_TOOLS` are available remotely.
  - `record_proof_of_value` needs `ARIA_MCP_ALLOW_WRITE=1`; `ask_aria` needs `ARIA_MCP_ALLOW_ASK=1`.
  - **Any tool not classified is refused remotely**, so a tool added later is never exposed by accident.
  - It's enforced at one central choke point (the MCP tool manager), with the per-tool checks kept as
    defense in depth.
  - `test_every_registered_tool_is_classified` fails until a new tool is classified.
- **Tunnel-ready.** Hostnames in `ARIA_MCP_PUBLIC_HOSTS` join the DNS-rebinding allow-list; everything
  else is still rejected.
- **Two ways to present the token** (compared in constant time):
  - `Authorization: Bearer <token>` header. Preferred; works with Claude Code.
  - A secret URL prefix, `https://<host>/k/<token>/mcp`, for clients that can't send headers (a claude.ai
    custom connector without OAuth). Weaker, because the token is part of the URL and can show up in proxy
    logs. Keep write and ask tools off in this mode.

## Payload

- `src/sovereign_agent/mcp_guard/policy.py` — launch policy, startup validation, and per-tool gating
- `src/sovereign_agent/mcp_guard/middleware.py` — the ASGI token gate
- `src/sovereign_agent/mcp_server.py` — **whole-file replacement** of the live server: a policy check in the
  two risky tools, plus a guarded `main()` / `build_remote_app()`. The original is backed up on apply.

## Verify / apply

```bash
./scripts/verify_module.sh aria-mcp-remote-guard   # 24 tests, live src untouched
./scripts/safe_apply.sh aria-mcp-remote-guard      # cockpit stopped; backs up mcp_server.py; auto-rollback
```

Verified 2026-10-02 against v6.5.0:
- 24 module tests pass.
- Removing the central gate makes the end-to-end "unclassified tool" test fail, so that test checks the
  gate.
- Dry-run apply on v6.5: 31 pass, including Aria's existing `test_mcp_server.py`. The apply also fixes
  that file's stale `assert __version__ == "0.4.0"` (it fails on pristine v6.5) to compare against the
  installed package version — stricter, not skipped.
- Earlier, against v0.4.0:
- With the guard removed, 3 of the original 17 fail, so they really test the guard. (The 4 added later test audit events and input checks.)
- A dry-run apply on a throwaway copy passed 28 tests (these 21 plus the 7 existing `test_mcp_server.py` tests).
- Restoring the backup gives back the original file byte for byte.

## Using it after apply

```bash
export ARIA_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"  # keep it in your key vault
export ARIA_MCP_PUBLIC_HOSTS=aria.yourdomain.com     # the tunnel's hostname
sov-mcp --transport streamable-http                  # listens on 127.0.0.1:8765
cloudflared tunnel --url http://127.0.0.1:8765       # or a named tunnel on your domain
```

- **Claude Code anywhere:**
  `claude mcp add --transport http aria https://aria.yourdomain.com/mcp --header "Authorization: Bearer $ARIA_MCP_TOKEN"`
- **claude.ai connector:** Settings → Connectors → Add custom connector →
  `https://aria.yourdomain.com/k/<token>/mcp`. Then start a new session, since connectors load at session
  start.

Stop `sov-mcp` when you aren't using it. Rotate the token if a URL containing it is ever shared.

## Not done here (honest limits)

- **No OAuth.** claude.ai's preferred auth for connectors is OAuth. The path secret is a practical
  stand-in, not an equivalent.
- **No rate limiting or request logging** beyond uvicorn's warnings.
- **Not tested against a live claude.ai connector or a real tunnel** — the cloud session that built this
  can't reach your machine. The HTTP behavior was tested end to end against the real MCP app in-process.
