# ADR 0001：目标架构与吸收边界

- 状态：Accepted
- 日期：2026-09-13
- 决策者：项目初始化

## 背景

工作区存在多个相关仓（数据 Skill、选股引擎、工作台、多 Agent、ETF 执行审查快照等）。目标是收敛为 **单一产品仓** `stock-platform`，避免三套行情抓取与两套回测口径长期并存。

## 决策

1. **本仓为唯一演进主线**；上游仓只读参考，按里程碑迁入后归档。
2. **分层**：
   - `packages/providers`：统一 Vendor（A 股先，美港后）
   - `apps/workbench`：UI/监控/选股回测壳（契约对齐 tick-stock-panel）
   - 研报 Agent：插件，不内嵌 HTTP 抓取
   - 执行层：后期可选，默认纸面
3. **第一版（0.0.x–0.1.0）只搭架子与契约**，不迁业务代码。
4. **版本工程**：SemVer + annotated tag；大/小里程碑映射见 `docs/versioning.md`。

## 后果

- 正面：边界清晰；可小步打 tag；合并冲突面可控。
- 负面：短期内双轨（旧仓仍可用）；需纪律避免在旧仓继续扩东财路径。
- 禁止：把 Skill Markdown 内嵌代码直接当生产运行时；整仓复制进 monorepo 再不整理。

## 后续 ADR

- 0002：数据集字段与单位（**已 Accepted，M0.2**）
- 0003：providers 包与 normalize_symbol（**已 Accepted，M1.1**）
- 0004：daily/realtime 录制回放（**已 Accepted，M1.2**）
- 0005：东财限流 + 能力矩阵（**已 Accepted，M1.3**）
- 0006：工作台最小壳（**已 Accepted，M2.1**）
- 0007：fail-closed 与口径对齐（**已 Accepted，M2.2/M2.3**）
