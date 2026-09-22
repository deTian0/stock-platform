# M-A1：TradingAgents-astock 可移植清单

> **状态**：done（2026-09-17）  
> **硬约束**：[ADR 0009](../architecture/0009-agent-plugins.md) — Agent **无内嵌 HTTP**；数据强制 `packages/providers`。  
> **禁止**：并入 `tradingagents/dataflows/a_stock.py`、默认完整 LangGraph、Streamlit 第二 UI 主链。

---

## 1. 角色提示（可迁要点 → 平台配置/文档）

| 角色 | 上游路径 | 可移植要点（无 URL） | 依赖矩阵能力（映射） | 平台现状 |
|------|----------|----------------------|----------------------|----------|
| 市场/技术 | `analysts/market_analyst.py` | A 股涨跌停/T+1/量价；指标名白名单（≤8） | `daily`、`adj_factor`；（指标本地算） | 薄；确定性辩论未分角色深提示 |
| 情绪/社交 | `social_media_analyst.py` | 舆情口径；禁当实时成交 | `news`（有限） | 部分 |
| 新闻 | `news_analyst.py` | 事件时间窗；缺数据标缺失 | `news` | 部分 |
| 基本面 | `fundamentals_analyst.py` | 三表/估值；历史日须 PIT 或告警 | `financial`；未来 `pit_fundamentals`（ADR 0050） | 部分 |
| **政策** | `policy_analyst.py` | 政策层级/力度/时间窗框架 | `news`；候选 `announcements` | **未迁** |
| **游资** | `hot_money_tracker.py` | 量价异动、龙虎榜、板块轮动框架 | `fund_flow`、`lhb`、`sector_fund_flow`；候选 `concept_blocks`/`hot_reason` | **未迁** |
| **解禁** | `lockup_watcher.py` | 解禁类型/规模/减持新规核对清单 | `unlock`、`news`、`financial` | **未迁** |
| Bull / Bear | `researchers/*` | 对抗论点结构 | 同上聚合 | 有确定性辩论 |
| 风险三方 | `risk_mgmt/*` | 激进/中性/保守视角 | 同上 | 有 Risk 槽 |
| RM / PM / Trader | `managers/*`、`trader/` | 计划→仓位叙事 | 评级词表 | 薄 / 纸面 SIMULATE |

迁入方式：抽取为 `packages/agents` 内中文 system 片段或 YAML；**提示内禁止写死数据源 URL**。

---

## 2. 工具清单（语义 → 矩阵 resolve）

上游 `@tool` 仅作**能力语义**对照；平台实现必须 `resolve(cap)` / 注入 Provider，禁止直连 dataflows。

| 上游工具 | 建议矩阵能力 | 可迁？ | 备注 |
|----------|--------------|--------|------|
| `get_stock_data` | `daily` / `realtime` | 是 | 归一化走 `normalize_symbol` |
| `get_indicators` | （本地计算） | 是 | 无新 HTTP |
| `get_news` / `get_global_news` | `news` | 部分 | 全球资讯未矩阵化则 fail-closed |
| `get_fundamentals` / 三表 | `financial` | 是 | 非 PIT |
| `get_fund_flow` | `fund_flow` | 是 | |
| `get_dragon_tiger_board` | `lhb` | 是 | |
| `get_lockup_expiry` | `unlock` | 是 | |
| `get_industry_comparison` | 候选 `industry_rank` / 现有 `sector_fund_flow` | 部分 | 见 M-D1 |
| `get_concept_blocks` | 候选 `concept_blocks` | 待 M-D3 | |
| `get_hot_stocks` / `get_northbound_flow` / `get_profit_forecast` | 候选 / 暂缓 | 否（现矩阵） | 无能力则角色 fail-closed |
| `get_insider_transactions` | 无直接对应 | 暂缓 | 勿从 dataflows 偷运 |

---

## 3. 评级边界（高优先级对齐 → M-A2）

上游权威：`tradingagents/agents/utils/rating.py`。

| 项 | 内容 |
|----|------|
| 五档词表 | Buy / Overweight / Hold / Underweight / Sell |
| 中文映射 | 强烈买入/买入→Buy；增持→Overweight；持有/中性/观望→Hold；减持→Underweight；卖出/清仓→Sell |
| **边界铁律** | 英文评级词后用「不能延续成更长词」：`(?!\*{0,2}(?:[A-Za-z0-9_]|-(?=[A-Za-z0-9_])))`，**不要**枚举标点白名单 |
| 混排 | 「最终评级：Buy」须识别 |
| 误判后果 | 静默改写会污染记忆日志与绩效 |

平台现状：`packages/agents` 辩论多为 **Buy/Hold/Sell 三档**；LLM 回退宽松。  
**M-A2**：对齐解析 + 全矩阵边界测（对齐上游 `test_rating_value_boundary_matrix` 意图）；误判不得进绩效 JSONL。

绩效命名：继续以 `direction_accuracy` 为判断准绳（与 usable / TA 口径一致）。

---

## 4. 明确不迁

- `dataflows/a_stock.py` 及一切内嵌抓取。  
- 完整 7 Analyst LangGraph 默认化（M-A4 可选且非默认）。  
- Streamlit Web / CLI Rich 作为第二产品前端。  
- mootdx BESTIP 探测写用户配置等副作用逻辑。

---

## 5. 建议吸收顺序

1. M-A2：评级边界 + 测试矩阵。  
2. 提示增量：解禁 / 游资 / 政策（各角色声明所需 capabilities；缺则 fail-closed）→ M-A3。  
3. 更深可选 LLM 图 → M-A4。
