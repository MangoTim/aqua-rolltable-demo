# aqua-rolltable-demo

Lunch Rolltable — the **user-facing workload** of the PROD/DR MCP pipeline
(`MangoTim/pipeline-dr`, Jenkins job `mcp-dr-pipeline`).

## What this is

A small Python-served static page (`lunch-roulette.html`) — a restaurant roulette
wheel for picking where to eat lunch in Tsim Sha Tsui — plus an **MCP status
panel** that shows which site is serving the page and what the peer site says.

The pipeline promotes this app as its **second artifact**: build → Aqua scan →
Trivy scan → tarball → deploy to both sites. The page then moves with the MCP
during a failover drill, and the panel proves it: the same image, a different
answer.

## The MCP panel

The page shows, live:

- **which site is serving** (PROD or DR) and its hostname,
- **two cluster tiles** — PROD and DR, each answering with its own hostname or
  `connection refused`,
- **the five MCP gate tools** — `get_system_information`,
  `get_listening_ports`, `get_cpu_information`, `get_memory_information`,
  `get_disk_usage`,
- **the raw JSON-RPC traffic** of the last call,
- **the MCP handshake, step by step** — one button runs a whole session and
  renders each exchange: `initialize` (with the session id the server hands
  back), `notifications/initialized` (the bodiless `202` that confirms the
  session), `tools/list`, and the `tools/call` that carries the SSH round-trip
  to the host.

The page never talks to the MCP directly. The MCP server sends **no CORS
headers**, so a browser on any other origin is blocked; `serve.py` proxies the
calls on the page's own origin instead. The app also never gets the SSH key —
the MCP is the only privileged component.

## API

| Route | What it does |
|---|---|
| `GET /` | the roulette page |
| `GET /api/mcp/status` | `{site, prod, dr, tools, appVersion}` — the local site's identity, both cluster tiles, the tool list |
| `GET /api/mcp/status?force=1` | the same, bypassing the server-side cache |
| `POST /api/mcp/call` | body `{"tool": "...", "args": {...}}` → the rendered answer plus the raw JSON-RPC exchange |
| `GET /api/mcp/handshake` | one full MCP session, returned step by step (request, HTTP status, response, a note on what each step is for) |

`/api/mcp/call` only accepts the five panel tools (override with
`MCP_TOOL_ALLOW`), so the page is not a general-purpose MCP proxy. The
handshake route names its tool in `serve.py`, not in the browser, so it is a
demonstration of the protocol rather than a second way into the MCP.

## Configuration (environment variables)

Set per site by Ansible; the defaults are for local dev.

| Variable | Default | Meaning |
|---|---|---|
| `HOST` | `0.0.0.0` | bind address |
| `PORT` | `8082` | listen port (container: `8084`) |
| `MCP_URL` | `http://127.0.0.1:8095/mcp` | the local site's MCP endpoint |
| `MCP_PORT` / `MCP_PATH` | `8095` / `/mcp` | used to derive the peer URL |
| `SITE_ROLE` | — | `PROD` or `DR` |
| `SITE_HOST` | — | the IP this site inspects itself through |
| `SITE_EXPECT` | — | the hostname this site is expected to report |
| `PEER_ROLE` / `PEER_HOST` / `PEER_URL` | — | the other site |
| `APP_VERSION` | — | the image tag, shown in the panel banner |

## Files

| File | Purpose |
|---|---|
| `lunch-roulette.html` | the roulette page and the MCP panel |
| `serve.py` | the HTTP server: static files + the MCP proxy (stdlib only) |
| `mcp_client.py` | a minimal MCP streamable-HTTP client (stdlib only — no `fastmcp`, no pip dependencies) |
| `Dockerfile` | Python 3.12-slim-**trixie** base, runs as non-root `appuser` (Aqua `root_user` control), exposes 8084 |
| `Jenkinsfile` | the retired single-site job — the pipeline owns `:8084` now |

> **Why trixie and not bookworm?** Debian 12 ships `libsqlite3-0` and `zlib1g`
> with two CRITICAL CVEs that have **no published fix**, so the pipeline's
> "no CRITICAL OS CVEs" gate cannot be met on that base. Debian 13 is clean.

## Local dev (without Docker)

```bash
HOST=127.0.0.1 PORT=8082 \
MCP_URL=http://192.168.147.105:8095/mcp \
SITE_ROLE=PROD SITE_HOST=192.168.147.105 \
PEER_ROLE=DR PEER_HOST=192.168.147.104 \
python serve.py
# → http://localhost:8082/
```

The `_tools/` Node.js scripts in the original `products/lunch roulette/` folder
(used for restaurant-data curation) are intentionally NOT included in the
container — they're development tooling, not runtime assets.
