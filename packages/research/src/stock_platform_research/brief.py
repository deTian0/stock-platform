"""Pre-market brief: panel → lvrev score → entry gates → TopN report."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from .batch import score_cross_section
from .panel import build_cross_section_panel, panel_to_csv
from .universe import load_universe


def _reason_for_row(row: pd.Series) -> str:
    parts: list[str] = []
    score = row.get("composite_score")
    if score is not None and pd.notna(score):
        parts.append(f"score={float(score):.4f}")
    vol = row.get("vol20")
    if vol is not None and pd.notna(vol):
        parts.append(f"low_vol(vol20={float(vol):.4f})")
    rev = row.get("rev_chg")
    if rev is not None and pd.notna(rev):
        parts.append(f"reversal(rev_chg={float(rev):.4f})")
    if row.get("trend_up") is True:
        parts.append("trend_up")
    rs = row.get("rs20")
    if rs is not None and pd.notna(rs):
        parts.append(f"rs20={float(rs):.2f}%")
    main = row.get("main_net")
    if main is not None and pd.notna(main):
        parts.append(f"main_net={float(main):.0f}")
    return "; ".join(parts) if parts else "gated_pass"


def build_premarket_brief(
    *,
    asof: date | str,
    symbols: list[str] | None = None,
    universe_path: str | Path | None = None,
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

    if panel is None:
        panel = build_cross_section_panel(
            asof=asof_d,
            symbols=symbols,
            universe_path=universe_path,
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

    univ_size = len(symbols) if symbols is not None else (
        len(load_universe(universe_path)) if universe_path is not None else len(panel)
    )

    scored = score_cross_section(
        panel,
        value_factor=value_factor,
        reversal_q=reversal_q,
        apply_gates=True,
        top_n=top_n,
    )

    picks: list[dict[str, Any]] = []
    for rank, (_, row) in enumerate(scored.iterrows(), start=1):
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
            "reason": _reason_for_row(row),
        }
        picks.append(item)

    return {
        "asof": asof_s,
        "market": "CN",
        "universeSize": int(univ_size),
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
                "reason": pick.get("reason"),
            }
        )
    return orders


def write_brief_csv(brief: dict[str, Any], path: str | Path) -> Path:
    """Write picks table to CSV."""
    df = pd.DataFrame(brief.get("picks") or [])
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out
