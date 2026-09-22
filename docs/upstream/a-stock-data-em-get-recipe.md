# a-stock-data：东财优先级与 `em_get` 配方摘要

> **只读归档** · 归档日：2026-09-22  
> **来源**：`../a-stock-data/SKILL.md`（约 V3.8.0；「数据源优先级 & 东财防封」章）  
> **平台权威实现**：`packages/providers` 的 `em_get` / [`../contracts/eastmoney-http.md`](../contracts/eastmoney-http.md)  
> **勿当运行时**：完整端点与内嵌代码仍在 Skill 仓；本仓禁止平行抓取。

## 优先级原则

| 优先级 | 数据源 | 封 IP 风险 | 典型用途 |
|--------|--------|-----------|----------|
| 1 | mootdx（通达信） | 不封 | K 线、五档、财务快照 |
| 2 | 腾讯财经 | 不封 | 实时价、估值快照 |
| 3 | 新浪 / 巨潮 / 同花顺 | 低 | 三表、公告、一致预期 |
| 4 | 东财 | **有风控** | 仅独有数据（资金流、龙虎榜、解禁、板块等） |

行情 / K 线 / 实时价能从 mootdx 或腾讯拿到的，不应默认打东财。

## 防封铁律（平台已落地）

1. **串行，不并发**东财请求。  
2. 间隔 ≥ 1s + 随机抖动；批量调大到 1.5～2s（`EM_MIN_INTERVAL`）。  
3. 复用 HTTP 会话（Keep-Alive）。  
4. 正常 UA；禁止裸 `requests.get` 打 `*.eastmoney.com`。  
5. 失败熔断 fail-closed（平台另有 `EM_CIRCUIT_*`）。

社区实测：绕过 `em_get` 高并发可导致 `push2` 系列 IP 级封禁数十小时；`datacenter-web` 子域可能仍可用——**不得**据此另开第二主链。

## 与本仓的关系

- 能力矩阵与缺口对照：[`../plans/m-d1-capability-gap-matrix.md`](../plans/m-d1-capability-gap-matrix.md)  
- 批量配方回馈：[`../ops/m-d6-batch-recipe-upstream-feedback.md`](../ops/m-d6-batch-recipe-upstream-feedback.md)  
