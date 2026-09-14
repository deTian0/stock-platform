# -*- coding: utf-8 -*-
"""Bump VERSION and all package version fields."""
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
ver = sys.argv[1] if len(sys.argv) > 1 else "1.7.1"

(root / "VERSION").write_text(ver + "\n", encoding="utf-8")

pyprojects = [
    "packages/providers/pyproject.toml",
    "packages/research/pyproject.toml",
    "packages/agents/pyproject.toml",
    "packages/execution/pyproject.toml",
    "apps/workbench/pyproject.toml",
]
inits = [
    "packages/providers/src/stock_platform_providers/__init__.py",
    "packages/research/src/stock_platform_research/__init__.py",
    "packages/agents/src/stock_platform_agents/__init__.py",
    "packages/execution/src/stock_platform_execution/__init__.py",
    "apps/workbench/src/stock_platform_workbench/__init__.py",
]

for rel in pyprojects:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    text2, n = re.subn(r'(?m)^version\s*=\s*"[^"]+"', f'version = "{ver}"', text, count=1)
    if n != 1:
        raise SystemExit(f"version= not found once in {rel}")
    p.write_text(text2, encoding="utf-8")

for rel in inits:
    p = root / rel
    text = p.read_text(encoding="utf-8")
    text2, n = re.subn(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{ver}"', text, count=1)
    if n != 1:
        raise SystemExit(f"__version__ not found once in {rel}")
    p.write_text(text2, encoding="utf-8")

print(f"bumped to {ver}")
