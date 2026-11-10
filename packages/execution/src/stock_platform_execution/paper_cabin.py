"""Paper cabin persistence + fill-price helpers (SIMULATE only, no live broker).

Default state lives under ``local/paper_cabin/`` (gitignored). Reuses
``PaperBroker`` / ``PaperLedger`` — does not invent a second ledger.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from .broker import DEFAULT_PAPER_CAPITAL, PaperBroker
from .contracts import Fill, Position
from .paper import PaperLedger

DEFAULT_STATE = Path("local") / "paper_cabin" / "state.json"
#: ADR 0098: paper capital defaults to ¥20,000 (small-account口径), not ¥1,000,000.
DEFAULT_CASH = DEFAULT_PAPER_CAPITAL


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {
            "cash": DEFAULT_CASH,
            "positions": {},
            "fills": [],
            "drafts": {},
            "accepted": {},
            "lifecycle": {},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — corrupt session → fresh cabin
        return {
            "cash": DEFAULT_CASH,
            "positions": {},
            "fills": [],
            "drafts": {},
            "accepted": {},
            "lifecycle": {},
        }
    if not isinstance(raw, dict):
        return {
            "cash": DEFAULT_CASH,
            "positions": {},
            "fills": [],
            "drafts": {},
            "accepted": {},
            "lifecycle": {},
        }
    raw.setdefault("cash", DEFAULT_CASH)
    raw.setdefault("positions", {})
    raw.setdefault("fills", [])
    raw.setdefault("drafts", {})
    raw.setdefault("accepted", {})
    raw.setdefault("lifecycle", {})
    return raw


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def hydrate_broker(state: dict[str, Any]) -> PaperBroker:
    ledger = PaperLedger()
    for draft_id, draft in (state.get("drafts") or {}).items():
        ledger._drafts[str(draft_id)] = dict(draft)  # noqa: SLF001
    for draft_id, accepted in (state.get("accepted") or {}).items():
        ledger._accepted[str(draft_id)] = dict(accepted)  # noqa: SLF001
    broker = PaperBroker(ledger=ledger)
    broker._cash = float(state.get("cash") if state.get("cash") is not None else DEFAULT_CASH)  # noqa: SLF001
    positions: dict[str, Position] = {}
    for symbol, raw in (state.get("positions") or {}).items():
        if not isinstance(raw, dict):
            continue
        positions[str(symbol)] = Position(
            symbol=str(raw.get("symbol") or symbol),
            qty=float(raw.get("qty") or 0),
            avg_price=float(raw.get("avg_price") or raw.get("avgPrice") or 0),
            market_value=(
                float(raw["market_value"])
                if raw.get("market_value") is not None
                else (
                    float(raw["marketValue"])
                    if raw.get("marketValue") is not None
                    else None
                )
            ),
        )
    broker._positions = positions  # noqa: SLF001
    fills: list[Fill] = []
    for raw in state.get("fills") or []:
        if not isinstance(raw, dict):
            continue
        fills.append(
            Fill(
                fill_id=str(raw.get("fill_id") or raw.get("fillId") or ""),
                order_id=str(raw.get("order_id") or raw.get("orderId") or ""),
                symbol=str(raw.get("symbol") or ""),
                side=str(raw.get("side") or "buy").lower(),
                qty=float(raw.get("qty") or 0),
                price=float(raw.get("price") or 0),
                filled_at=str(raw.get("filled_at") or raw.get("filledAt") or ""),
                draft_id=(
                    str(raw["draft_id"])
                    if raw.get("draft_id") is not None
                    else (
                        str(raw["draftId"])
                        if raw.get("draftId") is not None
                        else None
                    )
                ),
            )
        )
    broker._fills = fills  # noqa: SLF001
    return broker


def persist_broker(state: dict[str, Any], broker: PaperBroker) -> None:
    state["cash"] = float(broker._cash)  # noqa: SLF001
    state["positions"] = {
        sym: p.to_dict() for sym, p in broker._positions.items()  # noqa: SLF001
    }
    state["fills"] = [f.to_dict() for f in broker._fills]  # noqa: SLF001
    state["drafts"] = {k: dict(v) for k, v in broker.ledger._drafts.items()}  # noqa: SLF001
    state["accepted"] = {k: dict(v) for k, v in broker.ledger._accepted.items()}  # noqa: SLF001


def resolve_fill_price(
    symbol: str,
    *,
    asof: str | None = None,
    price: float | None = None,
    db: str | Path | None = None,
) -> tuple[float, str]:
    """Resolve a SIMULATE fill price without inventing THS connectivity.

    Priority: explicit ``price`` → read-only engine ``market.db`` close on/before
    ``asof`` (or latest available). Never claims Tonghuashun fill.
    """
    if price is not None:
        px = float(price)
        if px <= 0:
            raise ValueError("price must be > 0")
        return px, "cli:--price"

    db_path: Path | None
    if db is not None:
        db_path = Path(db)
    else:
        raw = (os.environ.get("STOCK_PLATFORM_ENGINE_MARKET_DB") or "").strip()
        db_path = Path(raw) if raw else None

    if db_path is None or not db_path.is_file():
        raise ValueError(
            "缺少成交价：请传 --price，或提供可读 market.db（--db / "
            "STOCK_PLATFORM_ENGINE_MARKET_DB）。禁止伪造同花顺成交。"
        )

    from stock_platform_providers.engine_sqlite import EngineSqliteProvider

    provider = EngineSqliteProvider(db_path)
    end = date.fromisoformat(str(asof)[:10]) if asof else date.today()
    start = end - timedelta(days=30)
    rows = provider.get_daily([symbol], start=start, end=end)
    if not rows:
        raise ValueError(f"market.db 无 {symbol} 在 {start}..{end} 的收盘价（只读）")
    # Prefer exact asof, else last row on/before end.
    chosen = None
    for row in rows:
        d = str(row.get("date") or "")[:10]
        if d <= end.isoformat():
            chosen = row
    if chosen is None:
        chosen = rows[-1]
    close = chosen.get("close")
    if close is None:
        raise ValueError(f"market.db 行缺少 close：{symbol} {chosen.get('date')}")
    px = float(close)
    if px <= 0:
        raise ValueError(f"非法 close={px} for {symbol}")
    return px, f"market.db:close:{chosen.get('date')}"


def parse_now(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = str(raw).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        from zoneinfo import ZoneInfo

        dt = dt.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    return dt
