"""X2 ranking boards — zero network, no real market.db."""

from __future__ import annotations

import json

import pandas as pd

from stock_platform_research.rankings import (
    ACTIONS_KEY,
    BOARD_KEYS,
    BOARD_SLUGS,
    HOLDINGS_KEY,
    QUALITY_KEY,
    SHORT_TERM_KEY,
    WATCHLIST_KEY,
    RankingConfig,
    apply_score_floor,
    build_rankings,
    code_key,
    enrich_holdings,
    format_rankings_markdown,
    rankings_to_rows,
)


def _scored(n: int = 40, *, with_entry_ok: bool = False) -> pd.DataFrame:
    """Descending composite_score, as ``score_lvrev`` returns."""
    rows = []
    for i in range(n):
        code = f"{600000 + i}"
        row = {
            "symbol": code,
            "close": 100.0 - i,
            "vol20": 0.02,
            "rev_chg": -0.05,
            "ma20": 50.0,
            "ma60": 40.0,
            "composite_score": round(0.95 - i * 0.01, 4),
        }
        if with_entry_ok:
            # only the tail half passes the entry gates
            row["entry_ok"] = bool(i >= n // 2)
        rows.append(row)
    return pd.DataFrame(rows)


def test_board_keys_match_the_engine_labels() -> None:
    assert BOARD_KEYS == (QUALITY_KEY, SHORT_TERM_KEY, HOLDINGS_KEY, ACTIONS_KEY, WATCHLIST_KEY)
    assert set(BOARD_SLUGS) == set(BOARD_KEYS)


def test_quality_short_and_watchlist_split() -> None:
    cfg = RankingConfig(quality_top_n=10, short_term_top_n=5, watchlist_top_n=23)
    out = build_rankings(_scored(40), config=cfg)
    quality = out["boards"]["quality"]["items"]
    short = out["boards"]["short_term"]["items"]
    watch = out["boards"]["watchlist"]["items"]

    assert [i["symbol"] for i in quality] == [f"{600000 + i}" for i in range(10)]
    # ②B never overlaps ②A
    assert not (set(i["symbol"] for i in quality) & set(i["symbol"] for i in short))
    assert len(short) == 5
    # ③C is the slice right after the ②A head
    assert [i["symbol"] for i in watch] == [f"{600000 + i}" for i in range(10, 33)]


def test_short_term_prefers_entry_passing_rows() -> None:
    df = _scored(40, with_entry_ok=True)
    out = build_rankings(df, config=RankingConfig(short_term_top_n=5))
    short = out["boards"]["short_term"]["items"]
    assert len(short) == 5
    for item in short:
        idx = int(item["symbol"]) - 600000
        assert idx >= 20  # entry_ok rows only


def test_short_term_top_up_when_entry_passing_is_short() -> None:
    df = _scored(40, with_entry_ok=True)
    df.loc[df.index[:30], "entry_ok"] = False
    df.loc[df.index[30:32], "entry_ok"] = True
    out = build_rankings(df, config=RankingConfig(short_term_top_n=5))
    short = out["boards"]["short_term"]["items"]
    assert len(short) == 5
    assert [i["symbol"] for i in short[:2]] == ["600030", "600031"]


def test_score_floor_filters_the_recommendation_boards() -> None:
    df = _scored(40)
    kept, dropped = apply_score_floor(df, 0.70)
    # 0.95 down to 0.56 in 0.01 steps: rows ≥ 0.70 are i ≤ 25 → 26 kept / 14 dropped
    assert dropped == 14
    assert len(kept) == 26
    out = build_rankings(df, config=RankingConfig(min_composite_score=0.70))
    assert len(out["boards"]["quality"]["items"]) == 10
    assert any("最低评分门槛" in n for n in out["notes"])


def test_holdings_board_intersects_the_cross_section() -> None:
    df = _scored(20)
    holdings = [{"code": "600005", "entry_price": 100.0}, {"code": "999999", "entry_price": 10.0}]
    out = build_rankings(df, holdings=holdings, asof="2026-09-03")
    items = out["boards"]["holdings"]["items"]
    assert [i["symbol"] for i in items] == ["600005"]  # 999999 is not in the panel
    assert items[0]["crossSectionRank"] == 6
    # score 0.90 vs median 0.855 → above median
    assert items[0]["belowMedian"] is False


def test_holding_outside_the_entry_gates_is_still_listed() -> None:
    """A held code that fails today's gates stays on ③A (no score, no rank)."""
    df = _scored(20).head(3)  # only 3 rows pass: 600000/600001/600002
    panel = pd.DataFrame(
        [
            {"symbol": "600000", "close": 100.0},
            {"symbol": "600001", "close": 99.0},
            {"symbol": "600002", "close": 98.0},
            {"symbol": "600009", "close": 91.0},
        ]
    )
    out = build_rankings(
        df,
        holdings=[{"code": "600009", "entry_price": 90.0}],
        panel=panel,
        asof="2026-09-03",
    )
    items = out["boards"]["holdings"]["items"]
    assert [i["symbol"] for i in items] == ["600009"]
    assert items[0]["composite_score"] is None
    assert "未过今日入场闸门" in items[0]["reasonSummary"]


def test_actions_board_is_delegated_to_the_b5_rules() -> None:
    df = _scored(20)
    panel = pd.DataFrame([{"symbol": "600005", "close": 88.0, "ma20": 90.0, "ma60": 80.0}])
    # −12 % from cost ⇒ the shared stop-loss fires; nothing here re-implements it.
    holdings = [{"code": "600005.SH", "entry_price": 100.0}]
    out = build_rankings(df, holdings=holdings, panel=panel, asof="2026-09-03")
    actions = out["boards"]["actions"]["items"]
    assert len(actions) == 1
    assert actions[0]["action"] == "exit"
    # reason string comes verbatim from ``rules`` (B5) — never rewritten here
    assert "stop_loss" in (actions[0]["reason"] or "")
    assert actions[0]["ret_pct"] == -12.0


def test_holdings_without_price_is_fail_closed() -> None:
    df = _scored(20)
    out = build_rankings(df, holdings=[{"code": "600005"}], asof="2026-09-03")
    assert out["boards"]["holdings"]["items"] == [] or all(
        i["rank"] >= 1 for i in out["boards"]["holdings"]["items"]
    )
    assert out["boards"]["actions"]["items"] == []
    assert any("缺成本价" in n or "缺" in n for n in out["notes"])


def test_no_holdings_means_empty_book_boards_with_a_note() -> None:
    out = build_rankings(_scored(20))
    assert out["boards"]["holdings"]["items"] == []
    assert out["boards"]["actions"]["items"] == []
    assert any("未提供持仓" in n for n in out["notes"])


def test_empty_cross_section_is_fail_closed() -> None:
    out = build_rankings(pd.DataFrame(), holdings=[{"code": "600000", "entry_price": 1.0}])
    assert out["counts"] == {slug: 0 for slug in BOARD_SLUGS.values()}
    assert all(b["items"] == [] for b in out["boards"].values())
    assert any("fail-closed" in n for n in out["notes"])


def test_code_key_normalises_every_form() -> None:
    assert code_key("600519.SH") == "600519"
    assert code_key("600519") == "600519"
    assert code_key("sh600519") == "600519"
    assert code_key(None) == ""


def test_enrich_holdings_takes_prices_from_the_panel() -> None:
    panel = pd.DataFrame([{"symbol": "600519.SH", "close": 12.5, "ma20": 11.0, "ma60": 10.0}])
    out = enrich_holdings([{"code": "600519", "entry_price": 10.0}], panel)
    assert out[0]["price"] == 12.5
    assert out[0]["ma20"] == 11.0


def test_brief_exposes_boards_while_picks_stay_put() -> None:
    from stock_platform_research.brief import build_premarket_brief

    panel = _scored(40)
    holdings = [{"code": "600005", "entry_price": 100.0}]
    brief = build_premarket_brief(
        asof="2026-09-03", panel=panel, top_n=10, holdings=holdings
    )
    # legacy contract unchanged: picks == the ②A head
    assert len(brief["picks"]) == 10
    assert brief["rankingsCounts"]["quality"] == 10
    assert brief["rankings"]["boards"]["watchlist"]["key"] == WATCHLIST_KEY
    assert len(brief["rankings"]["boards"]["watchlist"]["items"]) == 23
    assert len(brief["rankings"]["boards"]["holdings"]["items"]) == 1


def test_brief_without_holdings_keeps_book_boards_empty() -> None:
    from stock_platform_research.brief import build_premarket_brief

    brief = build_premarket_brief(asof="2026-09-03", panel=_scored(40), top_n=10)
    assert brief["rankings"]["boards"]["holdings"]["items"] == []
    assert brief["rankings"]["boards"]["actions"]["items"] == []


def test_rankings_cli_writes_md_json_and_csv(tmp_path) -> None:
    from stock_platform_research.rankings_cli import main

    panel_path = tmp_path / "panel.csv"
    _scored(40).to_csv(panel_path, index=False)
    book = tmp_path / "book.json"
    book.write_text(
        json.dumps({"holdings": [{"code": "600005", "entry_price": 100.0}]}),
        encoding="utf-8",
    )
    md_path = tmp_path / "boards.md"
    json_path = tmp_path / "boards.json"
    csv_path = tmp_path / "boards.csv"
    rc = main(
        [
            "--panel",
            str(panel_path),
            "--asof",
            "2026-09-03",
            "--holdings",
            str(book),
            "--md",
            str(md_path),
            "--json",
            str(json_path),
            "--csv",
            str(csv_path),
            "--quiet",
        ]
    )
    assert rc == 0
    text = md_path.read_text(encoding="utf-8")
    for key in BOARD_KEYS:
        assert key in text
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["counts"]["quality"] == 10
    assert payload["counts"]["watchlist"] == 23
    rows = pd.read_csv(csv_path)
    assert "board" in rows.columns
    assert len(rows) >= 30


def test_rows_and_markdown_cover_every_board() -> None:
    out = build_rankings(_scored(40), holdings=[{"code": "600001", "entry_price": 90.0}])
    rows = rankings_to_rows(out)
    assert rows and {"board", "rank", "symbol"} <= set(rows[0])
    md = format_rankings_markdown(out)
    for key in BOARD_KEYS:
        assert key in md
