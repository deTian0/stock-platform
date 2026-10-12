"""Repo-root pytest guard — the test suite must never write the production data dir.

``stock-platform`` resolves its authoritative *runtime* stores from cwd-relative
defaults (``ADR 0049`` / ``ADR 0057``):

    brief archive + hit cycles : ``STOCK_PLATFORM_DB_URL``            -> ``./data/stock_platform.db``
    performance decision log   : ``STOCK_PLATFORM_PERFORMANCE_LOG``    -> ``./data/recommend_decisions.jsonl``

A test that drives the daily CLI / pipeline (or the workbench routes) without
overriding those two writes straight into the repo's real ``data/``. That is not
a theoretical risk: ``test_daily_cli_settle_after_logs_performance`` did exactly
this, upserting a fixture brief for ``2026-09-02`` into the production archive on
*every* full-suite run. Because the digest renders the latest ``asof``, the
polluted row shadowed the genuine brief and the user-visible daily report went
blank (``ADR 0069``).

Redirect both stores for the whole session **at import time** — before any test
module body (or ``.env`` load) can capture the production defaults — and hand
the scratch dir back at exit. Set ``STOCK_PLATFORM_TEST_DATA_DIR`` to keep a copy
of the scratch files for debugging instead of discarding them.

Import-time setup alone proved insufficient: a test that assigns or deletes these
variables directly (instead of using ``monkeypatch``) re-points *every later test*
at the repo ``data/`` — one new test did exactly that and re-introduced the very
pollution this file exists to prevent. So the redirect is also **re-asserted
before every test** by an autouse fixture, which makes the guard idempotent and
self-healing (``ADR 0070``).
"""

from __future__ import annotations

import atexit
import os
import shutil
import tempfile
from pathlib import Path

import pytest

#: Env vars that decide where the *runtime* stores live.
GUARDED_ENV = ("STOCK_PLATFORM_DB_URL", "STOCK_PLATFORM_PERFORMANCE_LOG")

_scratch = Path(tempfile.mkdtemp(prefix="stock-platform-tests-"))
_saved: dict[str, str | None] = {key: os.environ.get(key) for key in GUARDED_ENV}

_REDIRECT: dict[str, str] = {
    "STOCK_PLATFORM_DB_URL": f"sqlite:///{(_scratch / 'briefs.db').as_posix()}",
    "STOCK_PLATFORM_PERFORMANCE_LOG": str(_scratch / "recommend_decisions.jsonl"),
}
os.environ.update(_REDIRECT)


@pytest.fixture(autouse=True)
def _enforce_test_data_isolation() -> None:
    """Re-assert the redirect before **every** test (self-healing guard)."""
    for key, value in _REDIRECT.items():
        os.environ[key] = value
    yield


def _restore() -> None:
    keep = os.environ.get("STOCK_PLATFORM_TEST_DATA_DIR")
    if keep:
        shutil.copytree(_scratch, keep, dirs_exist_ok=True)
    for key, value in _saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    shutil.rmtree(_scratch, ignore_errors=True)


atexit.register(_restore)
