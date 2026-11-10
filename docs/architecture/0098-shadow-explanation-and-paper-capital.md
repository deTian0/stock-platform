# 0098 — 影子说明、卖出费用口径、模拟盘 2 万本金

- **状态**：Accepted
- **日期**：2026-11-10
- **相关**：ADR [`0093`](0093-multi-strategy-shadow-board.md)（影子链）· [`0081`](0081-concrete-order-sizing.md)（③B 可执行委托）· [`0096`](0096-midday-digest-session.md)（midday 会话）· [`0097`](0097-holdings-single-source-and-post-close.md)（持仓单一真源）

---

## 背景

审计（2026-11-10）确认三处缺口，都是「数据已有、展示或默认值没接上」：

1. **影子附录只回答「谁」，不回答「为什么」。** `final_board_{asof}.json` 里已有 `trigger` / `expectation` / `invalidation` / `reasonSource`、各校 `status` + `reason`、`round2.rejected` 及淘汰理由，但 `digest_hook.render_shadow_board_appendix` 只渲染 `代码/名称/学校/得分/持有期` 五列。读者看不到 S1 为何空池（择时关闭）、16 进 2 的硬闸淘汰了谁。
2. **③B 的「金额」是毛额。** `position_sizing.plan_orders` 不引用任何成本模型，卖出 5,050 元在表上就是 5,050 元，但实际到账要扣佣金与印花税。费用定义 `portfolio.CostModel` 早已存在且是 SSOT，只是没接上呈现层。
3. **模拟盘本金是 100 万。** `paper_cabin.DEFAULT_CASH` = `broker._cash` = `MockThsTransport(cash=)` = 1,000,000，与用户实际小账户（约 1.1 万）差两个数量级，模拟结论不可迁移。全仓无 20,000 这个数。

## 决策

1. **影子附录扩写为三段**（`shadow_board/digest_hook.py`，三份报告同源生效）：
   - `### Round1 · 各校入池`：每校 `status` / 入池数 / `reason`（`reason` 缺失时回退 `profile.trend`），`retired` 标「（已下线）」，`advisoryOnly` 标 advisory；
   - `### Round2 · 硬闸淘汰`：`入闸 N / 过闸 M` + 每只 `代码/名称/学校/淘汰原因`；
   - `### 入选席位`：逐席 `触发（为什么选）/ 预期 / 失效（何时承认选错）/ 理由来源`。
   - 仍 **fail-closed**：快照缺失、JSON 损坏、非 dict 一律返回 `[]`，整段省略，绝不补位。表格单元格统一 `_cell()` 转义（换行→空格、`|`→`\|`）。
2. **③B 拆「毛额 / 费用 / 净额」三列**：`plan_orders` 新增 `cost_model` 参数（缺省 `portfolio.CostModel()`），每笔委托补 `fee` / `netAmount`，汇总补 `totalFee` / `totalNetAmount` / `costModel`。费用一律走 `CostModel.costs()`，**不新增第二套费率定义**。
3. **模拟盘本金 20,000**：新增 `broker.DEFAULT_PAPER_CAPITAL = 20_000.0` 作为唯一定义；`paper_cabin.DEFAULT_CASH` 与 `MockThsTransport` 默认 `cash` 均引用它。
4. **`PaperBroker` 增加可选 `cost_model`（duck-typed）**：`None` ⇒ 零费用，保持 ADR 0098 之前的全部行为；注入后 `_apply_fills` 按 `costs()` 扣现金并累计 `total_fees`。`research.CostModel` 天然满足该协议，故执行层不 import 研究层，也不复制常量。

## 非目标

- 不改 `W_DEFAULT` / `min_pick_score` / 出厂 picks。
- 不改 `CostModel` 的费率数值（佣金万 0.854、印花税万 5、ETF 免、免 5）。
- 不改 `compute_metrics(initial_capital=50000)` —— 那是回测口径，与本 ADR 的模拟盘本金是两回事。
- 不建「每日自动开仓/平仓的模拟盘账本」。`PaperBroker` 仍是手动/命令驱动；日常三份报告只出费用列，不出模拟净值曲线。
- 不动 `_apply_fills` 的 `avg_price` 口径（仍不摊入买入费用）。

## 后果

- 影子链从「结果表」变成「可复核的筛选过程」，S1 空池、集中度硬闸淘汰这类判断第一次进了报告。
- ③B 的金额第一次与实际到账一致；ETF 与股票的费用差额在表上可见。
- 模拟盘默认本金与小账户同量级，仓位换算不再被 100 万摊薄到无意义。
- 遗留：`PaperBroker` 的 `avg_price` 不含买入费用，持仓成本会略低于真实；`AccountSnapshot` 无费用字段，只能读 `total_fees`。二者留待需要时另开 ADR。
