# ADR 0053：情报报告 ↔ 盘前 brief 对照（非替换）

- **状态**：Accepted
- **日期**：2026-09-23
- **相关**：MR-3 / MR-5 · [`docs/plans/market-report-dashboard-merge-milestones.md`](../plans/market-report-dashboard-merge-milestones.md) · [`docs/upstream/market-report-templates/README.md`](../upstream/market-report-templates/README.md) · ADR 0041（daily pipeline）

## 背景

Workbench 已有「今日推荐 / 向导」产物（`build_premarket_brief` → SQLite），以及
`#intel-report` 三类 HTML **只读配方**（来自 Skill 仓 market-report-dashboard）。
二者同属「盘前」语义，但数据链与产物形态不同；若不写清对照，易被理解成互相替换，
或误用 Skill WebSearch 结果写入 brief 库。

## 决策

### 1. 对照关系（并列，非替换）

| 维度 | 情报报告（模板 / Skill） | 平台 brief（今日推荐） |
|------|--------------------------|------------------------|
| 产物 | HTML 看板（机会/风险叙事） | 结构化 TopN picks + reasons |
| 数据主链 | 助手侧 Skill（常含 WebSearch） | `packages/providers` + 能力矩阵 |
| 截面键 | 报告日期（叙事日） | `asof` 交易日 + `universeTier` / symbols |
| 权威用途 | 盘面情报阅读 / 布局配方 | lvrev 打分推荐、绩效、纸面 |
| 落库 | **不得**写入 brief SQLite | `open_brief_repository` 权威存档 |

### 2. Workbench 联动（MR-3）

- 「情报报告」与「今日推荐 / 向导」提供**互相跳转**与 **asof / 宇宙对照提示**。
- 对照只读：展示同日 brief 摘要（若已落库）；**禁止**把预填/Skill 输出写回 brief 库。
- 缺同日 brief → 中文空态，不静默伪造 picks。

### 3. 平台数据预填（MR-5）

- 仅用已有能力：已存/可生成的 brief picks、`concept_blocks`（可选）、`ops` health、日历字段。
- 模板中无对应能力的字段（指数点位、涨跌停统计、隔夜美股、情绪阶段、新闻全文等）
  **保留 `{{占位符}}`**，并在 API 的 `missing` 列表用中文说明缺什么。
- **禁止**假数据静默填满；**禁止** `import` Skill 运行时；**禁止**平行 WebSearch 当行情主链。

## 非目标

- 用情报 HTML 替换 lvrev 今日推荐。
- `pip install` market-report-dashboard。
- 实盘 / M-E4。

## 后果

- ADR + Workbench UI/API 可点验；fail-closed。
- 预填预览为「部分填充 + 缺能力清单」，非完整 Skill 报告。
