"""Pre-market brief: panel → lvrev score → entry gates → TopN report.

M39: structured readable ``reasons[]`` (Chinese summary + machine keys)
while keeping legacy ``reason`` string for compatibility.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .batch import score_cross_section
from .panel import build_cross_section_panel, panel_to_csv
from .universe import load_universe


def _fmt_num(value: Any, *, digits: int = 4) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return None


def build_reasons_for_row(row: pd.Series, *, gated: bool = True) -> list[dict[str, Any]]:
    """Build human-readable reason items for a scored panel row.

    Each item: ``{key, summary, value?}``. Empty gate pass yields a single
    explanatory item (never a silent empty list).
    """
    items: list[dict[str, Any]] = []

    score = row.get("composite_score")
    if score is not None and pd.notna(score):
        items.append(
            {
                "key": "composite_score",
                "summary": f"综合分 {float(score):.4f}",
                "value": float(score),
            }
        )

    vol = row.get("vol20")
    if vol is not None and pd.notna(vol):
        items.append(
            {
                "key": "low_vol",
                "summary": f"低波动贡献（vol20={float(vol):.4f}）",
                "value": float(vol),
            }
        )

    rev = row.get("rev_chg")
    if rev is not None and pd.notna(rev):
        items.append(
            {
                "key": "reversal",
                "summary": f"反转贡献（rev_chg={float(rev):.4f}）",
                "value": float(rev),
            }
        )

    if row.get("trend_up") is True:
        items.append({"key": "trend_up", "summary": "均线趋势向上（trend_up）", "value": True})

    rs = row.get("rs20")
    if rs is not None and pd.notna(rs):
        items.append(
            {
                "key": "rs20",
                "summary": f"相对强弱 rs20={float(rs):.2f}%",
                "value": float(rs),
            }
        )

    main = row.get("main_net")
    if main is not None and pd.notna(main):
        items.append(
            {
                "key": "main_net",
                "summary": f"主力净流入约 {float(main):.0f} 元",
                "value": float(main),
            }
        )

    ma20 = row.get("ma20")
    ma60 = row.get("ma60")
    if (
        ma20 is not None
        and ma60 is not None
        and pd.notna(ma20)
        and pd.notna(ma60)
        and float(ma20) > float(ma60)
    ):
        items.append(
            {
                "key": "ma_stack",
                "summary": f"均线多头（ma20={float(ma20):.2f} > ma60={float(ma60):.2f}）",
                "value": {"ma20": float(ma20), "ma60": float(ma60)},
            }
        )

    if gated and not items:
        items.append(
            {
                "key": "gated_pass",
                "summary": "通过入场闸门；无额外分数贡献字段",
                "value": None,
            }
        )
    elif not items:
        items.append(
            {
                "key": "empty",
                "summary": "无可用特征说明（空闸门/缺列）",
                "value": None,
            }
        )
    return items


def reasons_to_legacy_string(reasons: list[dict[str, Any]]) -> str:
    """Compat string for older UI/CLI expecting ``reason``."""
    parts: list[str] = []
    for item in reasons:
        key = str(item.get("key") or "")
        value = item.get("value")
        if key == "composite_score" and value is not None:
            parts.append(f"score={float(value):.4f}")
        elif key == "low_vol" and value is not None:
            parts.append(f"low_vol(vol20={float(value):.4f})")
        elif key == "reversal" and value is not None:
            parts.append(f"reversal(rev_chg={float(value):.4f})")
        elif key == "trend_up":
            parts.append("trend_up")
        elif key == "rs20" and value is not None:
            parts.append(f"rs20={float(value):.2f}%")
        elif key == "main_net" and value is not None:
            parts.append(f"main_net={float(value):.0f}")
        elif key == "ma_stack":
            parts.append("ma_stack")
        elif key in {"gated_pass", "empty"}:
            parts.append(key)
        elif item.get("summary"):
            parts.append(str(item["summary"]))
    return "; ".join(parts) if parts else "gated_pass"


def _reason_for_row(row: pd.Series) -> str:
    return reasons_to_legacy_string(build_reasons_for_row(row, gated=True))


def reason_summary(reasons: list[dict[str, Any]]) -> str:
    """Single Chinese line for tables / workbench cells."""
    summaries = [str(r.get("summary") or "").strip() for r in reasons]
    summaries = [s for s in summaries if s]
    return "；".join(summaries) if summaries else "通过闸门"


def build_premarket_brief(
    *,
    asof: date | str,
    symbols: list[str] | None = None,
    universe_path: str | Path | None = None,
    universe_tier: str | None = None,
    daily_provider: Any | None = None,
    get_daily: Any | None = None,
    adj_provider: Any | None = None,
    fund_flow_provider: Any | None = None,
    apply_adjust_fn: Any | None = None,
    adjust_kind: str | None = "qfq",
    panel: pd.DataFrame | None = None,
    top_n: int = 10,
    value_factor: bool = False,
    reversal_q: float = 0.30,
    lookback_calendar_days: int = 120,
) -> dict[str, Any]:
    """Build a deterministic TopN pre-market brief.

    Prefer injecting an already-built ``panel`` in tests; otherwise build via
    ``build_cross_section_panel`` (requires daily provider).
    """
    if isinstance(asof, str):
        asof_s = asof[:10]
        asof_d = date.fromisoformat(asof_s)
    else:
        asof_d = asof
        asof_s = asof.isoformat()

    resolved_symbols = symbols
    if resolved_symbols is None and universe_path is not None:
        resolved_symbols = load_universe(universe_path, tier=universe_tier)

    if panel is None:
        panel = build_cross_section_panel(
            asof=asof_d,
            symbols=resolved_symbols,
            universe_path=universe_path if resolved_symbols is None else None,
            daily_provider=daily_provider,
            get_daily=get_daily,
            adj_provider=adj_provider,
            fund_flow_provider=fund_flow_provider,
            apply_adjust_fn=apply_adjust_fn,
            adjust_kind=adjust_kind,
            lookback_calendar_days=lookback_calendar_days,
        )
    else:
        panel = panel.copy()

    univ_size = len(resolved_symbols) if resolved_symbols is not None else len(panel)

    scored = score_cross_section(
        panel,
        value_factor=value_factor,
        reversal_q=reversal_q,
        apply_gates=True,
        top_n=top_n,
    )

    picks: list[dict[str, Any]] = []
    for rank, (_, row) in enumerate(scored.iterrows(), start=1):
        reasons = build_reasons_for_row(row, gated=True)
        item = {
            "rank": rank,
            "symbol": str(row.get("symbol") or row.get("code") or ""),
            "composite_score": float(row["composite_score"])
            if "composite_score" in row and pd.notna(row["composite_score"])
            else None,
            "close": float(row["close"]) if "close" in row and pd.notna(row["close"]) else None,
            "vol20": float(row["vol20"]) if "vol20" in row and pd.notna(row["vol20"]) else None,
            "rev_chg": float(row["rev_chg"]) if "rev_chg" in row and pd.notna(row["rev_chg"]) else None,
            "ma20": float(row["ma20"]) if "ma20" in row and pd.notna(row["ma20"]) else None,
            "ma60": float(row["ma60"]) if "ma60" in row and pd.notna(row["ma60"]) else None,
            "reasons": reasons,
            "reasonSummary": reason_summary(reasons),
            "reason": reasons_to_legacy_string(reasons),
        }
        picks.append(item)

    return {
        "asof": asof_s,
        "market": "CN",
        "universeSize": int(univ_size),
        "universeTier": universe_tier,
        "panelSize": int(len(panel)),
        "topN": int(top_n),
        "valueFactor": bool(value_factor),
        "reversalQ": float(reversal_q),
        "picks": picks,
        "environment": "SIMULATE",
        "disclaimer": "Research brief only; not investment advice; paper SIMULATE by default.",
    }


def brief_to_orders(brief: dict[str, Any], *, qty: int = 100, side: str = "buy") -> list[dict[str, Any]]:
    """Map brief picks to simple paper order dicts."""
    orders: list[dict[str, Any]] = []
    for pick in brief.get("picks") or []:
        sym = str(pick.get("symbol") or "").strip()
        if not sym:
            continue
        orders.append(
            {
                "symbol": sym,
                "side": side,
                "qty": int(qty),
                "score": pick.get("composite_score"),
                "reason": pick.get("reasonSummary") or pick.get("reason"),
            }
        )
    return orders


def write_brief_csv(brief: dict[str, Any], path: str | Path) -> Path:
    """Write picks table to CSV."""
    rows = []
    for pick in brief.get("picks") or []:
        row = dict(pick)
        row["reasonSummary"] = pick.get("reasonSummary") or ""
        row.pop("reasons", None)
        rows.append(row)
    df = pd.DataFrame(rows)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out
