#!/usr/bin/env python3
"""Start Local Hands HTTP plus a Cloudflare quick tunnel.

Requires the user-installed `cloudflared` executable.  No credentials are
stored by Local Hands.  The generated public URL changes whenever the quick
tunnel restarts; the high-entropy MCP path remains persistent unless reset.
"""

import argparse
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import http_agent
import local_agent as core

URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.I)


def choose_port(preferred):
    for port in [preferred] + [p for p in range(8765, 8775) if p != preferred]:
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free loopback port found in the Local Hands port range")


def main():
    ap = argparse.ArgumentParser(description="Local Hands + Cloudflare quick tunnel")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    cloudflared = shutil.which("cloudflared")
    if not cloudflared:
        raise SystemExit("cloudflared is not on PATH. Install Cloudflare's cloudflared first, then run this launcher again.")

    port = choose_port(args.port)
    secret = http_agent.load_or_create_secret()
    mcp_path = "/mcp/" + secret
    server = http_agent.Server(("127.0.0.1", port), http_agent.Handler, mcp_path, http_agent.allowed_origins(), args.verbose)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.25}, daemon=True)
    thread.start()

    local_origin = f"http://127.0.0.1:{port}"
    print(f"Local Hands {core.SERVER_VERSION} companion listening on {local_origin}", flush=True)
    proc = subprocess.Popen([cloudflared, "tunnel", "--no-autoupdate", "--url", local_origin], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
    public = None
    try:
        deadline = time.time() + 45
        for line in iter(proc.stdout.readline, ""):
            if args.verbose:
                print("[cloudflared] " + line.rstrip(), flush=True)
            match = URL_RE.search(line)
            if match and public is None:
                public = match.group(0).rstrip("/")
                print("PUBLIC MCP URL:", public + mcp_path, flush=True)
                print("Treat the complete URL as a secret. Add it as a Streamable HTTP custom MCP app in ChatGPT Developer mode.", flush=True)
            if public is None and time.time() > deadline:
                raise RuntimeError("Timed out waiting for cloudflared to report a quick-tunnel URL")
            if proc.poll() is not None:
                break
        code = proc.wait()
        if code != 0:
            raise RuntimeError(f"cloudflared exited with code {code}")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
