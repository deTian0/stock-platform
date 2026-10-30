"""Same-session OHLC snapshot fallback (Tencent / Sina). No live network."""

from __future__ import annotations

import pytest

from stock_platform_providers.snapshot import (
    fetch_day_snapshot,
    parse_sina_snapshot,
    parse_tencent_snapshot,
)

DAY = "2026-10-30"

# Real payload (verified live 2026-10-30 15:38): open 4.21 / high 4.33 / low 4.15 / close 4.18.
TQ_REAL = (
    'v_sh600854="1~春兰股份~600854~4.18~4.28~4.21~83939~40506~43433~4.17~119~4.16~529'
    "~4.15~369~4.14~146~4.13~280~4.18~81~4.19~122~4.20~37~4.21~169~4.22~69~~"
    '20261030153833~-0.10~-2.34~4.33~4.15~4.18/83939/35468570~83939~3547~1.62~20.15~~4.33~4.15~4.21";'
)

SN_REAL = (
    'var hq_str_sh600854="春兰股份,4.210,4.280,4.180,4.330,4.150,4.170,4.180,8393900,'
    '35468570.000,11900,4.170,52900,4.160,36900,4.150,14600,4.140,28000,4.130,8100,4.180,'
    '12200,4.190,3700,4.200,16900,4.210,6900,4.220,2026-10-30,15:00:00,00,";\n'
)


def _tq_line(code: str, *, close, prev, open_, high, low, stamp: str, paper: str = "") -> str:
    """Build a Tencent line with the vendor's field order (30=stamp, 33=high, 34=low)."""
    fields = ["1", "N", code, close, prev, open_] + ["0"] * 24 + [stamp, "0", "0", high, low]
    return f'v_{paper or ("sh" + code)}="{"~".join(fields)}";'


def _sn_line(code: str, *, open_, prev, close, high, low, day: str, paper: str = "") -> str:
    """Build a Sina line (1=open, 2=prev, 3=close, 4=high, 5=low, 30=date)."""
    fields = ["N", open_, prev, close, high, low] + ["0"] * 24 + [day, "15:00:00"]
    return 'var hq_str_%s="%s";' % (paper or ("sh" + code), ",".join(fields))


def test_parse_tencent_real_payload():
    rows = parse_tencent_snapshot(TQ_REAL, DAY)
    assert set(rows) == {"600854"}
    assert rows["600854"] == {"open": 4.21, "high": 4.33, "low": 4.15, "close": 4.18}


def test_parse_sina_real_payload():
    rows = parse_sina_snapshot(SN_REAL, DAY)
    assert set(rows) == {"600854"}
    assert rows["600854"] == {"open": 4.21, "high": 4.33, "low": 4.15, "close": 4.18}


def test_tencent_and_sina_agree():
    """两源同日同一只必须给同一组价，否则说明字段位错。"""
    assert parse_tencent_snapshot(TQ_REAL, DAY) == parse_sina_snapshot(SN_REAL, DAY)


def test_both_parsers_drop_other_sessions():
    """旧快照绝不能冒充当日行情 —— 日期不符整行丢弃。"""
    assert parse_tencent_snapshot(TQ_REAL, "2026-10-29") == {}
    assert parse_sina_snapshot(SN_REAL, "2026-10-29") == {}


def test_suspended_bar_is_dropped():
    """停牌时厂商给 open=0；补零会污染涨跌，必须整行丢弃。"""
    body = _tq_line("600000", close="0.00", prev="9.00", open_="0.00", high="0.00", low="0.00", stamp="20261030150000")
    assert parse_tencent_snapshot(body, DAY) == {}


def test_bse_symbol_uses_bj_prefix():
    body = _tq_line("830799", close="5.0", prev="4.9", open_="4.95", high="5.1", low="4.9",
                    stamp="20261030150000", paper="bj830799")
    assert parse_tencent_snapshot(body, DAY)["830799"]["close"] == 5.0


def test_fetch_falls_back_from_tencent_to_sina():
    calls: list[str] = []

    def _get_text(url: str, referer: str) -> str:
        calls.append(url)
        if "gtimg" in url:
            raise ConnectionError("tencent down")
        return SN_REAL

    rows, note = fetch_day_snapshot(["600854"], DAY, get_text=_get_text)
    assert set(rows) == {"600854"}
    assert note is None
    assert any("gtimg" in url for url in calls) and any("sinajs" in url for url in calls)


def test_fetch_merges_partial_sources():
    """腾讯只回一只时，缺的那只由新浪补，note 为空（全覆盖）。"""

    def _get_text(url: str, referer: str) -> str:
        if "gtimg" in url:
            return TQ_REAL
        return _sn_line("000488", open_="1.860", prev="1.870", close="1.890",
                        high="1.900", low="1.830", day=DAY)

    rows, note = fetch_day_snapshot(["600854", "000488"], DAY, get_text=_get_text)
    assert set(rows) == {"600854", "000488"}
    assert rows["000488"]["close"] == 1.89
    assert note is None


def test_fetch_reports_total_failure_without_raising():
    def _boom(url: str, referer: str) -> str:
        raise ConnectionError("all down")

    rows, note = fetch_day_snapshot(["600854"], DAY, get_text=_boom)
    assert rows == {}
    assert note and "全部失败" in note


def test_fetch_rejects_bad_day():
    rows, note = fetch_day_snapshot(["600854"], "2026-13-40", get_text=lambda u, r: "")
    assert rows == {}
    assert note


def test_fetch_empty_symbols():
    rows, note = fetch_day_snapshot([], DAY, get_text=lambda u, r: "")
    assert rows == {}
    assert note


@pytest.mark.parametrize("code", ["600854", "000488", "830799", "920001"])
def test_request_url_carries_exchange_prefix(code):
    """沪 / 深 / 北交所都要能拼出场内前缀，否则该板整块拿不到快照。"""
    seen: list[str] = []

    def _get_text(url: str, referer: str) -> str:
        seen.append(url)
        return ""

    fetch_day_snapshot([code], DAY, get_text=_get_text)
    assert seen
    assert f"{code}" in seen[0]
    assert seen[0].split(",")[0].rsplit("=", 1)[-1][:2] in {"sh", "sz", "bj"}
