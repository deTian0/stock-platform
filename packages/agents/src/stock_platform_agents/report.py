"""Report builders — consume MarketDataProvider only (no eastmoney/tencent HTTP)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Protocol

from stock_platform_providers import normalize_symbol
from stock_platform_providers.base import MarketDataProvider

from .errors import AgentError


class SupportsMarketData(Protocol):
    name: str

    def get_daily(self, symbols: list[str], *, start: date | None = None, end: date | None = None, asset_type: str = "stock") -> list[dict[str, Any]]: ...

    def get_realtime(self, symbols: list[str], *, asset_type: str = "stock") -> list[dict[str, Any]]: ...


@dataclass
class ResearchReport:
    symbol: str
    asof: str
    provider: str
    roles: dict[str, str]
    daily_bars: int
    last_close: float | None
    change_pct: float | None
    warnings: list[str] = field(default_factory=list)
    kind: str = "research"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse_asof(asof: str | date | None) -> date:
    if asof is None:
        return date.today()
    if isinstance(asof, date):
        return asof
    return date.fromisoformat(str(asof)[:10])


def _historical_warning(asof: date) -> str | None:
    today = date.today()
    if asof < today:
        return (
            f"分析日 {asof.isoformat()} 早于今天 {today.isoformat()}："
            "不得把实时快照当作分析日事实；仅使用 as-of 截断后的历史序列。"
        )
    return None


def build_research_report(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    lookback_days: int = 60,
) -> ResearchReport:
    """Build a multi-role research stub using provider daily (+ optional realtime)."""
    code = normalize_symbol(symbol)
    asof_d = _parse_asof(asof)
    warnings: list[str] = []
    hist = _historical_warning(asof_d)
    if hist:
        warnings.append(hist)

    start = date.fromordinal(max(asof_d.toordinal() - int(lookback_days), 1))
    bars = provider.get_daily([code], start=start, end=asof_d)
    # Strict PIT: drop any bar after asof (provider should already filter; belt-and-suspenders)
    bars = [b for b in bars if str(b.get("date", ""))[:10] <= asof_d.isoformat()]
    if not bars:
        raise AgentError(f"no daily bars for {code} asof {asof_d.isoformat()}")

    last = bars[-1]
    last_close = last.get("close")
    change_pct = last.get("change_pct")

    # Realtime only when asof is today; never inject live quote into historical runs
    if asof_d == date.today():
        try:
            rt = provider.get_realtime([code])
            if rt:
                change_pct = rt[0].get("change_pct", change_pct)
                last_close = rt[0].get("price", last_close)
        except Exception as exc:  # noqa: BLE001 — provider may lack realtime
            warnings.append(f"realtime unavailable: {exc}")
    else:
        warnings.append("已跳过 realtime（历史分析日）")

    roles = {
        "market": f"{code} 近 {len(bars)} 根日K，最新收盘 {last_close}（provider={provider.name}）",
        "fundamentals": "基本面占位：等待 financial 能力接入；本插件不直连东财/腾讯。",
        "news": "新闻占位：无内嵌抓取；由上游新闻 Provider 注入。",
        "risk": "风险提示：缺分钟/财务能力时应 fail-closed，不得静默编造。",
        "verdict": "Hold（模板结论，非投资建议）",
    }
    return ResearchReport(
        symbol=code,
        asof=asof_d.isoformat(),
        provider=getattr(provider, "name", type(provider).__name__),
        roles=roles,
        daily_bars=len(bars),
        last_close=float(last_close) if last_close is not None else None,
        change_pct=float(change_pct) if change_pct is not None else None,
        warnings=warnings,
        kind="research",
    )


def build_review_report(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
) -> ResearchReport:
    """Review slot: shorter lookback, same no-embedded-HTTP rule."""
    report = build_research_report(provider, symbol, asof=asof, lookback_days=20)
    report.kind = "review"
    report.roles["verdict"] = "复盘模板：对照信号日与下一交易日开盘，检查是否未来函数。"
    return report
