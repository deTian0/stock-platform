"""WeStock CLI adapter — local Go binary (``westock``), Markdown-table output.

Why a CLI and not HTTP
----------------------
WorkBuddy exposes market data through the ``westock`` CLI (published by Tencent at
``stockbuddy.qq.com``, SHA256-pinned install). It is a **local executable**, so —
unlike the agent-only ``neodata`` search endpoint, which needs a live
``connect_cloud_service`` token — a platform subprocess can call it inside the
15:30 / 08:30 pipeline. That is the only reason it is usable as a provider.

The CLI prints **Markdown tables** (no ``--json``), so this module owns a tiny
deterministic table parser. Column order is *not* stable between invocations
(field sets differ per market/command), therefore every read is by **header
name**, never by position.

Verified behaviour (2026-10-30, live probes)
-------------------------------------------
* ``quote`` accepts ~60 symbols per call (300/300 rows returned, 2–5 s/call) and
  already carries **same-session** open/high/low/close after the 15:00 close.
* ``kline --period day`` returns the same day's bar too, so this can also repair
  a missing session bar without waiting for the 18:30 backfill.
* ``--fq`` accepts ``nofq`` / ``qfq`` / ``hfq``; **``bfq`` fails server-side**
  (``code=1620053001``) even though ``--fq`` help text lists it.
* Omitting ``--fq`` is equivalent to ``qfq`` (verified symbol-by-symbol).
* Acceptance rule adopted here: **qfq is the contract default**. A 15-symbol ×
  8-day comparison against the engine ``market.db`` gave **0/120** mismatches for
  qfq and 120/120 for hfq — the engine store is a 前复权 series, so ``hfq`` would
  be off by two orders of magnitude.

Hard rules
----------
* Only rows whose trade date equals the requested session are accepted; a stale
  row must never masquerade as the quote day.
* ``open``/``close`` <= 0 (suspended / not yet traded) drops the whole row —
  never pad with zeros.
* Failures degrade: :func:`fetch_day_snapshot` returns ``(rows, note)`` and never
  raises; the provider methods raise only when the binary itself is absent, so
  routing can fail closed with an actionable message.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .base import AssetType
from .normalize import normalize_daily_row, normalize_realtime_row
from .symbol import exchange_prefix, normalize_symbol

PROVIDER_NAME = "westock"

ENV_WESTOCK_BIN = "STOCK_PLATFORM_WESTOCK_BIN"
ENV_WESTOCK_TIMEOUT = "STOCK_PLATFORM_WESTOCK_TIMEOUT"

DEFAULT_TIMEOUT_SEC = 60
QUOTE_CHUNK = 60  # verified: 60 symbols/call, 300/300 filled
KLINE_CHUNK = 20  # conservative; multi-code kline returns one block per symbol

# Beijing wall clock at the A-share close — used to build ``asof_ts`` when the
# vendor only reports a date.
_BJ = timezone(timedelta(hours=8))
_CLOSE_HOUR = 15

MSG_NO_BIN = (
    "未找到 westock CLI：请先安装（技能 westock-data 的 scripts/setup.cjs，"
    "默认装到 ~/.local/bin），或用 STOCK_PLATFORM_WESTOCK_BIN 指定可执行文件路径。"
    "平台不自动下载二进制。"
)

Runner = Callable[[Sequence[str]], str]


# --------------------------------------------------------------------------- #
# binary resolution / process invocation
# --------------------------------------------------------------------------- #
def resolve_westock_bin(env: dict[str, str] | None = None) -> Path | None:
    """Locate the ``westock`` executable, or ``None`` when unavailable."""
    source = env if env is not None else os.environ
    explicit = str(source.get(ENV_WESTOCK_BIN, "") or "").strip()
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    names = ["westock.exe", "westock"] if os.name == "nt" else ["westock"]
    candidates: list[Path] = [Path.home() / ".local" / "bin" / n for n in names]
    for name in names:
        found = _which(name)
        if found:
            candidates.append(Path(found))
    for path in candidates:
        if path.is_file():
            return path
    return None


def _which(name: str) -> str | None:
    from shutil import which

    return which(name)


def _timeout(env: dict[str, str] | None = None) -> int:
    source = env if env is not None else os.environ
    raw = str(source.get(ENV_WESTOCK_TIMEOUT, "") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SEC
    try:
        value = int(float(raw))
    except ValueError:
        return DEFAULT_TIMEOUT_SEC
    return value if value > 0 else DEFAULT_TIMEOUT_SEC


def run_cli(
    args: Sequence[str],
    *,
    bin_path: Path | None = None,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> str:
    """Run ``westock <args>`` and return decoded stdout (UTF-8).

    Raises ``RuntimeError`` with the vendor stderr when the binary is missing or
    the process exits non-zero — callers decide whether to degrade.
    """
    path = bin_path if bin_path is not None else resolve_westock_bin(env)
    if path is None:
        raise RuntimeError(MSG_NO_BIN)
    cmd = [str(path), *[str(a) for a in args]]
    kwargs: dict[str, Any] = {}
    if os.name == "nt":  # keep the console quiet in scheduled runs
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.run(
        cmd,
        capture_output=True,
        timeout=timeout or _timeout(env),
        **kwargs,
    )
    stdout = proc.stdout.decode("utf-8", "replace")
    stderr = proc.stderr.decode("utf-8", "replace")
    if proc.returncode != 0:
        detail = (stderr or stdout or "").strip().splitlines()
        reason = detail[0] if detail else f"exit={proc.returncode}"
        raise RuntimeError(f"westock {args[0] if args else ''} 失败：{reason}"[:300])
    # Some failures arrive on stdout with exit code 0 (vendor quirk).
    head = stdout.lstrip()[:40]
    if not head.startswith("|") and not head.startswith("[Batch]"):
        text = (stderr or stdout).strip().splitlines()
        if text and ("失败" in text[0] or "error" in text[0].lower()):
            raise RuntimeError(f"westock {args[0] if args else ''} 失败：{text[0]}"[:300])
    return stdout


# --------------------------------------------------------------------------- #
# Markdown table parsing (pure)
# --------------------------------------------------------------------------- #
def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_separator(cells: Iterable[str]) -> bool:
    items = list(cells)
    return bool(items) and all(set(c) <= {"-", ":", " "} for c in items)


def parse_md_table(text: str) -> tuple[list[str], list[list[str]]]:
    """Parse the first Markdown table in ``text`` as ``(headers, rows)``."""
    lines = [ln.strip() for ln in str(text or "").splitlines() if ln.strip().startswith("|")]
    if len(lines) < 2:
        return [], []
    headers = _cells(lines[0])
    rows: list[list[str]] = []
    for line in lines[1:]:
        cells = _cells(line)
        if _is_separator(cells):
            continue
        rows.append(cells)
    return headers, rows


def _num(value: Any) -> float | None:
    try:
        out = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def _code6(raw: Any) -> str:
    text = str(raw or "").strip()
    for prefix in ("sh", "sz", "bj", "SH", "SZ", "BJ"):
        if text.startswith(prefix):
            text = text[len(prefix) :]
            break
    text = text.split(".")[0]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:] if digits else ""


def _ws_code(code: str) -> str | None:
    """``600519`` → ``sh600519`` (same authority as the rest of the CN surface)."""
    six = _code6(code)
    if len(six) != 6:
        return None
    return f"{exchange_prefix(six)}{six}"


def _pick(head: list[str], cells: list[str], *names: str) -> str | None:
    for name in names:
        if name in head:
            idx = head.index(name)
            if idx < len(cells):
                return cells[idx]
    return None


def _bar(
    *, day: str, trade_date: Any, open_: Any, high: Any, low: Any, close: Any
) -> dict[str, Any] | None:
    """Assemble one OHLC bar, or ``None`` when it is unusable/stale."""
    if str(trade_date or "").strip()[:10] != str(day)[:10]:
        return None
    values = {
        "open": _num(open_),
        "high": _num(high),
        "low": _num(low),
        "close": _num(close),
    }
    if not values["close"] or values["close"] <= 0:
        return None
    if not values["open"] or values["open"] <= 0:
        return None
    return values


def parse_quote_rows(text: str, day: str) -> dict[str, dict[str, Any]]:
    """Parse ``westock quote`` output into ``{code6: {open, high, low, close}}``."""
    head, rows = parse_md_table(text)
    if not head:
        return {}
    out: dict[str, dict[str, Any]] = {}
    for cells in rows:
        code = _code6(_pick(head, cells, "symbol", "code"))
        if not code:
            continue
        bar = _bar(
            day=day,
            trade_date=_pick(head, cells, "time", "date"),
            open_=_pick(head, cells, "open"),
            high=_pick(head, cells, "high"),
            low=_pick(head, cells, "low"),
            close=_pick(head, cells, "price", "close", "last"),
        )
        if bar:
            out[code] = bar
    return out


def parse_kline_rows(
    text: str,
    *,
    symbols: Sequence[str] = (),
) -> dict[str, list[dict[str, Any]]]:
    """Parse ``westock kline`` output into ``{code6: [raw bar dicts]}``.

    A single-symbol request omits the ``code`` column, so ``symbols`` supplies
    the fallback identity (and is ignored when the column is present).
    """
    head, rows = parse_md_table(text)
    if not head:
        return {}
    has_code = "code" in head
    fallback = ""
    if not has_code:
        cleaned = [_code6(s) for s in symbols if _code6(s)]
        fallback = cleaned[0] if len(cleaned) == 1 else ""
        if not fallback:
            return {}
    out: dict[str, list[dict[str, Any]]] = {}
    for cells in rows:
        code = _code6(_pick(head, cells, "code")) if has_code else fallback
        if not code:
            continue
        trade_date = str(_pick(head, cells, "date") or "").strip()[:10]
        if not trade_date:
            continue
        verdict = _num(_pick(head, cells, "last", "close"))
        if verdict is None or verdict <= 0:
            continue
        out.setdefault(code, []).append(
            {
                "symbol": code,
                "date": trade_date,
                "open": _num(_pick(head, cells, "open")),
                "high": _num(_pick(head, cells, "high")),
                "low": _num(_pick(head, cells, "low")),
                "close": verdict,
                "volume": _num(_pick(head, cells, "volume")),
                "amount": _num(_pick(head, cells, "amount")),
                "change_pct": _num(_pick(head, cells, "change_pct")),
                "pct_unit": "percent",
            }
        )
    return out


# --------------------------------------------------------------------------- #
# P0 — day_quote 4th source
# --------------------------------------------------------------------------- #
def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def fetch_day_snapshot(
    symbols: list[str],
    day: str,
    *,
    runner: Runner | None = None,
) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Same-session OHLC for ``symbols`` via ``westock quote --date <day>``.

    Mirrors :func:`stock_platform_providers.snapshot.fetch_day_snapshot` so the
    caller can treat the two interchangeably. Returns ``(rows, note)``; ``note``
    is ``None`` when nothing failed. **Never raises.**
    """
    day_s = str(day)[:10]
    try:
        date.fromisoformat(day_s)
    except ValueError:
        return {}, f"非法交易日 {day!r}"

    papers: dict[str, str] = {}
    for raw in symbols:
        paper = _ws_code(raw)
        if paper:
            papers.setdefault(paper, _code6(raw))
    if not papers:
        return {}, "无可请求的标的"

    exec_args = runner or (lambda args: run_cli(args))
    rows: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    ordered = list(papers)
    requested = set(papers.values())
    for chunk in _chunks(ordered, QUOTE_CHUNK):
        try:
            text = exec_args(["quote", ",".join(chunk), "--date", day_s])
        except Exception as exc:  # noqa: BLE001 — 兜底源只降级
            errors.append(f"{type(exc).__name__}")
            continue
        for code, bar in parse_quote_rows(text, day_s).items():
            if code in requested:  # 厂商可能多回未请求的标的，绝不外溢
                rows.setdefault(code, bar)

    missing = [papers[p] for p in ordered if papers[p] not in rows]
    if not rows:
        return {}, "westock 快照全部失败" + (f"（{' / '.join(errors)}）" if errors else "")
    if missing:
        return rows, f"westock 快照缺 {len(missing)}/{len(papers)} 只" + (
            f"（{' / '.join(errors)}）" if errors else ""
        )
    return rows, None


# --------------------------------------------------------------------------- #
# P1 — provider for the capability matrix
# --------------------------------------------------------------------------- #
def _asof_ms(day: str) -> int | None:
    """Beijing 15:00 on ``day`` → epoch milliseconds (vendor reports date only)."""
    try:
        d = date.fromisoformat(str(day)[:10])
    except ValueError:
        return None
    return int(datetime(d.year, d.month, d.day, _CLOSE_HOUR, tzinfo=_BJ).timestamp() * 1000)


class WestockProvider:
    """CN ``daily`` / ``realtime`` via the local ``westock`` CLI.

    ``daily`` uses ``kline --period day`` with the default (qfq) adjustment — the
    only mode that matches the engine ``market.db`` series (see module docstring).
    ``realtime`` uses ``quote``, whose ``price`` is the session close after 15:00.
    """

    name = PROVIDER_NAME

    def __init__(
        self,
        *,
        bin_path: str | Path | None = None,
        timeout: int | None = None,
        runner: Runner | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self._env = env
        self._explicit = Path(bin_path).expanduser() if bin_path is not None else None
        self._timeout = timeout
        self._runner = runner

    # -- plumbing ---------------------------------------------------------- #
    @property
    def bin_path(self) -> Path | None:
        return self._explicit or resolve_westock_bin(self._env)

    def _exec(self, args: Sequence[str]) -> str:
        if self._runner is not None:
            return self._runner(args)
        return run_cli(args, bin_path=self.bin_path, timeout=self._timeout, env=self._env)

    def _require_bin(self) -> None:
        if self._runner is None and self.bin_path is None:
            raise RuntimeError(MSG_NO_BIN)

    # -- capabilities ------------------------------------------------------ #
    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        self._require_bin()
        start_s = (start or date(1990, 1, 1)).isoformat()
        end_s = (end or date(2099, 12, 31)).isoformat()
        wanted: dict[str, str] = {}
        for raw in symbols:
            paper = _ws_code(raw)
            if paper:
                wanted.setdefault(paper, _code6(raw))
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(list(wanted), KLINE_CHUNK):
            chunk_codes = {wanted[c] for c in chunk}
            text = self._exec(
                [
                    "kline",
                    ",".join(chunk),
                    "--period",
                    "day",
                    "--start",
                    start_s,
                    "--end",
                    end_s,
                    "--fq",
                    "qfq",
                ]
            )
            parsed = parse_kline_rows(text, symbols=[wanted[c] for c in chunk])
            for code, bars in parsed.items():
                if code not in chunk_codes:
                    continue  # 厂商多回的标的不外溢
                for bar in bars:
                    d = date.fromisoformat(bar["date"])
                    if start and d < start:
                        continue
                    if end and d > end:
                        continue
                    try:
                        row = normalize_daily_row(
                            bar,
                            source=self.name,
                            asset_type=asset_type,
                            default_symbol=code,
                            market="CN",
                        )
                    except ValueError:
                        continue
                    rows.append(row)
        rows.sort(key=lambda r: (r["symbol"], r["date"]))
        # ``kline`` 不回首日前的收盘，用同标的上一根 close 回填 pre_close（首根留 None）。
        prev_close: dict[str, float] = {}
        for row in rows:
            symbol = row["symbol"]
            if row.get("pre_close") is None and symbol in prev_close:
                row["pre_close"] = prev_close[symbol]
            if row.get("close") is not None:
                prev_close[symbol] = row["close"]
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        self._require_bin()
        wanted: dict[str, str] = {}
        for raw in symbols:
            paper = _ws_code(raw)
            if paper:
                wanted.setdefault(paper, _code6(raw))
        rows: list[dict[str, Any]] = []
        for chunk in _chunks(list(wanted), QUOTE_CHUNK):
            chunk_codes = {wanted[c] for c in chunk}
            head, table = parse_md_table(self._exec(["quote", ",".join(chunk)]))
            if not head:
                continue
            for cells in table:
                code = _code6(_pick(head, cells, "symbol", "code"))
                if not code or code not in chunk_codes:
                    continue
                asof = _asof_ms(_pick(head, cells, "time") or "")
                if asof is None:
                    continue
                raw = {
                    "symbol": code,
                    "name": _pick(head, cells, "name"),
                    "price": _pick(head, cells, "price", "last"),
                    "prev_close": _pick(head, cells, "prev_close"),
                    "change_amount": _pick(head, cells, "change"),
                    "change_pct": _pick(head, cells, "change_percent", "change_pct"),
                    "amplitude": _pick(head, cells, "range_pct"),
                    "turnover_rate": _pick(head, cells, "turnover_rate"),
                    "volume": _pick(head, cells, "volume"),
                    "amount": _pick(head, cells, "amount"),
                    "asof_ts": asof,
                    "pct_unit": "percent",
                }
                try:
                    rows.append(
                        normalize_realtime_row(
                            raw,
                            source=self.name,
                            asset_type=asset_type,
                            default_symbol=code,
                            market="CN",
                        )
                    )
                except ValueError:
                    continue
        return rows


__all__ = [
    "ENV_WESTOCK_BIN",
    "ENV_WESTOCK_TIMEOUT",
    "KLINE_CHUNK",
    "MSG_NO_BIN",
    "PROVIDER_NAME",
    "QUOTE_CHUNK",
    "WestockProvider",
    "fetch_day_snapshot",
    "parse_kline_rows",
    "parse_md_table",
    "parse_quote_rows",
    "resolve_westock_bin",
    "run_cli",
]
