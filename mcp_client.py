"""Minimal MCP client over streamable HTTP — standard library only.

The lunch-rolltable container has no pip dependencies (that is a hard
requirement of the Aqua `root_user` / no-vulnerability gate the image has to
pass), so the page cannot use `fastmcp`. This module speaks the MCP
streamable-HTTP protocol directly with `urllib.request`:

    1. POST initialize              -> 200, the session id arrives in the
                                       `mcp-session-id` response header
    2. POST notifications/initialized -> 202, no body
    3. POST tools/list | tools/call -> 200, the answer is an SSE stream
                                       (`content-type: text/event-stream`),
                                       so the JSON-RPC payload has to be
                                       picked out of the `data:` lines

Every exchange is kept in `client.trace` so the page can show the raw
JSON-RPC traffic next to the rendered answer — the panel is only
believable if the wire format is visible.

Public API:

    list_tools(url)                  -> list of tool descriptors
    call_tool(url, name, arguments)  -> {"text":..., "structured":...,
                                         "raw":..., "trace":[...]}
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

DEFAULT_TIMEOUT = 45.0
PROTOCOL_VERSION = "2025-06-18"


class MCPError(RuntimeError):
    """Any failure while talking to the MCP server."""


def _parse_sse(body: str):
    """Pull the JSON-RPC payload out of an SSE stream.

    The server answers with `event: message` followed by one or more
    `data: {...}` lines. Only the last complete JSON object is of
    interest, but intermediate `data:` lines are kept so a multi-part
    answer is not lost.
    """
    payloads = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[5:].strip()
        if not chunk:
            continue
        try:
            payloads.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return payloads


def _extract_result(body: str, headers) -> dict:
    """Return the JSON-RPC response object from a 200 response."""
    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = (value or "").lower()
            break

    if "text/event-stream" in content_type:
        payloads = _parse_sse(body)
        if not payloads:
            raise MCPError("the server returned an empty event stream")
        return payloads[-1]

    # A server that answers with plain JSON instead of SSE.
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise MCPError(f"unreadable response ({content_type or 'no content-type'}): {exc}") from exc


class MCPClient:
    """One MCP session against one endpoint."""

    def __init__(self, url: str, timeout: float = DEFAULT_TIMEOUT,
                 client_name: str = "lunch-rolltable"):
        self.url = url
        self.timeout = timeout
        self.client_name = client_name
        self.session_id = None
        self.server_info = {}
        self.trace = []
        self._next_id = 0

    # ---------------------------------------------------------------- low level

    def _post(self, payload: dict):
        data = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(self.url, data=data, method="POST")
        request.add_header("Content-Type", "application/json")
        # The MCP streamable-HTTP transport requires both media types.
        request.add_header("Accept", "application/json, text/event-stream")
        if self.session_id:
            request.add_header("mcp-session-id", self.session_id)

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return (response.status, dict(response.headers),
                        response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise MCPError(f"HTTP {exc.code} from {self.url}: {body[:400]}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"cannot reach {self.url}: {exc.reason}") from exc
        except OSError as exc:
            raise MCPError(f"cannot reach {self.url}: {exc}") from exc

    def _record(self, step: str, request: dict, status: int, response) -> None:
        self.trace.append({
            "step": step,
            "request": request,
            "status": status,
            "session": self.session_id,
            "response": response,
        })

    def _rpc(self, step: str, method: str, params=None, want_response=True):
        """Send one JSON-RPC message and return the `result` object."""
        payload = {"jsonrpc": "2.0", "method": method}
        if want_response:
            self._next_id += 1
            payload["id"] = self._next_id
        if params is not None:
            payload["params"] = params

        status, headers, body = self._post(payload)

        if not want_response:
            # notifications are answered with 202 and an empty body
            self._record(step, payload, status, None)
            return None

        message = _extract_result(body, headers)
        self._record(step, payload, status, message)

        if "error" in message:
            error = message["error"]
            raise MCPError(f"{method} failed: {error.get('message', error)}")
        return message.get("result", {})

    # ---------------------------------------------------------------- session

    def initialize(self) -> dict:
        """Open the session. Must be called before anything else."""
        if self.session_id:
            return self.server_info

        payload = {
            "jsonrpc": "2.0",
            "id": 0,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": self.client_name, "version": "1.0"},
            },
        }
        status, headers, body = self._post(payload)
        message = _extract_result(body, headers)
        self.session_id = headers.get("mcp-session-id") or headers.get("Mcp-Session-Id")
        self.server_info = message.get("result", {})
        # The server sends a few kilobytes of prose as `instructions`. It is
        # not part of the demo, and it would drown the trace panel.
        instructions = self.server_info.get("instructions")
        if isinstance(instructions, str) and len(instructions) > 300:
            self.server_info["instructions"] = instructions[:300] + " … (truncated)"
        self._record("initialize", payload, status, message)

        if not self.session_id:
            raise MCPError("the server did not return an mcp-session-id header")

        # the session is only usable after the client has confirmed it
        self._rpc("notifications/initialized", "notifications/initialized",
                  want_response=False)
        return self.server_info

    def list_tools(self) -> list:
        """Return the tool descriptors the server exposes."""
        if not self.session_id:
            self.initialize()
        result = self._rpc("tools/list", "tools/list", {})
        return result.get("tools", [])

    def call_tool(self, name: str, arguments: dict) -> dict:
        """Call one tool and return its rendered text plus the raw payload."""
        if not self.session_id:
            self.initialize()
        result = self._rpc("tools/call", "tools/call",
                           {"name": name, "arguments": arguments or {}})

        chunks = []
        for block in result.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if text:
                    chunks.append(text)

        structured = result.get("structuredContent")
        if structured is None:
            structured = result.get("structured_content")

        text = "\n".join(chunks)
        if not text and structured is not None:
            text = json.dumps(structured, indent=2, default=str)

        return {
            "tool": name,
            "arguments": arguments or {},
            "text": text,
            "structured": structured,
            "isError": bool(result.get("isError")),
            "raw": result,
        }


# ---------------------------------------------------------------- module API


def list_tools(url: str, timeout: float = DEFAULT_TIMEOUT) -> list:
    """Open a session on `url` and return the tool descriptors."""
    client = MCPClient(url, timeout=timeout)
    client.initialize()
    return client.list_tools()


def call_tool(url: str, name: str, arguments: dict, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Open a session on `url`, call one tool and return the answer.

    The returned dict carries `text` (what the page renders), `structured`
    (the parsed payload when the tool has one) and `trace` (the raw JSON-RPC
    exchange, for the "MCP traffic" panel).
    """
    client = MCPClient(url, timeout=timeout)
    client.initialize()
    answer = client.call_tool(name, arguments)
    answer["trace"] = client.trace
    answer["serverInfo"] = client.server_info.get("serverInfo", {})
    return answer


# ---------------------------------------------------------------- handshake

# What each step of the handshake is FOR. The page shows these next to the
# raw JSON, so the protocol is legible to someone who has never seen MCP.
STEP_NOTES = {
    "initialize": "open the session — the server answers with an mcp-session-id header",
    "notifications/initialized": "confirm the session — the server answers 202 with no body",
    "tools/list": "ask the server what it can do",
    "tools/call": "call one tool — the SSH round-trip to the host happens here",
}

PREVIEW_LIMIT = 1400


def _preview(payload, limit: int = PREVIEW_LIMIT) -> str:
    """Render one JSON-RPC message as the compact text the page shows."""
    try:
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(payload)
    if len(text) > limit:
        text = text[:limit] + "\n… (%d more characters)" % (len(text) - limit)
    return text


def handshake(url: str, tool: str = "get_system_information",
              arguments: dict = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Run one full MCP session and return every step of it.

    The four exchanges of the MCP streamable-HTTP handshake:

        1. initialize                 -> 200, the session id arrives in a header
        2. notifications/initialized   -> 202, no body
        3. tools/list                 -> 200, the tool descriptors
        4. tools/call                 -> 200, the answer

    Each step comes back with the request, the HTTP status, the response and
    a short note, so the page can render the protocol and not only the result.

    The tool and the arguments are fixed by the caller — nothing here comes
    from the browser — so this demonstrates the protocol and is not a
    general-purpose MCP proxy.
    """
    client = MCPClient(url, timeout=timeout)
    client.initialize()
    tools = client.list_tools()
    answer = client.call_tool(tool, arguments or {})

    steps = []
    for index, entry in enumerate(client.trace, start=1):
        response = entry["response"]
        if entry["step"] == "tools/list":
            # Every tool's full input schema would be pages of JSON. The names
            # are the point of the step.
            response = {"tools": [t.get("name") for t in tools]}

        steps.append({
            "n": index,
            "step": entry["step"],
            "note": STEP_NOTES.get(entry["step"], ""),
            "method": entry["request"].get("method", ""),
            "status": entry["status"],
            "session": entry["session"],
            "requestPreview": _preview(entry["request"]),
            "responsePreview": _preview(response),
        })

    return {
        "url": url,
        "serverInfo": client.server_info.get("serverInfo", {}),
        "toolCount": len(tools),
        "tool": tool,
        "steps": steps,
        "answer": {
            "text": answer.get("text", ""),
            "structured": answer.get("structured"),
            "isError": bool(answer.get("isError")),
        },
    }
