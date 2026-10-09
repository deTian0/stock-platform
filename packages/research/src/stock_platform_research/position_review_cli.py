"""CLI: online book review over a holdings JSON (``B5``).

    stock-platform-position-review --holdings book.json
    stock-platform-position-review --holdings book.json --db <market.db> --asof 2026-09-08 --md out.md

Two input modes:

* **self-contained** — each holding already carries ``price`` / ``ma20`` / ``ma60``;
* **enriched** — pass ``--db`` (read-only ``market.db``) and the missing fields are
  filled from the engine dump. Enrichment rebuilds the **same dividend-adjusted
  series the backtest uses** (:func:`backtest.compute_features`, from ``pct_chg``),
  so ``ma20`` / ``ma60`` mean the same thing on both paths — but it also means
  ``entry_price`` must be supplied on that *same* adjusted basis for the return to
  be comparable. ``--db`` also derives ``held_days`` from ``entry_date``.

The DB is opened read-only (``mode=ro``) and is never written. SIMULATE only.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .backtest import compute_features
from .position_review import format_review_markdown, review_positions
from .rules import CooldownPolicy, DriftPolicy, ExitPolicy

ENV_DB = "STOCK_PLATFORM_ENGINE_MARKET_DB"
_TAIL_SESSIONS = 90  # enough for ma60 + a little slack


def _code_of(row: Mapping[str, Any]) -> str:
    for k in ("code", "symbol", "ts_code"):
        if row.get(k) is not None:
            return str(row[k]).strip()
    return ""


def load_holdings(path: str | Path) -> list[dict[str, Any]]:
    """Read a holdings JSON: either a bare list or ``{"holdings": [...]}``.

    Decoded as ``utf-8-sig`` so a file saved by Windows PowerShell
    (``Set-Content -Encoding UTF8`` writes a BOM) loads without a manual strip.
    """
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(data, Mapping):
        data = data.get("holdings") or []
    if not isinstance(data, list):
        raise ValueError("holdings JSON must be a list or {'holdings': [...]}")
    return [dict(r) for r in data if isinstance(r, Mapping)]


def enrich_from_db(
    holdings: list[dict[str, Any]],
    *,
    db_path: str | Path,
    asof: str | None = None,
) -> list[dict[str, Any]]:
    """Fill missing ``price`` / ``ma20`` / ``ma60`` / ``held_days`` / ``pct_chg``.

    Uses the backtest's own feature builder so trend inputs are on an identical
    basis. Codes absent from the dump are left untouched (review flags them
    ``pending`` rather than guessing).
    """
    codes = sorted({c for c in (_code_of(r) for r in holdings) if c})
    if not codes:
        return holdings

    uri = "file:%s?mode=ro" % str(db_path).replace("\\", "/")
    placeholders = ",".join("?" * len(codes))
    sql = (
        "SELECT code, date, close, pct_chg FROM daily_price "
        f"WHERE code IN ({placeholders})"
    )
    con = sqlite3.connect(uri, uri=True)
    try:
        raw = pd.read_sql_query(sql, con, params=list(codes))
    finally:
        con.close()
    if raw.empty:
        return holdings
    if asof:
        raw = raw[raw["date"] <= asof]
    if raw.empty:
        return holdings

    raw_sorted = raw.sort_values(["code", "date"])
    tail = (
        raw_sorted.groupby("code", sort=False)
        .tail(_TAIL_SESSIONS)
        .reset_index(drop=True)
    )
    feats = compute_features(tail)

    # Sessions come from the *full* per-code history so ``held_days`` still
    # resolves when the entry predates the feature tail window.
    sessions: dict[str, list[str]] = {
        code: [str(d)[:10] for d in g["date"].tolist()]
        for code, g in raw_sorted.groupby("code", sort=False)
    }

    latest: dict[str, dict[str, Any]] = {}
    for code, g in feats.groupby("code", sort=False):
        g = g.sort_values("trade_date")
        last = g.iloc[-1]
        # ``compute_features`` returns ``trade_date`` (a Timestamp), not ``date``.
        latest[code] = {
            "price": float(last["close"]),
            "ma20": None if pd.isna(last["ma20"]) else float(last["ma20"]),
            "ma60": None if pd.isna(last["ma60"]) else float(last["ma60"]),
            "pct_chg": None if pd.isna(last["pct_chg"]) else float(last["pct_chg"]),
            "asof": str(last["trade_date"])[:10],
        }

    out: list[dict[str, Any]] = []
    for row in holdings:
        code = _code_of(row)
        info = latest.get(code)
        if info is None:
            out.append(row)
            continue
        merged = dict(row)
        merged.setdefault("code", code)
        if merged.get("price") is None:
            merged["price"] = info["price"]
        if merged.get("ma20") is None:
            merged["ma20"] = info["ma20"]
        if merged.get("ma60") is None:
            merged["ma60"] = info["ma60"]
        if merged.get("pct_chg") is None:
            merged["pct_chg"] = info["pct_chg"]
        if merged.get("held_days") is None and merged.get("entry_date"):
            entry = str(merged["entry_date"])[:10]
            seq = sessions.get(code) or []
            if entry in seq:
                merged["held_days"] = len(seq) - 1 - seq.index(entry)
            else:
                # entry predates the dump's coverage — flag it, never guess 0
                merged["held_days_unresolved"] = True
        out.append(merged)
    return out


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stock-platform-position-review",
        description="Review the current book with the shared trading rules (SIMULATE).",
    )
    p.add_argument("--holdings", required=True, help="holdings JSON (list or {'holdings': [...]})")
    p.add_argument("--db", default=os.environ.get(ENV_DB, ""), help=f"market.db for enrichment (default: ${ENV_DB})")
    p.add_argument("--asof", default=None, help="inclusive asof date YYYY-MM-DD (enrichment only)")
    p.add_argument("--stop-loss", type=float, default=8.0)
    p.add_argument("--take-profit", type=float, default=0.0)
    p.add_argument("--min-hold", type=int, default=45)
    p.add_argument("--max-hold-days", type=int, default=60)
    p.add_argument("--cooldown-days", type=int, default=0, help="冷静期: block re-entry N sessions after an exit")
    p.add_argument("--drift-band", type=float, default=None, help="持仓偏差 band, e.g. 0.30 = ±30%% of target weight")
    p.add_argument("--md", default=None, help="also write the markdown report here")
    p.add_argument("--json", action="store_true", help="emit the full review payload as JSON")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    holdings = load_holdings(args.holdings)
    print(f"[holdings] {len(holdings)} rows", file=sys.stderr)

    db = (args.db or "").strip()
    if db:
        if not Path(db).is_file():
            raise SystemExit(f"market.db not found: {db}")
        print(f"[db] {db} (read-only, enriched via compute_features)", file=sys.stderr)
        holdings = enrich_from_db(holdings, db_path=db, asof=args.asof)
    else:
        print("[db] none — using the values supplied in the JSON", file=sys.stderr)

    res = review_positions(
        holdings,
        exit_policy=ExitPolicy(
            stop_loss=args.stop_loss,
            take_profit=args.take_profit,
            min_hold=args.min_hold,
            max_hold_days=args.max_hold_days,
        ),
        cooldown_policy=CooldownPolicy(cooldown_days=args.cooldown_days),
        drift_policy=DriftPolicy(band=args.drift_band),
        asof=args.asof,
    )

    if args.json:
        print(json.dumps(res, ensure_ascii=False, default=str))
    else:
        print(json.dumps(res["counts"], ensure_ascii=False))
        for r in res["rows"]:
            print(
                "{code:>12} {act:<8} held={held:<4} ret={ret} {reason} {note}".format(
                    code=r["code"] or "?",
                    act=r["action"],
                    held=r["held_days"],
                    ret="" if r["ret_pct"] is None else f"{r['ret_pct']:+.2f}%",
                    reason=r["reason"] or "",
                    note=r["note"] or "",
                )
            )

    if args.md:
        out = Path(args.md)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(format_review_markdown(res), encoding="utf-8")
        print(f"[md] {out}", file=sys.stderr)

    return 0 if res.get("ok") else 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
