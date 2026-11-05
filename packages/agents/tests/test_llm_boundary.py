"""ADR 0088: deterministic imports must not load the LLM module face."""

from __future__ import annotations

import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_AGENTS_SRC = Path(__file__).resolve().parents[1] / "src"


def _fresh_import_script(body: str) -> str:
    """Build a subprocess snippet with agents ``src`` on ``sys.path``."""
    return (
        "import sys\n"
        f"sys.path.insert(0, r'{_AGENTS_SRC}')\n"
        # providers is a normal install in the venv; keep env PYTHONPATH as-is.
        + body
    )


def test_fresh_package_import_skips_llm_modules() -> None:
    """Isolated process: importing the package root must not load LLM modules."""
    script = _fresh_import_script(
        """
import stock_platform_agents as agents
assert 'stock_platform_agents.llm_debate' not in sys.modules
assert 'stock_platform_agents.deep_llm_graph' not in sys.modules
assert 'stock_platform_agents.llm' not in sys.modules
assert callable(agents.build_debate_report)
assert callable(agents.attach_debate_lane)
assert 'stock_platform_agents.llm_debate' not in sys.modules
print('ok')
"""
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok" in proc.stdout


def test_deterministic_lane_does_not_import_llm_debate() -> None:
    script = _fresh_import_script(
        """
from datetime import date, timedelta
from typing import Any
from stock_platform_agents import attach_debate_lane

class _Seq:
    name = 'seq'
    def get_daily(self, symbols, *, start=None, end=None, asset_type='stock'):
        rows = []
        d = date(2026, 1, 2)
        closes = [100.0 + i for i in range(20)]
        for i, close in enumerate(closes):
            while d.weekday() >= 5:
                d += timedelta(days=1)
            prev = closes[i - 1] if i else close
            rows.append({
                'symbol': '600519', 'date': d.isoformat(), 'close': close,
                'open': prev, 'high': max(prev, close), 'low': min(prev, close),
                'volume': 1000.0,
                'change_pct': (close / prev - 1.0) if prev else 0.0,
            })
            d += timedelta(days=1)
        return rows
    def get_realtime(self, symbols, *, asset_type='stock'):
        return []

lane = attach_debate_lane(
    _Seq(),
    {'asof': '2026-02-20', 'picks': [{'rank': 1, 'symbol': '600519'}]},
    engine='deterministic',
)
assert lane['debateCount'] == 1
assert 'stock_platform_agents.llm_debate' not in sys.modules
print('ok')
"""
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok" in proc.stdout


def test_llm_subpackage_is_canonical_face() -> None:
    from stock_platform_agents import llm

    assert callable(llm.llm_debate_status)
    assert callable(llm.run_debate)
    assert callable(llm.run_deep_llm_graph)
    import stock_platform_agents as agents

    assert agents.llm_debate_status is llm.llm_debate_status


def test_lazy_getattr_loads_llm_on_demand() -> None:
    script = _fresh_import_script(
        """
import stock_platform_agents as agents
assert 'stock_platform_agents.llm_debate' not in sys.modules
_ = agents.llm_debate_status
assert 'stock_platform_agents.llm_debate' in sys.modules
print('ok')
"""
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok" in proc.stdout


def test_deterministic_plugin_in_process() -> None:
    """In-process smoke: plugin default engine stays on build_debate_report."""
    from stock_platform_agents import DebateAgentPlugin

    class _Seq:
        name = "seq"

        def get_daily(self, symbols, *, start=None, end=None, asset_type="stock"):
            rows: list[dict[str, Any]] = []
            d = date(2026, 1, 2)
            closes = [100.0 + i for i in range(20)]
            for i, close in enumerate(closes):
                while d.weekday() >= 5:
                    d += timedelta(days=1)
                prev = closes[i - 1] if i else close
                rows.append(
                    {
                        "symbol": "600519",
                        "date": d.isoformat(),
                        "close": close,
                        "open": prev,
                        "high": max(prev, close),
                        "low": min(prev, close),
                        "volume": 1000.0,
                        "change_pct": (close / prev - 1.0) if prev else 0.0,
                    }
                )
                d += timedelta(days=1)
            return rows

        def get_realtime(self, symbols, *, asset_type="stock"):
            return []

    out = DebateAgentPlugin(_Seq()).run("600519", asof="2026-02-20")
    assert out["kind"] == "debate"
    assert out["verdict"] in {"Buy", "Hold", "Sell"}
