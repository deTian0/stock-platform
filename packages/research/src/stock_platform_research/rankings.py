"""Ranking boards — ``X2``: align the ``a-stock-engine`` board semantics.

Five boards, matching the production engine's ``multifactor.categorize`` split::

    ②A 质量榜    top ``quality_top_n`` by composite score
    ②B 短线榜    ``short_term_top_n`` outside the ②A head (entry-passing first)
    ③A 持仓      current book ∩ scored cross-section
    ③B 操作建议  exit / trim instructions — delegated to :mod:`rules` (B5)
    ③C 观察名单  the next ``watchlist_top_n`` rows after the ②A head

Single definition policy
------------------------
* reason strings come from :func:`brief.build_reasons_for_row` — never rebuilt here.
* ③B decisions come from :func:`position_review.review_positions`, i.e. the same
  :mod:`rules` layer the backtest uses. **No median-score sell rule is written
  here**; the engine's "score below cross-section median" heuristic is degraded
  to a passive ``belowMedian`` marker on ③A rows (informational, never an
  instruction) so the platform keeps exactly one actionable source (B5).
* BSE prefixes / symbol normalisation stay in ``providers.symbol``; this module
  only matches on the 6-digit numeric core, which is what both sides emit.

SIMULATE only. Not investment advice.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Sequence

import pandas as pd

QUALITY_KEY = "②A_质量榜"
SHORT_TERM_KEY = "②B_短线榜"
HOLDINGS_KEY = "③A_持仓"
ACTIONS_KEY = "③B_操作建议"
WATCHLIST_KEY = "③C_观察名单"

BOARD_KEYS: tuple[str, ...] = (
    QUALITY_KEY,
    SHORT_TERM_KEY,
    HOLDINGS_KEY,
    ACTIONS_KEY,
    WATCHLIST_KEY,
)

# engine key → stable machine slug (API / CSV friendly)
BOARD_SLUGS: dict[str, str] = {
    QUALITY_KEY: "quality",
    SHORT_TERM_KEY: "short_term",
    HOLDINGS_KEY: "holdings",
    ACTIONS_KEY: "actions",
    WATCHLIST_KEY: "watchlist",
}

# Actions from B5 that mean "reduce exposure". ``add`` is a drift top-up,
# ``hold``/``pending`` are not instructions.
REDUCE_ACTIONS = ("exit", "trim")

_CODE_RE = re.compile(r"(\d{6})")


@dataclass(frozen=True)
class RankingConfig:
    """Board sizes + the low-score floor.

    ``min_composite_score`` mirrors the engine's ``output.min_composite_score``
    but on the platform's own scale: ``composite_score`` here is a [0, 1]
    percentile blend, **not** the engine's 0-100 scale — do not copy ``60``
    across. Default ``0.0`` = disabled (no floor).
    """

    quality_top_n: int = 10
    short_term_top_n: int = 5
    watchlist_top_n: int = 23
    min_composite_score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def code_key(value: Any) -> str:
    """6-digit numeric core of any code form (``600519.SH`` / ``600519`` / ``sh600519``)."""
    if value is None:
        return ""
    m = _CODE_RE.search(str(value))
    return m.group(1) if m else ""


def _series_of_keys(frame: pd.DataFrame) -> pd.Series:
    col = "symbol" if "symbol" in frame.columns else ("code" if "code" in frame.columns else None)
    if col is None:
        return pd.Series([""] * len(frame), index=frame.index)
    return frame[col].map(code_key)


def _sym_of(row: pd.Series) -> str:
    for key in ("symbol", "code", "ts_code"):
        val = row.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _item_from_row(row: pd.Series, rank: int, *, gated: bool) -> dict[str, Any]:
    from .brief import build_reasons_for_row, reason_summary  # local: avoid import cycle

    reasons = build_reasons_for_row(row, gated=gated)
    return {
        "rank": rank,
        "symbol": _sym_of(row),
        "composite_score": float(row["composite_score"])
        if "composite_score" in row.index and pd.notna(row["composite_score"])
        else None,
        "close": float(row["close"]) if "close" in row.index and pd.notna(row["close"]) else None,
        "reasons": reasons,
        "reasonSummary": reason_summary(reasons),
    }


def _items_from_frame(frame: pd.DataFrame, *, gated: bool = True) -> list[dict[str, Any]]:
    if frame is None or len(frame) == 0:
        return []
    return [_item_from_row(row, i, gated=gated) for i, (_, row) in enumerate(frame.iterrows(), start=1)]


def apply_score_floor(scored: pd.DataFrame, min_score: float) -> tuple[pd.DataFrame, int]:
    """Drop rows below ``min_score`` (applies to ②A / ②B / ③C, not to holdings).

    Returns ``(kept, dropped_count)``.
    """
    if scored is None or len(scored) == 0:
        return scored if scored is not None else pd.DataFrame(), 0
    if not min_score or "composite_score" not in scored.columns:
        return scored, 0
    keep = scored["composite_score"] >= float(min_score)
    return scored.loc[keep], int((~keep).sum())


def enrich_holdings(
    holdings: Sequence[Mapping[str, Any]],
    panel: pd.DataFrame | None = None,
) -> list[dict[str, Any]]:
    """Fill ``price`` / ``ma20`` / ``ma60`` for holdings from the asof panel.

    Uses the panel the brief was scored on, so the book is reviewed on exactly
    the same prices the ranking saw. Missing ``entry_price`` stays missing →
    :func:`review_positions` flags it ``pending`` (fail-closed, never guessed).
    """
    rows = [dict(r) for r in (holdings or []) if isinstance(r, Mapping)]
    if not rows or panel is None or len(panel) == 0:
        return rows
    by_key: dict[str, dict[str, Any]] = {}
    for _, prow in panel.iterrows():
        key = code_key(_sym_of(prow))
        if key:
            by_key[key] = {
                "close": prow.get("close"),
                "ma20": prow.get("ma20"),
                "ma60": prow.get("ma60"),
                "pct_chg": prow.get("pct_chg"),
            }
    for row in rows:
        src = by_key.get(code_key(row.get("code") or row.get("symbol") or row.get("ts_code")))
        if not src:
            continue
        if row.get("price") is None:
            row["price"] = src.get("close")
        for field in ("ma20", "ma60", "pct_chg"):
            if row.get(field) is None and src.get(field) is not None:
                row[field] = src.get(field)
    return rows


def build_rankings(
    scored: pd.DataFrame,
    *,
    holdings: Sequence[Mapping[str, Any]] | None = None,
    config: RankingConfig | None = None,
    panel: pd.DataFrame | None = None,
    asof: str | None = None,
    gated: bool = True,
) -> dict[str, Any]:
    """Split a scored cross-section into the five boards.

    ``scored`` must already be point-in-time and sorted by ``composite_score``
    descending (that is what :func:`lvrev.score_lvrev` returns).

    Empty input is **fail-closed**: all boards empty plus a Chinese note, never
    fabricated rows.
    """
    cfg = config or RankingConfig()
    notes: list[str] = []

    if scored is None or len(scored) == 0:
        return {
            "asof": asof,
            "config": cfg.to_dict(),
            "counts": {BOARD_SLUGS[k]: 0 for k in BOARD_KEYS},
            "boards": {
                BOARD_SLUGS[k]: {"key": k, "label": k, "slug": BOARD_SLUGS[k], "items": []}
                for k in BOARD_KEYS
            },
            "notes": ["截面为空：无可排名标的（fail-closed，不生成占位榜单）"],
            "environment": "SIMULATE",
            "disclaimer": "榜单为研究口径；③B 操作建议与回测共用同一规则实现；非投资建议。",
        }

    rec, dropped = apply_score_floor(scored, cfg.min_composite_score)
    if dropped:
        notes.append(f"最低评分门槛 {cfg.min_composite_score:.2f}：过滤 {dropped} 只低分标的")

    keys = _series_of_keys(rec)

    # ②A 质量榜
    quality = rec.head(int(cfg.quality_top_n)).copy()

    # ②B 短线榜 — same lvrev kernel as ②A (never "buy strength"):
    # drop the ②A head, prefer entry-passing rows, top up by score.
    short = pd.DataFrame()
    if len(rec) > 0:
        qa_keys = set(keys.loc[quality.index].tolist())
        rest = rec.loc[~keys.isin(qa_keys)].copy()
        rest_keys = _series_of_keys(rest)
        if "entry_ok" in rest.columns and bool(rest["entry_ok"].any()):
            passed = rest.loc[rest["entry_ok"]]
            short = passed.head(int(cfg.short_term_top_n)).copy()
        if len(short) < int(cfg.short_term_top_n):
            used = set(_series_of_keys(short).tolist())
            remain = rest.loc[~rest_keys.isin(used)]
            need = int(cfg.short_term_top_n) - len(short)
            if need > 0 and len(remain):
                short = pd.concat([short, remain.head(need)], axis=0)
        if len(short) == 0 and len(rest):
            # Gates already removed non-passing rows: the pool *is* the
            # entry-passing set, so fall back to score order (documented).
            short = rest.head(int(cfg.short_term_top_n)).copy()

    # ③C 观察名单
    watchlist = rec.iloc[int(cfg.quality_top_n) : int(cfg.quality_top_n) + int(cfg.watchlist_top_n)].copy()

    # ③A 持仓 + ③B 操作建议
    book = enrich_holdings(holdings or [], panel)
    holding_items: list[dict[str, Any]] = []
    action_items: list[dict[str, Any]] = []
    median_score = (
        float(rec["composite_score"].median())
        if "composite_score" in rec.columns and len(rec)
        else None
    )
    score_by_key: dict[str, float] = {}
    rank_by_key: dict[str, int] = {}
    for i, (idx, row) in enumerate(rec.iterrows(), start=1):
        k = code_key(_sym_of(row))
        if not k:
            continue
        score_by_key.setdefault(k, float(row["composite_score"]))
        rank_by_key.setdefault(k, i)

    if book:
        from .position_review import review_positions  # local: keep module import-light

        book_keys = {code_key(r.get("code") or r.get("symbol") or r.get("ts_code")) for r in book}
        book_keys.discard("")
        in_book = rec.loc[keys.isin(book_keys)].copy() if book_keys else rec.iloc[0:0].copy()
        for i, (_, row) in enumerate(in_book.iterrows(), start=1):
            k = code_key(_sym_of(row))
            item = _item_from_row(row, i, gated=gated)
            item["belowMedian"] = bool(
                median_score is not None and item["composite_score"] is not None
                and item["composite_score"] < median_score
            )
            item["crossSectionRank"] = rank_by_key.get(k)
            holding_items.append(item)

        # Positions that did **not** pass today's entry gates still belong on the
        # ③A board (they are held, not candidates) — list them from the panel with
        # a null score instead of silently dropping them.
        seen_keys = {code_key(i["symbol"]) for i in holding_items}
        if panel is not None and len(panel):
            for _, prow in panel.iterrows():
                k = code_key(_sym_of(prow))
                if not k or k in seen_keys or k not in book_keys:
                    continue
                holding_items.append(
                    {
                        "rank": len(holding_items) + 1,
                        "symbol": _sym_of(prow),
                        "composite_score": None,
                        "close": float(prow["close"])
                        if "close" in prow.index and pd.notna(prow["close"])
                        else None,
                        "reasons": [],
                        "reasonSummary": "未过今日入场闸门（仅列示持仓，不参与推荐排名）",
                        "belowMedian": False,
                        "crossSectionRank": None,
                    }
                )
                seen_keys.add(k)

        review = review_positions(book, asof=asof)
        for row in review.get("rows") or []:
            if row.get("action") not in REDUCE_ACTIONS:
                continue
            k = code_key(row.get("code"))
            action_items.append(
                {
                    "rank": len(action_items) + 1,
                    "symbol": row.get("code") or "",
                    "action": row.get("action"),
                    "reason": row.get("reason"),
                    "ret_pct": row.get("ret_pct"),
                    "deferred": bool(row.get("deferred")),
                    "assetClass": row.get("asset_class"),
                    "compositeScore": score_by_key.get(k),
                    "crossSectionRank": rank_by_key.get(k),
                }
            )
        if not action_items:
            notes.append(
                "持仓无需减仓：B5 规则（退出/冷静期/偏差）未对当日持仓触发 exit/trim"
            )
        pending = sum(1 for r in (review.get("rows") or []) if r.get("action") == "pending")
        if pending:
            notes.append(f"{pending} 只持仓缺成本价/现价，未给出操作建议（fail-closed）")
    else:
        notes.append("未提供持仓（holdings 为空）：③A 持仓与 ③B 操作建议为空")

    boards: dict[str, dict[str, Any]] = {}
    frames = {
        QUALITY_KEY: quality,
        SHORT_TERM_KEY: short,
        WATCHLIST_KEY: watchlist,
    }
    for key in BOARD_KEYS:
        slug = BOARD_SLUGS[key]
        if key in frames:
            items = _items_from_frame(frames[key], gated=gated)
        elif key == HOLDINGS_KEY:
            items = holding_items
        else:
            items = action_items
        boards[slug] = {"key": key, "label": key, "slug": slug, "items": items}

    return {
        "asof": asof,
        "config": cfg.to_dict(),
        "counts": {slug: len(boards[slug]["items"]) for slug in boards},
        "boards": boards,
        "notes": notes,
        "environment": "SIMULATE",
        "disclaimer": "榜单为研究口径；③B 操作建议与回测共用同一规则实现；非投资建议。",
    }


def rankings_to_rows(rankings: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten all boards to CSV-ish rows (``board`` column = engine key)."""
    rows: list[dict[str, Any]] = []
    for slug, board in (rankings.get("boards") or {}).items():
        for item in board.get("items") or []:
            row = dict(item)
            row.pop("reasons", None)
            row["board"] = board.get("key") or slug
            rows.append(row)
    return rows


def format_rankings_markdown(rankings: Mapping[str, Any]) -> str:
    """Render all five boards as markdown (empty board ⇒ explicit line, never blank)."""
    asof = rankings.get("asof") or "-"
    lines = [f"# 榜单（{asof} · SIMULATE · 非投资建议）", ""]
    counts = rankings.get("counts") or {}
    lines.append("| 榜单 | 数量 |\n|---|---|")
    for key in BOARD_KEYS:
        lines.append(f"| {key} | {counts.get(BOARD_SLUGS[key], 0)} |")
    lines.append("")
    for key in BOARD_KEYS:
        board = (rankings.get("boards") or {}).get(BOARD_SLUGS[key]) or {}
        items = board.get("items") or []
        lines.append(f"## {key}（{len(items)}）")
        lines.append("")
        if not items:
            lines.append("_无（fail-closed：不生成占位条目）_")
            lines.append("")
            continue
        if key == ACTIONS_KEY:
            lines.append("| # | 代码 | 动作 | 收益% | 原因 |")
            lines.append("|---|---|---|---|---|")
            for it in items:
                lines.append(
                    "| {r} | {c} | {a} | {ret} | {why} |".format(
                        r=it.get("rank"),
                        c=it.get("symbol") or "",
                        a=it.get("action") or "",
                        ret="" if it.get("ret_pct") is None else f"{it['ret_pct']:+.2f}",
                        why=it.get("reason") or "",
                    )
                )
        else:
            lines.append("| # | 代码 | 综合分 | 收盘 | 说明 |")
            lines.append("|---|---|---|---|---|")
            for it in items:
                score = it.get("composite_score")
                extra = ""
                if it.get("belowMedian"):
                    extra = " ⚠️低于截面中位"
                lines.append(
                    "| {r} | {c} | {s} | {px} | {why}{e} |".format(
                        r=it.get("rank"),
                        c=it.get("symbol") or "",
                        s="" if score is None else f"{score:.4f}",
                        px="" if it.get("close") is None else f"{it['close']:.2f}",
                        why=it.get("reasonSummary") or "",
                        e=extra,
                    )
                )
        lines.append("")
    for note in rankings.get("notes") or []:
        lines.append(f"> {note}")
    if rankings.get("notes"):
        lines.append("")
    lines.append(f"> {rankings.get('disclaimer')}")
    return "\n".join(lines) + "\n"


__all__ = [
    "ACTIONS_KEY",
    "BOARD_KEYS",
    "BOARD_SLUGS",
    "HOLDINGS_KEY",
    "QUALITY_KEY",
    "RankingConfig",
    "SHORT_TERM_KEY",
    "WATCHLIST_KEY",
    "apply_score_floor",
    "build_rankings",
    "code_key",
    "enrich_holdings",
    "format_rankings_markdown",
    "rankings_to_rows",
]
