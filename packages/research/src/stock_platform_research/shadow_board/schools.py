"""Round1 — five school candidate pools.

S3/S4 reuse ``secondary_pick``. S1/S2/S5 use thin rules when data/hooks exist;
otherwise fail-closed empty pools with a Chinese ``reason`` (never pad).
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from ..secondary_pick import AMOUNT_MIN, select_secondary

SCHOOL_IDS: tuple[str, ...] = ("S1", "S2", "S3", "S4", "S5")

SCHOOL_NAMES: dict[str, str] = {
    "S1": "宏观/择时",
    "S2": "事件/主题",
    "S3": "质量/防守",
    "S4": "短线动量",
    "S5": "资金流/流动性",
}

# Default holding periods for rule-filled structured reasons.
_HOLDING: dict[str, str] = {
    "S1": "5–15 交易日",
    "S2": "3–10 交易日",
    "S3": "10–20 交易日",
    "S4": "2–5 交易日",
    "S5": "5–10 交易日",
}

# S1 breadth: need enough scored rows; below floor → risk-off empty board.
_S1_MIN_BREADTH_ROWS = 5
_S1_BREADTH_FLOOR = 0.35
_S1_INDEX_MA_WINDOW = 20

ProviderLike = Any  # duck-typed provider or preloaded payload / callable


def _row_code(row: Mapping[str, Any]) -> str:
    for key in ("code", "symbol", "ts_code"):
        raw = row.get(key)
        if raw is None or raw == "":
            continue
        s = str(raw).strip().upper()
        digits = "".join(ch for ch in s if ch.isdigit())
        if len(digits) >= 6:
            return digits[-6:]
        if digits:
            return digits.zfill(6)
    return ""


def _num(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _candidate(
    row: Mapping[str, Any],
    *,
    school: str,
    score: float,
    reason_seed: str,
) -> dict[str, Any]:
    code = _row_code(row)
    name = str(row.get("name") or "").strip() or code
    industry = str(row.get("industry") or row.get("sector") or "").strip() or None
    keep_keys = (
        "amount",
        "rev_chg",
        "rs20",
        "vol20",
        "pct_chg",
        "composite_score",
        "main_net",
        "main_net_inflow",
        "fund_flow",
        "illiq",
        "ma20",
        "close",
        "trend_up",
    )
    return {
        "code": code,
        "name": name,
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "score": float(score),
        "industry": industry,
        "holdingPeriod": _HOLDING.get(school, "5–10 交易日"),
        "trigger": reason_seed,
        "expectation": (
            f"{_HOLDING.get(school, '5–10 交易日')}内收益不低于同校池中位数"
            f"（规则预期；学校 {school}）"
        ),
        "invalidation": "收盘跌破 MA20 或触发硬闸（ST/成交额低于 1000 万/涨停封板），或学校池撤销",
        "excludedFromPerformance": True,
        "sourceFields": {k: row.get(k) for k in keep_keys if k in row},
    }


def _empty(school: str, reason: str) -> dict[str, Any]:
    return {
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "status": "empty",
        "reason": reason,
        "candidates": [],
    }


def _ok(
    school: str,
    candidates: list[dict[str, Any]],
    *,
    reason: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "school": school,
        "schoolName": SCHOOL_NAMES.get(school, school),
        "status": "ok",
        "reason": reason,
        "candidates": candidates,
    }
    payload.update(extra)
    return payload


def _from_secondary(
    items: Sequence[Mapping[str, Any]] | None,
    *,
    school: str,
    profile: str,
    top_k: int,
) -> dict[str, Any]:
    if not items:
        return _empty(school, "输入截面为空，学校池 fail-closed")
    result = select_secondary(list(items), profile=profile, top_k=top_k)  # type: ignore[arg-type]
    selected = result.get("selected") or []
    candidates: list[dict[str, Any]] = []
    for row in selected:
        seed = str(row.get("secondaryReason") or f"{SCHOOL_NAMES.get(school, school)}规则入选")
        score = float(row.get("secondaryScore") or row.get("composite_score") or 0.0)
        cand = _candidate(row, school=school, score=score, reason_seed=seed)
        if cand["code"]:
            candidates.append(cand)
    note = (result.get("stats") or {}).get("note")
    if not candidates:
        return _empty(
            school,
            note or "二次精选后无入选；空池合法",
        )
    return _ok(school, candidates, reason=note, profile=result.get("profile"))


def _above_ma(row: Mapping[str, Any]) -> bool | None:
    """True/False when measurable; None when fields missing."""
    trend = row.get("trend_up")
    if isinstance(trend, bool):
        return trend
    rs = _num(row.get("rs20"))
    if rs is not None:
        return rs >= 0.0
    close = _num(row.get("close"))
    ma20 = _num(row.get("ma20"))
    if close is not None and ma20 is not None and ma20 > 0:
        return close >= ma20
    return None


def _index_timing_from_bars(bars: Sequence[Mapping[str, Any]] | None) -> tuple[bool | None, str]:
    """Thin index MA rule: last close vs MA20. Returns (ok, reason_fragment)."""
    if not bars:
        return None, ""
    closes: list[float] = []
    for bar in bars:
        if not isinstance(bar, Mapping):
            continue
        c = _num(bar.get("close") or bar.get("Close"))
        if c is not None:
            closes.append(c)
    if len(closes) < _S1_INDEX_MA_WINDOW:
        return None, f"指数序列不足 {_S1_INDEX_MA_WINDOW} 根"
    window = closes[-_S1_INDEX_MA_WINDOW:]
    ma = sum(window) / len(window)
    last = window[-1]
    if ma <= 0:
        return None, "指数均线无效"
    if last >= ma:
        return True, f"指数收盘站上 MA{_S1_INDEX_MA_WINDOW}（{last:.2f}≥{ma:.2f}）"
    return False, f"指数收盘跌破 MA{_S1_INDEX_MA_WINDOW}（{last:.2f}<{ma:.2f}）"


#: S1 regime states for the board-level gate / scale experiment (§11.6).
S1_REGIME_STATES: tuple[str, ...] = ("strong", "mid", "weak", "unknown")
#: ``strong`` threshold for the experiment; ``weak`` reuses S1's own floor.
S1_STRONG_BREADTH = 0.50


def s1_regime_state(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    weak_below: float = _S1_BREADTH_FLOOR,
    strong_at: float = S1_STRONG_BREADTH,
) -> dict[str, Any]:
    """S1's breadth judgement as a board-level regime (no picks).

    Same measurement as :func:`school_s1_macro`'s breadth path (``_above_ma`` over
    the session universe, ≥ ``_S1_MIN_BREADTH_ROWS`` measurable rows), so it only
    sees the asof cross-section — PIT by construction. ``breadth < weak_below`` →
    ``weak`` (S1's existing 择时关闭 floor); ``≥ strong_at`` → ``strong``; between →
    ``mid``; too few measurable rows → ``unknown`` (callers treat it fail-closed).
    """
    measured = [f for f in (_above_ma(r) for r in (universe or []) if isinstance(r, Mapping)) if f is not None]
    n = len(measured)
    if n < _S1_MIN_BREADTH_ROWS:
        return {"state": "unknown", "breadth": None, "measured": n}
    breadth = sum(1 for x in measured if x) / n
    if breadth < weak_below:
        state = "weak"
    elif breadth >= strong_at:
        state = "strong"
    else:
        state = "mid"
    return {"state": state, "breadth": breadth, "measured": n}


def school_s1_macro(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    asof: str | None = None,
    regime: Mapping[str, bool] | None = None,
    index_bars: Sequence[Mapping[str, Any]] | None = None,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Macro/timing: regime gate → index MA → universe breadth; then thin picks."""
    rows = [r for r in (universe or []) if isinstance(r, Mapping)]
    day = (asof or "").strip()[:10] or None

    if regime is not None and day:
        if not bool(regime.get(day, True)):
            return _empty("S1", f"regime 标记 {day} 不可开仓；fail-closed 空池")

    timing_ok: bool | None = None
    timing_note = ""
    require_above_ma = True  # breadth path prefers names already contributing to width

    idx_ok, idx_note = _index_timing_from_bars(index_bars)
    if idx_ok is not None:
        timing_ok = idx_ok
        timing_note = idx_note
        require_above_ma = False  # index gate already decided; rank all liquid names
        if not idx_ok:
            return _empty("S1", f"择时关闭：{idx_note}")

    if timing_ok is None:
        measured: list[bool] = []
        for r in rows:
            flag = _above_ma(r)
            if flag is not None:
                measured.append(flag)
        if len(measured) < _S1_MIN_BREADTH_ROWS:
            if regime is not None and day and bool(regime.get(day, True)):
                # Regime says open but no breadth/index → still fail-closed on thin alpha.
                return _empty(
                    "S1",
                    "regime 允许开仓，但缺截面宽度字段（rs20/ma20/trend_up）与指数序列；fail-closed 空池",
                )
            return _empty(
                "S1",
                "缺宏观/择时数据（regime / index_bars / 截面 rs20|ma20|trend_up）；fail-closed 空池",
            )
        breadth = sum(1 for x in measured if x) / len(measured)
        timing_note = f"截面宽度 {breadth:.0%}（{sum(1 for x in measured if x)}/{len(measured)} 站上均线或动量非负）"
        if breadth < _S1_BREADTH_FLOOR:
            return _empty(
                "S1",
                f"择时关闭：{timing_note}，低于地板 {_S1_BREADTH_FLOOR:.0%}",
            )
        timing_ok = True

    # Timing open → thin picks with adequate liquidity.
    scored: list[tuple[float, Mapping[str, Any], str]] = []
    for r in rows:
        code = _row_code(r)
        if not code:
            continue
        amount = _num(r.get("amount"))
        if amount is None or amount < AMOUNT_MIN:
            continue
        flag = _above_ma(r)
        if require_above_ma and flag is False:
            continue
        rs = _num(r.get("rs20")) or 0.0
        # Mild preference for not overheated momentum + liquidity.
        score = 0.55 + min(max(rs, -5.0), 5.0) / 50.0
        if flag is True:
            score += 0.1
        amt_boost = min(amount / 1e9, 0.2)
        score += amt_boost
        seed = f"择时开仓（{timing_note}）；流动性达标"
        scored.append((score, r, seed))

    scored.sort(key=lambda t: (-t[0], _row_code(t[1])))
    candidates: list[dict[str, Any]] = []
    for score, row, seed in scored[: max(1, top_k)]:
        cand = _candidate(row, school="S1", score=score, reason_seed=seed)
        if cand["code"]:
            candidates.append(cand)
    if not candidates:
        return _empty("S1", f"择时开仓（{timing_note}），但无满足流动性的候选；空池合法")
    return _ok("S1", candidates, reason=timing_note)


def _materialize_hook(
    provider: ProviderLike,
    *,
    label: str,
    symbols: list[str],
    method_names: tuple[str, ...],
    errors: list[str],
) -> Any:
    """Resolve preloaded payload / callable / duck-typed provider; errors → None."""
    if provider is None:
        return None
    if isinstance(provider, (list, dict, tuple)):
        return provider

    def _safe(fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — provider best-effort
            errors.append(f"{label}:{type(exc).__name__}")
            return None

    for name in method_names:
        getter = getattr(provider, name, None)
        if callable(getter):
            return _safe(lambda g=getter: g(symbols))

    if callable(provider):
        return _safe(lambda: provider(symbols))
    return provider


def _lead_codes_from_concepts(payload: Any) -> dict[str, str]:
    """Map code → concept name from concept_blocks payload."""
    leads: dict[str, str] = {}
    boards: list[Any] = []
    if isinstance(payload, Mapping):
        raw_boards = payload.get("boards") or payload.get("items") or []
        if isinstance(raw_boards, list):
            boards.extend(raw_boards)
        # Per-symbol list of concept payloads
        for key in ("concept_tags",):
            tags = payload.get(key)
            if isinstance(tags, list):
                for tag in tags:
                    if isinstance(tag, Mapping):
                        boards.append(tag)
    elif isinstance(payload, list):
        for item in payload:
            if not isinstance(item, Mapping):
                continue
            if item.get("lead_stock") or item.get("name"):
                boards.append(item)
            nested = item.get("boards")
            if isinstance(nested, list):
                boards.extend(nested)
    for board in boards:
        if not isinstance(board, Mapping):
            continue
        lead = board.get("lead_stock") or board.get("lead") or board.get("symbol")
        name = str(board.get("name") or board.get("concept") or "主题").strip()
        if lead is None or lead == "":
            continue
        digits = "".join(ch for ch in str(lead) if ch.isdigit())
        if len(digits) >= 6:
            code = digits[-6:]
            leads.setdefault(code, name)
    return leads


def _hot_sectors(payload: Any) -> list[str]:
    rows: list[Mapping[str, Any]] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, Mapping)]
    elif isinstance(payload, Mapping):
        for key in ("items", "rows", "flows", "sectors"):
            block = payload.get(key)
            if isinstance(block, list):
                rows = [r for r in block if isinstance(r, Mapping)]
                break
        if not rows and ("sector_name" in payload or "main_net" in payload):
            rows = [payload]
    scored: list[tuple[float, str]] = []
    for r in rows:
        name = str(r.get("sector_name") or r.get("name") or r.get("industry") or "").strip()
        if not name:
            continue
        flow = _num(r.get("main_net") or r.get("main_net_inflow") or r.get("fund_flow")) or 0.0
        scored.append((flow, name))
    scored.sort(key=lambda t: -t[0])
    # Prefer inflow-positive sectors; if none, still expose top names for matching.
    positive = [n for flow, n in scored if flow > 0]
    return (positive or [n for _, n in scored])[:8]


def _lhb_codes(payload: Any) -> set[str]:
    codes: set[str] = set()
    items: list[Any]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, Mapping):
        items = [payload]
        for key in ("items", "records", "rows"):
            block = payload.get(key)
            if isinstance(block, list):
                items = block
                break
    else:
        return codes
    for item in items:
        if not isinstance(item, Mapping):
            continue
        sym = item.get("symbol") or item.get("code") or item.get("lead_stock")
        if sym:
            digits = "".join(ch for ch in str(sym) if ch.isdigit())
            if len(digits) >= 6:
                codes.add(digits[-6:])
        # Nested records under symbol wrapper
        if item.get("records") and item.get("symbol"):
            digits = "".join(ch for ch in str(item.get("symbol")) if ch.isdigit())
            if len(digits) >= 6:
                codes.add(digits[-6:])
    return codes


def school_s2_theme(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    concept_blocks: ProviderLike = None,
    sector_fund_flow: ProviderLike = None,
    lhb: ProviderLike = None,
    unlock: ProviderLike = None,
    s2_snapshot_meta: Mapping[str, Any] | None = None,
    **_: Any,
) -> dict[str, Any]:
    """Event/theme: DI concept_blocks / sector_fund_flow / lhb / unlock; empty if absent.

    Signals are advisory for the shadow chain only — not admitted to ``FACTOR_LIBRARY`` /
    production ``W_DEFAULT``. ``s2_snapshot_meta`` (S2-P1 daily snapshot summary) is
    only echoed into the pool for observability; it never adds candidates itself.
    """
    pool = _school_s2_theme_core(
        universe,
        top_k=top_k,
        concept_blocks=concept_blocks,
        sector_fund_flow=sector_fund_flow,
        lhb=lhb,
        unlock=unlock,
        s2_snapshot_meta=s2_snapshot_meta,
    )
    if s2_snapshot_meta is not None:
        pool["snapshot"] = dict(s2_snapshot_meta)
    return pool


def _school_s2_theme_core(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int,
    concept_blocks: ProviderLike,
    sector_fund_flow: ProviderLike,
    lhb: ProviderLike,
    unlock: ProviderLike,
    s2_snapshot_meta: Mapping[str, Any] | None,
) -> dict[str, Any]:
    rows = [r for r in (universe or []) if isinstance(r, Mapping)]
    if (
        concept_blocks is None
        and sector_fund_flow is None
        and lhb is None
        and unlock is None
    ):
        if s2_snapshot_meta is not None:
            snap_status = str(s2_snapshot_meta.get("status") or "missing")
            return _empty(
                "S2",
                f"S2 当日快照 status={snap_status}，无 PIT 可用信号"
                "（龙虎榜/板块排名/解禁均缺或非当日）；fail-closed 空池",
            )
        return _empty(
            "S2",
            "未注入主题/事件 provider（concept_blocks / sector_fund_flow / lhb / unlock）；"
            "未过 FACTOR_LIBRARY 不得进生产权重；fail-closed 空池",
        )

    symbols = [_row_code(r) for r in rows if _row_code(r)]
    industries = sorted(
        {
            str(r.get("industry") or r.get("sector") or "").strip()
            for r in rows
            if str(r.get("industry") or r.get("sector") or "").strip()
        }
    )
    errors: list[str] = []
    resolved = {
        "concept_blocks": _materialize_hook(
            concept_blocks,
            label="concept_blocks",
            symbols=symbols,
            method_names=("get_concept_blocks",),
            errors=errors,
        ),
        "sector_fund_flow": _materialize_hook(
            sector_fund_flow,
            label="sector_fund_flow",
            symbols=industries,
            method_names=("get_sector_fund_flow",),
            errors=errors,
        ),
        "lhb": _materialize_hook(
            lhb,
            label="lhb",
            symbols=symbols,
            method_names=("get_lhb",),
            errors=errors,
        ),
        "unlock": _materialize_hook(
            unlock,
            label="unlock",
            symbols=symbols,
            method_names=("get_unlock",),
            errors=errors,
        ),
        "errors": errors,
    }
    leads = _lead_codes_from_concepts(resolved["concept_blocks"])
    hot = _hot_sectors(resolved["sector_fund_flow"])
    lhb_set = _lhb_codes(resolved["lhb"])
    # unlock: if present as list of upcoming heavy unlocks, treat as soft exclude
    unlock_exclude: set[str] = set()
    unlock_payload = resolved["unlock"]
    if isinstance(unlock_payload, list):
        for item in unlock_payload:
            if not isinstance(item, Mapping):
                continue
            sym = item.get("symbol") or item.get("code")
            upcoming = item.get("upcoming")
            heavy = False
            if isinstance(upcoming, list) and upcoming:
                for ev in upcoming:
                    if isinstance(ev, Mapping):
                        ratio = _num(ev.get("ratio"))
                        if ratio is not None and ratio >= 5.0:
                            heavy = True
                            break
                else:
                    heavy = True  # has upcoming unlock window
            if sym and heavy:
                digits = "".join(ch for ch in str(sym) if ch.isdigit())
                if len(digits) >= 6:
                    unlock_exclude.add(digits[-6:])

    if not leads and not hot and not lhb_set:
        err = "；".join(resolved["errors"]) if resolved["errors"] else ""
        suffix = f"（provider 错误：{err}）" if err else ""
        return _empty(
            "S2",
            f"主题/事件 provider 已注入但无可用信号{suffix}；fail-closed 空池",
        )

    by_code = {_row_code(r): r for r in rows if _row_code(r)}
    scored: list[tuple[float, Mapping[str, Any], str]] = []
    for code, row in by_code.items():
        if code in unlock_exclude:
            continue
        amount = _num(row.get("amount"))
        if amount is None or amount < AMOUNT_MIN:
            continue
        score = 0.0
        bits: list[str] = []
        if code in leads:
            score += 0.55
            bits.append(f"概念龙头·{leads[code]}")
        ind = str(row.get("industry") or row.get("sector") or "").strip()
        if ind and any(ind in h or h in ind for h in hot):
            score += 0.35
            bits.append(f"板块资金流·{ind}")
        if code in lhb_set:
            score += 0.25
            bits.append("龙虎榜窗口")
        if score <= 0:
            continue
        scored.append((score, row, "；".join(bits) + "（影子主题信号，未过 FACTOR_LIBRARY）"))

    scored.sort(key=lambda t: (-t[0], _row_code(t[1])))
    candidates = [
        _candidate(row, school="S2", score=score, reason_seed=seed)
        for score, row, seed in scored[: max(1, top_k)]
        if _row_code(row)
    ]
    candidates = [c for c in candidates if c["code"]]
    if not candidates:
        return _empty("S2", "主题信号未命中截面宇宙或流动性不足；空池合法")
    return _ok(
        "S2",
        candidates,
        reason="主题/事件薄规则（advisory；不进生产权重）",
        advisoryOnly=True,
    )


def school_s3_quality(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Quality/defensive pool via secondary_pick quality profile (lvrev-adjacent)."""
    return _from_secondary(universe, school="S3", profile="quality", top_k=top_k)


def school_s4_short(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Short momentum via secondary_pick short weights."""
    return _from_secondary(universe, school="S4", profile="short", top_k=top_k)


def _flow_value(row: Mapping[str, Any]) -> float | None:
    for key in ("main_net", "main_net_inflow", "fund_flow"):
        if key in row:
            v = _num(row.get(key))
            if v is not None:
                return v
    return None


def school_s5_flow(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    **_: Any,
) -> dict[str, Any]:
    """Fund-flow / liquidity: rank by main_net/fund_flow, else amount±illiq thin rule."""
    rows = [r for r in (universe or []) if isinstance(r, Mapping)]
    if not rows:
        return _empty("S5", "输入截面为空，学校池 fail-closed")

    has_flow = any(_flow_value(r) is not None for r in rows)
    has_illiq = any(_num(r.get("illiq")) is not None for r in rows)
    has_amount = any(_num(r.get("amount")) is not None for r in rows)
    if not has_flow and not has_amount and not has_illiq:
        return _empty(
            "S5",
            "缺资金流/流动性字段（main_net / fund_flow / amount / illiq）；fail-closed 空池",
        )

    scored: list[tuple[float, Mapping[str, Any], str]] = []
    for r in rows:
        code = _row_code(r)
        if not code:
            continue
        amount = _num(r.get("amount"))
        if amount is None or amount < AMOUNT_MIN:
            continue
        flow = _flow_value(r)
        illiq = _num(r.get("illiq"))
        if has_flow:
            if flow is None or flow <= 0:
                continue
            # Normalize roughly: 1e8 CNY net → ~0.5 contribution
            score = min(flow / 2e8, 1.0) * 0.7 + min(amount / 1e9, 0.3)
            seed = f"主力净流入 {flow:.0f}；成交额达标"
        else:
            # Thin liquidity proxy: prefer larger amount / lower illiq
            score = min(amount / 1e9, 0.8)
            if illiq is not None and illiq > 0:
                score += max(0.0, 0.2 - min(illiq, 0.2))
                seed = f"流动性薄规则：成交额 {amount:.0f}，illiq={illiq:.4g}"
            else:
                seed = f"流动性薄规则：成交额 {amount:.0f}（无 fund_flow/illiq）"
        scored.append((score, r, seed))

    scored.sort(key=lambda t: (-t[0], _row_code(t[1])))
    candidates = [
        _candidate(row, school="S5", score=score, reason_seed=seed)
        for score, row, seed in scored[: max(1, top_k)]
        if _row_code(row)
    ]
    candidates = [c for c in candidates if c["code"]]
    if not candidates:
        mode = "资金流" if has_flow else "流动性"
        return _empty("S5", f"{mode}规则后无入选；空池合法")
    reason = (
        "资金流排序（main_net/fund_flow）"
        if has_flow
        else "流动性薄规则（amount/illiq；无资金流字段）"
    )
    return _ok("S5", candidates, reason=reason)


_SCHOOL_RUNNERS = {
    "S1": school_s1_macro,
    "S2": school_s2_theme,
    "S3": school_s3_quality,
    "S4": school_s4_short,
    "S5": school_s5_flow,
}


def run_round1(
    universe: Sequence[Mapping[str, Any]] | None,
    *,
    top_k: int = 8,
    asof: str | None = None,
    regime: Mapping[str, bool] | None = None,
    index_bars: Sequence[Mapping[str, Any]] | None = None,
    concept_blocks: ProviderLike = None,
    sector_fund_flow: ProviderLike = None,
    lhb: ProviderLike = None,
    unlock: ProviderLike = None,
    **hooks: Any,
) -> dict[str, dict[str, Any]]:
    """Run all five schools; optional DI hooks forwarded to each runner."""
    out: dict[str, dict[str, Any]] = {}
    common = {
        "top_k": top_k,
        "asof": asof,
        "regime": regime,
        "index_bars": index_bars,
        "concept_blocks": concept_blocks,
        "sector_fund_flow": sector_fund_flow,
        "lhb": lhb,
        "unlock": unlock,
        **hooks,
    }
    for sid in SCHOOL_IDS:
        runner = _SCHOOL_RUNNERS[sid]
        out[sid] = runner(universe, **common)
    return out


__all__ = [
    "SCHOOL_IDS",
    "SCHOOL_NAMES",
    "run_round1",
    "school_s1_macro",
    "school_s2_theme",
    "school_s3_quality",
    "school_s4_short",
    "school_s5_flow",
]
