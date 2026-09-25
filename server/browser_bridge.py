#!/usr/bin/env python3
"""Loopback browser bridge for Local Hands.

This bridge is intentionally separate from the MCP HTTP surface. A Chrome/Edge
companion extension pairs with a one-time six-digit code, receives a persistent
bearer token, and may then invoke the same Local Hands tool dispatcher. The
bridge binds to loopback by default and never exposes a filesystem route of its
own.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import local_agent as core

BRIDGE_VERSION = 1
SERVER_VERSION = "0.6.2"
DEFAULT_PORTS = tuple(range(8766, 8771))
MAX_BODY = 4 * 1024 * 1024
MAX_CALLS = 8
MAX_IMAGE_BYTES = 16 * 1024 * 1024
MUTATION_LOCK = threading.RLock()


def _bridge_token_file() -> Path:
    return core.DATA_DIR / "browser_bridge_token.txt"


def load_or_create_token() -> str:
    path = _bridge_token_file()
    try:
        if path.exists():
            token = path.read_text(encoding="utf-8").strip()
            if len(token) >= 32:
                return token
    except OSError:
        pass
    token = secrets.token_urlsafe(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(token + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return token


def new_pair_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def is_extension_origin(origin: str | None) -> bool:
    if not origin:
        return False
    return origin.startswith("chrome-extension://") or origin.startswith("edge-extension://")


def _sanitize_tool_result(value):
    """Separate image payloads from text/structured tool results."""
    attachments = []
    if not isinstance(value, dict):
        return value, attachments
    result = dict(value)
    content = result.get("content")
    if not isinstance(content, list):
        return result, attachments
    clean = []
    total = 0
    for item in content:
        if isinstance(item, dict) and item.get("type") == "image" and isinstance(item.get("data"), str):
            raw_len = (len(item["data"]) * 3) // 4
            if total + raw_len > MAX_IMAGE_BYTES:
                clean.append({"type": "text", "text": "[Local Hands image omitted: attachment budget exceeded]"})
                continue
            total += raw_len
            attachments.append({
                "mimeType": item.get("mimeType") or "image/png",
                "data": item["data"],
            })
        else:
            clean.append(item)
    result["content"] = clean
    return result, attachments


def dispatch_one(call):
    if not isinstance(call, dict):
        raise ValueError("Each call must be an object")
    tool = str(call.get("tool") or "").strip()
    if not tool:
        raise ValueError("call.tool is required")
    arguments = call.get("arguments") or {}
    if not isinstance(arguments, dict):
        raise ValueError("call.arguments must be an object")
    try:
        if tool == "__local_hands_tools__":
            requested = arguments.get("names") or []
            if not isinstance(requested, list) or any(not isinstance(x, str) for x in requested):
                raise ValueError("__local_hands_tools__.arguments.names must be an array of tool names")
            tools = core.tools_list()
            if requested:
                wanted = set(requested)
                tools = [item for item in tools if item.get("name") in wanted]
            raw = {
                "content": [{"type": "text", "text": json.dumps({"tools": tools}, ensure_ascii=False)}],
                "isError": False,
            }
        elif tool in getattr(core, "MUTATING", set()):
            with MUTATION_LOCK:
                raw = core.dispatch_tool(tool, arguments)
        else:
            raw = core.dispatch_tool(tool, arguments)
        cleaned, attachments = _sanitize_tool_result(raw)
        is_error = bool(cleaned.get("isError")) if isinstance(cleaned, dict) else False
        return {"tool": tool, "ok": not is_error, "result": cleaned}, attachments
    except Exception as exc:
        return {
            "tool": tool,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }, []


def dispatch_batch(calls, stop_on_error=True):
    if not isinstance(calls, list) or not calls:
        raise ValueError("calls must be a non-empty array")
    if len(calls) > MAX_CALLS:
        raise ValueError(f"At most {MAX_CALLS} calls are allowed in one batch")
    results = []
    attachments = []
    for call in calls:
        result, images = dispatch_one(call)
        results.append(result)
        attachments.extend(images)
        if stop_on_error and not result.get("ok", False):
            break
    return results, attachments


class BridgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler, pair_code, token, verbose=False):
        super().__init__(address, handler)
        self.pair_code = pair_code
        self.token = token
        self.verbose = verbose
        self.started_at = time.time()


class Handler(BaseHTTPRequestHandler):
    server_version = "LocalHandsBrowserBridge/0.6.2"

    def log_message(self, fmt, *args):
        if self.server.verbose:
            super().log_message(fmt, *args)

    def _origin(self):
        return self.headers.get("Origin")

    def _extension_request(self):
        return self.headers.get("X-Local-Hands-Extension") == "1"

    def _origin_ok(self):
        # Chrome/Edge extension service-worker fetches with host_permissions may
        # omit Origin entirely. Require our extension marker on every real
        # request; when Origin is present, it must still be an extension origin.
        origin = self._origin()
        return self._extension_request() and (not origin or is_extension_origin(origin))

    def _cors(self):
        origin = self._origin()
        if is_extension_origin(origin):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Local-Hands-Extension")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self._cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _empty(self, status):
        self.send_response(status)
        self._cors()
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("Invalid Content-Length")
        if length < 0 or length > MAX_BODY:
            raise OverflowError("Request body too large")
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as exc:
            raise ValueError("Invalid JSON body") from exc
        if not isinstance(obj, dict):
            raise ValueError("JSON body must be an object")
        return obj

    def _authorized(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return False
        return secrets.compare_digest(auth[7:], self.server.token)

    def do_OPTIONS(self):
        # Browser CORS preflight carries Origin and Access-Control-Request-Headers,
        # not the requested custom header itself. Validate the extension origin
        # here; validate X-Local-Hands-Extension on the real request.
        if not is_extension_origin(self._origin()):
            self._empty(HTTPStatus.FORBIDDEN)
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors()
        self.send_header("Access-Control-Max-Age", "600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path != "/v1/status":
            self._empty(HTTPStatus.NOT_FOUND)
            return
        if not self._origin_ok():
            self._empty(HTTPStatus.FORBIDDEN)
            return
        authorized = self._authorized()
        self._json(HTTPStatus.OK, {
            "ok": True,
            "bridge_version": BRIDGE_VERSION,
            "server_version": SERVER_VERSION,
            "runtime_version": getattr(core, "SERVER_VERSION", "unknown"),
            "paired": authorized,
            "token_fingerprint": token_fingerprint(self.server.token) if authorized else None,
        })

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if not self._origin_ok():
            self._empty(HTTPStatus.FORBIDDEN)
            return
        try:
            body = self._read_json()
        except OverflowError:
            self._empty(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
            return

        if path == "/v1/pair":
            code = str(body.get("code") or "").strip()
            if not secrets.compare_digest(code, self.server.pair_code):
                self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Invalid pairing code"})
                return
            self.server.pair_code = new_pair_code()
            print(f"NEW PAIRING CODE: {self.server.pair_code}", flush=True)
            self._json(HTTPStatus.OK, {
                "ok": True,
                "bridge_version": BRIDGE_VERSION,
                "server_version": SERVER_VERSION,
                "token": self.server.token,
                "token_fingerprint": token_fingerprint(self.server.token),
            })
            return

        if not self._authorized():
            self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Not paired"})
            return

        if path == "/v1/tools":
            self._json(HTTPStatus.OK, {"ok": True, "tools": core.tools_list()})
            return

        if path == "/v1/call":
            result, attachments = dispatch_one({
                "tool": body.get("tool"),
                "arguments": body.get("arguments") or {},
            })
            self._json(HTTPStatus.OK, {
                "ok": result.get("ok", False),
                "request_id": body.get("request_id"),
                "results": [result],
                "attachments": attachments,
            })
            return

        if path == "/v1/batch":
            try:
                results, attachments = dispatch_batch(
                    body.get("calls"),
                    bool(body.get("stop_on_error", True)),
                )
            except ValueError as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            self._json(HTTPStatus.OK, {
                "ok": all(item.get("ok", False) for item in results),
                "request_id": body.get("request_id"),
                "results": results,
                "attachments": attachments,
            })
            return

        self._empty(HTTPStatus.NOT_FOUND)


def choose_port(preferred=None):
    ports = [preferred] if preferred else list(DEFAULT_PORTS)
    for port in ports:
        if port is None:
            continue
        try:
            server = BridgeServer(("127.0.0.1", int(port)), Handler, new_pair_code(), load_or_create_token())
            server.server_close()
            return int(port)
        except OSError:
            continue
    raise RuntimeError("No free Local Hands browser bridge port found")


def main():
    ap = argparse.ArgumentParser(description="Local Hands browser bridge")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=0, help="0 = first free port in 8766-8770")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Browser bridge must remain loopback-only")
    port = choose_port(args.port or None)
    token = load_or_create_token()
    pair_code = new_pair_code()
    server = BridgeServer(("127.0.0.1", port), Handler, pair_code, token, args.verbose)
    print(f"Local Hands Browser Bridge {SERVER_VERSION}", flush=True)
    print(f"Bridge URL: http://127.0.0.1:{port}", flush=True)
    print(f"PAIRING CODE: {pair_code}", flush=True)
    print("Load extension/ as an unpacked Chrome/Edge extension, then enter this six-digit code once.", flush=True)
    print("The bridge is loopback-only. Keep the persistent browser bridge token private.", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
