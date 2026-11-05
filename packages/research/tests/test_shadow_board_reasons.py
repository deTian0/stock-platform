"""LLM reason schema validation / vacuous-phrase detection / fallback (ADR 0093 §6/§7)."""

from __future__ import annotations

from stock_platform_research.shadow_board.reasons import (
    REQUIRED_REASON_FIELDS,
    apply_reason_policy,
    build_reason_prompt,
    validate_reason,
)


def _good_reason() -> dict[str, str]:
    return {
        "holdingPeriod": "5–10 交易日",
        "trigger": "成交额连续 3 日高于 60 日均值",
        "expectation": "5 日内相对沪深300 超额收益 ≥ 1%",
        "invalidation": "收盘跌破 MA20",
    }


def test_validate_reason_accepts_measurable_fields() -> None:
    check = validate_reason(_good_reason())
    assert check["ok"] is True
    assert check["problems"] == []


def test_validate_reason_rejects_missing_fields() -> None:
    reason = _good_reason()
    del reason["invalidation"]
    check = validate_reason(reason)
    assert check["ok"] is False
    assert any("缺字段 invalidation" in p for p in check["problems"])


def test_validate_reason_rejects_vacuous_slogans() -> None:
    reason = {
        "holdingPeriod": "5–10 交易日",
        "trigger": "市场情绪好，龙头股值得关注",
        "expectation": "前景广阔，值得期待",
        "invalidation": "基本面变差",
    }
    check = validate_reason(reason)
    assert check["ok"] is False
    # expectation/invalidation must carry something falsifiable (number/comparator).
    assert any("空话" in p or "不可证伪" in p for p in check["problems"])


def test_validate_reason_rejects_non_mapping() -> None:
    check = validate_reason(None)
    assert check["ok"] is False


def test_validate_reason_requires_holding_period_number() -> None:
    reason = _good_reason()
    reason["holdingPeriod"] = "中短期"
    check = validate_reason(reason)
    assert check["ok"] is False
    assert any("holdingPeriod" in p for p in check["problems"])


def test_apply_reason_policy_no_provider_keeps_rule_reason() -> None:
    rows = [{"code": "600519", **_good_reason()}]
    kept, dropped, stats = apply_reason_policy(rows)
    assert len(kept) == 1
    assert dropped == []
    assert kept[0]["reasonSource"] == "rule"
    assert kept[0]["excludedFromPerformance"] is True
    assert stats == {"llmAccepted": 0, "llmFallback": 0, "ruleDropped": 0}


def test_apply_reason_policy_accepts_valid_llm_reason() -> None:
    rows = [{"code": "600519", **_good_reason()}]
    llm_reason = {
        "holdingPeriod": "3–5 交易日",
        "trigger": "龙虎榜净买入居首",
        "expectation": "3 日内跑赢行业指数 ≥ 2%",
        "invalidation": "次日收盘跌破前低",
    }

    def provider(_rows):
        return {"600519": llm_reason}

    kept, dropped, stats = apply_reason_policy(rows, reason_provider=provider)
    assert len(kept) == 1
    assert kept[0]["reasonSource"] == "llm"
    assert kept[0]["holdingPeriod"] == "3–5 交易日"
    assert stats["llmAccepted"] == 1
    assert dropped == []


def test_apply_reason_policy_falls_back_on_vacuous_llm_reason() -> None:
    rows = [{"code": "600519", **_good_reason()}]
    vacuous = {
        "holdingPeriod": "短期",
        "trigger": "情绪好",
        "expectation": "看好后续表现",
        "invalidation": "基本面恶化",
    }

    def provider(_rows):
        return {"600519": vacuous}

    kept, dropped, stats = apply_reason_policy(rows, reason_provider=provider)
    assert len(kept) == 1
    assert kept[0]["reasonSource"] == "rule_fallback"
    # Falls back to the rule-filled deterministic reason, not the vacuous LLM text.
    assert kept[0]["holdingPeriod"] == "5–10 交易日"
    assert "reasonDegrade" in kept[0]
    assert stats["llmFallback"] == 1
    assert dropped == []


def test_apply_reason_policy_drops_when_deterministic_reason_itself_invalid() -> None:
    rows = [
        {
            "code": "600519",
            "holdingPeriod": "短期",
            "trigger": "情绪好",
            "expectation": "看好",
            "invalidation": "变差",
        }
    ]
    kept, dropped, stats = apply_reason_policy(rows)
    assert kept == []
    assert len(dropped) == 1
    assert stats["ruleDropped"] == 1


def test_apply_reason_policy_provider_exception_falls_back_safely() -> None:
    rows = [{"code": "600519", **_good_reason()}]

    def broken_provider(_rows):
        raise RuntimeError("llm sidecar down")

    kept, dropped, stats = apply_reason_policy(rows, reason_provider=broken_provider)
    assert len(kept) == 1
    assert kept[0]["reasonSource"] == "rule_fallback"
    assert "LLM provider 错误" in kept[0]["reasonDegrade"]
    assert stats["llmFallback"] == 1


def test_build_reason_prompt_includes_schema_and_banned_phrases() -> None:
    prompt = build_reason_prompt(
        {"code": "600519", "name": "贵州茅台", "school": "S3", "score": 0.8}
    )
    assert set(REQUIRED_REASON_FIELDS).issubset(prompt["schema"]["required"])
    assert "看好" in prompt["bannedPhrases"]
    assert prompt["excludedFromPerformance"] is True
    assert prompt["facts"]["code"] == "600519"
