"""日用循环健康度单点（loop health）——「今天的循环到底正不正常」的一个只读答案。

背景（R3，v4.7.0）::

    平台的日用循环由五段拼成：**供数 → 选股 → 命中记账 → 绩效结算 → 名称展示**。
    每段各自有守卫（供数 C2 `coverage_snapshot`、文档 ADR 0049 / 0057 / 0068 / 0072），
    但**没有任何一个地方把五段放在一起裁决**。后果是「早上打开日报，看起来一切正常」，
    而真相可能是：库里供数滞后 3 个交易日、最新 brief 是空的、绩效样本只有 3 条。

    本模块把这些**已存在的只读信号**聚合成一份可机读（JSON）+ 可人读（Markdown）的
    体检报告，并给出一个**规则化**的裁决（``ok`` / ``degraded`` / ``blocked``）。

聚合的六路信号（全部**只读**）

1. ``coverage``       —— 复用 ``EngineSqliteProvider.coverage_snapshot``（C2 单点，**懒导入**）
2. ``latestBrief``    —— 平台 SQLite ``daily_briefs`` 最新一行（ADR 0049）
3. ``hits``           —— 命中记账三累计（ADR 0057 / X3）
4. ``performance``    —— ``recommend_decisions.jsonl`` 的 settled / pending（ADR 0068）
5. ``symbolMaster``   —— 本地名称主表行数（ADR 0072）
6. ``nextSettlement`` —— 由 brief asof + ``holding`` 推出下一个预期结算日（**提示**，非承诺）

口径（硬约束）

- **零网络**：本模块不发布任何 HTTP 请求，也不触发任何 provider 抓数。
- **只读**：不写任何库 / 表；``market.db`` 以 ``mode=ro`` 打开（由 provider 保证）。
- **fail-closed**：某段缺失 → 该段 ``status="unavailable"`` 并附 ``reason``，
  **绝不**用默认值冒充「正常」。
- **方法永不抛**：任何一段异常都被就地降级为 ``unavailable``，其余段照常产出；
  `collect_loop_health` 对调用方是 total function。

历史台账（趋势面，T1 / v4.9.0）

``collect_loop_health`` 额外读一段 **``history``**：来自 ``<dir>/history.jsonl``
（``append_history`` 追加，CLI 落盘时写），给出 ``degradedStreak`` / ``blockedStreak`` /
``notOkStreak``（**含本次**；同一天重跑只算一次，本次覆盖当天旧记录）与近 N 天裁决。
**``history`` 不参与裁决** —— 裁决仍只看六路信号的当下快照，历史只回答「这次降级是持续还是偶发」。
台账只写平台自有 ``data/``，绝不写 ``market.db`` 或任何库。

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import json
import os
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .hit_tracking import HIT_SESSION_TYPES, open_hit_repository
from .performance import (
    MIN_MEANINGFUL_SAMPLE,
    default_performance_log_path,
    load_jsonl,
    performance_summary,
)
from .persistence import open_brief_repository
from .symbol_master import open_symbol_master

# 默认输出目录（CLI 用）。相对 cwd，与 data/ 其它产物同级。
DEFAULT_LOOP_HEALTH_OUT_DIR = "./data/health"

# 历史台账（T1 / v4.9.0）—— 每次体检追加一行 ``{ts, asof, status, failed, warned}``。
# 目录可用 ``STOCK_PLATFORM_LOOP_HEALTH_DIR`` 覆盖；台账**只写平台自有 data/**，
# 绝不写 ``market.db`` 或任何库（承接 ADR 0058 只读）。
LOOP_HEALTH_HISTORY_FILENAME = "history.jsonl"
ENV_LOOP_HEALTH_DIR = "STOCK_PLATFORM_LOOP_HEALTH_DIR"
DEFAULT_HISTORY_RECENT = 7
HISTORY_MAX_RECORDS = 400

# 各段 status 取值（fail-closed 的显式词表）。
SECTION_OK = "ok"
SECTION_EMPTY = "empty"
SECTION_UNAVAILABLE = "unavailable"

# 供数段「不可判」的硬失败档 —— 没有供数就是物理上选不出票，不许当「正常」。
# 含 ``error``（库存在但不可读）与 ``unconfigured``（未配置路径）：
# 这两档在 v4.7.0 的裁决里既非 fail 也非 warn，会被误判成 ok（T1 / v4.9.0 修正）。
COVERAGE_HARD_FAIL = frozenset(
    {SECTION_UNAVAILABLE, SECTION_EMPTY, "missing_table", "error", "unconfigured"}
)
# 供数段「可跑但要打折看」的档。
COVERAGE_WARN = frozenset({"stale", "thin"})

# 裁决档位。
VERDICT_OK = "ok"
VERDICT_DEGRADED = "degraded"
VERDICT_BLOCKED = "blocked"

_LEVEL_OK = "ok"
_LEVEL_WARN = "warn"
_LEVEL_FAIL = "fail"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _error_text(exc: BaseException) -> str:
    cls = type(exc).__name__
    msg = str(exc).strip() or cls
    return f"{cls}: {msg}"[:500]


def _section_unavailable(exc: BaseException) -> dict[str, Any]:
    return {
        "status": SECTION_UNAVAILABLE,
        "reason": _error_text(exc),
        "traceback": traceback.format_exc(limit=3),
    }


# --------------------------------------------------------------------------- #
# 1. 供数覆盖率（复用 C2 单点；providers 只能函数内导入）
# --------------------------------------------------------------------------- #
def _collect_coverage(
    market_db: str | Path | None,
    *,
    asof: str | None,
    lookback_days: int | None,
    min_rows: int | None,
) -> dict[str, Any]:
    from stock_platform_providers import (  # type: ignore[import-not-found]
        EngineSqliteProvider,
        resolve_engine_market_db,
    )

    explicit = str(market_db or "").strip()
    path = Path(explicit) if explicit else resolve_engine_market_db()
    if path is None or not Path(path).is_file():
        return {
            "status": SECTION_UNAVAILABLE,
            "source": "engine_sqlite",
            "reason": (
                "引擎 market.db 不可用：请配置 STOCK_PLATFORM_ENGINE_MARKET_DB 指向 "
                "a-stock-engine/data_cache/market.db（只读），或用 --market-db 指定。"
            ),
        }
    provider = EngineSqliteProvider(path)
    kwargs: dict[str, Any] = {}
    if lookback_days is not None:
        kwargs["lookback_days"] = int(lookback_days)
    if min_rows is not None:
        kwargs["min_rows"] = int(min_rows)
    snap = dict(provider.coverage_snapshot(asof=asof, **kwargs) or {})
    snap.setdefault("status", SECTION_UNAVAILABLE)
    snap["source"] = "engine_sqlite"
    return snap


# --------------------------------------------------------------------------- #
# 2. 最新 brief
# --------------------------------------------------------------------------- #
def _collect_latest_brief(db_url: str | Path | None) -> dict[str, Any]:
    repo = open_brief_repository(db_url)
    recent = list(repo.list_recent(limit=1) or [])
    if not recent:
        return {"status": SECTION_EMPTY, "asof": None, "pickCount": 0,
                "reason": "daily_briefs 为空：尚无任何归档 brief。"}
    rec = recent[0]
    return {
        "status": SECTION_OK,
        "asof": str(rec.asof or "")[:10] or None,
        "pickCount": len(rec.picks or []),
        "provider": rec.provider,
        "universeTier": rec.universe_tier,
        "generatedAt": rec.generated_at,
        "updatedAt": rec.updated_at,
    }


# --------------------------------------------------------------------------- #
# 3. 命中记账
# --------------------------------------------------------------------------- #
def _collect_hits(db_url: str | Path | None) -> dict[str, Any]:
    repo = open_hit_repository(db_url)
    per_type: dict[str, Any] = {}
    total_codes = 0
    total_hits = 0
    last_pick: str | None = None
    for st in HIT_SESSION_TYPES:
        rows = list(repo.summary(session_type=st) or [])
        codes = len(rows)
        hits = sum(int(r.get("cumulative_hits") or 0) for r in rows)
        cycles = sum(int(r.get("total_cycles") or 0) for r in rows)
        latest = max((str(r.get("last_pick_date") or "") for r in rows), default="")
        per_type[st] = {
            "sessionType": st,
            "codeCount": codes,
            "cumulativeHits": hits,
            "totalCycles": cycles,
            "lastPickDate": latest[:10] or None,
        }
        total_codes += codes
        total_hits += hits
        if latest:
            last_pick = max(last_pick or "", latest)[:10]
    if total_codes == 0:
        return {
            "status": SECTION_EMPTY,
            "bySession": per_type,
            "totalCodeCount": 0,
            "totalCumulativeHits": 0,
            "lastPickDate": None,
            "reason": "命中记账为空：尚无任何被重复选中的记录。",
        }
    return {
        "status": SECTION_OK,
        "bySession": per_type,
        "totalCodeCount": total_codes,
        "totalCumulativeHits": total_hits,
        "lastPickDate": last_pick,
    }


# --------------------------------------------------------------------------- #
# 4. 绩效闭环
# --------------------------------------------------------------------------- #
def _collect_performance(
    perf_log: str | Path | None,
    *,
    holding_days: int,
) -> dict[str, Any]:
    path = Path(perf_log) if perf_log is not None else default_performance_log_path()
    summary = performance_summary(path)
    entries = load_jsonl(path)
    settled_dates = sorted(
        {str(e.get("date") or "")[:10] for e in entries if not e.get("pending")}
        - {""}
    )
    settled = int(summary.get("settledCount") or 0)
    return {
        "status": SECTION_OK if entries else SECTION_EMPTY,
        "logPath": str(path),
        "totalEntries": int(summary.get("totalEntries") or 0),
        "pendingCount": int(summary.get("pendingCount") or 0),
        "settledCount": settled,
        "avgReturn": (summary.get("metrics") or {}).get("avg_return"),
        "sampleNote": (summary.get("metrics") or {}).get("sample_note"),
        "minMeaningfulSample": int(MIN_MEANINGFUL_SAMPLE),
        "sampleSufficient": settled >= int(MIN_MEANINGFUL_SAMPLE),
        "latestSettledDate": settled_dates[-1] if settled_dates else None,
        "settledDates": settled_dates,
        "holdingDays": int(holding_days),
        **({"reason": "绩效台账为空：尚未记账任何决策。"} if not entries else {}),
    }


# --------------------------------------------------------------------------- #
# 5. 名称主表
# --------------------------------------------------------------------------- #
def _collect_symbol_master(db_url: str | Path | None) -> dict[str, Any]:
    stats = open_symbol_master(db_url).stats()
    total = int(stats.get("total") or 0)
    out: dict[str, Any] = {
        "status": SECTION_OK if total else SECTION_EMPTY,
        "total": total,
        "bySource": list(stats.get("bySource") or []),
    }
    if not total:
        out["reason"] = "symbol_master 为空：名称将全部显示占位符「—」。"
    return out


# --------------------------------------------------------------------------- #
# 6. 下一个预期结算日（提示，非承诺）
# --------------------------------------------------------------------------- #
def _trading_day_lag(start: str | None, end: str | None) -> int | None:
    """``start`` 之后到 ``end``（含）之间的交易日数；无法判定 → ``None``。"""
    if not start or not end:
        return None
    s, e = str(start)[:10], str(end)[:10]
    if s >= e:
        return 0
    try:
        from stock_platform_providers import get_trading_calendar  # type: ignore

        cal = get_trading_calendar("CN")
        cursor = date.fromisoformat(s) + timedelta(days=1)
        end_d = date.fromisoformat(e)
        lag = 0
        while cursor <= end_d:
            if cal.is_trading_day(cursor):
                lag += 1
            cursor += timedelta(days=1)
        return lag
    except Exception:  # noqa: BLE001 — 日历不可用 → 无法判定，不猜
        return None


def _next_settlement_hint(
    latest_brief_asof: str | None, holding_days: int
) -> dict[str, Any]:
    """由 brief asof 推下一个结算日：asof 之后第 ``holding_days`` 个交易日。

    只是**提示**（真实结算仍取决于行情是否到位），故缺日历时返回
    ``{"available": False}`` 而非编造日期。
    """
    if not latest_brief_asof:
        return {"available": False, "reason": "无最新 brief asof。"}
    try:
        from stock_platform_providers import get_trading_calendar  # type: ignore

        cal = get_trading_calendar("CN")
        cursor = date.fromisoformat(str(latest_brief_asof)[:10])
        remaining = max(1, int(holding_days))
        for _ in range(400):  # 上限一年多的自然日，防御性
            cursor += timedelta(days=1)
            if cal.is_trading_day(cursor):
                remaining -= 1
                if remaining == 0:
                    return {
                        "available": True,
                        "entryAsof": str(latest_brief_asof)[:10],
                        "holdingDays": int(holding_days),
                        "expectedSettlementDate": cursor.isoformat(),
                    }
        return {"available": False, "reason": "日历内未找到结算日。"}
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "reason": _error_text(exc)}


# --------------------------------------------------------------------------- #
# 裁决
# --------------------------------------------------------------------------- #
def roll_up_verdict(sections: Mapping[str, Any]) -> dict[str, Any]:
    """把五段信号卷成一个裁决（**纯函数**，便于单测与复用）。

    ``ok``        —— 全部检查项通过；
    ``degraded``  —— 至少一项 ``warn``（可跑，但结果需打折看）；
    ``blocked``   —— 至少一项 ``fail``（不满足日用循环的最低前提）。

    规则（写进契约 ``docs/contracts/loop-health.md``）：

    - coverage：``COVERAGE_HARD_FAIL``（``unavailable`` / ``empty`` / ``missing_table`` /
      ``error`` / ``unconfigured``）→ fail；``COVERAGE_WARN``（``stale`` / ``thin``）→ warn；
      其余 → ok
    - latestBrief：``unavailable`` / ``empty`` → fail；
      ``asof`` 落后 ``coverage.latestTradeDate``（按交易日）→ warn；否则 ok
    - hits：``unavailable`` → warn；``empty`` → warn；``ok`` → ok
    - performance：``unavailable`` → warn；``empty`` → warn；
      样本 < ``MIN_MEANINGFUL_SAMPLE`` → warn；否则 ok
    - symbolMaster：``unavailable`` → warn；``empty``（``total==0``）→ warn；否则 ok
    """
    checks: list[dict[str, Any]] = []

    def add(cid: str, level: str, detail: str) -> None:
        checks.append({"id": cid, "level": level, "detail": detail})

    cov = sections.get("coverage") or {}
    cov_status = str(cov.get("status") or SECTION_UNAVAILABLE)
    if cov_status in COVERAGE_HARD_FAIL:
        add("coverage", _LEVEL_FAIL, f"供数不可用（status={cov_status}）")
    elif cov_status in COVERAGE_WARN:
        add("coverage", _LEVEL_WARN, f"供数异常（status={cov_status}）")
    else:
        add("coverage", _LEVEL_OK, f"供数正常（status={cov_status}）")

    brief = sections.get("latestBrief") or {}
    brief_status = str(brief.get("status") or SECTION_UNAVAILABLE)
    if brief_status in {SECTION_UNAVAILABLE, SECTION_EMPTY}:
        add("latestBrief", _LEVEL_FAIL, f"最新 brief 不可用（status={brief_status}）")
    else:
        lag = _trading_day_lag(brief.get("asof"), cov.get("latestTradeDate"))
        if lag and lag > 0:
            add(
                "latestBrief",
                _LEVEL_WARN,
                f"brief asof={brief.get('asof')} 落后供数 "
                f"{cov.get('latestTradeDate')} 共 {lag} 个交易日",
            )
        elif lag is None:
            add("latestBrief", _LEVEL_OK, f"brief asof={brief.get('asof')}（滞后未判定）")
        else:
            add("latestBrief", _LEVEL_OK, f"brief asof={brief.get('asof')} 与供数同步")

    hits = sections.get("hits") or {}
    hits_status = str(hits.get("status") or SECTION_UNAVAILABLE)
    if hits_status == SECTION_UNAVAILABLE:
        add("hits", _LEVEL_WARN, "命中记账不可用")
    elif hits_status == SECTION_EMPTY:
        add("hits", _LEVEL_WARN, "命中记账为空（尚无重复选中）")
    else:
        add(
            "hits",
            _LEVEL_OK,
            f"{hits.get('totalCodeCount')} 码 / 累计 {hits.get('totalCumulativeHits')} 次",
        )

    perf = sections.get("performance") or {}
    perf_status = str(perf.get("status") or SECTION_UNAVAILABLE)
    if perf_status == SECTION_UNAVAILABLE:
        add("performance", _LEVEL_WARN, "绩效台账不可用")
    elif perf_status == SECTION_EMPTY:
        add("performance", _LEVEL_WARN, "绩效台账为空")
    elif not perf.get("sampleSufficient", False):
        add(
            "performance",
            _LEVEL_WARN,
            f"已结算样本 {perf.get('settledCount')} < "
            f"{perf.get('minMeaningfulSample')}（噪音区，勿过度解读）",
        )
    else:
        add("performance", _LEVEL_OK, f"已结算样本 {perf.get('settledCount')}")

    sm = sections.get("symbolMaster") or {}
    sm_status = str(sm.get("status") or SECTION_UNAVAILABLE)
    if sm_status == SECTION_UNAVAILABLE:
        add("symbolMaster", _LEVEL_WARN, "名称主表不可用")
    elif sm_status == SECTION_EMPTY:
        add("symbolMaster", _LEVEL_WARN, "名称主表为空（名称将显示「—」）")
    else:
        add("symbolMaster", _LEVEL_OK, f"{sm.get('total')} 行名称")

    failed = [c["id"] for c in checks if c["level"] == _LEVEL_FAIL]
    warned = [c["id"] for c in checks if c["level"] == _LEVEL_WARN]
    if failed:
        status = VERDICT_BLOCKED
    elif warned:
        status = VERDICT_DEGRADED
    else:
        status = VERDICT_OK
    return {"status": status, "failed": failed, "warned": warned, "checks": checks}


# --------------------------------------------------------------------------- #
# 7. 历史台账（趋势面）—— 只写平台自有 data/，不写库
# --------------------------------------------------------------------------- #
def default_loop_health_dir() -> Path:
    """体检产物目录：``STOCK_PLATFORM_LOOP_HEALTH_DIR`` 优先，否则 ``./data/health``。"""
    raw = os.environ.get(ENV_LOOP_HEALTH_DIR, "").strip()
    return Path(raw) if raw else Path(DEFAULT_LOOP_HEALTH_OUT_DIR)


def default_loop_health_history_path() -> Path:
    """默认历史上台账路径（``<dir>/history.jsonl``）。"""
    return default_loop_health_dir() / LOOP_HEALTH_HISTORY_FILENAME


def read_history(path: str | Path | None = None) -> list[dict[str, Any]]:
    """读历史台账（最旧在前）。文件不存在 → ``[]``；**读失败向上抛**（由调用方 fail-closed）。

    坏行（非 JSON / 缺 ``asof``）**跳过而不抛** —— 单行损坏不该让整条趋势面消失。
    """
    p = Path(path) if path is not None else default_loop_health_history_path()
    if not p.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            rec = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and str(rec.get("asof") or "").strip():
            out.append(rec)
    return out


def append_history(
    payload: Mapping[str, Any], path: str | Path | None = None
) -> dict[str, Any]:
    """把一次体检结果追加进历史台账（**fail-open，永不抛**）。

    只落四个审计字段（``ts`` / ``asof`` / ``status`` / ``failed`` / ``warned``），
    不落整份 payload（趋势面只需要裁决）。超过 ``HISTORY_MAX_RECORDS`` 行时裁掉最旧部分。
    """
    p = Path(path) if path is not None else default_loop_health_history_path()
    verdict = payload.get("verdict") or {}
    record = {
        "ts": str(payload.get("generatedAt") or _utcnow_iso()),
        "asof": str(payload.get("asof") or "")[:10],
        "status": str(verdict.get("status") or ""),
        "failed": list(verdict.get("failed") or []),
        "warned": list(verdict.get("warned") or []),
    }
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        trimmed = _trim_history(p, HISTORY_MAX_RECORDS)
        return {"appended": True, "path": str(p), "record": record, "trimmed": trimmed}
    except Exception as exc:  # noqa: BLE001 — 台账是锦上添花，绝不拖垮体检
        return {"appended": False, "path": str(p), "reason": _error_text(exc)}


def _trim_history(path: Path, keep: int) -> int:
    """把台账裁到最近 ``keep`` 行；返回裁掉的行数（失败 → 0）。"""
    try:
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if len(lines) <= keep:
            return 0
        dropped = len(lines) - keep
        path.write_text("\n".join(lines[-keep:]) + "\n", encoding="utf-8")
        return dropped
    except Exception:  # noqa: BLE001
        return 0


def _dedupe_by_asof(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    """按 ``asof`` 去重（同一天多次体检只算一次，``ts`` 较晚者胜）。"""
    by: dict[str, dict[str, Any]] = {}
    for rec in records:
        day = str(rec.get("asof") or "")[:10]
        if not day:
            continue
        ts = str(rec.get("ts") or "")
        prev = by.get(day)
        if prev is not None and ts < str(prev.get("ts") or ""):
            continue
        by[day] = {
            "asof": day,
            "status": str(rec.get("status") or ""),
            "ts": ts or None,
            "failed": list(rec.get("failed") or []),
            "warned": list(rec.get("warned") or []),
        }
    return by


def summarize_history(
    records: Sequence[Mapping[str, Any]],
    *,
    asof: str | None,
    status: str | None,
    recent_limit: int = DEFAULT_HISTORY_RECENT,
) -> dict[str, Any]:
    """把历史行卷成趋势摘要（**纯函数**）。

    ``asof`` / ``status`` 是**本次**体检的时点与裁决 —— 计入连续段（同一天重跑只算一次，
    本次覆盖当天旧记录），因此 ``degradedStreak`` 含本次。
    """
    by = _dedupe_by_asof(records)
    stored_days = len(by)
    day = str(asof or "")[:10]
    if day:
        by[day] = {
            "asof": day,
            "status": str(status or ""),
            "ts": None,
            "failed": [],
            "warned": [],
        }
    days = sorted(by)

    def _trailing(pred: Callable[[str], bool]) -> int:
        n = 0
        for d in reversed(days):
            if pred(by[d]["status"]):
                n += 1
            else:
                break
        return n

    degraded = _trailing(lambda s: s == VERDICT_DEGRADED)
    blocked = _trailing(lambda s: s == VERDICT_BLOCKED)
    not_ok = _trailing(lambda s: s not in {"", VERDICT_OK})
    limit = max(1, int(recent_limit))
    return {
        "status": SECTION_OK if stored_days else SECTION_EMPTY,
        "daysRecorded": stored_days,
        "degradedStreak": degraded,
        "blockedStreak": blocked,
        "notOkStreak": not_ok,
        "streakSince": days[len(days) - not_ok] if not_ok else None,
        "recent": [by[d] for d in reversed(days[-limit:])],
        **({} if stored_days else {"reason": "历史台账为空：本次是第一条记录。"}),
    }


def _collect_history(
    path: str | Path | None, *, asof: str, status: str
) -> dict[str, Any]:
    """读历史台账并给出趋势摘要（读失败向上抛 → 由 ``_safe`` 标 ``unavailable``）。"""
    records = read_history(path)
    summary = summarize_history(records, asof=asof, status=status)
    summary["path"] = str(
        Path(path) if path is not None else default_loop_health_history_path()
    )
    return summary


# --------------------------------------------------------------------------- #
# 总入口
# --------------------------------------------------------------------------- #
def collect_loop_health(
    *,
    db_url: str | Path | None = None,
    market_db: str | Path | None = None,
    perf_log: str | Path | None = None,
    asof: str | None = None,
    holding_days: int = 5,
    coverage_lookback_days: int | None = None,
    coverage_min_rows: int | None = None,
    history_path: str | Path | None = None,
    history_recent: int = DEFAULT_HISTORY_RECENT,
) -> dict[str, Any]:
    """聚合一次日用循环健康度快照（**永不抛**）。

    每一段独立 try/except：失败段 → ``status="unavailable"`` + ``reason``，
    其余段照常产出，最终仍给出一份完整 payload。

    额外给出一段 **``history``（趋势面，T1 / v4.9.0）**：读 ``history.jsonl`` 并算
    ``degradedStreak`` / ``blockedStreak`` / ``notOkStreak``（**含本次**，同一天重跑只算一次）。
    ``history`` **不参与裁决** —— 裁决仍只看六路信号的当下快照，历史只解释「是持续还是偶发」。
    """
    asof_day = str(asof or date.today().isoformat())[:10]

    def _safe(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        try:
            return dict(fn() or {})
        except Exception as exc:  # noqa: BLE001 — 单段失败不拖垮整表
            return _section_unavailable(exc)

    coverage = _safe(
        lambda: _collect_coverage(
            market_db,
            asof=asof_day,
            lookback_days=coverage_lookback_days,
            min_rows=coverage_min_rows,
        )
    )
    latest_brief = _safe(lambda: _collect_latest_brief(db_url))
    hits = _safe(lambda: _collect_hits(db_url))
    performance = _safe(
        lambda: _collect_performance(perf_log, holding_days=int(holding_days))
    )
    symbol_master = _safe(lambda: _collect_symbol_master(db_url))

    sections = {
        "coverage": coverage,
        "latestBrief": latest_brief,
        "hits": hits,
        "performance": performance,
        "symbolMaster": symbol_master,
        "nextSettlement": _next_settlement_hint(
            latest_brief.get("asof"), int(holding_days)
        ),
    }
    verdict = roll_up_verdict(sections)
    history = _safe(
        lambda: _collect_history(
            history_path, asof=asof_day, status=str(verdict.get("status") or "")
        )
    )
    if history.get("status") == SECTION_OK and "recent" in history:
        history["recent"] = history["recent"][: max(1, int(history_recent))]

    return {
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "asof": asof_day,
        "generatedAt": _utcnow_iso(),
        "holdingDays": int(holding_days),
        "verdict": verdict,
        **sections,
        "history": history,
        "disclaimer": (
            "只读体检：零网络、不写库；研究指标，非投资建议；"
            "各段口径见 docs/contracts/loop-health.md。"
        ),
    }


# --------------------------------------------------------------------------- #
# 渲染
# --------------------------------------------------------------------------- #
_STATUS_ZH: dict[str, str] = {
    SECTION_OK: "正常",
    SECTION_EMPTY: "空",
    SECTION_UNAVAILABLE: "不可用",
    "stale": "滞后",
    "thin": "偏薄",
    "missing_table": "缺表",
}
_VERDICT_ZH: dict[str, str] = {
    VERDICT_OK: "✅ 正常",
    VERDICT_DEGRADED: "⚠️ 需留意",
    VERDICT_BLOCKED: "⛔ 阻断",
}
_LEVEL_ZH: dict[str, str] = {_LEVEL_OK: "✅", _LEVEL_WARN: "⚠️", _LEVEL_FAIL: "⛔"}


def _status_zh(value: Any) -> str:
    key = str(value or "")
    return _STATUS_ZH.get(key, key or "—")


def _pct(value: Any) -> str:
    if isinstance(value, (int, float)):
        sign = "+" if float(value) >= 0 else ""
        return f"{sign}{float(value) * 100.0:.2f}%"
    return "—"


def _cell(value: Any) -> str:
    return "—" if value in (None, "") else str(value)


def render_loop_health_markdown(payload: Mapping[str, Any]) -> str:
    """人读版体检报告（结论先行、逐段表格）。"""
    verdict = payload.get("verdict") or {}
    status = str(verdict.get("status") or "unknown")
    cov = payload.get("coverage") or {}
    brief = payload.get("latestBrief") or {}
    hits = payload.get("hits") or {}
    perf = payload.get("performance") or {}
    sm = payload.get("symbolMaster") or {}
    nxt = payload.get("nextSettlement") or {}

    lines = [
        "# 日用循环健康度（loop health）",
        "",
        f"- 裁决：**{_VERDICT_ZH.get(status, status)}**"
        f"（fail={verdict.get('failed') or '[]'} / warn={verdict.get('warned') or '[]'}）",
        f"- 时点：`{payload.get('asof')}`（生成于 `{payload.get('generatedAt')}`）",
        "- 环境：SIMULATE（`liveTradingEnabled=false`）· 只读 · 零网络",
        "",
        "## 裁决明细",
        "",
        "| 检查项 | 结论 | 说明 |",
        "|---|---|---|",
    ]
    for check in verdict.get("checks") or []:
        lines.append(
            "| {id} | {lv} | {detail} |".format(
                id=check.get("id"),
                lv=_LEVEL_ZH.get(str(check.get("level")), str(check.get("level"))),
                detail=str(check.get("detail") or "").replace("|", "\\|"),
            )
        )
    lines += [
        "",
        "## 六路信号",
        "",
        "| 段 | 状态 | 关键指标 |",
        "|---|---|---|",
        "| 供数覆盖率 | {s} | 最新交易日 `{ltd}` · 行数 {lr} · 滞后 {lag} 个交易日 |".format(
            s=_status_zh(cov.get("status")),
            ltd=_cell(cov.get("latestTradeDate")),
            lr=_cell(cov.get("latestRows")),
            lag=_cell(cov.get("lagTradingDays")),
        ),
        "| 最新 brief | {s} | asof `{a}` · 选股 {p} 只 · provider {pv} |".format(
            s=_status_zh(brief.get("status")),
            a=_cell(brief.get("asof")),
            p=_cell(brief.get("pickCount")),
            pv=_cell(brief.get("provider")),
        ),
        "| 命中记账 | {s} | {c} 码 · 累计 {h} 次 · 最近选日 `{d}` |".format(
            s=_status_zh(hits.get("status")),
            c=_cell(hits.get("totalCodeCount")),
            h=_cell(hits.get("totalCumulativeHits")),
            d=_cell(hits.get("lastPickDate")),
        ),
        "| 绩效闭环 | {s} | 台账 {t} 条 · 已结算 {st} · 待结算 {pd} · 平均收益 {ar} |".format(
            s=_status_zh(perf.get("status")),
            t=_cell(perf.get("totalEntries")),
            st=_cell(perf.get("settledCount")),
            pd=_cell(perf.get("pendingCount")),
            ar=_pct(perf.get("avgReturn")),
        ),
        "| 名称主表 | {s} | {n} 行 |".format(
            s=_status_zh(sm.get("status")), n=_cell(sm.get("total"))
        ),
        "| 下一个结算日 | {s} | {d} |".format(
            s="有" if nxt.get("available") else "未知",
            d=_cell(nxt.get("expectedSettlementDate")),
        ),
        "",
    ]

    if perf.get("sampleNote"):
        lines.append(f"> ⚠️ {perf['sampleNote']}")
        lines.append("")

    reasons = [
        (name, sec.get("reason"))
        for name, sec in (
            ("供数覆盖率", cov),
            ("最新 brief", brief),
            ("命中记账", hits),
            ("绩效闭环", perf),
            ("名称主表", sm),
        )
        if sec.get("reason")
    ]
    if reasons:
        lines += ["## 缺失/异常说明", ""]
        for name, reason in reasons:
            lines.append(f"- **{name}**：{reason}")
        lines.append("")

    lines += _render_history_block(payload.get("history") or {})

    lines += [
        "> 说明：本报告只**汇总既有只读信号**，不抓数、不写库、不改口径；",
        "> 供数覆盖与结算口径分别见 ADR 0058 / ADR 0068，供数守卫见 ADR 0070；",
        "> 趋势台账只写平台自有 `data/health/history.jsonl`，不写任何库（T1 / ADR 0075）。",
        "",
    ]
    return "\n".join(lines) + "\n"


def _render_history_block(hist: Mapping[str, Any]) -> list[str]:
    """趋势块（历史台账）：连续段 + 近 N 天裁决。"""
    if not hist:
        return []
    out = ["## 趋势（历史台账）", ""]
    if str(hist.get("status") or "") == SECTION_UNAVAILABLE:
        out += [f"- 历史台账不可用：{hist.get('reason')}", ""]
        return out
    since = str(hist.get("streakSince") or "")
    out += [
        "- 台账：`{p}`（{n} 天记录）".format(
            p=_cell(hist.get("path")), n=_cell(hist.get("daysRecorded"))
        ),
        "- 连续：degraded **{d}** 天 · blocked **{b}** 天 · 非正常 **{k}** 天{g}".format(
            d=_cell(hist.get("degradedStreak")),
            b=_cell(hist.get("blockedStreak")),
            k=_cell(hist.get("notOkStreak")),
            g=f"（自 `{since}` 起）" if since else "",
        ),
        "",
        "| 时点 | 裁决 | warn |",
        "|---|---|---|",
    ]
    recent = list(hist.get("recent") or [])
    if not recent:
        out.append("| — | — | — |")
    for rec in recent:
        status_raw = str(rec.get("status") or "")
        out.append(
            "| {a} | {s} | {w} |".format(
                a=_cell(rec.get("asof")),
                s=_VERDICT_ZH.get(status_raw, _cell(status_raw)),
                w=", ".join(str(x) for x in (rec.get("warned") or [])) or "—",
            )
        )
    out.append("")
    return out


def default_loop_health_out_dir() -> Path:
    """默认输出目录（相对 cwd）。"""
    return Path(DEFAULT_LOOP_HEALTH_OUT_DIR)


__all__ = [
    "COVERAGE_HARD_FAIL",
    "COVERAGE_WARN",
    "DEFAULT_HISTORY_RECENT",
    "DEFAULT_LOOP_HEALTH_OUT_DIR",
    "ENV_LOOP_HEALTH_DIR",
    "HISTORY_MAX_RECORDS",
    "LOOP_HEALTH_HISTORY_FILENAME",
    "SECTION_EMPTY",
    "SECTION_OK",
    "SECTION_UNAVAILABLE",
    "VERDICT_BLOCKED",
    "VERDICT_DEGRADED",
    "VERDICT_OK",
    "append_history",
    "collect_loop_health",
    "default_loop_health_dir",
    "default_loop_health_history_path",
    "default_loop_health_out_dir",
    "read_history",
    "render_loop_health_markdown",
    "roll_up_verdict",
    "summarize_history",
]
