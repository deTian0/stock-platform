"""Brief SQLite repository tests (temp file / memory; no public net)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_research.persistence import (
    SqliteBriefRepository,
    open_brief_repository,
    reset_brief_repository_cache,
    resolve_sqlite_path,
)


def _sample_brief(**overrides):
    base = {
        "asof": "2026-09-02",
        "provider": "replay",
        "universeTier": "watch",
        "universeSize": 3,
        "panelSize": 3,
        "topN": 2,
        "softGates": True,
        "gatesRelaxed": False,
        "dataNote": "单测样例",
        "generatedAt": "2026-09-15T03:00:00+00:00",
        "environment": "SIMULATE",
        "picks": [
            {
                "rank": 1,
                "symbol": "600519",
                "composite_score": 1.23,
                "reason": "score=1.2300",
            },
            {"rank": 2, "symbol": "000001", "composite_score": 0.9},
        ],
    }
    base.update(overrides)
    return base


def test_resolve_sqlite_path_relative_and_memory() -> None:
    assert resolve_sqlite_path("sqlite:///:memory:") == ":memory:"
    p = resolve_sqlite_path("sqlite:///./data/stock_platform.db")
    assert isinstance(p, Path)
    assert "stock_platform.db" in str(p).replace("\\", "/")


def test_sqlite_repo_save_get_list_upsert(tmp_path: Path) -> None:
    db = tmp_path / "briefs.db"
    repo = SqliteBriefRepository(db)
    r1 = repo.save(_sample_brief(), symbols=["600519", "000001", "510300"])
    assert r1.asof == "2026-09-02"
    assert len(r1.picks) == 2
    assert r1.environment == "SIMULATE"
    assert r1.symbols == ["600519", "000001", "510300"]

    got = repo.get_by_asof("2026-09-02")
    assert got is not None
    assert got.picks[0]["symbol"] == "600519"
    assert got.provider == "replay"

    created = got.created_at
    r2 = repo.save(
        _sample_brief(provider="tushare_http", picks=[{"rank": 1, "symbol": "510300"}]),
        symbols=["510300"],
    )
    assert r2.provider == "tushare_http"
    assert len(r2.picks) == 1
    assert r2.created_at == created  # first-write created_at preserved
    assert r2.updated_at >= created

    listed = repo.list_recent(limit=10)
    assert len(listed) == 1
    assert listed[0].summary_dict()["pickCount"] == 1

    repo.save(_sample_brief(asof="2026-09-01", picks=[]))
    listed2 = repo.list_recent(limit=10)
    assert [x.asof for x in listed2] == ["2026-09-02", "2026-09-01"]


def test_open_brief_repository_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_brief_repository_cache()
    monkeypatch.setenv("STOCK_PLATFORM_DB_URL", "sqlite:///:memory:")
    reset_brief_repository_cache()
    repo = open_brief_repository()
    repo.save(_sample_brief(asof="2026-08-01"))
    assert repo.get_by_asof("2026-08-01") is not None
    reset_brief_repository_cache()


def test_save_rejects_missing_asof(tmp_path: Path) -> None:
    repo = SqliteBriefRepository(tmp_path / "x.db")
    with pytest.raises(ValueError, match="asof"):
        repo.save({"picks": []})


def test_session_never_resolves_the_repo_data_dir() -> None:
    """ADR 0069 — the pytest session must not write the production stores.

    Both runtime stores default to cwd-relative paths under the repo's own
    ``data/``. ``test_daily_cli_settle_after_logs_performance`` drove the whole
    CLI without pinning ``STOCK_PLATFORM_DB_URL``, so every full-suite run
    upserted a fixture brief into the authoritative archive — and because the
    digest renders the latest ``asof``, that row shadowed the genuine brief and
    the user-visible daily report went blank. The repo-root ``conftest.py``
    redirects both stores; this test fails loudly if that guard is removed.
    """
    from stock_platform_research.performance import default_performance_log_path

    repo_data = (Path(__file__).resolve().parents[3] / "data").resolve()
    resolved = {
        "brief db": Path(resolve_sqlite_path()).resolve(),
        "perf log": Path(default_performance_log_path()).resolve(),
    }
    for label, path in resolved.items():
        assert repo_data not in path.parents, f"{label} targets the repo data dir: {path}"
