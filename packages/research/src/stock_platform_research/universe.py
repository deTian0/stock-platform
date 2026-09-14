"""CN stock universe loader — config/fixtures first; empty = fail-closed.

M39: layered tiers ``core`` / ``watch`` / ``full`` for daily-use sizing.
CI keeps using the small packaged sample fixture.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Literal

UniverseTier = Literal["core", "watch", "full"]

UNIVERSE_TIERS: tuple[UniverseTier, ...] = ("core", "watch", "full")

# Soft guidance for EM throttling when live refresh is used (docs + ops).
# CI / default path remains replay and does not hit the public net.
RECOMMENDED_SIZE_LIMITS: dict[UniverseTier, int] = {
    "core": 50,
    "watch": 200,
    "full": 800,
}
EM_MIN_INTERVAL_HINT = (
    "When using live East Money via em_get, keep EM_MIN_INTERVAL>=1.0s "
    "(batch scenes 1.5–2.0s). Prefer replay for CI and local demos."
)


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


def _symbols_from_payload(data: Any, *, path: Path) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # Layered object: {"core": [...], "watch": [...], "full": [...]}
        if any(k in data for k in UNIVERSE_TIERS):
            return []
        return list(data.get("symbols") or data.get("universe") or [])
    raise UniverseEmptyError(f"universe file must be list or object, got {type(data).__name__}: {path}")


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise UniverseEmptyError(f"universe file not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def load_universe_tiers(path: str | Path) -> dict[UniverseTier, list[str]]:
    """Load a layered universe config.

    Accepted shapes:
      - flat list / ``{"symbols":[...]}`` → all tiers share the same list
      - ``{"core":[...], "watch":[...], "full":[...]}`` (missing tiers inherit
        from the next narrower non-empty tier: core←watch←full)

    Empty after normalize → ``UniverseEmptyError``.
    """
    p = Path(path)
    data = _load_json(p)

    if isinstance(data, list) or (
        isinstance(data, dict) and not any(k in data for k in UNIVERSE_TIERS)
    ):
        flat = normalize_universe(_symbols_from_payload(data, path=p))
        if not flat:
            raise UniverseEmptyError(f"universe file is empty after normalize: {p}")
        return {"core": list(flat), "watch": list(flat), "full": list(flat)}

    assert isinstance(data, dict)
    raw_tiers: dict[str, list[str]] = {}
    for tier in UNIVERSE_TIERS:
        raw = data.get(tier)
        if raw is None:
            raw_tiers[tier] = []
        elif isinstance(raw, list):
            raw_tiers[tier] = normalize_universe(raw)
        else:
            raise UniverseEmptyError(f"universe tier {tier!r} must be a list in {p}")

    # Inherit upward: full may stand alone; watch defaults to full; core to watch.
    full = raw_tiers["full"] or raw_tiers["watch"] or raw_tiers["core"]
    watch = raw_tiers["watch"] or full
    core = raw_tiers["core"] or watch
    if not full:
        raise UniverseEmptyError(f"layered universe is empty after normalize: {p}")
    return {"core": core, "watch": watch, "full": full}


def load_universe(
    path: str | Path | None = None,
    *,
    symbols: Iterable[Any] | None = None,
    tier: UniverseTier | str | None = None,
) -> list[str]:
    """Load a CN equity universe.

    Precedence:
      1. Explicit ``symbols`` iterable (if not None) — ``tier`` ignored
      2. JSON file at ``path`` (list, ``{"symbols": [...]}``, or layered tiers)

    When ``tier`` is set on a layered file, return that tier's symbols.
    Flat files ignore ``tier`` (all tiers identical).

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
    if tier is None:
        data = _load_json(p)
        if isinstance(data, dict) and any(k in data for k in UNIVERSE_TIERS):
            # Default daily-use tier for layered configs.
            tier = "watch"
        else:
            out = normalize_universe(_symbols_from_payload(data, path=p))
            if not out:
                raise UniverseEmptyError(f"universe file is empty after normalize: {p}")
            return out

    tier_key = str(tier).strip().lower()
    if tier_key not in UNIVERSE_TIERS:
        raise UniverseEmptyError(f"unknown universe tier {tier!r}; expected one of {UNIVERSE_TIERS}")
    tiers = load_universe_tiers(p)
    out = tiers[tier_key]  # type: ignore[index]
    if not out:
        raise UniverseEmptyError(f"universe tier {tier_key!r} is empty after normalize: {p}")
    return out


def default_universe_fixture_path() -> Path:
    """Packaged sample universe (small; for offline demos / tests)."""
    return Path(__file__).resolve().parent / "fixtures" / "universe_cn_sample.json"


def default_daily_universe_path() -> Path:
    """Packaged daily-use layered universe (core/watch/full sample)."""
    return Path(__file__).resolve().parent / "fixtures" / "universe_cn_daily.json"


def universe_size_guidance(tier: UniverseTier | str = "watch") -> dict[str, Any]:
    """Documented soft limits + EM interval hint (not enforced at runtime)."""
    key = str(tier).strip().lower()
    if key not in RECOMMENDED_SIZE_LIMITS:
        key = "watch"
    return {
        "tier": key,
        "recommendedMaxSymbols": RECOMMENDED_SIZE_LIMITS[key],  # type: ignore[index]
        "emMinIntervalHint": EM_MIN_INTERVAL_HINT,
        "ciFixture": str(default_universe_fixture_path().name),
        "dailySample": str(default_daily_universe_path().name),
    }
