"""CN stock universe loader — config/fixtures first; empty = fail-closed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


class UniverseEmptyError(ValueError):
    """Raised when the resolved CN universe has no symbols."""


def _normalize_symbol(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip().upper()
    if not text:
        return None
    # Strip common market prefixes (SH600519 / SZ000001).
    if text.startswith(("SH", "SZ", "BJ")) and len(text) > 2:
        text = text[2:]
    if text.endswith((".SH", ".SZ", ".BJ")):
        text = text.rsplit(".", 1)[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 6:
        return digits
    return None


def normalize_universe(symbols: Iterable[Any]) -> list[str]:
    """Deduplicate while preserving order; drop invalid entries."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        sym = _normalize_symbol(raw)
        if sym is None or sym in seen:
            continue
        seen.add(sym)
        out.append(sym)
    return out


def load_universe(
    path: str | Path | None = None,
    *,
    symbols: Iterable[Any] | None = None,
) -> list[str]:
    """Load a CN equity universe.

    Precedence:
      1. Explicit ``symbols`` iterable (if not None)
      2. JSON file at ``path`` (list or ``{"symbols": [...]}``)

    Fail-closed: empty result raises ``UniverseEmptyError``.
    """
    if symbols is not None:
        out = normalize_universe(symbols)
        if not out:
            raise UniverseEmptyError("universe symbols list is empty after normalize")
        return out

    if path is None:
        raise UniverseEmptyError("universe path is required when symbols is omitted")

    p = Path(path)
    if not p.is_file():
        raise UniverseEmptyError(f"universe file not found: {p}")

    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, list):
        raw_list = data
    elif isinstance(data, dict):
        raw_list = data.get("symbols") or data.get("universe") or []
    else:
        raise UniverseEmptyError(f"universe file must be list or object, got {type(data).__name__}")

    out = normalize_universe(raw_list)
    if not out:
        raise UniverseEmptyError(f"universe file is empty after normalize: {p}")
    return out


def default_universe_fixture_path() -> Path:
    """Packaged sample universe (small; for offline demos / tests)."""
    return Path(__file__).resolve().parent / "fixtures" / "universe_cn_sample.json"
