"""Deterministic Bull/Bear/Risk debate — MarketDataProvider only, no LLM/HTTP."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any, Literal

from stock_platform_providers import normalize_symbol

from .errors import AgentError
from .report import SupportsMarketData, _historical_warning, _parse_asof

Verdict = Literal["Buy", "Hold", "Sell"]


@dataclass
class DebateRound:
    role: str
    thesis: str


@dataclass
class DebateReport:
    symbol: str
    asof: str
    provider: str
    rounds: list[DebateRound]
    score: dict[str, float]
    verdict: Verdict
    daily_bars: int
    last_close: float | None
    warnings: list[str] = field(default_factory=list)
    kind: str = "debate"
    disclaimer: str = "模板结论，非投资建议；确定性规则辩论，未调用 LLM。"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    out: list[float] = []
    for bar in bars:
        c = bar.get("close")
        if c is None:
            continue
        out.append(float(c))
    return out


def _metrics(closes: list[float]) -> dict[str, float]:
    if len(closes) < 2:
        raise AgentError("need at least 2 daily closes for debate scoring")
    first, last = closes[0], closes[-1]
    ret = (last / first) - 1.0 if first else 0.0
    peak = closes[0]
    max_dd = 0.0
    down_days = 0
    for i, c in enumerate(closes):
        if c > peak:
            peak = c
        if peak:
            max_dd = min(max_dd, (c / peak) - 1.0)
        if i > 0 and c < closes[i - 1]:
            down_days += 1
    ma = sum(closes) / len(closes)
    vs_ma = (last / ma) - 1.0 if ma else 0.0
    # simple volatility proxy: mean abs day-to-day return
    day_rets = []
    for i in range(1, len(closes)):
        if closes[i - 1]:
            day_rets.append(abs((closes[i] / closes[i - 1]) - 1.0))
    vol = sum(day_rets) / len(day_rets) if day_rets else 0.0
    down_ratio = down_days / max(len(closes) - 1, 1)
    return {
        "return": ret,
        "max_drawdown": max_dd,
        "vs_ma": vs_ma,
        "vol": vol,
        "down_ratio": down_ratio,
    }


def _score(m: dict[str, float]) -> dict[str, float]:
    """Positive score leans Bull; negative leans Bear. Risk is magnitude of stress."""
    bull = 0.0
    bear = 0.0
    if m["return"] > 0:
        bull += min(m["return"] * 10.0, 2.0)
    else:
        bear += min(abs(m["return"]) * 10.0, 2.0)
    if m["vs_ma"] > 0:
        bull += min(m["vs_ma"] * 8.0, 1.5)
    else:
        bear += min(abs(m["vs_ma"]) * 8.0, 1.5)
    bear += min(abs(m["max_drawdown"]) * 8.0, 2.0)
    bear += min(m["down_ratio"] * 2.0, 1.5)
    risk = min(m["vol"] * 20.0 + abs(m["max_drawdown"]) * 5.0, 3.0)
    net = bull - bear
    return {"bull": round(bull, 4), "bear": round(bear, 4), "risk": round(risk, 4), "net": round(net, 4)}


def _verdict(score: dict[str, float]) -> Verdict:
    net = score["net"]
    if net >= 0.75:
        return "Buy"
    if net <= -0.75:
        return "Sell"
    return "Hold"


def build_debate_report(
    provider: SupportsMarketData,
    symbol: str,
    *,
    asof: str | date | None = None,
    lookback_days: int = 60,
) -> DebateReport:
    code = normalize_symbol(symbol)
    asof_d = _parse_asof(asof)
    warnings: list[str] = []
    hist = _historical_warning(asof_d)
    if hist:
        warnings.append(hist)

    start = date.fromordinal(max(asof_d.toordinal() - int(lookback_days), 1))
    bars = provider.get_daily([code], start=start, end=asof_d)
    bars = [b for b in bars if str(b.get("date", ""))[:10] <= asof_d.isoformat()]
    if not bars:
        raise AgentError(f"no daily bars for {code} asof {asof_d.isoformat()}")

    if asof_d == date.today():
        try:
            provider.get_realtime([code])
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"realtime unavailable: {exc}")
    else:
        warnings.append("已跳过 realtime（历史分析日）")

    closes = _closes(bars)
    metrics = _metrics(closes)
    score = _score(metrics)
    verdict = _verdict(score)
    last_close = closes[-1]

    rounds = [
        DebateRound(
            role="bull",
            thesis=(
                f"近 {len(closes)} 日累计收益 {metrics['return']:.2%}，"
                f"收盘相对均线 {metrics['vs_ma']:.2%}；看多侧引用动量与均线支撑。"
            ),
        ),
        DebateRound(
            role="bear",
            thesis=(
                f"区间最大回撤 {metrics['max_drawdown']:.2%}，阴线占比 {metrics['down_ratio']:.0%}；"
                f"看空侧强调回撤与弱势日。"
            ),
        ),
        DebateRound(
            role="risk",
            thesis=(
                f"日波动代理 {metrics['vol']:.2%}，风险分 {score['risk']:.2f}；"
                f"缺分钟/财务能力时不得编造，应 fail-closed。"
            ),
        ),
        DebateRound(
            role="judge",
            thesis=(
                f"模板裁决 {verdict}（net={score['net']:.2f}）。"
                f"非投资建议；未调用 LLM。"
            ),
        ),
    ]

    return DebateReport(
        symbol=code,
        asof=asof_d.isoformat(),
        provider=getattr(provider, "name", type(provider).__name__),
        rounds=rounds,
        score=score,
        verdict=verdict,
        daily_bars=len(bars),
        last_close=last_close,
        warnings=warnings,
    )
