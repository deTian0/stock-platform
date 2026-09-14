"""Build a point-in-time daily cross-section panel for research scoring.

Providers are injected (capability-matrix resolve at the call site). No HTTP.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

import pandas as pd

from .universe import UniverseEmptyError, load_universe, normalize_universe


class DailyProvider(Protocol):
    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]: ...


class AdjFactorProvider(Protocol):
    def get_adj_factor(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        kind: str = "qfq",
        asset_type: str = "stock",
    ) -> list[dict[str, Any]]: ...


class FundFlowProvider(Protocol):
    def get_fund_flow(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        limit: int = 120,
    ) -> list[dict[str, Any]]: ...


GetDaily = Callable[..., list[dict[str, Any]]]


def _to_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:8]))
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _bars_to_frame(rows: list[dict[str, Any]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(
            columns=["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]
        )
    records: list[dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").strip()
        day = _to_date(row.get("date") or row.get("trade_date"))
        if not sym or day is None:
            continue
        close = row.get("close")
        if close is None:
            continue
        records.append(
            {
                "symbol": sym,
                "trade_date": day,
                "open": float(row.get("open") or close),
                "high": float(row.get("high") or close),
                "low": float(row.get("low") or close),
                "close": float(close),
                "volume": float(row.get("volume") or row.get("vol") or 0.0),
                "amount": float(row.get("amount") or row.get("amt") or 0.0),
            }
        )
    if not records:
        return pd.DataFrame(
            columns=["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount"]
        )
    df = pd.DataFrame(records)
    df = df.sort_values(["symbol", "trade_date"]).drop_duplicates(
        ["symbol", "trade_date"], keep="last"
    )
    return df.reset_index(drop=True)


def _compute_features(hist: pd.DataFrame, asof: date) -> pd.DataFrame:
    """Per-symbol features as-of ``asof`` (inclusive)."""
    rows: list[dict[str, Any]] = []
    for sym, g in hist.groupby("symbol", sort=False):
        g = g[g["trade_date"] <= asof].sort_values("trade_date")
        if g.empty:
            continue
        last = g.iloc[-1]
        if last["trade_date"] != asof:
            # Strict PIT: require a bar on asof itself.
            continue
        close = g["close"].astype(float)
        ret = close.pct_change()
        vol20 = float(ret.tail(21).iloc[1:].std()) if len(ret) >= 21 else float("nan")
        if len(close) >= 21:
            rev_chg = float(close.iloc[-1] / close.iloc[-21] - 1.0)
        else:
            rev_chg = float("nan")
        ma20 = float(close.tail(20).mean()) if len(close) >= 20 else float("nan")
        ma60 = float(close.tail(60).mean()) if len(close) >= 60 else float("nan")
        trend_up = bool(ma20 > ma60) if pd.notna(ma20) and pd.notna(ma60) else False
        rs20 = float(close.iloc[-1] / ma20 - 1.0) * 100.0 if pd.notna(ma20) and ma20 else float("nan")
        rows.append(
            {
                "trade_date": asof.isoformat(),
                "symbol": str(sym),
                "open": float(last["open"]),
                "high": float(last["high"]),
                "low": float(last["low"]),
                "close": float(last["close"]),
                "volume": float(last["volume"]),
                "amount": float(last["amount"]),
                "vol20": vol20,
                "rev_chg": rev_chg,
                "ma20": ma20,
                "ma60": ma60,
                "trend_up": trend_up,
                "rs20": rs20,
            }
        )
    return pd.DataFrame(rows)


def _merge_fund_flow(
    panel: pd.DataFrame,
    flow_rows: list[dict[str, Any]],
    asof: date,
) -> pd.DataFrame:
    if panel.empty or not flow_rows:
        return panel
    by_sym: dict[str, dict[str, Any]] = {}
    for row in flow_rows:
        sym = str(row.get("symbol") or "").strip()
        day = _to_date(row.get("date") or row.get("trade_date"))
        if not sym or day is None or day > asof:
            continue
        prev = by_sym.get(sym)
        if prev is None or day >= prev["_day"]:
            by_sym[sym] = {
                "_day": day,
                "main_net": row.get("main_net"),
                "small_net": row.get("small_net"),
                "mid_net": row.get("mid_net"),
                "large_net": row.get("large_net"),
                "super_net": row.get("super_net"),
            }
    if not by_sym:
        return panel
    out = panel.copy()
    for col in ("main_net", "small_net", "mid_net", "large_net", "super_net"):
        out[col] = out["symbol"].map(
            lambda s, c=col: by_sym.get(str(s), {}).get(c)  # type: ignore[misc]
        )
    return out


def build_cross_section_panel(
    *,
    asof: date | str,
    symbols: list[str] | None = None,
    universe_path: str | Path | None = None,
    daily_provider: DailyProvider | None = None,
    get_daily: GetDaily | None = None,
    adj_provider: AdjFactorProvider | None = None,
    fund_flow_provider: FundFlowProvider | None = None,
    lookback_calendar_days: int = 120,
    apply_adjust_fn: Callable[..., list[dict[str, Any]]] | None = None,
    adjust_kind: str | None = "qfq",
) -> pd.DataFrame:
    """Build a single-day PIT cross-section DataFrame (CSV-compatible).

    Requires an injectable daily source (``daily_provider`` or ``get_daily``).
    Optional adj_factor + ``apply_adjust_fn`` scales OHLC before feature calc.
    Optional fund_flow attaches latest as-of nets when available.
    """
    if isinstance(asof, str):
        asof_d = date.fromisoformat(asof[:10])
    else:
        asof_d = asof

    if symbols is not None:
        univ = normalize_universe(symbols)
        if not univ:
            raise UniverseEmptyError("symbols list is empty after normalize")
    else:
        univ = load_universe(universe_path)

    if daily_provider is None and get_daily is None:
        raise ValueError("daily_provider or get_daily is required")

    start = asof_d - timedelta(days=int(lookback_calendar_days))
    if daily_provider is not None:
        raw_bars = daily_provider.get_daily(univ, start=start, end=asof_d)
    else:
        assert get_daily is not None
        raw_bars = get_daily(univ, start=start, end=asof_d)

    bars = list(raw_bars)
    if adjust_kind and apply_adjust_fn is not None and adj_provider is not None:
        factors = adj_provider.get_adj_factor(
            univ, start=start, end=asof_d, kind=adjust_kind
        )
        if factors:
            bars = apply_adjust_fn(bars, factors, kind=adjust_kind)

    hist = _bars_to_frame(bars)
    panel = _compute_features(hist, asof_d)

    if fund_flow_provider is not None and not panel.empty:
        try:
            flows = fund_flow_provider.get_fund_flow(univ, start=start, end=asof_d, limit=120)
        except Exception:  # noqa: BLE001 — optional enrichment must not break panel
            flows = []
        panel = _merge_fund_flow(panel, flows, asof_d)

    return panel.reset_index(drop=True)


def panel_to_csv(panel: pd.DataFrame, path: str | Path) -> Path:
    """Persist panel as CSV (UTF-8, no index)."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    panel.to_csv(out, index=False)
    return out
