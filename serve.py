"""Serve lunch-roulette.html at the root, plus the MCP proxy the page needs.

Three things are served from this one port:

  /                    the lunch roulette wheel
  /api/mcp/status      which site is serving, and what the peer site says
  /api/mcp/call        call one MCP tool and return the answer + the raw
                       JSON-RPC exchange

Why the proxy exists
--------------------
The MCP server (Red Hat `linux-mcp-server`, streamable HTTP on :8095) sends
**no CORS headers** — `OPTIONS /mcp` answers 405 and the POST response carries
no `access-control-allow-origin`. A browser page on any other origin is
therefore blocked from calling it. Proxying through this server makes the
call same-origin, and it keeps the app image free of CORS hacks.

The app never gets the SSH key. The MCP is the only privileged component: it
inspects the host over SSH as the site's own deploy user. The app only
speaks HTTP.

Configuration (environment variables, set per site by Ansible)
--------------------------------------------------------------
  MCP_URL       the local site's MCP endpoint (default http://127.0.0.1:8095/mcp)
  MCP_PORT      port used to derive the peer URL (default 8095)
  MCP_PATH      path used to derive the peer URL (default /mcp)
  SITE_ROLE     PROD | DR — which site this instance runs on
  SITE_HOST     the IP this site inspects itself through
  SITE_EXPECT   the hostname this site is expected to report
  PEER_ROLE     PROD | DR — which site the peer is
  PEER_HOST     the IP of the peer site
  PEER_URL      the peer site's MCP endpoint (derived from the two above if unset)
  APP_VERSION   the app image tag, shown in the panel banner
  MCP_TOOL_ALLOW comma-separated tool allowlist for /api/mcp/call
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import sys
import threading
import time
import urllib.parse

import mcp_client

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX = "lunch-roulette.html"

# ---------------------------------------------------------------- configuration

MCP_URL = os.environ.get("MCP_URL", "http://127.0.0.1:8095/mcp")
MCP_PORT = os.environ.get("MCP_PORT", "8095")
MCP_PATH = os.environ.get("MCP_PATH", "/mcp")
SITE_ROLE = os.environ.get("SITE_ROLE", "")
SITE_HOST = os.environ.get("SITE_HOST", "")
SITE_EXPECT = os.environ.get("SITE_EXPECT", "")
PEER_ROLE = os.environ.get("PEER_ROLE", "")
PEER_HOST = os.environ.get("PEER_HOST", "")
PEER_URL = os.environ.get("PEER_URL", "")
APP_VERSION = os.environ.get("APP_VERSION", "")
MCP_TIMEOUT = float(os.environ.get("MCP_TIMEOUT", "45"))
PORT = int(os.environ.get("PORT", "8082"))
HOST = os.environ.get("HOST", "0.0.0.0")

# The panel offers five tools. The proxy only lets those through, so the
# page is not a general-purpose MCP proxy for anything on the site.
DEFAULT_TOOL_ALLOW = [
    "get_system_information",
    "get_listening_ports",
    "get_cpu_information",
    "get_memory_information",
    "get_disk_usage",
]
TOOL_ALLOW = [
    t.strip() for t in
    os.environ.get("MCP_TOOL_ALLOW", ",".join(DEFAULT_TOOL_ALLOW)).split(",")
    if t.strip()
]

if not PEER_URL and PEER_HOST:
    PEER_URL = "http://%s:%s%s" % (PEER_HOST, MCP_PORT, MCP_PATH)

# The status endpoint costs an SSH round-trip per site, so the answer is
# cached for a few seconds. The page polls; a manual refresh busts the cache.
STATUS_TTL = float(os.environ.get("MCP_STATUS_TTL", "8"))
_status_lock = threading.Lock()
_status_cache = {"at": 0.0, "value": None}


# ---------------------------------------------------------------- MCP helpers

def _short_error(message: str) -> str:
    """Turn a urllib/connection error into something a tile can show."""
    text = str(message)
    if ("Connection refused" in text or "Errno 111" in text
            or "actively refused" in text or "WinError 10061" in text):
        return "connection refused"
    if "timed out" in text.lower():
        return "timed out"
    if "cannot reach" in text:
        return text.split("cannot reach", 1)[1].strip()
    return text[:200]


def _probe_site(url: str, host: str, role: str) -> dict:
    """Ask one MCP endpoint about one host.

    The MCP on a site can only inspect that site (its SSH user exists only
    there), so each tile asks its own site's MCP about its own IP.
    """
    tile = {"role": role, "host": host, "url": url, "ok": False,
            "hostname": None, "error": None, "info": None}

    if not url or not host:
        tile["error"] = "not configured"
        return tile

    try:
        answer = mcp_client.call_tool(url, "get_system_information",
                                      {"host": host}, timeout=MCP_TIMEOUT)
    except mcp_client.MCPError as exc:
        tile["error"] = _short_error(exc)
        return tile
    except Exception as exc:  # noqa: BLE001 - a broken tile must not break the page
        tile["error"] = f"{type(exc).__name__}: {exc}"[:200]
        return tile

    structured = answer.get("structured") or {}
    tile["ok"] = not answer.get("isError")
    tile["hostname"] = structured.get("hostname")
    tile["info"] = structured
    if not tile["ok"]:
        tile["error"] = "the tool reported an error"
    return tile


def site_status(force: bool = False) -> dict:
    """The payload behind GET /api/mcp/status."""
    now = time.time()
    with _status_lock:
        if (not force and _status_cache["value"] is not None
                and now - _status_cache["at"] < STATUS_TTL):
            return _status_cache["value"]

    local = _probe_site(MCP_URL, SITE_HOST, SITE_ROLE)
    peer = _probe_site(PEER_URL, PEER_HOST, PEER_ROLE)

    # The PROD and DR tiles are always in the same order, whoever is serving.
    by_role = {local["role"]: local, peer["role"]: peer}
    prod = by_role.get("PROD") or {"role": "PROD", "host": "", "url": "",
                                   "ok": False, "hostname": None,
                                   "error": "not configured", "info": None}
    dr = by_role.get("DR") or {"role": "DR", "host": "", "url": "",
                               "ok": False, "hostname": None,
                               "error": "not configured", "info": None}

    tools = []
    try:
        tools = [t.get("name") for t in mcp_client.list_tools(MCP_URL, timeout=MCP_TIMEOUT)]
    except Exception:  # noqa: BLE001 - the tool list is a nicety, not a gate
        tools = []

    payload = {
        "site": {
            "role": SITE_ROLE,
            "host": SITE_HOST,
            "expect": SITE_EXPECT,
            "mcpUrl": MCP_URL,
            "ok": local["ok"],
            "hostname": local["hostname"],
            "error": local["error"],
            "info": local["info"],
        },
        "prod": prod,
        "dr": dr,
        "tools": tools,
        "appVersion": APP_VERSION,
        "checkedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    with _status_lock:
        _status_cache["at"] = time.time()
        _status_cache["value"] = payload
    return payload


# ---------------------------------------------------------------- HTTP handler

class LunchHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _json(self, status: int, payload) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/mcp/status":
            force = urllib.parse.urlparse(self.path).query == "force=1"
            return self._json(200, site_status(force=force))
        if path in ("/", "/index.html"):
            self.path = "/" + INDEX
        return super().do_GET()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        if path != "/api/mcp/call":
            return self._json(404, {"error": "not found"})

        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            request = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            return self._json(400, {"error": f"bad JSON: {exc}"})

        tool = (request.get("tool") or "").strip()
        if not tool:
            return self._json(400, {"error": "no tool named"})
        if tool not in TOOL_ALLOW:
            return self._json(403, {
                "error": f"tool {tool!r} is not exposed by this panel",
                "allowed": TOOL_ALLOW,
            })

        args = request.get("args") or {}
        if not isinstance(args, dict):
            return self._json(400, {"error": "args must be a JSON object"})
        # The MCP policy refuses local execution, so every call needs a host.
        # Default to the site this app runs on.
        args.setdefault("host", SITE_HOST)

        try:
            answer = mcp_client.call_tool(MCP_URL, tool, args, timeout=MCP_TIMEOUT)
        except mcp_client.MCPError as exc:
            return self._json(502, {"error": str(exc), "tool": tool})
        except Exception as exc:  # noqa: BLE001
            return self._json(502, {"error": f"{type(exc).__name__}: {exc}", "tool": tool})

        answer.pop("raw", None)
        return self._json(200, answer)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (PORT, fmt % args))


def main():
    os.chdir(ROOT)
    # Threading: an MCP round-trip over SSH blocks for seconds, and a
    # single-threaded server would freeze the page while it waits.
    httpd = ThreadingHTTPServer((HOST, PORT), LunchHandler)
    httpd.daemon_threads = True
    print(f"Serving {ROOT} on http://{HOST}:{PORT}/  (root -> {INDEX})")
    print(f"  MCP proxy : {MCP_URL}  site={SITE_ROLE or '-'} host={SITE_HOST or '-'}")
    print(f"  peer      : {PEER_URL or '-'}  role={PEER_ROLE or '-'}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
