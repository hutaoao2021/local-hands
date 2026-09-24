#!/usr/bin/env python3
"""Loader for the GitHub-published Local Hands runtime.

The installed plugin ships local_agent.py as one source file. The public
repository stores that exact v0.5.0 source gzip-compressed so it can be
published through the connected GitHub API without truncation.
"""
from pathlib import Path
import gzip

_here = Path(__file__).resolve().parent
_payload = _here / "local_agent.py.gz"
if not _payload.is_file():
    raise SystemExit("Local Hands runtime payload is missing: server/local_agent.py.gz")
_source = gzip.decompress(_payload.read_bytes()).decode("utf-8")
exec(compile(_source, str(Path(__file__)), "exec"), globals(), globals())
