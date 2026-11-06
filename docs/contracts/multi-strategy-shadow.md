# 契约：多策略影子 Final Board

- 里程碑：多策略影子链 MVP（目标累计发版 `v4.14.0`）
- 单点：`stock_platform_research.shadow_board`
- CLI：`stock-platform-shadow-board`
- ADR：[0093](../architecture/0093-multi-strategy-shadow-board.md)
- 计划：[../plans/multi-strategy-final-board.md](../plans/multi-strategy-final-board.md)
- 状态：生效（SIMULATE / 影子只写 / 不改出厂）

## 1. 硬约束

| 约束 | 含义 |
|------|------|
| 影子隔离 | 只写 `local/shadow/`（或 `STOCK_PLATFORM_SHADOW_DIR`）；禁止写生产 picks / hits / 主绩效 JSONL |
| 空板合法 | Round2 禁止 pad-to-N；Final 可为空 |
| 集 A 硬仲裁 | ST / 流动性 / 涨停 / 集中度 / 学校优先级；fail-closed |
| 集 B 顾问 | 贝叶斯+LLM 不可放行未过硬闸票；`excludedFromPerformance=true` |
| LLM | 不可覆盖硬闸；理由缺结构化字段 → degrade / 不采用正式解释 |
| market.db | 只读；东财 HTTP 仍经 `em_get`（本 MVP 默认不发网） |
| 升级门 | 证据只喂 Y1；Y2 签核前不改出厂默认档 |

## 2. 学校 ID

| ID | 名称 | MVP / 现行 |
|----|------|------------|
| `S1` | 宏观/择时 | 薄规则：`regime` 闸 → 可注入 `index_bars` MA20 → 否则截面 `rs20`/`ma20`/`trend_up` 宽度；仍缺 → 空池 + reason |
| `S2` | 事件/主题 | DI：`concept_blocks` / `sector_fund_flow` / `lhb` / `unlock`；未注入或无信号 → 空池；未过 `FACTOR_LIBRARY` 不得进生产权重 |
| `S3` | 质量/防守 | 可复用 lvrev-like / quality 二次精选权重 |
| `S4` | 短线动量 | 可复用 short secondary 权重 |
| `S5` | 资金流/流动性 | `main_net`/`fund_flow` 排序；否则 amount/illiq 流动性薄规则；全缺 → 空池 |

学校优先级（集 A 同票冲突，高者胜）：`S3 > S4 > S5 > S2 > S1`。

## 3. Payload 形状

顶层：

```json
{
  "schemaVersion": 1,
  "asof": "YYYY-MM-DD",
  "status": "ok | empty | degraded",
  "excludedFromPerformance": true,
  "shadowOnly": true,
  "schools": { "S1": { "candidates": [], "status": "empty", "reason": "…" }, "…" },
  "round2": {
    "rejected": [{ "code": "…", "school": "S3", "reason": "…" }],
    "passed": [{ "code": "…", "school": "S3", "score": 0.0 }],
    "arbiter": "set_a"
  },
  "advisoryB": null,
  "finalBoard": [
    {
      "code": "600519",
      "name": "…",
      "school": "S3",
      "score": 0.82,
      "holdingPeriod": "10–20 交易日",
      "trigger": "…",
      "expectation": "…",
      "invalidation": "…",
      "excludedFromPerformance": true
    }
  ],
  "ledgerPath": "local/shadow/…"
}
```

`status`：

| 值 | 含义 |
|----|------|
| `ok` | Final 至少 1 只 |
| `empty` | 合法空板（无候选或硬闸后空） |
| `degraded` | 有顾问/LLM 路径缺字段等可观测降级，仍可空板或短板 |

## 4. 落盘

| 文件 | 内容 |
|------|------|
| `local/shadow/final_board_{asof}.json` | 当日完整 payload |
| `local/shadow/final_board.jsonl` | 追加一行（摘要 + finalBoard 计数） |
| `local/shadow/shadow_decisions.jsonl` | 影子**前向绩效账本**（每个终榜席位一行 pending，`(date, symbol)` 幂等；空榜不落行） |

### 4.1 影子前向绩效账本（`shadow_board.performance`）

- 与主账本 `recommend_decisions.jsonl` 物理隔离（文件名守卫 `FORBIDDEN_BASENAMES`），**不混算**。
- 结算复用主结算单点 `settle_pending_entries`（同一持有窗口、同一 alpha=raw−benchmark 口径），缺行情则保持 pending，不编造。
- 行内 `setA`（确定性仲裁通过）与 `setB`（顾问排序/分数/胜率/期望）并存；摘要分别报告：
  - 集 A：主 `compute_performance` 口径 + 分校（bySchool）；
  - 集 B：顾问排序上半区 vs 下半区平均收益差（`topMinusBottom`）、胜率 Brier；无顾问字段 → `available=false`。
- 入口：`run_daily_pipeline(shadow_board=True)` 自动追加 pending；`stock-platform-shadow-board --settle-daily` 结算；`--perf-summary` 只读摘要。
- 样本 < `MIN_MEANINGFUL_SAMPLE`(20) 时 `sampleSufficient=false`，不得据此下结论。

**禁止**写入：`local/recommend_decisions.jsonl`、hits 表、生产 brief picks。

### 4.2 历史 walk-forward 回测（`shadow_board.backtest`）

- 入口：`stock-platform-shadow-board --backtest --start YYYY-MM-DD [--end ...] [--db ...] [--bt-out-dir local/shadow/backtest]`（只读 `market.db`，产物不提交）。
- 同一引擎：影子终榜与 lvrev 基线都走 `book_replay.replay_book`（X4 单点），T+1 / 涨跌停 / 冷静期 / 成本口径与主回测一致；差异只在 entry provider。
- 无未来函数：每个交易日只用截至当日的截面（`compute_features` 为 PIT-safe），逐日调用与日循环相同的 `run_round1` → `apply_round2_set_a`。
- 报告：总收益 / 年化 / 超额（沪深300，缺则 `None`）/ 回撤 / 夏普 / 胜率 / 笔数 / 换手 / 空榜比例 / 分校覆盖，`delta = 影子 − lvrev`。
- 已知限制（写入报告 `limitations`）：`name`/`industry` 取 fundamentals 当前快照（非 PIT）；S2 无历史 DI → 恒空池；S5 走流动性薄规则；仅回放集 A，集 B / LLM 不进回测。

## 5. digest 只读附录（可选）

若存在 `local/shadow/final_board_{asof}.json`（或 `STOCK_PLATFORM_SHADOW_DIR`），盘前/盘后 digest 在「绩效台账」后追加 **附录 · 影子 Final Board（只读）**；文件缺失则**整段省略**（不 pad、不编造）。不改 picks / 同花顺导入语义。

## 6. 仍 stub / 延后

| 项 | 状态 |
|----|------|
| 集 B 真实贝叶斯先验 + LLM 胜率 | 仍 experimental 占位（可有学校优先级 `rankHints`）；不可覆盖硬闸 |
| S2 自动拉东财主题（无 DI 时） | 日循环影子链开启时经 S2-P1 每日快照（`em_get`，预算 `STOCK_PLATFORM_S2_EM_BUDGET` 默认 300/日，开关 `STOCK_PLATFORM_S2_SNAPSHOT`，fail-soft；replay / pytest 不发网）；字段见 [`datasets.md`](datasets.md)「影子链产物」；回测仍无 DI → 空池 |
| Workbench 影子只读页 | 延后 |
| 改 `W_DEFAULT` / 出厂 picks | 禁止（须 Y1→Y2） |

## 7. 非目标

改出厂 picks 写路径；开 live；默认开 LLM；主题校绕过 `FACTOR_LIBRARY`。
