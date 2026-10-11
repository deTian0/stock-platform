"""WorkBuddy MCP bridge — ``westock`` CLI output → provider JSON cache.

Why this module exists
----------------------
The ``workbuddy`` provider (:mod:`stock_platform_providers.workbuddy`) is a
deliberately dumb, fully offline **reader** of a JSON cache directory. Nothing
in the platform ever *populated* that cache: the module docstring named an "MCP
bridge" that was never written, so "workbuddy mode" could never actually carry
live data.

The bridge is that missing half. WorkBuddy ships the :command:`westock` CLI
(``westock-data`` skill, Go binary published at
``https://stockbuddy.qq.com/release/workbuddy/cli``) whose ``kline`` and
``quote`` sub-commands emit **stable Markdown tables**. This module:

1. shells out to ``westock`` for a symbol list (batched, comma-separated);
2. parses the Markdown table back into row dicts;
3. hands them to the canonical writers
   (:func:`~stock_platform_providers.workbuddy.write_daily_cache` /
   :func:`write_realtime_cache`) so the *schema lives in exactly one place*.

Design rules (mirroring the rest of the platform)
-------------------------------------------------
- **The provider stays read-only.** Only this module writes the cache.
- **No second schema.** Bars are shaped for
  :func:`~stock_platform_providers.normalize.normalize_daily_row`; the writers
  own the on-disk layout.
- **Fail-soft per symbol.** One bad symbol must not sink a whole refresh run;
  every failure is collected into :class:`BridgeReport` and surfaced, never
  swallowed silently.
- **Unit-testable with zero network.** Parsing and the writer hand-off are pure
  functions of text; only :func:`westock_kline` touches a subprocess, and
  :func:`run_bridge` accepts an injectable *runner* so tests never spawn one.
- **Explicit provenance.** Every run reports the resolved CLI path + version,
  because "which binary produced this cache" is exactly the question a stale
  cache makes unanswerable.

Field mapping (``kline`` → ``normalize_daily_row``)
---------------------------------------------------
``westock`` names the close column ``last`` and reports ``change_pct`` already
in percent (``0.5741405808`` == ``+0.574%``). ``exchange`` is the turnover
*rate* in percent, not an exchange code — it is dropped rather than smuggled
into a field with a different meaning. So:

===============  ====================  ==================================
westock column   provider field        note
===============  ====================  ==================================
date             date                  ISO ``YYYY-MM-DD``
open             open                  —
last             close                 renamed
high / low       high / low            —
volume           volume                手
amount           amount                元
change_pct       change_pct            ``pct_unit="percent"`` so the
                                       normalizer divides by 100
===============  ====================  ==================================
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

ENV_WESTOCK_BIN = "STOCK_PLATFORM_WESTOCK_BIN"
ENV_WORKBUDDY_CACHE_DIR = "STOCK_PLATFORM_WORKBUDDY_CACHE_DIR"

PROVIDER_NAME = "workbuddy"
DEFAULT_PERIOD = "day"
DEFAULT_ADJUST = "qfq"
DEFAULT_LIMIT = 120
DEFAULT_TIMEOUT_S = 60

#: Sane default install location used by the shipped ``setup.cjs`` / ``setup.ps1``.
DEFAULT_BIN_DIRS = (
    "~/.local/bin",
    "~/.westock/bin",
)

MSG_NO_BIN = (
    "未找到 westock CLI：请用 finance-data 插件的安装脚本装好后重试，"
    "或设置 STOCK_PLATFORM_WESTOCK_BIN 指向可执行文件。\n"
    "  node <plugin>/skills/westock-data/scripts/setup.cjs -d %USERPROFILE%\\.local\\bin -y"
)
MSG_NO_CACHE_DIR = (
    "未配置 WorkBuddy 数据缓存目录：请设置 STOCK_PLATFORM_WORKBUDDY_CACHE_DIR"
    "（桥会把 westock 数据写到这里，provider 再从只读消费）。"
)

_RE_MD_SEP = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")


# --------------------------------------------------------------------------- #
# Markdown table parsing
# --------------------------------------------------------------------------- #
def _split_md_row(line: str) -> list[str]:
    """Split one Markdown table row into trimmed cells (outer pipes optional)."""
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _is_separator_row(cells: Sequence[str]) -> bool:
    """``--- | ---`` style divider row (dashes/colons only)."""
    if not cells:
        return False
    return all(cell == "" or set(cell) <= {"-", ":", " "} for cell in cells)


def parse_markdown_tables(text: str) -> list[dict[str, list[str]]]:
    """Extract every Markdown table in ``text`` as ``{"columns": [...], "rows": [...]}``.

    Handles the two shapes ``westock`` emits: a header row followed by a
    separator row then data rows; and the batch variant (``kline a,b``) which
    prefixes each table with a ``[Batch]`` status line — such lines are skipped
    because they never look like a table.
    """
    tables: list[dict[str, list[str]]] = []
    columns: list[str] | None = None
    rows: list[list[str]] = []

    def flush() -> None:
        nonlocal columns, rows
        if columns is not None and rows:
            tables.append({"columns": columns, "rows": rows})
        columns, rows = None, []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            flush()
            continue
        if "|" not in line:
            # A non-table line ends any table in progress (e.g. "[Batch] …").
            flush()
            continue
        cells = _split_md_row(line)
        if _is_separator_row(cells):
            continue
        if columns is None:
            columns = cells
            continue
        if len(cells) == len(columns):
            rows.append(cells)
        else:
            # Width mismatch → treat as the start of a different table.
            flush()
            columns = cells
    flush()
    return tables


def rows_from_table(table: dict[str, list[str]]) -> list[dict[str, str]]:
    """Zip ``columns`` with each row into dicts (short rows are padded)."""
    columns = list(table["columns"])
    out: list[dict[str, str]] = []
    for row in table["rows"]:
        cells = list(row) + [""] * (len(columns) - len(row))
        out.append({col: cells[i] for i, col in enumerate(columns)})
    return out


# --------------------------------------------------------------------------- #
# westock row → provider vendor dict
# --------------------------------------------------------------------------- #
def _f(value: Any) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def kline_row_to_bar(row: dict[str, str], *, symbol: str | None = None) -> dict[str, Any]:
    """Map one ``westock kline`` table row onto a ``normalize_daily_row`` dict.

    ``last`` is the close column; ``change_pct`` is percent-scaled and flagged
    via ``pct_unit`` so the normalizer converts it to a decimal. Unknown columns
    (``exchange``) are ignored on purpose — see the module docstring.
    """
    sym = (symbol or row.get("code") or row.get("symbol") or "").strip()
    bar: dict[str, Any] = {
        "date": (row.get("date") or "").strip(),
        "open": _f(row.get("open")),
        "high": _f(row.get("high")),
        "low": _f(row.get("low")),
        "close": _f(row.get("last") if row.get("last") not in (None, "") else row.get("close")),
        "volume": _f(row.get("volume")),
        "amount": _f(row.get("amount")),
        "change_pct": _f(row.get("change_pct")),
        "pct_unit": "percent",
    }
    if sym:
        bar["symbol"] = sym
    return bar


def quote_row_to_quote(row: dict[str, str], *, symbol: str | None = None) -> dict[str, Any]:
    """Map one ``westock quote`` row onto a ``normalize_realtime_row`` dict.

    ``quote`` emits far more columns than ``realtime`` needs; the ones the
    contract understands are lifted, everything else (``pe_ratio``, ``wb_ratio``
    …) is carried through as extra keys so nothing is lost for future datasets —
    :func:`normalize_realtime_row` simply ignores what it does not declare.
    """
    sym = (symbol or row.get("symbol") or row.get("code") or "").strip()
    quote: dict[str, Any] = {
        "name": (row.get("name") or "").strip() or None,
        "price": _f(row.get("price") or row.get("last")),
        "prev_close": _f(row.get("prev_close") or row.get("pre_close")),
        "change_amount": _f(row.get("change") or row.get("change_amount")),
        "change_pct": _f(row.get("change_percent") or row.get("change_pct")),
        "turnover_rate": _f(row.get("turnover_rate")),
        "volume": _f(row.get("volume")),
        "amount": _f(row.get("amount")),
        "pct_unit": "percent",
    }
    if sym:
        quote["symbol"] = sym
    if (row.get("time") or "").strip():
        quote["time"] = row["time"].strip()
    for extra in ("pe_ratio", "pb_ratio", "total_market_cap", "circulating_market_cap", "high", "low", "open"):
        if (row.get(extra) or "").strip():
            quote[extra] = row[extra].strip()
    return quote


# --------------------------------------------------------------------------- #
# subprocess layer
# --------------------------------------------------------------------------- #
def resolve_westock_bin(env: dict[str, str] | None = None) -> str | None:
    """Locate the ``westock`` executable (env override → PATH → known dirs).

    Returns the resolved path, or ``None`` when nothing is installed — callers
    turn that into :data:`MSG_NO_BIN` rather than a bare ``FileNotFoundError``.
    """
    source: dict[str, str] = os.environ if env is None else env  # type: ignore[assignment]
    raw = str(source.get(ENV_WESTOCK_BIN, "") or "")
    if raw.strip():
        # An override was supplied: honour it or fail. Never let a broken
        # override silently degrade into auto-discovery — that would hide a
        # typo'd path behind "it worked yesterday".
        return _resolve_explicit_bin(raw)

    found = shutil.which("westock")
    if found:
        return found
    for raw_dir in DEFAULT_BIN_DIRS:
        for name in ("westock.exe", "westock"):
            candidate = (Path(raw_dir).expanduser() / name)
            if candidate.is_file():
                return str(candidate)
    return None


def _resolve_explicit_bin(raw: str) -> str | None:
    """Resolve a user-supplied ``STOCK_PLATFORM_WESTOCK_BIN`` value.

    Accepts an absolute path, a path containing a separator (resolved relative
    to the CWD) or a bare command name (resolved via ``PATH``). Returns ``None``
    when the key is unset so the caller can fall through to auto-discovery.
    """
    text = raw.strip()
    if not text:
        return None
    candidate = Path(text).expanduser()
    if candidate.is_file():
        return str(candidate)
    # A separator means "this is a path" — do not silently degrade to PATH.
    if os.sep in text or (os.altsep and os.altsep in text):
        return None
    return shutil.which(text)


def westock_version(binary: str, *, timeout: int = DEFAULT_TIMEOUT_S) -> str | None:
    """Best-effort ``westock --version`` probe (``None`` on any failure)."""
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return (proc.stdout or proc.stderr or "").strip().splitlines()[0] if (proc.stdout or proc.stderr) else None


def run_westock(
    binary: str,
    args: Sequence[str],
    *,
    timeout: int = DEFAULT_TIMEOUT_S,
) -> tuple[int, str]:
    """Run ``binary args`` and return ``(returncode, stdout+stderr)``.

    Never raises on a non-zero exit — the CLI is agent-facing and puts status
    lines on stdout, so the caller decides what counts as success.
    """
    proc = subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part)
    return proc.returncode, combined


def _chunks(items: Sequence[str], size: int) -> Iterable[list[str]]:
    for i in range(0, len(items), size):
        yield list(items[i : i + size])


# --------------------------------------------------------------------------- #
# high-level driver
# --------------------------------------------------------------------------- #
@dataclass
class SymbolResult:
    """Outcome of bridging one dataset for one symbol."""

    symbol: str
    dataset: str
    ok: bool
    bars: int = 0
    path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "dataset": self.dataset,
            "ok": self.ok,
            "bars": self.bars,
            "path": self.path,
            "error": self.error,
        }


@dataclass
class BridgeReport:
    """Aggregate of one bridge run (daily and/or realtime)."""

    cache_dir: str
    binary: str
    version: str | None = None
    items: list[SymbolResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    dry_run: bool = False

    @property
    def failures(self) -> list[SymbolResult]:
        return [i for i in self.items if not i.ok]

    @property
    def ok_count(self) -> int:
        return sum(1 for i in self.items if i.ok)

    @property
    def bar_count(self) -> int:
        return sum(i.bars for i in self.items if i.ok)

    @property
    def success(self) -> bool:
        """A run succeeds when it did *something* and nothing hard-failed."""
        return bool(self.items) and not self.failures

    def to_dict(self) -> dict[str, Any]:
        return {
            "cacheDir": self.cache_dir,
            "binary": self.binary,
            "version": self.version,
            "dryRun": self.dry_run,
            "itemCount": len(self.items),
            "okCount": self.ok_count,
            "failCount": len(self.failures),
            "barCount": self.bar_count,
            "success": self.success,
            "warnings": list(self.warnings),
            "items": [i.to_dict() for i in self.items],
            "failures": [i.to_dict() for i in self.failures],
        }


Runner = Callable[[str, Sequence[str]], tuple[int, str]]


def _batch_size(command: str) -> int:
    """Codes per subprocess call (batch keeps process count sane)."""
    return 40 if command == "kline" else 30


def bridge_daily(
    symbols: Sequence[str],
    cache_dir: str | Path,
    *,
    binary: str,
    runner: Runner,
    period: str = DEFAULT_PERIOD,
    adjust: str = DEFAULT_ADJUST,
    limit: int = DEFAULT_LIMIT,
    start: str | None = None,
    end: str | None = None,
    report: BridgeReport | None = None,
    dry_run: bool = False,
) -> BridgeReport:
    """Fetch daily K-lines for ``symbols`` and write ``daily_{code}.json`` files."""
    from stock_platform_providers.workbuddy import write_daily_cache

    d = Path(cache_dir).expanduser()
    rep = report if report is not None else BridgeReport(cache_dir=str(d), binary=binary)
    syms = [s for s in dict.fromkeys(str(x).strip() for x in symbols) if s]

    for group in _chunks(syms, _batch_size("kline")):
        args = ["kline", ",".join(group), "--period", period, "--limit", str(limit)]
        if start:
            args += ["--start", start]
        if end:
            args += ["--end", end]
        if adjust:
            args += ["--fq", adjust]
        try:
            code, text = runner(binary, args)
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env dependent
            for sym in group:
                rep.items.append(SymbolResult(sym, "daily", False, error=f"westock invoke failed: {exc}"))
            continue

        tables = parse_markdown_tables(text)
        by_symbol: dict[str, list[dict[str, str]]] = {}
        unattributed: list[dict[str, str]] = []
        for table in tables:
            for row in rows_from_table(table):
                sym = (row.get("code") or row.get("symbol") or "").strip()
                if not sym:
                    # A single-code response has no `code` column (westock only
                    # adds it for batches); attribute it via the group size.
                    if len(group) == 1:
                        sym = group[0]
                    else:
                        unattributed.append(row)
                        continue
                by_symbol.setdefault(sym, []).append(row)

        if unattributed and len(group) > 1:
            rep.warnings.append(
                f"batch response had {len(unattributed)} row(s) with no code column "
                f"and {len(group)} symbols were requested — bars not attributable, skipped"
            )

        # Symbol keys in the CLI use sh/sz prefixes; the cache uses bare codes.
        normalized: dict[str, list[dict[str, str]]] = {}
        for sym, rows in by_symbol.items():
            normalized[_bare_symbol(sym)] = rows

        for sym in group:
            bare = _bare_symbol(sym)
            rows = normalized.get(bare)
            if not rows:
                rep.items.append(
                    SymbolResult(
                        sym,
                        "daily",
                        False,
                        error=f"no daily bars parsed (exit={code})",
                    )
                )
                continue
            bars = [kline_row_to_bar(r, symbol=bare) for r in rows]
            bars = [b for b in bars if b.get("date")]
            if not bars:
                rep.items.append(SymbolResult(sym, "daily", False, error="parsed bars had no dates"))
                continue
            if dry_run:
                rep.items.append(SymbolResult(sym, "daily", True, bars=len(bars)))
                continue
            path = write_daily_cache(bare, bars, d)
            rep.items.append(SymbolResult(sym, "daily", True, bars=len(bars), path=str(path)))
    return rep


def bridge_realtime(
    symbols: Sequence[str],
    cache_dir: str | Path,
    *,
    binary: str,
    runner: Runner,
    asof: str | None = None,
    report: BridgeReport | None = None,
    dry_run: bool = False,
) -> BridgeReport:
    """Fetch quotes for ``symbols`` and write ``realtime_{code}.json`` files."""
    from stock_platform_providers.workbuddy import write_realtime_cache

    d = Path(cache_dir).expanduser()
    rep = report if report is not None else BridgeReport(cache_dir=str(d), binary=binary)
    syms = [s for s in dict.fromkeys(str(x).strip() for x in symbols) if s]

    for group in _chunks(syms, _batch_size("quote")):
        args = ["quote", ",".join(group)]
        if asof:
            args += ["--date", asof]
        try:
            code, text = runner(binary, args)
        except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - env dependent
            for sym in group:
                rep.items.append(SymbolResult(sym, "realtime", False, error=f"westock invoke failed: {exc}"))
            continue

        parsed: dict[str, dict[str, str]] = {}
        unattributed_q = 0
        for table in parse_markdown_tables(text):
            for row in rows_from_table(table):
                sym = (row.get("symbol") or row.get("code") or "").strip()
                if not sym:
                    if len(group) == 1:
                        sym = group[0]
                    else:
                        unattributed_q += 1
                        continue
                parsed[_bare_symbol(sym)] = row
        if unattributed_q and len(group) > 1:
            rep.warnings.append(
                f"batch quote response had {unattributed_q} row(s) with no symbol "
                f"and {len(group)} symbols were requested — skipped"
            )

        for sym in group:
            row = parsed.get(_bare_symbol(sym))
            if row is None:
                rep.items.append(
                    SymbolResult(sym, "realtime", False, error=f"no quote parsed (exit={code})")
                )
                continue
            quote = quote_row_to_quote(row, symbol=_bare_symbol(sym))
            if dry_run:
                rep.items.append(SymbolResult(sym, "realtime", True, bars=1))
                continue
            path = write_realtime_cache(_bare_symbol(sym), quote, d)
            rep.items.append(SymbolResult(sym, "realtime", True, bars=1, path=str(path)))
    return rep


def _bare_symbol(symbol: str) -> str:
    """``sh600519`` / ``600519.SH`` → ``600519`` (matches the cache file naming)."""
    text = str(symbol).strip().upper()
    text = re.sub(r"^(SH|SZ|BJ)", "", text)
    text = re.sub(r"\.(SH|SZ|BJ)$", "", text)
    return text.strip()


def _collision_groups(symbols: Sequence[str]) -> dict[str, list[str]]:
    """Group requested symbols that collapse onto the same bare code.

    ``sh000001`` (上证指数) and ``sz000001`` (平安银行) both normalize to
    ``000001`` — the platform's symbol contract deliberately drops the exchange
    prefix, so the cache file name cannot tell them apart. Two different codes
    writing one ``daily_{code}.json`` would silently interleave bars, so the
    bridge refuses the ambiguous ones instead (see :func:`bridge_daily`).
    """
    groups: dict[str, list[str]] = {}
    for sym in symbols:
        groups.setdefault(_bare_symbol(sym), []).append(str(sym).strip())
    return {bare: originals for bare, originals in groups.items() if len(set(originals)) > 1}


def run_bridge(
    symbols: Sequence[str],
    *,
    cache_dir: str | Path | None = None,
    binary: str | None = None,
    datasets: Sequence[str] = ("daily",),
    asof: str | None = None,
    period: str = DEFAULT_PERIOD,
    adjust: str = DEFAULT_ADJUST,
    limit: int = DEFAULT_LIMIT,
    start: str | None = None,
    end: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_S,
    runner: Runner | None = None,
    env: dict[str, str] | None = None,
    dry_run: bool = False,
) -> BridgeReport:
    """Bridge ``symbols`` into the WorkBuddy cache directory.

    ``runner`` defaults to :func:`run_westock`; tests inject a fake so no
    subprocess is ever spawned. ``binary`` / ``cache_dir`` fall back to the
    environment, and a missing one raises :class:`SystemExit` with an actionable
    message rather than an opaque ``FileNotFoundError`` deep in the provider.
    """
    source: dict[str, str] = os.environ if env is None else env  # type: ignore[assignment]

    # An explicitly-passed binary is authoritative; a *path* that does not exist
    # is an error (never silently degrade to PATH), while a bare command name is
    # resolved via PATH.
    if binary:
        resolved_binary = _resolve_explicit_bin(binary)
        if resolved_binary is None:
            raise SystemExit(f"指定的 westock 可执行文件不存在：{binary}")
    else:
        resolved_binary = resolve_westock_bin(source)
    if not resolved_binary:
        raise SystemExit(MSG_NO_BIN)

    raw_dir = cache_dir or str(source.get(ENV_WORKBUDDY_CACHE_DIR, "") or "").strip()
    if not raw_dir:
        raise SystemExit(MSG_NO_CACHE_DIR)
    d = Path(str(raw_dir)).expanduser()
    if not dry_run:
        d.mkdir(parents=True, exist_ok=True)

    run = runner or (lambda b, a: run_westock(b, a, timeout=timeout))

    rep = BridgeReport(
        cache_dir=str(d),
        binary=str(resolved_binary),
        version=westock_version(str(resolved_binary), timeout=timeout) if not dry_run else None,
        dry_run=dry_run,
    )

    # Refuse ambiguous bare-code collisions (e.g. sh000001 index vs sz000001
    # stock) before anything is fetched: two sources cannot share one file.
    collisions = _collision_groups(symbols)
    if collisions:
        dropped = {orig for originals in collisions.values() for orig in originals}
        for bare, originals in sorted(collisions.items()):
            rep.warnings.append(
                f"code collision on {bare}: {', '.join(originals)} collapse to the same "
                "cache file — skipped (rename via a distinct symbol or bridge separately)"
            )
        symbols = [s for s in symbols if str(s).strip() not in dropped]

    wanted = {str(x).strip().lower() for x in datasets}
    if "daily" in wanted:
        bridge_daily(
            symbols,
            d,
            binary=str(resolved_binary),
            runner=run,
            period=period,
            adjust=adjust,
            limit=limit,
            start=start,
            end=end,
            report=rep,
            dry_run=dry_run,
        )
    if "realtime" in wanted:
        bridge_realtime(
            symbols,
            d,
            binary=str(resolved_binary),
            runner=run,
            asof=asof,
            report=rep,
            dry_run=dry_run,
        )
    return rep


def load_symbols_file(path: str | Path) -> list[str]:
    """Read a symbol list: one code per line, ``#`` comments, blank lines skipped."""
    text = Path(path).expanduser().read_text(encoding="utf-8")
    out: list[str] = []
    for line in text.splitlines():
        item = line.split("#", 1)[0].strip()
        if item:
            out.append(item)
    return out


__all__ = [
    "DEFAULT_ADJUST",
    "DEFAULT_LIMIT",
    "DEFAULT_PERIOD",
    "ENV_WESTOCK_BIN",
    "ENV_WORKBUDDY_CACHE_DIR",
    "MSG_NO_BIN",
    "MSG_NO_CACHE_DIR",
    "BridgeReport",
    "SymbolResult",
    "bridge_daily",
    "bridge_realtime",
    "kline_row_to_bar",
    "load_symbols_file",
    "parse_markdown_tables",
    "quote_row_to_quote",
    "resolve_westock_bin",
    "rows_from_table",
    "run_bridge",
    "run_westock",
    "westock_version",
]
