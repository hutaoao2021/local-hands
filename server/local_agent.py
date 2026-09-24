#!/usr/bin/env python3
"""Loader for the GitHub-published Local Hands runtime.

The installed plugin ships local_agent.py as one source file. The public
repository stores that exact v0.5.0 source gzip-compressed in several binary
parts so it can be published without truncation by the connected GitHub API.
"""
from pathlib import Path
import gzip

_here = Path(__file__).resolve().parent
_parts = sorted((_here / "local_agent_payload").glob("part_*.gzpart"))
if not _parts:
    raise SystemExit("Local Hands runtime payload parts are missing")
_payload = b"".join(p.read_bytes() for p in _parts)
_source = gzip.decompress(_payload).decode("utf-8")
exec(compile(_source, str(Path(__file__)), "exec"), globals(), globals())
