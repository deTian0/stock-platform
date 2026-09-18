"""concept_blocks — replay + mocked astock_http (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from stock_platform_providers import SymbolError
from stock_platform_providers.astock_http import AStockHttpProvider
from stock_platform_providers.normalize import normalize_concept_blocks_payload
from stock_platform_providers.replay import ReplayProvider, ReplayTransport

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_replay_concept_blocks() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    items = provider.get_concept_blocks(["600519"])
    assert len(items) == 1
    item = items[0]
    assert item["symbol"] == "600519"
    assert item["source"] == "replay"
    assert item["total"] == 3
    assert "食品饮料" in item["concept_tags"]
    assert item["boards"][0]["code"] == "BK0481"


def test_replay_concept_blocks_missing() -> None:
    provider = ReplayProvider(ReplayTransport(FIXTURES))
    with pytest.raises(SymbolError, match="no concept_blocks fixture"):
        provider.get_concept_blocks(["999999"])


def test_astock_http_concept_blocks_mocked() -> None:
    def get_json(url, params=None):
        assert "slist/get" in url
        assert params["secid"] == "1.600519"
        assert params["spt"] == "3"
        return {
            "data": {
                "diff": {
                    "0": {"f12": "BK0481", "f14": "食品饮料", "f3": 0.5, "f128": "贵州茅台"},
                    "1": {"f12": "BK0896", "f14": "白酒概念", "f3": 1.1, "f128": "贵州茅台"},
                }
            }
        }

    items = AStockHttpProvider(get_json=get_json).get_concept_blocks(["600519"])
    assert len(items) == 1
    assert items[0]["total"] == 2
    assert items[0]["boards"][0]["name"] == "食品饮料"
    assert items[0]["source"] == "astock_http"


def test_normalize_concept_blocks_requires_symbol() -> None:
    with pytest.raises(ValueError, match="missing symbol"):
        normalize_concept_blocks_payload({"boards": []}, source="test")
