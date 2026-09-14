# 上游参考仓归档说明

> 状态：**Accepted（M7）**  
> `stock-platform` 是唯一产品仓。下列仓库仅作历史参考 / 配方来源，**不得**再作为并行运行时或第二数据主链。

## 总表

| 上游仓 | 本地路径（典型） | 吸收进平台的内容 | 平台权威位置 | 归档建议 |
|--------|------------------|------------------|--------------|----------|
| tick-stock-panel | `../tick-stock-panel` | Provider 契约语义、能力矩阵七项、fail-closed | `docs/contracts/*`、`apps/workbench` | README 标注「参考；新功能只进 stock-platform」 |
| a-stock-data | `../a-stock-data` | 东财节流配方、字段语义 | `packages/providers`（`em_get`） | Skill/服务可只读保留；禁止平行抓取 |
| global-stock-data | `../global-stock-data` | US/HK 符号与日/实时字段语义（Skill，非 pip） | `MarketStrategy`、`GlobalReplayProvider`、`datasets.md` | **勿整仓搬** 期权/SEC/FINRA |
| a-stock-engine | `../a-stock-engine` | lvrev / 闸门 / PIT 口径 | `packages/research` | 引擎仓冻结新功能；缺陷优先修平台 |
| TradingAgents-astock | `../TradingAgents-astock` | 多角色研报思路（去内嵌抓取） | `packages/agents` | 完整 LangGraph 可选参考；数据必须经 providers |
| V2-code-review | `../V2-code-review-20260905` | 执行安全结论（新鲜度/事务/草稿激活/paper-only） | `packages/execution` | 审查快照只读；不吸收 Futu/凭据 |
| finance-quant-skills | `../finance-quant-skills` | 技能文档 | （不进运行时） | 文档仓；不安装为依赖 |

## 红线（产品期仍生效）

1. **一条数据主链**：东财流量只走 `em_get`；禁止各包裸 URL。
2. **能力矩阵权威**：缺能力 fail-closed（409），禁止静默降级到未知源。
3. **市场策略分表**：CN / US / HK 不得混用 T+1 / 涨跌停假设。
4. **执行默认纸面**：`SIMULATE` + `liveTradingEnabled=false`；无实盘开关。
5. **上游只读**：新需求默认在本仓开里程碑；上游 PR 仅当「配方回馈」且需双写说明。

## 未迁入（刻意延期）

| 能力 | 原因 |
|------|------|
| live HTTP 默认开启 | `astock_http`（M8）与 `global_http`（M9）均已接线；**CI / 默认偏好仍 replay** |
| TradingAgents 完整 LLM 辩论图 | M12 已提供确定性轻量辩论；完整 LangGraph/LLM 仍可选后续 |
| 券商实盘 / OpenD | M6 明确不吸收 |
| US/HK 官方假日 API 运行时拉取 | M13 已固化静态表（2024–2027）；不拉 NYSE/HKEX API |
| 半日市 / 多市场纸面默认非 CN | M14 已接 CN/US/HK timing（默认仍 CN）；半日市不建模 |
| UI SPA / 完整前端 | M11 已提供最小单页操作台；React/图表库仍延期 |
| 分钟/板块资金流、全市场龙虎榜/全市场解禁、`full_minute`、`adj_factor` | M20 已交付个股 `financial`；分钟/板块资金流、全市场龙虎榜与全市场解禁、`full_minute`、`adj_factor` 仍延期 |

## 维护动作（可选，人工）

在各上游 README 顶部增加指向本仓的归档横幅，例如：

```markdown
> **归档提示**：产品开发已收敛至 sibling 仓 `stock-platform`（本文件权威清单见该仓 `docs/upstream-archive.md`）。本仓仅作参考实现 / 配方来源。
```

本文件是平台侧权威清单；上游是否改 README 不阻塞 `v1.0.0`。
