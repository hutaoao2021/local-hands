#!/usr/bin/env python3
"""Streamable-HTTP companion for Local Hands.

This serves the same tool surface as local_agent.py over the 2025-era MCP
Streamable HTTP transport.  It is deliberately loopback-only by default and
uses a high-entropy secret path.  Put an HTTPS tunnel in front of it when a
remote ChatGPT custom MCP app needs to reach the machine.
"""

import argparse
import json
import os
import secrets
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import local_agent as core

SUPPORTED_PROTOCOLS = {"2025-03-26", "2025-06-18", "2025-11-25"}
MAX_BODY = 4 * 1024 * 1024
MUTATION_LOCK = threading.RLock()
DEFAULT_ORIGINS = {
    "https://chatgpt.com",
    "https://chat.openai.com",
    "http://localhost",
    "https://localhost",
}


def _secret_file():
    return core.DATA_DIR / "http_secret.txt"


def load_or_create_secret():
    env_secret = os.environ.get("LOCAL_HANDS_HTTP_SECRET", "").strip()
    if env_secret:
        if len(env_secret) < 24:
            raise ValueError("LOCAL_HANDS_HTTP_SECRET must be at least 24 characters")
        return env_secret
    path = _secret_file()
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if len(value) >= 24:
                return value
    except OSError:
        pass
    value = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "
", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def allowed_origins():
    extra = os.environ.get("LOCAL_HANDS_ALLOWED_ORIGINS", "")
    result = set(DEFAULT_ORIGINS)
    for value in extra.split(","):
        value = value.strip()
        if value:
            result.add(value.rstrip("/"))
    return result


def rpc_response(msg):
    if not isinstance(msg, dict):
        return {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "Invalid Request"}}
    method = msg.get("method")
    mid = msg.get("id")
    params = msg.get("params") or {}
    if mid is None:
        return None
    try:
        if method == "initialize":
            requested = params.get("protocolVersion") or core.DEFAULT_PROTOCOL
            if requested not in SUPPORTED_PROTOCOLS:
                requested = core.DEFAULT_PROTOCOL
            result = {
                "protocolVersion": requested,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": core.SERVER_NAME, "version": core.SERVER_VERSION},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": core.tools_list()}
        elif method == "tools/call":
            name = params.get("name", "")
            args = params.get("arguments") or {}
            if name in core.MUTATING:
                with MUTATION_LOCK:
                    result = core.dispatch_tool(name, args)
            else:
                result = core.dispatch_tool(name, args)
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Method not found: {method}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}}


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalHandsHTTP/0.3"

    def _origin_ok(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        normalized = origin.rstrip("/")
        return normalized in self.server.allowed_origins

    def _is_mcp_path(self):
        return self.path.split("?", 1)[0] == self.server.mcp_path

    def _send_json(self, status, obj, extra_headers=None):
        data = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for k, v in extra_headers.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _send_empty(self, status):
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        if self.path.split("?", 1)[0] == self.server.health_path:
            self._send_json(HTTPStatus.OK, {"ok": True, "server": core.SERVER_NAME, "version": core.SERVER_VERSION})
            return
        if not self._is_mcp_path():
            self._send_empty(HTTPStatus.NOT_FOUND)
            return
        if not self._origin_ok():
            self._send_empty(HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "POST")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self):
        if self._is_mcp_path():
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.send_header("Allow", "POST")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self._send_empty(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if not self._is_mcp_path():
            self._send_empty(HTTPStatus.NOT_FOUND)
            return
        if not self._origin_ok():
            self._send_empty(HTTPStatus.FORBIDDEN)
            return

        protocol = self.headers.get("MCP-Protocol-Version")
        if protocol and protocol not in SUPPORTED_PROTOCOLS:
            self._send_json(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": f"Unsupported MCP protocol version: {protocol}"}})
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_BODY:
            self._send_empty(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        raw = self.rfile.read(length)
        try:
            msg = json.loads(raw.decode("utf-8"))
        except Exception:
            self._send_json(HTTPStatus.BAD_REQUEST, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            return

        response = rpc_response(msg)
        if response is None:
            self._send_empty(HTTPStatus.ACCEPTED)
            return
        self._send_json(HTTPStatus.OK, response)

    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, mcp_path, origins, verbose=False):
        super().__init__(address, handler)
        self.mcp_path = mcp_path
        self.health_path = "/healthz/" + mcp_path.rsplit("/", 1)[-1]
        self.allowed_origins = origins
        self.verbose = verbose


def main():
    ap = argparse.ArgumentParser(description="Local Hands Streamable-HTTP companion")
    ap.add_argument("--host", default="127.0.0.1", help="Bind host; keep 127.0.0.1 when using a tunnel")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--secret", default=None, help="Override the persistent secret path token (>=24 chars)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    secret = args.secret or load_or_create_secret()
    if len(secret) < 24 or "/" in secret:
        raise SystemExit("Secret must be at least 24 characters and must not contain '/'.")
    path = "/mcp/" + secret
    origins = allowed_origins()
    server = Server((args.host, args.port), Handler, path, origins, args.verbose)
    print(f"Local Hands HTTP companion {core.SERVER_VERSION}", flush=True)
    print(f"Loopback MCP URL: http://{args.host}:{args.port}{path}", flush=True)
    print("Keep the secret path private. If using a tunnel, append the same /mcp/<secret> path to its public HTTPS origin.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
