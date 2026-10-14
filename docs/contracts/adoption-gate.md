# 契约：策略采纳闸门（Strategy Adoption Gate）

> 里程碑 **Y1 策略采纳闸门**（`v4.10.0`）·
> 代码单点：`packages/research/src/stock_platform_research/adoption_gate.py`
> CLI：`stock-platform-strategy-adoption`
> 相关 ADR：[0077](../architecture/0077-strategy-adoption-gate.md)（Y1 决定）·
> [0062](../architecture/0062-gate-parameter-sensitivity.md)（`S3` 闸门敏感性）·
> [0063](../architecture/0063-industry-neutralization.md)（`S4` 行业中性化）·
> [0060](../architecture/0060-strategy-ab-full-engine.md)（`S1` 同源 A/B）·
> [0059](../architecture/0059-picks-backtest-parity.md)（`X4` 回放单点）·
> [0058](../architecture/0058-market-db-source-of-truth.md)（market.db 只读真相源）
> 消费方契约：[strategy-ab](strategy-ab.md)（`delta` / `sameDefinition`）·
> [industry-neutralization](industry-neutralization.md)（`run_neutralization_book`）

## 1. 目的

回答一个问题：**「已经在单窗口回测里验证过的改进，到底该不该进生产？」**

`S` 域交付了一批**已验证但从未采纳**的改进 —— `S4` 行业中性化（`total_return`
0.3029 → 0.5257、`sharpe` 1.06 → 1.14）与 `S3` 闸门敏感性（出厂
`min_pick_score=0.80` 的 `sharpe` 1.060 是全网格最差）。当时的「不采纳」是对的：
**单窗口的最优点可能是噪声**。但「永远不采纳」等于所有研究都停在报告里 —— 平台赚不到钱。

本契约补上中间那一步：**在同一引擎上，把基线档与候选档在多个互不重叠的样本外窗口
各跑一遍，按事前登记的规则给出 `adopt` / `reject` / `insufficient` 裁决。**

## 2. 硬约束（不可协商）

| 约束 | 含义 |
|------|------|
| **只出建议** | 本模块**绝不**修改任何生产默认档（`W_DEFAULT` / `DEFAULT_MIN_PICK_SCORE` / 出厂闸门），**不写 brief / picks** |
| **零网络** | 不发布任何 HTTP 请求 |
| **只读行情** | `market.db` 以 `mode=ro` 打开；报告只写平台自有 `data/strategy/` |
| **同一引擎** | 基线档 = `neutralize=None` 的原始筛选档，与候选档共用 `run_neutralization_book`（内含 `X4` 单点 `book_replay.replay_book`）；差异只来自旋钮，不来自实现 |
| **样本外** | 窗口互不重叠、由最后交易日向前切分；窗口边界**不损失**均线预热（特征在全跨度上算一次再切窗） |
| **规则事前登记** | 阈值由 `AdoptionRule` 固定，**先于**看结果；纯函数 `decide_adoption` 不碰引擎、不碰 pandas |
| **样本不足不结论** | 任一窗口笔数 < `min_trades` → 该窗 `insufficient`；全部窗口不足 → 整体 `insufficient`（**不做结论**） |
| **无 `providers` 顶层导入** | 本模块只 import 本包内部单点（`neutralization` / `neutralization_ab` / `strategy_ab`） |

## 3. 基线与候选（`CandidateSpec`）

```python
@dataclass(frozen=True)
class CandidateSpec:
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
```

字段与 `run_neutralization_book` **1:1 对应**；`neutralize=False` 即生产基线
（帧只被读、不被改写）。`to_summary()` 输出 JSON 安全描述（`NeutralizeParams` 展开为 dict，
未开启时 `neutralizeParams=null`）。

| 常量 | 内容 |
|------|------|
| `BASELINE_SPEC` | 生产基线：`min_pick_score=0.80`、无中性化；**不是**候选（不在注册表内） |
| `DEFAULT_CANDIDATES` | `neutralized` / `neutralized_capped`（+`max_per_industry=3`）/ `gate_070` / `neutralized_capped_gate_070` |
| `CANDIDATE_REGISTRY` | `name → CandidateSpec` 映射（CLI `--candidates` 按名引用） |

## 4. 窗口

### 4.1 `build_windows(last_date, *, years=1, count=3)`（纯函数）

从 `last_date` **向前**按 `years` 切 `count` 个窗口，**互不重叠**（上一窗结束的次日
= 下一窗开始的再前一日），返回**由旧到新**排序的 `[{label, start, end}]`。
`years` / `count` 均夹到 ≥1。

### 4.2 `slice_window(feats, start, end)`（纯函数）

按 `trade_date` 取闭区间 `[start, end]`。**两侧都强制转 `Timestamp`** ——
`trade_date` 由 `prepare_book_frame` 产出时是 `datetime64`，裸字符串比较会**静默丢掉边界日**
（`"2024-04-08" < "2024-04-08 00:00:00"`）。

### 4.3 预热

特征帧在**全跨度**上算一次（含 `ma20` / `ma60` 预热），再按日期切窗 —— 因此窗口边界
**不损失**预热数据，也比「每窗重算」快得多。CLI 装载起点 = 最早窗口起点再往前
`DEFAULT_WINDOW_WARMUP_DAYS`（=180 天）。

## 5. 采纳规则与判定

### 5.1 `AdoptionRule`（冻结 dataclass，**事前登记**）

| 字段 | 默认 | 含义 |
|------|------|------|
| `min_sharpe_margin` | `0.05` | 候选夏普须**高于**基线的最小边际 |
| `max_drawdown_tolerance` | `0.05` | 允许的回撤恶化幅度（回撤为负；`cand ≥ base − tol` 才算过） |
| `max_winrate_drop` | `0.05` | 允许的胜率下滑幅度 |
| `min_trades` | `8` | 单窗最少成交笔数；低于此判 `insufficient` |
| `require_all_windows` | `True` | **要求全部窗口通过**（单窗幸运不可挟持结论） |

### 5.2 `decide_adoption(per_window, rule)`（**纯函数**）

`per_window` 元素 = `{"window": label, "baseline": metrics, "candidate": metrics}`。

**窗口判定**（三项风险闸门全过才 `pass`）：

| 检查 | 通过条件 |
|------|----------|
| `trades` | `baseline.n_trades ≥ min_trades` **且** `candidate.n_trades ≥ min_trades` |
| `sharpe` | `cand.sharpe − base.sharpe ≥ min_sharpe_margin` |
| `drawdown` | `cand.max_drawdown ≥ base.max_drawdown − max_drawdown_tolerance` |
| `winrate` | `cand.win_rate − base.win_rate ≥ −max_winrate_drop` |

任一指标缺失（`None`）→ 该检查**判否**（**不**默认通过）。

| 窗口 `verdict` | 条件 |
|----------------|------|
| `insufficient` | `trades` 检查不过 |
| `pass` | `sharpe` / `drawdown` / `winrate` **三项全过** |
| `fail` | 其余 |

**整体 `verdict`**：

| 情形 | 结论 |
|------|------|
| 无任何可评估窗口 | `insufficient`（并给出「笔数不足，不做结论」的理由） |
| `require_all_windows=True` 且有窗口 `fail` | `reject` |
| `require_all_windows=True` 且全部可评估窗口 `pass` | `adopt` |
| `require_all_windows=False` 且 `pass` 窗 **多于** `fail` 窗 | `adopt`，否则 `reject` |

返回含 `windows`（逐窗 `checks` / `blockingChecks` / 双方指标 / `delta`）、
`counts` / `passRate` / `failingWindows` / `meanDelta`（跨窗均值，键同 `AB_METRIC_KEYS`）/
`reasons`（中文阻塞理由）。

### 5.3 `run_candidate(feats, spec, *, params=None)`

把单个 `CandidateSpec` 经 `run_neutralization_book` 跑一遍，返回
`{metrics, review, tradeCount, finalEquity, nDays}`。

### 5.4 `evaluate_adoption(feats, *, baseline, candidates, windows, rule, params, generated_at)`

基线 + 全部候选 × 全部窗口；`feats` 为**全跨度**特征帧。空帧 / 空窗口 → `ok=False`（fail-closed）。

## 6. 报告与出口

| 出口 | 说明 |
|------|------|
| **CLI** | `stock-platform-strategy-adoption --years 1 --windows 3 [--start/--end 单窗｜--universe｜--candidates｜--out-dir｜--no-write｜--json]` |
| **规则覆盖** | `--min-sharpe-margin` / `--max-drawdown-tolerance` / `--max-winrate-drop` / `--min-trades` / `--any-window`（= `require_all_windows=False`） |
| **默认产出** | `data/strategy/adoption_gate.{json,md,html}`（`.json` 为机器契约，`.md` 报告，`.html` 走 `report_html` 单点、失败不拖垮报告） |
| **退出码** | `0` 出报告 · `2` 无 bar / 不可评估 · `1` 参数错 |
| **库导出** | `CandidateSpec` / `AdoptionRule` / `BASELINE_SPEC` / `DEFAULT_CANDIDATES` / `CANDIDATE_REGISTRY` / `DEFAULT_RULE` / `DEFAULT_ADOPTION_OUT_DIR` / `DEFAULT_WINDOW_COUNT` / `DEFAULT_WINDOW_YEARS` / `DEFAULT_WINDOW_WARMUP_DAYS` / `build_windows` / `slice_window` / `run_candidate` / `decide_adoption` / `evaluate_adoption` / `render_adoption_markdown` |

**payload 顶层键**：`ok` / `generatedAt` / `baseline` / `rule` / `windows` /
`candidates[]`（`name` / `label` / `summary` / `windows` / `decision`）/
`recommended[]` / `verdictCounts` / `metaKeys` / `environment`（`SIMULATE`）/
`liveTradingEnabled`（恒 `false`）/ `metricNote` / `adoptionNote` / `disclaimer`。

## 7. 采纳动作（本契约**之外**）

`adopt` 结论**只是建议**。把它写进生产默认档是**独立的人工签核步骤**（计划中的 `Y2`）：

1. 用 `--any-window` / 调阈值复核稳健性（**不得**为了凑 `adopt` 而先看结果改阈值）；
2. 人工签核 → 新增命名档案（`StrategyConfig` / 出厂闸门常量）；
3. 同步 ADR + 契约 + 权重的**单点定义**，并按既有流程打 tag。

**本模块不提供**「一键改默认档」的开关 —— 需求上就不该有。

## 8. 跳号与版本

- 本里程碑编 `v4.10.0`（minor，新能力），承接 `v4.9.1`（`T2`）；
  `v4.8.0`（`R5` ETF 进宇宙）仍因**生产侧 ETF 回补未完成**而顺延。
- `T3`（数据质量体检）原计划 `v4.10.0`，因 `Y1` 先落地而**顺延至 `v4.11.0`**。

## 9. 边界（本契约**不做**的事）

- **不改生产默认**：见 §7。
- **不做参数寻优**：本模块**评估**给定候选，**不**搜索最优旋钮（那是 `S3` 敏感性网格的职责）。
- **不做基准 alpha**：窗口胜负按 `sharpe` / 回撤 / 胜率等**自指标**裁决，不引入基准（避免把
  「跑赢基准」与「跑赢自己基线」两个问题混为一谈）。
- **不做生产侧回补**、**不做实盘**：承接 ADR 0058 只读与 `L1` 门禁。
