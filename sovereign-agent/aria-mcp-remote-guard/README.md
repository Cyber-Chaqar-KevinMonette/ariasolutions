# aria-mcp-remote-guard — Safe remote access to Aria's MCP server (the claude.ai connector path)

> Lets a claude.ai custom connector or a remote Claude Code session reach Aria **without** exposing her.
> Local stdio use (Claude Desktop, local Claude Code) is unchanged. Staged; nothing is live until applied.

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
- **Read-only by default for remote clients.** `record_proof_of_value` needs `ARIA_MCP_ALLOW_WRITE=1`;
  `ask_aria` needs `ARIA_MCP_ALLOW_ASK=1`. The other 10 tools are read-only and stay available.
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
./scripts/verify_module.sh aria-mcp-remote-guard   # 21 tests, live src untouched
./scripts/safe_apply.sh aria-mcp-remote-guard      # cockpit stopped; backs up mcp_server.py; auto-rollback
```

Verified 2026-10-02 in a clean cloud install:
- 21 module tests pass.
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
