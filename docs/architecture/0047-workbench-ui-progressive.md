# ADR 0047：Workbench 日用 UI 渐进披露

- 状态：Accepted
- 日期：2026-09-14

## 背景

M45 已加 IA + 一键向导，但面板仍全部平铺：行情工具 / 运维矩阵 / 实验区与
日用路径（向导、推荐）抢注意力；推荐结果偏表+原始 JSON，理由难扫读。

## 决策

1. **主流程置顶**：`#wizard` / `#recommend` / `#paper` / `#broker` 常开；主流程标 pill。
2. **次级折叠**：行情工具、运维与能力、实验区用 `<details>` 分组；锚点跳转时自动展开祖先。
3. **推荐卡片**：`#recommend-cards` 展示 symbol / score / close / `reasonSummary` + `reasons[]` chips；表与 JSON 保留（JSON 默认折叠）。
4. **结构化扫读**：向导步骤条、运维/纸面/broker 键值、矩阵可用 pill、绩效 stat 条、辩论 rounds；JSON 仅调试用。
5. **不做**：SPA、图表库、实盘开关、改 API 契约。

## 后果

- 日用扫读更快；既有 API 与测试锚点 id 保留；视觉延续青绿金融工具风，非营销紫渐变。
