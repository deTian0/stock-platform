# 0096 — 午间休盘简报会话（`midday`）

- **状态**：Accepted
- **日期**：2026-11-07
- **相关**：ADR [`0083`](0083-digest-pre-post-and-secondary-pick.md) · [`0085`](0085-ohlc-multi-source-fallback.md) · 计划 [`../plans/midday-session.md`](../plans/midday-session.md)

---

## 背景

盘前（08:30）与盘后（15:30）已分文件（ADR 0083）。用户在 **11:30 午间休盘** 需要第三份只读简报：对照盘前推荐，看当日截至午休的开盘/现价/涨跌，不改选股截面。定时触发由用户自行安排；平台只提供手动 CLI。

## 决策

1. **会话值**：`session ∈ {pre, post, midday}`（ValidateSet）。未知值 fail-closed 回落 `pre`（与既有盘前默认一致）。标签：盘前 / 盘后 / 午间。
2. **文件名**：`{reportDay}-midday.md` / `.html`，另写 `latest-midday.*`；`{reportDay}.md` 与 `latest.md` 仍是「最后一次成功渲染」别名（与盘后相同规则）。**不删除**同日 `-pre` / `-post`。
3. **数据源**：仍读 brief 库唯一 `asof` 行（T-1 截面）；不新建 brief 主键、不改 picks / 命中 / 绩效 / 同花顺生产语义。
4. **行情**：午间默认取运行日分钟线（经 `em_get`），**仅候选池**——生产 picks + ②B `short_term.pool`（无 pool 则 `items`）+ 基准码。行形状仍用 `open` / `close`，其中 `close` = 当日已拿到的**最后一根分钟收盘**（现价），不是日线收盘。表头第二价列写 **现价**，避免与盘后「收盘」混淆。
5. **触发**：仅 `stock-platform-digest --session midday --run-date <报告日>`（及库函数等价参数）。**不**注册计划任务 XML / schtask。**增补（2026-11-09）**：由 WorkBuddy 自动化「stock-platform 午间简报」在工作日 11:30 触发 —— 仓外触发器，不进 `scripts/ops/*.xml`，仍可手跑同一条 CLI。
6. **失败**：分钟源失败 → 三列 `—` + 数据备注，digest 本身成功（fail-soft）。禁止用 `market.db` 日线冒充现价。

## 非目标

改 asof；开 live；默认启用分钟全市场抓取；把 midday 写入 hit_tracking 新 session_type；自动调度。

## 后果

**正面**：午休可复盘盘前推荐的盘中进度，与盘前/盘后文件并存。  
**代价**：分钟请求受东财限流；候选池外的票看不到现价；现价非官方「收盘」。
