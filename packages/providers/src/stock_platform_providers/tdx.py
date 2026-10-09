"""通达信 (TDX) local daily-bar adapter — reads ``vipdoc/*/lday/*.day``.

TDX keeps every stock/ETF's daily history in a per-code binary file of fixed
32-byte records (little-endian)::

    <I  date   YYYYMMDD
    <I  open   price * 100
    <I  high   price * 100
    <I  low    price * 100
    <I  close  price * 100
    <f  amount 元
    <I  volume 手 (100 shares)
    <I  reserved

No network, no SDK — just ``struct`` over the on-disk bytes. The TDX desktop app
must have downloaded the data first (the files are its local cache). Realtime is
**not** available from these files (TDX live quotes come from its own TCP feed),
so ``get_realtime`` fails closed.
"""

from __future__ import annotations

import os
import struct
from datetime import date
from pathlib import Path
from typing import Any

from .base import AssetType
from .normalize import normalize_daily_row
from .symbol import exchange_prefix, normalize_symbol

ENV_TDX_ROOT = "STOCK_PLATFORM_TDX_ROOT"
PROVIDER_NAME = "tdx"

_RECORD = struct.Struct("<IIIIIfII")
_RECORD_SIZE = _RECORD.size  # 32 bytes

MSG_ROOT_MISSING = (
    "未找到通达信本地数据目录：请设置 STOCK_PLATFORM_TDX_ROOT 指向通达信安装根目录 "
    "（含 vipdoc/），或先由通达信客户端下载日线数据；平台只读、不抓取。"
)

# Common install roots probed when the env var is unset.
_COMMON_ROOTS = (
    r"D:\new_tdx",
    r"C:\new_tdx",
    r"D:\zd_zsone",
    r"C:\zd_zsone",
    r"D:\zd_pazq",
    r"C:\zd_pazq",
    r"D:\tdx",
    r"C:\tdx",
    r"D:\通达信",
    r"C:\通达信",
)


def resolve_tdx_root(env: dict[str, str] | None = None) -> Path | None:
    """Return a TDX install root whose ``vipdoc/`` exists, else None."""
    source = env if env is not None else os.environ
    raw = str(source.get(ENV_TDX_ROOT, "") or "").strip()
    candidates: list[str] = [raw] if raw else []
    candidates.extend(_COMMON_ROOTS)
    for cand in candidates:
        if not cand:
            continue
        root = Path(cand).expanduser()
        if (root / "vipdoc").is_dir():
            return root
    return None


def _day_path(root: Path, code: str) -> Path:
    prefix = exchange_prefix(code)
    return root / "vipdoc" / prefix / "lday" / f"{prefix}{code}.day"


def parse_day_file(path: Path) -> list[dict[str, Any]]:
    """Parse a TDX ``.day`` file into raw bar dicts (prices in 元, volume 手)."""
    data = path.read_bytes()
    bars: list[dict[str, Any]] = []
    for offset in range(0, len(data) - _RECORD_SIZE + 1, _RECORD_SIZE):
        (ymd, o, h, l, c, amount, volume, _res) = _RECORD.unpack_from(data, offset)
        if ymd == 0:
            continue
        y, m, d = ymd // 10000, (ymd // 100) % 100, ymd % 100
        try:
            dt = date(y, m, d)
        except ValueError:
            continue
        bars.append(
            {
                "date": dt.isoformat(),
                "open": o / 100.0,
                "high": h / 100.0,
                "low": l / 100.0,
                "close": c / 100.0,
                "volume": float(volume),
                "amount": float(amount),
            }
        )
    return bars


class TdxProvider:
    """Read CN daily bars from a TDX local install (offline)."""

    name = PROVIDER_NAME

    def __init__(self, root: str | Path | None = None) -> None:
        path = Path(root) if root is not None else resolve_tdx_root()
        if path is None:
            raise FileNotFoundError(MSG_ROOT_MISSING)
        if not (path / "vipdoc").is_dir():
            raise FileNotFoundError(f"TDX root has no vipdoc/: {path}")
        self.root = path.resolve()

    def get_daily(
        self,
        symbols: list[str],
        *,
        start: date | None = None,
        end: date | None = None,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for raw_sym in symbols:
            code = normalize_symbol(raw_sym, market="CN")
            path = _day_path(self.root, code)
            if not path.is_file():
                continue
            for bar in parse_day_file(path):
                row = normalize_daily_row(
                    bar,
                    source=self.name,
                    asset_type=asset_type,
                    default_symbol=code,
                    market="CN",
                )
                d = date.fromisoformat(row["date"])
                if start and d < start:
                    continue
                if end and d > end:
                    continue
                rows.append(row)
        rows.sort(key=lambda r: (r["symbol"], r["date"]))
        return rows

    def get_realtime(
        self,
        symbols: list[str],
        *,
        asset_type: AssetType = "stock",
    ) -> list[dict[str, Any]]:
        raise NotImplementedError(
            "tdx is daily-only (local vipdoc/*.day); live quotes come from the TDX "
            "desktop feed, not local files — use astock_http or workbuddy for realtime"
        )
