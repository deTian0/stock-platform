# global-stock-data：美港符号语义摘要

> **只读归档** · 归档日：2026-09-22  
> **来源**：`../global-stock-data/SKILL.md`（符号 / Yahoo / 新浪格式节）  
> **平台权威**：`MarketStrategy`、`normalize_symbol`、[`../contracts/market-strategy.md`](../contracts/market-strategy.md)、[`../contracts/datasets.md`](../contracts/datasets.md)  
> **刻意不吸收**：期权 Greeks、SEC/FINRA 深水区、HKEX CCASS 抓取（见 Skill 合规分级）。

## 符号格式（对照）

| 市场 | Yahoo | 新浪（示例） | 东财 SECUCODE（示例） |
|------|-------|--------------|------------------------|
| 美股 | `AAPL` | `gb_aapl` | `AAPL.O` / `BABA.N` |
| 港股 | `0700.HK` | `rt_hk00700` | `00700.HK` |

平台侧：美港 live 经 `GlobalHttpProvider`（Yahoo + 新浪等）；默认 CI 仍 `global_replay`。  
薄缺口与排除项：[`../ops/m-d5-global-thin-gap.md`](../ops/m-d5-global-thin-gap.md)。

## 合规提醒（摘录）

- Yahoo 等多为 personal use；商业用途须自核条款。  
- Skill 明确**不提供** HKEX CCASS 自动抓取代码。  
- 本仓不把 Skill 当 pip 依赖；软链见 [`../ops/skills-governance.md`](../ops/skills-governance.md)。
