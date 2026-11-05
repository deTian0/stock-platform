"""T3 — market.db data-quality scan (zero network, read-only, never throws).

Five checks (ADR 0091 / ``docs/contracts/data-quality.md``):

1. pct_chg scale mix (reuse :func:`pct_scale.detect_pct_scale`)
2. halt / zero-volume window
3. close jump without adj-factor hint
4. dirty codes (non-6-digit / prefix inconsistency)
5. declared benchmark + watch ETF coverage gaps
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from .benchmark import resolve_benchmark_symbol
from .pct_scale import SCALE_FRACTION, SCALE_POINTS, detect_pct_scale
from .portfolio import is_etf, is_fund

SECTION_OK = "ok"
SECTION_WARN = "warn"
SECTION_DEGRADED = "degraded"
SECTION_EMPTY = "empty"
SECTION_UNAVAILABLE = "unavailable"

DEFAULT_LOOKBACK_DAYS = 60
DEFAULT_SAMPLE_CODES = 400
ZERO_VOL_RATIO_WARN = 0.35
CLOSE_JUMP_FRACTION = 0.25  # |Δclose/close| ≥ 25% → corporate-action suspect
PCT_MIX_RATIO_DEGRADED = 0.25  # fraction of sampled codes disagreeing with prior

# Common on-exchange ETFs to probe for coverage (platform watch list; not exhaustive).
DEFAULT_WATCH_ETFS: tuple[str, ...] = (
    "510300",
    "510500",
    "588000",
    "588080",
    "159915",
    "159919",
)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _open_ro(db_path: str | Path) -> sqlite3.Connection:
    uri = "file:%s?mode=ro" % str(Path(db_path)).replace("\\", "/")
    return sqlite3.connect(uri, uri=True)


def _tables(con: sqlite3.Connection) -> set[str]:
    rows = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {str(r[0]) for r in rows}


def _latest_trade_date(con: sqlite3.Connection) -> str | None:
    row = con.execute("SELECT MAX(date) FROM daily_price").fetchone()
    if not row or not row[0]:
        return None
    return str(row[0])[:10]


def _load_window_bars(
    con: sqlite3.Connection,
    *,
    start: str,
    end: str,
    sample_codes: int,
) -> pd.DataFrame:
    """Load a bounded recent window; optionally subsample codes for scale voting."""
    codes = [
        str(r[0])
        for r in con.execute(
            "SELECT DISTINCT code FROM daily_price "
            "WHERE date >= ? AND date <= ? ORDER BY code LIMIT ?",
            (start, end, max(1, int(sample_codes))),
        ).fetchall()
    ]
    if not codes:
        return pd.DataFrame()
    placeholders = ",".join("?" for _ in codes)
    rows = con.execute(
        f"SELECT code, date, open, high, low, close, vol, pct_chg "
        f"FROM daily_price WHERE date >= ? AND date <= ? AND code IN ({placeholders})",
        [start, end, *codes],
    ).fetchall()
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(
        rows,
        columns=["code", "date", "open", "high", "low", "close", "vol", "pct_chg"],
    )
    df["date"] = df["date"].astype(str).str[:10]
    for col in ("open", "high", "low", "close", "vol", "pct_chg"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _bare(code: str) -> str:
    s = str(code or "").strip().upper()
    if "." in s:
        s = s.split(".", 1)[0]
    for p in ("SH", "SZ", "BJ"):
        if s.startswith(p) and s[len(p) :].isdigit():
            s = s[len(p) :]
            break
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[-6:].zfill(6) if digits else ""


def _check_pct_scale(bars: pd.DataFrame) -> dict[str, Any]:
    if bars.empty or "pct_chg" not in bars.columns:
        return {
            "id": "pctScale",
            "status": SECTION_EMPTY,
            "mixedCodes": 0,
            "sampledCodes": 0,
            "detail": "无 pct_chg 样本",
        }
    # detect_pct_scale expects bare-ish codes; keep engine codes as-is for grouping.
    scales = detect_pct_scale(bars)
    if scales.empty:
        return {
            "id": "pctScale",
            "status": SECTION_EMPTY,
            "mixedCodes": 0,
            "sampledCodes": 0,
            "detail": "无法拟合尺度",
        }
    # Prior: stock → fraction, fund/etf → points. Flag codes whose vote disagrees.
    mixed: list[str] = []
    for code, scale in scales.items():
        bare = _bare(str(code))
        prior = SCALE_POINTS if (is_etf(bare) or is_fund(bare)) else SCALE_FRACTION
        if scale != prior:
            mixed.append(str(code))
    n = len(scales)
    ratio = (len(mixed) / n) if n else 0.0
    status = SECTION_OK
    if mixed:
        status = SECTION_DEGRADED if ratio >= PCT_MIX_RATIO_DEGRADED else SECTION_WARN
    return {
        "id": "pctScale",
        "status": status,
        "sampledCodes": n,
        "mixedCodes": len(mixed),
        "mixedRatio": round(ratio, 4),
        "examples": mixed[:12],
        "detail": (
            f"相对资产类先验，{len(mixed)}/{n} 码尺度疑似混用"
            if mixed
            else f"抽样 {n} 码尺度与先验一致"
        ),
    }


def _check_halts(bars: pd.DataFrame) -> dict[str, Any]:
    if bars.empty:
        return {
            "id": "halts",
            "status": SECTION_EMPTY,
            "detail": "无成交量样本",
        }
    vol = bars["vol"].fillna(0.0)
    zero = int((vol <= 0).sum())
    total = int(len(bars))
    ratio = zero / total if total else 0.0
    # Per-code consecutive zero days (last window, trailing).
    long_halts: list[dict[str, Any]] = []
    for code, g in bars.sort_values("date").groupby("code", sort=False):
        streak = 0
        max_streak = 0
        for v in g["vol"].fillna(0.0).tolist():
            if v <= 0:
                streak += 1
                max_streak = max(max_streak, streak)
            else:
                streak = 0
        if max_streak >= 5:
            long_halts.append({"code": str(code), "maxZeroStreak": max_streak})
    long_halts.sort(key=lambda r: -int(r["maxZeroStreak"]))
    status = SECTION_WARN if ratio >= ZERO_VOL_RATIO_WARN or long_halts else SECTION_OK
    return {
        "id": "halts",
        "status": status,
        "zeroVolumeRows": zero,
        "totalRows": total,
        "zeroVolumeRatio": round(ratio, 4),
        "longHaltExamples": long_halts[:12],
        "detail": (
            f"零成交行占比 {ratio:.1%}；连续≥5 日零成交码 {len(long_halts)}"
        ),
    }


def _check_close_jumps(
    con: sqlite3.Connection,
    bars: pd.DataFrame,
    tables: set[str],
) -> dict[str, Any]:
    if bars.empty:
        return {"id": "closeJumps", "status": SECTION_EMPTY, "detail": "无收盘样本"}
    suspects: list[dict[str, Any]] = []
    has_adj = "adj_factor" in tables or "adjust_factor" in tables
    adj_table = "adj_factor" if "adj_factor" in tables else (
        "adjust_factor" if "adjust_factor" in tables else None
    )
    for code, g in bars.sort_values("date").groupby("code", sort=False):
        closes = g[["date", "close"]].dropna()
        if len(closes) < 2:
            continue
        prev = closes["close"].shift(1)
        ret = (closes["close"] - prev) / prev.replace(0, pd.NA)
        for dt, r in zip(closes["date"], ret):
            if r is None or (isinstance(r, float) and (r != r)):
                continue
            if abs(float(r)) < CLOSE_JUMP_FRACTION:
                continue
            has_factor = False
            if adj_table is not None:
                try:
                    row = con.execute(
                        f"SELECT 1 FROM {adj_table} WHERE code=? AND date=? LIMIT 1",
                        (str(code), str(dt)[:10]),
                    ).fetchone()
                    has_factor = bool(row)
                except Exception:  # noqa: BLE001
                    has_factor = False
            if has_factor:
                continue
            suspects.append(
                {
                    "code": str(code),
                    "date": str(dt)[:10],
                    "jump": round(float(r), 4),
                    "adjFactorPresent": has_adj and has_factor,
                }
            )
    status = SECTION_OK
    if suspects:
        status = SECTION_DEGRADED if len(suspects) >= 20 else SECTION_WARN
    return {
        "id": "closeJumps",
        "status": status,
        "suspectCount": len(suspects),
        "adjFactorTable": adj_table,
        "examples": suspects[:12],
        "detail": (
            f"{len(suspects)} 处 |Δclose|≥{CLOSE_JUMP_FRACTION:.0%} 且无复权因子行"
            if suspects
            else "未发现无复权说明的大幅跳变"
        ),
    }


def _check_dirty_codes(con: sqlite3.Connection) -> dict[str, Any]:
    try:
        rows = con.execute("SELECT DISTINCT code FROM daily_price").fetchall()
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "dirtyCodes",
            "status": SECTION_UNAVAILABLE,
            "detail": f"读码失败：{type(exc).__name__}",
        }
    dirty: list[dict[str, str]] = []
    for (raw,) in rows:
        code = str(raw or "")
        bare = _bare(code)
        if not (bare.isdigit() and len(bare) == 6):
            dirty.append({"code": code, "reason": "non_6_digit"})
            continue
        # Fund/ETF codes should match exchange_prefix expectations loosely:
        # 5xxxxx are SH funds; if stored with .SZ suffix → dirty.
        if bare.startswith("5") and code.upper().endswith(".SZ"):
            dirty.append({"code": code, "reason": "sh_fund_sz_suffix"})
        elif bare.startswith("1") and code.upper().endswith(".SH"):
            dirty.append({"code": code, "reason": "sz_fund_sh_suffix"})
        # Non-ETF 5/1 funds are valid; no dirty flag solely for missing ETF table.
        _ = is_etf(bare)
    status = SECTION_WARN if dirty else SECTION_OK
    return {
        "id": "dirtyCodes",
        "status": status,
        "dirtyCount": len(dirty),
        "examples": dirty[:20],
        "detail": f"脏码 {len(dirty)}" if dirty else "未发现明显脏码",
    }


def _code_dates(con: sqlite3.Connection, code: str, start: str, end: str) -> set[str]:
    variants = {code, f"{code}.SH", f"{code}.SZ", f"{code}.BJ"}
    bare = _bare(code)
    if bare:
        variants.update({bare, f"{bare}.SH", f"{bare}.SZ", f"{bare}.BJ"})
    out: set[str] = set()
    for c in variants:
        try:
            rows = con.execute(
                "SELECT date FROM daily_price WHERE code=? AND date>=? AND date<=?",
                (c, start, end),
            ).fetchall()
        except Exception:  # noqa: BLE001
            continue
        for (d,) in rows:
            out.add(str(d)[:10])
    return out


def _check_coverage_gaps(
    con: sqlite3.Connection,
    *,
    asof: str,
    start: str,
    benchmark: str,
    watch_etfs: Sequence[str],
) -> dict[str, Any]:
    # Trading days present in warehouse for the window (any code).
    try:
        days = [
            str(r[0])[:10]
            for r in con.execute(
                "SELECT DISTINCT date FROM daily_price WHERE date>=? AND date<=? ORDER BY date",
                (start, asof),
            ).fetchall()
        ]
    except Exception as exc:  # noqa: BLE001
        return {
            "id": "coverageGaps",
            "status": SECTION_UNAVAILABLE,
            "detail": f"读交易日失败：{type(exc).__name__}",
        }
    day_set = set(days)
    bench_days = _code_dates(con, benchmark, start, asof)
    bench_missing = sorted(day_set - bench_days) if day_set else []
    etf_gaps: list[dict[str, Any]] = []
    for etf in watch_etfs:
        d = _code_dates(con, etf, start, asof)
        missing = sorted(day_set - d) if day_set else []
        if not d:
            etf_gaps.append({"code": etf, "missingAll": True, "missingDays": len(day_set)})
        elif missing:
            etf_gaps.append(
                {"code": etf, "missingAll": False, "missingDays": len(missing), "examples": missing[:5]}
            )
    status = SECTION_OK
    if bench_missing or not bench_days:
        status = SECTION_DEGRADED
    elif etf_gaps:
        status = SECTION_WARN
    return {
        "id": "coverageGaps",
        "status": status,
        "benchmark": benchmark,
        "benchmarkPresentDays": len(bench_days),
        "windowDays": len(day_set),
        "benchmarkMissingDays": len(bench_missing),
        "benchmarkMissingExamples": bench_missing[:8],
        "etfGaps": etf_gaps,
        "detail": (
            f"基准 {benchmark} 缺 {len(bench_missing)}/{len(day_set)} 日"
            if (bench_missing or not bench_days)
            else (
                f"基准齐；{len(etf_gaps)} 只观察 ETF 有缺口"
                if etf_gaps
                else "基准与观察 ETF 覆盖正常"
            )
        ),
    }


def _roll_status(checks: Sequence[Mapping[str, Any]]) -> str:
    ranks = {
        SECTION_OK: 0,
        SECTION_EMPTY: 1,
        SECTION_WARN: 2,
        SECTION_UNAVAILABLE: 2,
        SECTION_DEGRADED: 3,
    }
    worst = SECTION_OK
    for c in checks:
        st = str(c.get("status") or SECTION_UNAVAILABLE)
        if ranks.get(st, 2) > ranks.get(worst, 0):
            worst = st if st in ranks else SECTION_WARN
    if worst == SECTION_EMPTY:
        return SECTION_UNAVAILABLE
    return worst


def collect_data_quality(
    *,
    market_db: str | Path | None = None,
    asof: str | None = None,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    sample_codes: int = DEFAULT_SAMPLE_CODES,
    benchmark: str | None = None,
    watch_etfs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Scan ``market.db`` and return a total-function quality payload."""
    asof_day = str(asof or date.today().isoformat())[:10]
    bench = _bare(benchmark or resolve_benchmark_symbol()) or resolve_benchmark_symbol()
    etfs = tuple(watch_etfs) if watch_etfs is not None else DEFAULT_WATCH_ETFS

    path: Path | None = None
    if market_db:
        path = Path(str(market_db))
    else:
        try:
            from stock_platform_providers import resolve_engine_market_db

            resolved = resolve_engine_market_db()
            path = Path(resolved) if resolved else None
        except Exception:  # noqa: BLE001
            path = None

    base: dict[str, Any] = {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "asof": asof_day,
        "generatedAt": _utcnow_iso(),
        "lookbackDays": int(lookback_days),
        "benchmark": bench,
        "marketDb": str(path) if path else None,
        "disclaimer": (
            "只读体检：零网络、不写行情库；严重项仅 degraded，永不阻断选股/日更；"
            "见 docs/contracts/data-quality.md。"
        ),
    }

    if path is None or not path.is_file():
        return {
            **base,
            "status": SECTION_UNAVAILABLE,
            "reason": "未配置或找不到引擎 market.db（STOCK_PLATFORM_ENGINE_MARKET_DB）",
            "checks": [],
        }

    try:
        con = _open_ro(path)
    except Exception as exc:  # noqa: BLE001
        return {
            **base,
            "status": SECTION_UNAVAILABLE,
            "reason": f"无法只读打开：{type(exc).__name__}: {exc}",
            "checks": [],
        }

    try:
        tables = _tables(con)
        if "daily_price" not in tables:
            return {
                **base,
                "status": SECTION_UNAVAILABLE,
                "reason": "missing_table: daily_price",
                "checks": [],
            }
        latest = _latest_trade_date(con) or asof_day
        end = min(asof_day, latest)
        start = (date.fromisoformat(end) - timedelta(days=max(1, int(lookback_days)))).isoformat()
        bars = _load_window_bars(con, start=start, end=end, sample_codes=sample_codes)

        checks: list[dict[str, Any]] = []
        try:
            checks.append(_check_pct_scale(bars))
        except Exception as exc:  # noqa: BLE001
            checks.append({"id": "pctScale", "status": SECTION_UNAVAILABLE, "detail": type(exc).__name__})
        try:
            checks.append(_check_halts(bars))
        except Exception as exc:  # noqa: BLE001
            checks.append({"id": "halts", "status": SECTION_UNAVAILABLE, "detail": type(exc).__name__})
        try:
            checks.append(_check_close_jumps(con, bars, tables))
        except Exception as exc:  # noqa: BLE001
            checks.append({"id": "closeJumps", "status": SECTION_UNAVAILABLE, "detail": type(exc).__name__})
        try:
            checks.append(_check_dirty_codes(con))
        except Exception as exc:  # noqa: BLE001
            checks.append({"id": "dirtyCodes", "status": SECTION_UNAVAILABLE, "detail": type(exc).__name__})
        try:
            checks.append(
                _check_coverage_gaps(
                    con, asof=end, start=start, benchmark=bench, watch_etfs=etfs
                )
            )
        except Exception as exc:  # noqa: BLE001
            checks.append(
                {"id": "coverageGaps", "status": SECTION_UNAVAILABLE, "detail": type(exc).__name__}
            )

        status = _roll_status(checks)
        return {
            **base,
            "asof": end,
            "windowStart": start,
            "latestTradeDate": latest,
            "sampledRows": int(len(bars)),
            "status": status,
            "checks": checks,
        }
    finally:
        try:
            con.close()
        except Exception:  # noqa: BLE001
            pass


def data_quality_section(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Shape for ``loop_health`` segment ``dataQuality``."""
    p = dict(payload or {})
    status = str(p.get("status") or SECTION_UNAVAILABLE)
    # Map data-quality vocabulary onto loop-health section vocabulary.
    if status == SECTION_DEGRADED:
        section_status = SECTION_DEGRADED
    elif status == SECTION_WARN:
        section_status = SECTION_WARN
    elif status == SECTION_OK:
        section_status = SECTION_OK
    elif status == SECTION_EMPTY:
        section_status = SECTION_EMPTY
    else:
        section_status = SECTION_UNAVAILABLE
    checks = list(p.get("checks") or [])
    return {
        "status": section_status,
        "asof": p.get("asof"),
        "checkCount": len(checks),
        "degradedChecks": [
            c.get("id") for c in checks if c.get("status") == SECTION_DEGRADED
        ],
        "warnChecks": [
            c.get("id")
            for c in checks
            if c.get("status") in {SECTION_WARN, SECTION_UNAVAILABLE}
        ],
        "summary": [
            {"id": c.get("id"), "status": c.get("status"), "detail": c.get("detail")}
            for c in checks
        ],
        "reason": p.get("reason"),
        "marketDb": p.get("marketDb"),
    }


def render_data_quality_markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        "# 数据质量体检",
        "",
        f"- asof：`{payload.get('asof')}`",
        f"- 状态：**{payload.get('status')}**",
        f"- market.db：`{payload.get('marketDb') or '—'}`",
        f"- 窗口：`{payload.get('windowStart') or '—'}` → `{payload.get('asof')}`",
        f"- 基准：`{payload.get('benchmark')}`",
        "",
        "## 检查项",
        "",
        "| id | status | detail |",
        "|----|--------|--------|",
    ]
    for c in payload.get("checks") or []:
        lines.append(
            f"| {c.get('id')} | {c.get('status')} | {str(c.get('detail') or '').replace('|', '/')} |"
        )
    if payload.get("reason"):
        lines.extend(["", f"> {payload['reason']}"])
    lines.extend(["", str(payload.get("disclaimer") or ""), ""])
    return "\n".join(lines)


__all__ = [
    "DEFAULT_LOOKBACK_DAYS",
    "DEFAULT_WATCH_ETFS",
    "SECTION_DEGRADED",
    "SECTION_EMPTY",
    "SECTION_OK",
    "SECTION_UNAVAILABLE",
    "SECTION_WARN",
    "collect_data_quality",
    "data_quality_section",
    "render_data_quality_markdown",
]
