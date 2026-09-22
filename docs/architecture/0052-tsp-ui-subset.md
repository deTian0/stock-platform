# ADR 0052：TSP UI 子集范围（M-U3）

- 状态：**Accepted**
- 日期：2026-09-22
- 里程碑：M-U3 → 首刀 M-U4

## 背景

能力域路线图要求：短期仍以 Workbench（FastAPI + Jinja2 / 原生 JS）为**唯一产品前端主链**；
tick-stock-panel（TSP）的图表 / 监控交互语义可按子集吸收，但禁止并行维护完整 React+Vite+ECharts SPA。

## 决策

### 1. 页面 / 能力白名单（子集）

| 允许吸收的语义 | 落地位置 | 说明 |
|----------------|----------|------|
| 近 N 日绩效 / accuracy 趋势监控 | `#recommend` 绩效条 + `#tsp-subset` | SVG/原生 canvas 迷你图；口径=`direction_accuracy` |
| 回测折线 / 摘要只读展示 | `#backtest` 折叠区 | 已有 walk-forward / rolling；可增量字段 |
| 策略对比扫读 | `#strategy-compare` | 已有；不迁 TSP screener 整页 |

### 2. 明确禁止（双主链红线）

- 整仓 merge TSP `frontend/` React SPA 或引入 Vite/ECharts 为第二发行前端。
- 同时宣称「Workbench + TSP 完整站」为双入口产品。
- 为子集引入 Polars/DuckDB 前端运行时。
- 改默认端口习惯以外的第二常驻 UI 服务（仍默认 3018 习惯）。

### 3. 技术约束

1. 数据仍经平台 `/api/*` + providers 能力矩阵；缺能力 fail-closed。
2. 首刀实现优先 **零新前端依赖**（原生 SVG / 少量 CSS）。
3. 维护边界：子集组件写在 `apps/workbench/static`；文档交叉链本 ADR + ROADMAP。
4. 产品定位不变：研究 + 纸面 SIMULATE Workbench。

### 4. 首刀选型（M-U4）

**近 N 日 `direction_accuracy` SVG sparkline**（监控语义），挂在 `#tsp-subset` 并复用
`/api/research/performance` 的 `recentDays[]`。非整仓图表库。

## 后果

- M-U4 可在 Accepted 后开工；超出白名单须新 ADR。
- usable / 能力域路线图「不做完整 SPA」叙事保持一致。
