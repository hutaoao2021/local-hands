#!/usr/bin/env python3
"""Loader for the GitHub-published Local Hands runtime source fragments.

The installed plugin ships local_agent.py as one file. The public repository
stores that source in small reviewable fragments so it can be published through
the connected GitHub API without truncation.
"""
from pathlib import Path

_here = Path(__file__).resolve().parent
_parts = sorted((_here / "local_agent_src").glob("part_*.pyfrag"))
if not _parts:
    raise SystemExit("Local Hands source fragments are missing")
_source = "".join(p.read_text(encoding="utf-8") for p in _parts)
exec(compile(_source, str(Path(__file__)), "exec"), globals(), globals())
