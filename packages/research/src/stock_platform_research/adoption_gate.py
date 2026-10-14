"""策略采纳闸门（milestone ``Y1``）—— 把「已验证的改进」经样本外验证后落到生产的裁决面。

平台在 ``S`` 域积累了若干**已在单窗口回测中验证、但从未进生产**的改进：

- ``S4`` 行业中性化：``total_return`` 0.3029 → 0.5257、``sharpe`` 1.06 → 1.14
  （叠加 ``max_per_industry=3`` → 0.5850 / 1.2492），当时**明确不采纳**；
- ``S3`` 闸门敏感性：出厂 ``min_pick_score=0.80`` 的 ``sharpe`` 1.060 是全网格**最差**，
  ``0.5/0.6/0.7`` 为 1.253/1.129/1.157，同样**不采纳**。

「不采纳」的理由是正当的 —— **单窗口的最优点可能是噪声**（曲线拟合）。但「永远不采纳」
也不是答案：那样所有研究都停在报告里，平台赚不到钱。本模块补上中间那一步：

**在同一引擎上，把基线档与候选档在多个互不重叠的样本外窗口各跑一遍，按预先登记的
规则给出 ``adopt`` / ``reject`` / ``insufficient`` 裁决。**

设计要点
--------
- **同一引擎**：基线档就是「``neutralize=None`` 的原始筛选档」，与候选档共用
  :func:`neutralization_ab.run_neutralization_book`（其内部是 ``X4`` 单点
  :func:`book_replay.replay_book`）。差异只来自候选旋钮，不来自实现。
- **特征只算一次**：``feats`` 在全跨度上算一遍（含 ``ma20/ma60`` 预热），再按日期切窗；
  窗口边界因此**不会**损失预热数据，也比「每窗重算」快得多。
- **纯函数裁决**：:func:`decide_adoption` 只吃 ``{baseline, candidate}`` 两组指标字典，
  不碰引擎、不碰 pandas，可被单测穷举。
- **样本外**：窗口由 :func:`build_windows` 从最后交易日**向前**按年切分，互不重叠。
- **只出建议**：本模块**绝不**改生产默认档、不写 brief / picks。采纳是**独立的人工签核步骤**
  （见 ``docs/contracts/adoption-gate.md`` §6）。

SIMULATE only；不构成投资建议。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

import pandas as pd

from .neutralization import NeutralizeParams
from .neutralization_ab import run_neutralization_book
from .strategy_ab import AB_METRIC_KEYS, _delta_metrics

#: Default output directory (platform-owned ``data/``; never the engine DB).
DEFAULT_ADOPTION_OUT_DIR = "data/strategy"

#: Rolling out-of-sample window defaults: last ``DEFAULT_WINDOW_COUNT`` years.
DEFAULT_WINDOW_COUNT = 3
DEFAULT_WINDOW_YEARS = 1

#: Extra calendar span loaded *before* the earliest window so ``ma60`` is warm.
DEFAULT_WINDOW_WARMUP_DAYS = 180

VERDICT_ADOPT = "adopt"
VERDICT_REJECT = "reject"
VERDICT_INSUFFICIENT = "insufficient"
VERDICT_ZH: dict[str, str] = {
    VERDICT_ADOPT: "采纳",
    VERDICT_REJECT: "不采纳",
    VERDICT_INSUFFICIENT: "样本不足",
}

WINDOW_PASS = "pass"
WINDOW_FAIL = "fail"
WINDOW_INSUFFICIENT = "insufficient"
WINDOW_ZH: dict[str, str] = {
    WINDOW_PASS: "通过",
    WINDOW_FAIL: "未达标",
    WINDOW_INSUFFICIENT: "样本不足",
}

#: The three risk gates a window must clear to count as a pass.
WINDOW_CHECKS = ("sharpe", "drawdown", "winrate")
CHECK_ZH: dict[str, str] = {
    "trades": "样本笔数",
    "sharpe": "夏普",
    "drawdown": "最大回撤",
    "winrate": "胜率",
}


# --------------------------------------------------------------------------- #
# Candidate / rule specs
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CandidateSpec:
    """One strategy variant, expressed as the knobs ``book_replay`` accepts.

    ``neutralize=False`` reproduces the production baseline exactly (the frame is
    read, never rewritten); every other field maps 1:1 onto
    :func:`neutralization_ab.run_neutralization_book`.
    """

    name: str
    label: str
    description: str = ""
    min_pick_score: float = 0.80
    neutralize: bool = False
    neutralize_params: NeutralizeParams | None = None
    max_per_industry: int | None = None
    value_factor: bool = False
    reversal_q: float | None = None
    weights: Mapping[str, float] | None = None
    gate_params: Any = None

    def to_summary(self) -> dict[str, Any]:
        """JSON-safe description (``NeutralizeParams`` expanded, weights copied)."""
        return {
            "name": self.name,
            "label": self.label,
            "description": self.description,
            "minPickScore": self.min_pick_score,
            "neutralize": bool(self.neutralize),
            "neutralizeParams": (
                asdict(self.neutralize_params)
                if (self.neutralize and self.neutralize_params is not None)
                else (asdict(NeutralizeParams()) if self.neutralize else None)
            ),
            "maxPerIndustry": self.max_per_industry,
            "valueFactor": bool(self.value_factor),
            "reversalQ": self.reversal_q,
            "weights": dict(self.weights) if self.weights else None,
        }


@dataclass(frozen=True)
class AdoptionRule:
    """Pre-registered adoption thresholds — fixed *before* looking at results.

    A window ``pass``es only when **all three** risk gates clear; the candidate is
    ``adopt``ed only when every evaluable window passes (``require_all_windows``),
    so a single lucky window cannot carry the decision.
    """

    min_sharpe_margin: float = 0.05
    max_drawdown_tolerance: float = 0.05
    max_winrate_drop: float = 0.05
    min_trades: int = 8
    require_all_windows: bool = True


DEFAULT_RULE = AdoptionRule()

#: The production baseline — the yardstick, never a candidate itself.
BASELINE_SPEC = CandidateSpec(
    name="baseline",
    label="生产基线",
    description="当前出厂档：min_pick_score=0.80、无行业中性化（等价 neutralize=None）。",
)

#: Improvements that research validated on a single window but never adopted.
DEFAULT_CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        name="neutralized",
        label="行业中性化",
        description="开启 S4 行业中性化（demean + rank 还原），闸门与权重不变。",
        neutralize=True,
    ),
    CandidateSpec(
        name="neutralized_capped",
        label="中性化 + 行业上限 3",
        description="中性化叠加 max_per_industry=3 行业暴露约束。",
        neutralize=True,
        max_per_industry=3,
    ),
    CandidateSpec(
        name="gate_070",
        label="闸门 0.70",
        description="把 min_pick_score 从 0.80 放到 S3 稳健区间内的 0.70。",
        min_pick_score=0.70,
    ),
    CandidateSpec(
        name="neutralized_capped_gate_070",
        label="中性化 + 上限 3 + 闸门 0.70",
        description="三项已验证改进的叠加。",
        neutralize=True,
        max_per_industry=3,
        min_pick_score=0.70,
    ),
)

CANDIDATE_REGISTRY: dict[str, CandidateSpec] = {
    spec.name: spec for spec in DEFAULT_CANDIDATES
}


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
def build_windows(
    last_date: str,
    *,
    years: int = DEFAULT_WINDOW_YEARS,
    count: int = DEFAULT_WINDOW_COUNT,
) -> list[dict[str, str]]:
    """Split the ``count`` most recent ``years``-long spans, oldest first.

    Windows are **disjoint**: each one ends the day before the previous one
    starts. ``last_date`` is the most recent bar date (``YYYY-MM-DD``).
    """
    end = date.fromisoformat(str(last_date)[:10])
    years = max(1, int(years))
    count = max(1, int(count))
    out: list[dict[str, str]] = []
    for i in range(count):
        start = end - timedelta(days=years * 365)
        out.append({"label": f"w{count - i}", "start": start.isoformat(), "end": end.isoformat()})
        end = start - timedelta(days=1)
    out.reverse()  # oldest first
    return out


def slice_window(feats: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Slice a pre-built feature frame to ``[start, end]`` (inclusive, by ``trade_date``).

    ``trade_date`` may be a string column *or* a ``datetime64`` column depending on
    how the frame was built, so both sides are coerced to timestamps before the
    comparison — a raw string compare silently drops the boundary day.
    """
    if feats.empty:
        return feats
    days = pd.to_datetime(feats["trade_date"], errors="coerce")
    lo = pd.Timestamp(str(start)[:10])
    hi = pd.Timestamp(str(end)[:10])
    mask = ((days >= lo) & (days <= hi)).fillna(False)
    return feats[mask].reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Engine runs
# --------------------------------------------------------------------------- #
def run_candidate(
    feats: pd.DataFrame,
    spec: CandidateSpec,
    *,
    params: Any = None,
) -> dict[str, Any]:
    """Replay one :class:`CandidateSpec` through the shared loop; return its block."""
    neutralize = None
    if spec.neutralize:
        neutralize = spec.neutralize_params or NeutralizeParams()
    book = run_neutralization_book(
        feats,
        neutralize=neutralize,
        params=params,
        max_per_industry=spec.max_per_industry,
        min_pick_score=spec.min_pick_score,
        weights=spec.weights,
        gate_params=spec.gate_params,
        value_factor=spec.value_factor,
        reversal_q=spec.reversal_q,
    )
    return {
        "metrics": book["metrics"],
        "review": book["review"],
        "tradeCount": len(book.get("trades") or []),
        "finalEquity": book["final_equity"],
        "nDays": book["n_days"],
    }


# --------------------------------------------------------------------------- #
# Pure decision
# --------------------------------------------------------------------------- #
def _num(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


def decide_adoption(
    per_window: Sequence[Mapping[str, Any]],
    rule: AdoptionRule | None = None,
) -> dict[str, Any]:
    """Pure verdict for one candidate across windows (no engine, no pandas).

    ``per_window`` items are ``{"window": label, "baseline": metrics, "candidate": metrics}``.
    Returns the per-window checks plus the rolled-up verdict.
    """
    rule = rule or DEFAULT_RULE
    rows: list[dict[str, Any]] = []
    deltas: list[dict[str, float]] = []

    for item in per_window:
        base = dict(item.get("baseline") or {})
        cand = dict(item.get("candidate") or {})
        b_n = int(base.get("n_trades") or 0)
        c_n = int(cand.get("n_trades") or 0)
        b_sharpe = _num(base.get("sharpe"))
        c_sharpe = _num(cand.get("sharpe"))
        b_dd = _num(base.get("max_drawdown"))
        c_dd = _num(cand.get("max_drawdown"))
        b_wr = _num(base.get("win_rate"))
        c_wr = _num(cand.get("win_rate"))

        checks = {
            "trades": bool(b_n >= rule.min_trades and c_n >= rule.min_trades),
            "sharpe": bool(
                b_sharpe is not None
                and c_sharpe is not None
                and (c_sharpe - b_sharpe) >= rule.min_sharpe_margin
            ),
            "drawdown": bool(
                b_dd is not None
                and c_dd is not None
                and c_dd >= b_dd - rule.max_drawdown_tolerance
            ),
            "winrate": bool(
                b_wr is not None
                and c_wr is not None
                and (c_wr - b_wr) >= -rule.max_winrate_drop
            ),
        }

        if not checks["trades"]:
            verdict = WINDOW_INSUFFICIENT
        elif all(checks[k] for k in WINDOW_CHECKS):
            verdict = WINDOW_PASS
        else:
            verdict = WINDOW_FAIL

        delta = _delta_metrics(base, cand)
        deltas.append({k: v for k, v in delta.items() if isinstance(v, (int, float))})
        rows.append(
            {
                "window": item.get("window"),
                "verdict": verdict,
                "checks": checks,
                "blockingChecks": [k for k in WINDOW_CHECKS if not checks[k]],
                "baseline": {
                    "sharpe": b_sharpe,
                    "maxDrawdown": b_dd,
                    "winRate": b_wr,
                    "nTrades": b_n,
                    "totalReturn": _num(base.get("total_return")),
                },
                "candidate": {
                    "sharpe": c_sharpe,
                    "maxDrawdown": c_dd,
                    "winRate": c_wr,
                    "nTrades": c_n,
                    "totalReturn": _num(cand.get("total_return")),
                },
                "delta": delta,
            }
        )

    evaluated = [r for r in rows if r["verdict"] != WINDOW_INSUFFICIENT]
    passed = [r for r in rows if r["verdict"] == WINDOW_PASS]
    failed = [r for r in rows if r["verdict"] == WINDOW_FAIL]

    if not evaluated:
        verdict = VERDICT_INSUFFICIENT
    elif rule.require_all_windows:
        verdict = VERDICT_ADOPT if not failed else VERDICT_REJECT
    else:
        verdict = VERDICT_ADOPT if len(passed) > len(failed) else VERDICT_REJECT

    mean_delta: dict[str, float | None] = {}
    for key in AB_METRIC_KEYS:
        vals = [d[key] for d in deltas if key in d and d[key] is not None]
        mean_delta[key] = (sum(vals) / len(vals)) if vals else None

    reasons: list[str] = []
    if verdict == VERDICT_INSUFFICIENT:
        reasons.append(
            f"全部窗口样本笔数 < {rule.min_trades}，不足以裁决（不做结论）。"
        )
    for row in rows:
        for key in row["blockingChecks"]:
            reasons.append(f"{row['window']}：{CHECK_ZH[key]}未达标")

    return {
        "verdict": verdict,
        "verdictZh": VERDICT_ZH.get(verdict, verdict),
        "rule": asdict(rule),
        "windows": rows,
        "counts": {
            "total": len(rows),
            "pass": len(passed),
            "fail": len(failed),
            "insufficient": len(rows) - len(evaluated),
        },
        "passRate": (len(passed) / len(evaluated)) if evaluated else None,
        "failingWindows": [r["window"] for r in failed],
        "meanDelta": mean_delta,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# Whole-report evaluation
# --------------------------------------------------------------------------- #
def evaluate_adoption(
    feats: pd.DataFrame,
    *,
    baseline: CandidateSpec = BASELINE_SPEC,
    candidates: Sequence[CandidateSpec] = DEFAULT_CANDIDATES,
    windows: Sequence[Mapping[str, str]],
    rule: AdoptionRule | None = None,
    params: Any = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Run the baseline + every candidate across every window and roll up verdicts.

    ``feats`` is the **full-span** feature frame (features computed once); each
    window is sliced from it, so window edges carry no warm-up penalty.
    """
    rule = rule or DEFAULT_RULE
    windows = list(windows or [])
    if feats is None or feats.empty or not windows:
        return {
            "ok": False,
            "reason": "no bars in range" if not windows else "empty feature frame",
            "environment": "SIMULATE",
            "liveTradingEnabled": False,
            "disclaimer": "Research only; not investment advice.",
        }

    window_meta: list[dict[str, Any]] = []
    baseline_metrics: dict[str, dict[str, Any]] = {}
    for win in windows:
        frame = slice_window(feats, win["start"], win["end"])
        run = run_candidate(frame, baseline, params=params)
        baseline_metrics[win["label"]] = run["metrics"]
        window_meta.append(
            {
                "label": win["label"],
                "start": win["start"],
                "end": win["end"],
                "nDays": run["nDays"],
                "baselineTrades": run["tradeCount"],
            }
        )

    blocks: list[dict[str, Any]] = []
    for spec in candidates:
        per_window: list[dict[str, Any]] = []
        for win in windows:
            frame = slice_window(feats, win["start"], win["end"])
            run = run_candidate(frame, spec, params=params)
            per_window.append(
                {
                    "window": win["label"],
                    "baseline": baseline_metrics[win["label"]],
                    "candidate": run["metrics"],
                    "tradeCount": run["tradeCount"],
                    "nDays": run["nDays"],
                }
            )
        decision = decide_adoption(
            [{"window": r["window"], "baseline": r["baseline"], "candidate": r["candidate"]} for r in per_window],
            rule,
        )
        for row, src in zip(decision["windows"], per_window):
            row["candidateTrades"] = src["tradeCount"]
            row["nDays"] = src["nDays"]
        blocks.append(
            {
                "name": spec.name,
                "label": spec.label,
                "summary": spec.to_summary(),
                "windows": decision["windows"],
                "decision": decision,
            }
        )

    recommend = [b["name"] for b in blocks if b["decision"]["verdict"] == VERDICT_ADOPT]
    counts = {v: sum(1 for b in blocks if b["decision"]["verdict"] == v) for v in
              (VERDICT_ADOPT, VERDICT_REJECT, VERDICT_INSUFFICIENT)}
    return {
        "ok": True,
        "generatedAt": generated_at,
        "baseline": baseline.to_summary(),
        "rule": asdict(rule),
        "windows": window_meta,
        "candidates": blocks,
        "recommended": recommend,
        "verdictCounts": counts,
        "metaKeys": list(AB_METRIC_KEYS),
        "environment": "SIMULATE",
        "liveTradingEnabled": False,
        "metricNote": (
            "每个窗口内基线档与候选档共用同一引擎（book_replay 单点定义），"
            "delta = 候选 − 基线，同口径无需二次归一。"
        ),
        "adoptionNote": (
            "本报告只出**建议**：不修改任何生产默认档、不写 brief / picks。"
            "采纳是把候选写进命名档案的独立人工签核步骤。"
        ),
        "disclaimer": "策略采纳闸门（研究结论）；非投资建议；SIMULATE。",
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #
def _fmt_pct(value: Any) -> str:
    num = _num(value)
    return "-" if num is None else f"{num * 100:.2f}%"


def _fmt_num(value: Any, *, digits: int = 3) -> str:
    num = _num(value)
    return "-" if num is None else f"{num:.{digits}f}"


def _fmt_signed(value: Any, *, digits: int = 3) -> str:
    num = _num(value)
    if num is None:
        return "-"
    return f"{num:+.{digits}f}"


def render_adoption_markdown(payload: Mapping[str, Any]) -> str:
    """Markdown report for the adoption gate (``JSON`` is the machine contract)."""
    if not payload.get("ok"):
        return f"# 策略采纳闸门\n\n无可用数据：{payload.get('reason')}\n"

    lines: list[str] = ["# 策略采纳闸门报告", ""]
    if payload.get("generatedAt"):
        lines += [f"- 生成时间：{payload['generatedAt']}"]
    base = payload.get("baseline") or {}
    lines += [
        f"- 基线档：**{base.get('label')}**（min_pick_score={base.get('minPickScore')}, "
        f"neutralize={'on' if base.get('neutralize') else 'off'}）",
        f"- 窗口数：**{len(payload.get('windows') or [])}**（互不重叠，按年向前切分）",
        f"- 环境：{payload.get('environment')} · liveTradingEnabled="
        f"{str(payload.get('liveTradingEnabled'))}",
        "",
    ]

    rule = payload.get("rule") or {}
    lines += [
        "## 采纳规则（事前登记）",
        "",
        "| 项 | 阈值 |",
        "|----|------|",
        f"| 夏普边际（候选 − 基线） | ≥ {rule.get('min_sharpe_margin')} |",
        f"| 回撤恶化容差 | ≤ {rule.get('max_drawdown_tolerance')} |",
        f"| 胜率下滑容差 | ≤ {rule.get('max_winrate_drop')} |",
        f"| 单窗最少笔数 | ≥ {rule.get('min_trades')} |",
        f"| 全窗口要求 | {'是' if rule.get('require_all_windows') else '否'} |",
        "",
    ]

    lines += ["## 窗口", "", "| 窗口 | 起 | 止 | 交易日 | 基线笔数 |", "|------|----|----|--------|----------|"]
    for win in payload.get("windows") or []:
        lines.append(
            f"| {win['label']} | {win['start']} | {win['end']} | {win.get('nDays')} | "
            f"{win.get('baselineTrades')} |"
        )
    lines.append("")

    lines += [
        "## 裁决总表",
        "",
        "| 候选 | 判定 | 通过窗 | Δ夏普(均) | Δ收益(均) | Δ回撤(均) | Δ胜率(均) |",
        "|------|------|--------|-----------|-----------|-----------|-----------|",
    ]
    for block in payload.get("candidates") or []:
        dec = block.get("decision") or {}
        md = dec.get("meanDelta") or {}
        lines.append(
            f"| {block['label']} | **{dec.get('verdictZh')}** | "
            f"{dec.get('counts', {}).get('pass')}/{dec.get('counts', {}).get('total')} | "
            f"{_fmt_signed(md.get('sharpe'))} | {_fmt_pct(md.get('total_return'))} | "
            f"{_fmt_signed(md.get('max_drawdown'))} | {_fmt_pct(md.get('win_rate'))} |"
        )
    lines.append("")

    lines += ["## 逐窗明细", ""]
    for block in payload.get("candidates") or []:
        dec = block.get("decision") or {}
        lines += [
            f"### {block['label']} — {dec.get('verdictZh')}",
            "",
            "| 窗口 | 判定 | 基线夏普 | 候选夏普 | Δ夏普 | 基线回撤 | 候选回撤 | 笔数(基/候) | 阻塞项 |",
            "|------|------|----------|----------|-------|----------|----------|-------------|--------|",
        ]
        for row in block.get("windows") or []:
            b = row.get("baseline") or {}
            c = row.get("candidate") or {}
            blockers = "、".join(CHECK_ZH[k] for k in (row.get("blockingChecks") or [])) or "—"
            lines.append(
                f"| {row['window']} | {WINDOW_ZH.get(row.get('verdict'), row.get('verdict'))} | "
                f"{_fmt_num(b.get('sharpe'))} | {_fmt_num(c.get('sharpe'))} | "
                f"{_fmt_signed((row.get('delta') or {}).get('sharpe'))} | "
                f"{_fmt_pct(b.get('maxDrawdown'))} | {_fmt_pct(c.get('maxDrawdown'))} | "
                f"{b.get('nTrades')}/{c.get('nTrades')} | {blockers} |"
            )
        reasons = dec.get("reasons") or []
        if reasons:
            lines += ["", "阻塞理由："]
            lines += [f"- {r}" for r in reasons]
        lines.append("")

    rec = payload.get("recommended") or []
    lines += [
        "## 建议",
        "",
        ("**建议采纳**：" + "、".join(rec)) if rec else "**无候选通过闸门** —— 维持生产基线。",
        "",
        f"> {payload.get('adoptionNote', '')}",
        "",
        f"> {payload.get('metricNote', '')}",
        "",
    ]
    return "\n".join(lines)


__all__ = [
    "AdoptionRule",
    "BASELINE_SPEC",
    "CANDIDATE_REGISTRY",
    "DEFAULT_ADOPTION_OUT_DIR",
    "DEFAULT_CANDIDATES",
    "DEFAULT_RULE",
    "DEFAULT_WINDOW_COUNT",
    "DEFAULT_WINDOW_WARMUP_DAYS",
    "DEFAULT_WINDOW_YEARS",
    "CandidateSpec",
    "VERDICT_ADOPT",
    "VERDICT_INSUFFICIENT",
    "VERDICT_REJECT",
    "WINDOW_FAIL",
    "WINDOW_INSUFFICIENT",
    "WINDOW_PASS",
    "build_windows",
    "decide_adoption",
    "evaluate_adoption",
    "render_adoption_markdown",
    "run_candidate",
    "slice_window",
]
