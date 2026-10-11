"""Repo-root ``.env`` loader — one implementation for every CLI / entry point.

Why this module exists
----------------------
``start-workbench.bat`` injects ``.env`` line by line before starting the
Workbench, so the HTTP app has always had the live token / DB path. Every
**CLI** (``stock-platform-daily``, ``-refresh``, ``-backtest``, ``-hits`` …) reads
plain :data:`os.environ` and therefore saw an empty environment when launched
directly or from Task Scheduler. The observed failure was::

    live provider='cn_tushare_http' requires STOCK_PLATFORM_TUSHARE_TOKEN
    (set in local .env only; never commit the token).
    Do not use STOCK_PLATFORM_BRIEF_FALLBACK to fake live.

and, for the offline path::

    FileNotFoundError: 未配置或找不到引擎 market.db：请设置
    STOCK_PLATFORM_ENGINE_MARKET_DB …

Both are the *same* root cause: nobody loaded ``.env``. This module fixes it at
the entry-point level so manual runs, scheduled tasks and ad-hoc ``python -m``
invocations behave identically to the ``.bat`` launch.

Contract
--------
- **Never override** an existing environment variable (``setdefault``
  semantics): an explicitly exported value always wins, which keeps CI, unit
  tests and ``$env:FOO=...`` debugging authoritative.
- **Never raise**: a missing or unreadable ``.env`` is normal (CI has none) and
  must not break a run.
- Supports ``KEY=VALUE``, ``#`` comments, blank lines, an optional leading
  ``export``, quoted values and inline ``#`` comments after an unquoted value.
- Idempotent and cheap: repeated calls after the first are a no-op unless
  ``override=True`` is passed.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping
ENV_DOTENV_PATH = "STOCK_PLATFORM_DOTENV"
ENV_DOTENV_DISABLE = "STOCK_PLATFORM_DOTENV_DISABLE"

# Any of these being "1/true" disables the implicit .env load. ``PYTEST_CURRENT_TEST``
# is set by pytest for every test, so a test run never inherits the developer's real
# token / market.db by accident — tests must inject their own environment explicitly.
_TEST_MARKERS = ("PYTEST_CURRENT_TEST", "PYTEST_VERSION")

# Marker so a second call in the same process is free.
_LOADED: set[str] = set()


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def is_disabled(env: Mapping[str, str] | None = None) -> bool:
    """Whether the implicit ``.env`` load is switched off for this process."""
    source: Mapping[str, str] = os.environ if env is None else env
    if _truthy(source.get(ENV_DOTENV_DISABLE)):
        return True
    # Under pytest the developer's real .env must not leak into tests.
    return any(str(source.get(marker) or "").strip() for marker in _TEST_MARKERS)


def _repo_root_candidates() -> list[Path]:
    """Directories to search for ``.env``, nearest-first.

    ``__file__`` lives at ``<repo>/packages/research/src/stock_platform_research``
    in a source checkout, so ``parents[3]`` is the repo root. Installed layouts
    differ, hence the walk-up instead of a single hard-coded hop.
    """
    here = Path(__file__).resolve()
    out: list[Path] = []
    for parent in here.parents:
        out.append(parent)
    out.append(Path.cwd())
    return out


def find_dotenv_path(explicit: str | Path | None = None) -> Path | None:
    """Locate the ``.env`` this process should load (``None`` if none exists).

    Precedence: explicit arg > ``STOCK_PLATFORM_DOTENV`` > nearest ``.env``
    found walking up from this module > ``.env`` in the current directory.
    """
    if explicit is not None:
        candidate = Path(explicit).expanduser()
        return candidate if candidate.is_file() else None

    from_env = (os.environ.get(ENV_DOTENV_PATH) or "").strip()
    if from_env:
        candidate = Path(from_env).expanduser()
        return candidate if candidate.is_file() else None

    for directory in _repo_root_candidates():
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def parse_dotenv_text(text: str) -> dict[str, str]:
    """Parse ``.env`` content into a plain mapping (no environment mutation).

    Kept separate from :func:`load_dotenv` so the parsing rules are unit-testable
    without touching :data:`os.environ`.
    """
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            quote = value[0]
            value = value[1:-1]
            if quote == '"':
                # Only the escapes a dotenv file realistically needs.
                value = value.replace("\\n", "\n").replace('\\"', '"')
        elif " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        values[key] = value
    return values


def load_dotenv(
    path: str | Path | None = None,
    *,
    override: bool = False,
    env: MutableMapping[str, str] | None = None,
    required: Iterable[str] | None = None,
    force: bool = False,
) -> dict[str, str]:
    """Load ``.env`` into ``env`` (defaults to :data:`os.environ`).

    Returns the mapping of values that were actually *applied* (so callers and
    tests can assert on it). Missing file → ``{}`` and no exception.

    Parameters
    ----------
    path:
        Explicit ``.env`` location; otherwise :func:`find_dotenv_path`.
    override:
        When ``True``, ``.env`` wins over an already-set variable. Default
        ``False`` keeps an explicitly exported value authoritative.
    env:
        Mapping to write into; defaults to :data:`os.environ` (the real entry
        point uses this). Tests pass their own dict.
    required:
        Names that must resolve after loading; a missing one raises
        :class:`DotenvMissingError` instead of failing much later with a
        confusing provider error.
    force:
        Bypass the pytest / ``STOCK_PLATFORM_DOTENV_DISABLE`` guard. Needed by
        the loader's own tests, which must exercise the real thing.
    """
    target: MutableMapping[str, str] = os.environ if env is None else env
    # The guard protects *any* implicit load, reading its markers from the real
    # process environment (so an injected mapping cannot smuggle a load past it,
    # and the pytest marker is honoured even when the caller passes its own env).
    # Loader tests pass ``force=True`` to exercise reality.
    if not force and is_disabled(os.environ):
        return {}

    resolved = find_dotenv_path(path)
    if resolved is None:
        applied: dict[str, str] = {}
    else:
        cache_key = f"{resolved}:{override}"
        if cache_key in _LOADED and env is None:
            applied = {}
        else:
            try:
                text = resolved.read_text(encoding="utf-8")
            except OSError:
                return {}
            parsed = parse_dotenv_text(text)
            applied = {}
            for key, value in parsed.items():
                if override or key not in target:
                    target[key] = value
                    applied[key] = value
            if env is None:
                _LOADED.add(cache_key)

    if required:
        missing = [name for name in required if not str(target.get(name, "")).strip()]
        if missing:
            raise DotenvMissingError(
                f"missing required env var(s) {missing}; looked in {resolved or 'no .env found'}"
            )
    return applied


class DotenvMissingError(RuntimeError):
    """A ``required`` key is still unset after loading ``.env``."""


def reset_dotenv_cache() -> None:
    """Forget the "already loaded" markers (test helper)."""
    _LOADED.clear()


__all__ = [
    "ENV_DOTENV_DISABLE",
    "ENV_DOTENV_PATH",
    "DotenvMissingError",
    "find_dotenv_path",
    "is_disabled",
    "load_dotenv",
    "parse_dotenv_text",
    "reset_dotenv_cache",
]
