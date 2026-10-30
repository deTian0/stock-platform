"""Same-session OHLC snapshot fallback — Tencent / Sina batch quotes.

Why this module exists
----------------------
East Money ``push2his/kline`` is the primary daily-bar source, but it is a
single point of failure: when the host refuses connections (``RemoteDisconnected``)
or its circuit breaker trips, **every** symbol loses open/high/low at once and the
digest's 「开盘/收盘/涨跌」 columns render as ``—`` for the whole session
(observed 2026-10-29 and again 2026-10-30).

Tencent ``qt.gtimg.cn`` and Sina ``hq.sinajs.cn`` are plain batch quote endpoints
(one request for many symbols, GBK text) that carry the **same-session**
open/high/low/close. They are independent of East Money and of each other, so
they can refill the gap instead of leaving the columns blank.

Hard rules
----------
* **Only rows whose trade date equals the requested session are accepted.** A
  stale snapshot must never be presented as the quote day; a row with no
  parseable date is dropped.
* These are non-East-Money endpoints, so they **must not** go through ``em_get``
  (same convention as the Sina financial / adj-factor paths in
  :mod:`stock_platform_providers.astock_http`).
* Any failure returns ``{}`` — callers degrade, never raise.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any, Callable

from .symbol import exchange_prefix

TENCENT_SNAPSHOT_URL = "https://qt.gtimg.cn/q="
SINA_SNAPSHOT_URL = "https://hq.sinajs.cn/list="

TENCENT_REFERER = "https://finance.qq.com/"
SINA_REFERER = "https://finance.sina.com.cn/"

DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# One request per chunk keeps the URL well under the ~2 KB vendor limit.
SNAPSHOT_CHUNK = 50
SNAPSHOT_TIMEOUT = 12

# Tencent ``~``-separated fields used here (verified on live payloads).
_TQ_PRICE = 3  # 当前价 == 当日收盘（收盘后不再变动）
_TQ_PREV_CLOSE = 4
_TQ_OPEN = 5
_TQ_TIMESTAMP = 30  # yyyymmddHHMMSS
_TQ_HIGH = 33
_TQ_LOW = 34

# Sina ``,``-separated fields.
_SN_OPEN = 1
_SN_PREV_CLOSE = 2
_SN_CLOSE = 3
_SN_HIGH = 4
_SN_LOW = 5
_SN_DATE = 30  # yyyy-mm-dd
_SN_TIME = 31

_TQ_LINE = re.compile(r'v_(?P<paper>[a-z]{2}\d{6})="(?P<body>[^"]*)"')
_SN_LINE = re.compile(r'var hq_str_(?P<paper>[a-z]{2}\d{6})="(?P<body>[^"]*)"')


def _sym6(code: str) -> str:
    digits = "".join(ch for ch in str(code or "").split(".")[0] if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def _paper(code: str) -> str | None:
    six = _sym6(code)
    if len(six) != 6:
        return None
    return f"{exchange_prefix(six)}{six}"


def _float(raw: Any) -> float | None:
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return None
    if value != value:  # NaN
        return None
    return value


def _row(*, day: str, trade_date: str, open_: Any, high: Any, low: Any, close: Any) -> dict[str, Any] | None:
    """Assemble one OHLC row, or ``None`` when the bar is unusable."""
    if str(trade_date)[:10] != str(day)[:10]:
        return None  # 非本交易日的快照一律丢弃，绝不冒充当日行情
    values = {
        "open": _float(open_),
        "high": _float(high),
        "low": _float(low),
        "close": _float(close),
    }
    # 停牌/未开盘时厂商会给 0 或空；补零会污染涨跌幅，直接整行丢弃。
    if not values["close"] or values["close"] <= 0:
        return None
    if not values["open"] or values["open"] <= 0:
        return None
    return values


def parse_tencent_snapshot(text: str, day: str) -> dict[str, dict[str, Any]]:
    """Parse a ``qt.gtimg.cn`` body into ``{code6: {open, high, low, close}}``."""
    rows: dict[str, dict[str, Any]] = {}
    for match in _TQ_LINE.finditer(str(text or "")):
        fields = match.group("body").split("~")
        if len(fields) <= _TQ_LOW:
            continue
        stamp = str(fields[_TQ_TIMESTAMP]).strip()[:8]
        if len(stamp) != 8 or not stamp.isdigit():
            continue
        row = _row(
            day=day,
            trade_date=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:8]}",
            open_=fields[_TQ_OPEN],
            high=fields[_TQ_HIGH],
            low=fields[_TQ_LOW],
            close=fields[_TQ_PRICE],
        )
        code = _sym6(fields[2] if len(fields) > 2 else match.group("paper"))
        if row and code:
            rows[code] = row
    return rows


def parse_sina_snapshot(text: str, day: str) -> dict[str, dict[str, Any]]:
    """Parse a ``hq.sinajs.cn`` body into ``{code6: {open, high, low, close}}``."""
    rows: dict[str, dict[str, Any]] = {}
    for match in _SN_LINE.finditer(str(text or "")):
        fields = match.group("body").split(",")
        if len(fields) <= _SN_LOW:
            continue
        trade_date = str(fields[_SN_DATE]).strip() if len(fields) > _SN_DATE else ""
        row = _row(
            day=day,
            trade_date=trade_date,
            open_=fields[_SN_OPEN],
            high=fields[_SN_HIGH],
            low=fields[_SN_LOW],
            close=fields[_SN_CLOSE],
        )
        code = _sym6(match.group("paper"))
        if row and code:
            rows[code] = row
    return rows


def _http_text(url: str, referer: str) -> str:
    """GBK plain-text GET. Non-East-Money, so no ``em_get`` (see module docstring)."""
    import requests

    from .eastmoney import http_trust_env

    with requests.Session() as session:
        session.trust_env = http_trust_env()
        resp = session.get(
            url,
            headers={"User-Agent": DEFAULT_UA, "Referer": referer},
            timeout=SNAPSHOT_TIMEOUT,
        )
        resp.raise_for_status()
        resp.encoding = "gbk"
        return resp.text


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_day_snapshot(
    symbols: list[str],
    day: str,
    *,
    get_text: Callable[[str, str], str] | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Same-session OHLC for ``symbols`` via Tencent, then Sina for the rest.

    Returns ``(rows, note)``. ``note`` is ``None`` when every requested symbol was
    filled, otherwise a short human-readable reason (never raises).
    """
    day_s = str(day)[:10]
    try:
        date.fromisoformat(day_s)
    except ValueError:
        return {}, f"非法交易日 {day!r}"

    papers: dict[str, str] = {}
    for raw in symbols:
        paper = _paper(raw)
        if paper:
            papers.setdefault(paper, _sym6(raw))
    if not papers:
        return {}, "无可请求的标的"

    fetch = get_text or _http_text
    rows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    ordered = list(papers)
    for label, base_url, referer, parser in (
        ("tencent", TENCENT_SNAPSHOT_URL, TENCENT_REFERER, parse_tencent_snapshot),
        ("sina", SINA_SNAPSHOT_URL, SINA_REFERER, parse_sina_snapshot),
    ):
        pending = [p for p in ordered if papers[p] not in rows]
        if not pending:
            break
        for chunk in _chunks(pending, SNAPSHOT_CHUNK):
            url = base_url + ",".join(chunk)
            try:
                parsed = parser(fetch(url, referer), day_s)
            except Exception as exc:  # noqa: BLE001 — 备用源失败只降级
                errors.append(f"{label}:{type(exc).__name__}")
                continue
            for code, row in parsed.items():
                rows.setdefault(code, row)

    missing = [papers[p] for p in ordered if papers[p] not in rows]
    if not rows:
        return {}, "腾讯/新浪快照全部失败" + (f"（{' / '.join(errors)}）" if errors else "")
    if missing:
        return rows, f"快照缺 {len(missing)}/{len(papers)} 只" + (
            f"（{' / '.join(errors)}）" if errors else ""
        )
    return rows, None


__all__ = [
    "SINA_SNAPSHOT_URL",
    "SNAPSHOT_CHUNK",
    "TENCENT_SNAPSHOT_URL",
    "fetch_day_snapshot",
    "parse_sina_snapshot",
    "parse_tencent_snapshot",
]
