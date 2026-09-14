"""Paper/wizard UX helpers — SIMULATE auto-ensure + friendly Chinese errors."""

from __future__ import annotations

import re
from typing import Any

from stock_platform_execution import (
    AUTO_ACTIVATED_STATUS_ZH,
    ActivationBlocked,
    evaluate_admission,
)

# Re-export for routes / tests
__all__ = [
    "AUTO_ACTIVATED_STATUS_ZH",
    "ensure_active_simulate_strategy",
    "friendly_execution_detail",
]


def ensure_active_simulate_strategy(lifecycle: Any) -> dict[str, Any]:
    """Ensure a SIMULATE strategy is active for daily paper paths (idempotent).

    Still requires admission safety for activate; never sets liveTradingEnabled.
    """
    admission = evaluate_admission(
        data_ok=True,
        simulate_ok=True,
        live_off=True,
        hash_ok=True,
        timing_ok=True,
        idempotency_ok=True,
        order_guards_ok=True,
    )
    try:
        return lifecycle.ensure_default_simulate_active(
            execution_safety_passed=admission["passed"],
        )
    except ActivationBlocked as exc:
        raise ActivationBlocked(friendly_execution_detail(exc)) from exc


def friendly_execution_detail(exc: BaseException) -> str:
    """Map common English execution/paper errors to short Chinese copy."""
    msg = str(exc)
    rules: list[tuple[str, str]] = [
        (
            r"no active strategy",
            "当前没有激活的纸面策略；向导/一键纸面会自动创建并激活默认 SIMULATE 策略",
        ),
        (r"executionSafety\.passed is required", "执行安全检查未通过，无法激活策略"),
        (r"validatedHash mismatch", "策略校验哈希不匹配，请先保存并校验草稿"),
        (r"draft hash mismatch", "草稿哈希不匹配，请先保存策略草稿再校验"),
        (r"signal bar for .+ is not completed", "信号日 K 线尚未完成，无法建立纸面草稿"),
        (r"execution window is (\w+)", r"当前不在纸面执行时间窗内（\1），未静默绕过"),
        (r"admission gates failed", "准入闸门未通过，拒绝建草稿/下单"),
        (r"refusing to submit empty order list", "订单列表为空，拒绝提交"),
        (r"draft older than", "纸面草稿已过期，请重新生成"),
        (r"unknown draftId", "未知草稿 ID"),
        (r"liveTradingEnabled must be False", "禁止实盘：liveTradingEnabled 必须为 false"),
        (r"allowedEnvironment must be", "仅允许 SIMULATE 环境"),
        (r"readyForPaperTrading is False", "执行配置未就绪（readyForPaperTrading=false）"),
    ]
    for pattern, zh in rules:
        m = re.search(pattern, msg, flags=re.IGNORECASE)
        if m:
            if "\\" in zh:
                return m.expand(zh)
            return zh
    return msg
