# 0081 — ③B 操作建议必须给出可执行数量（股数 / 金额）

- Status: Accepted
- Date: 2026-10-23
- Supersedes: —
- Related: ADR 0068（绩效 PnL 闭环）、ADR 0070（日用循环自足）、ADR 0078（亏损归因）

## 背景

③B 操作建议长期只输出一句 `stop_loss(-12.3%)`，**没有股数、没有金额**，读者无法据此下单。
2026-10-23 用户直接质疑：「操作建议怎么回事，应该给出具体的，加仓多少，减仓多少。」

排查后是三层问题叠加，不是某一处漏算：

| # | 环节 | 位置 | 问题 |
|---|------|------|------|
| 1 | 规则层 | `rules.evaluate_exit` | 返回 `reason + ret_pct + held_days`，**不含仓位概念** |
| 2 | 规则开关 | `rules.py` `DriftPolicy.band` 默认 `None` | 偏差规则**默认禁用**；且账本无 `target_weight` ⇒ `evaluate_drift` 恒 `hold`，trim/add 结构性不可能触发 |
| 3 | 组装层 | `rankings.build_rankings` ③B 分支 | 只挑 `action/reason/ret_pct/deferred/asset_class/score/rank`，把账本的 `qty / available_qty / weight / market_value` **全部丢弃** |

第 1 层是**刻意的**：同一套规则要服务回测，回测自带股本书，规则本身必须与仓位无关，
否则两条路径会漂移（见 `test_position_review.py` 的差分测试）。所以**不能**在 `rules.py` 里补数量。

第 2 层暴露的是另一件事：③B 为空时的提示语写「B5 规则（退出/冷静期/**偏差**）未对当日持仓触发
exit/trim」——其中偏差规则**是被禁用**，不是「未触发」。措辞会让人误判「检查过且没命中」。

## 决定

**在呈现侧新增一层折算**：`position_sizing.plan_orders(book, review)` 把复核裁决翻译成
整手取整的委托。`rules.py` / `backtest.py` **一行不改**，回测口径零影响。

数量只有两个来源，优先级从高到低：

| 来源 | 触发 | 数量 |
|------|------|------|
| `exit` 裁决 | 止损 / 移动止损 / 长持上限 | 卖出**全部可卖**股数（`available_qty`，缺失回退 `qty`） |
| 单票上限 `cap_weight`（默认 **20%**） | 复核后权重仍 > 上限 | 按 100 股整手 `ceil` 减到上限以内 |

补充规则：

- **`exit` 优先于 `trim`**：同时满足时全清，不是只减到上限。
- **`available_qty` 是硬约束**：今日买入（T+1）卖不掉的部分记为 `unsellable`，不假装能卖。
- **永不产生 `add`**：账本只有一个现金数字、没有组合目标权重，
  任何买入数量都只能拍脑袋。宁可不给，也不给编的。
- 无价格的行**跳过**，不猜（fail-closed，与 `review_positions` 的 `pending` 同精神）。

### 落点

| 位置 | 作用 |
|------|------|
| `position_sizing.py` | 新增纯函数模块（无 I/O、无 pandas），唯一折算入口 |
| `rankings.build_rankings` | ③B 条目补 `suggestQty / suggestAmount / weightPct / weightAfterPct / heldQty / availableQty`；「复核 hold 但超上限」也会补一条 `trim` |
| `rankings` 返回体 | 新增 `positionSizing`（capWeight / lot / totalValue / orders / counts / totalAmount） |
| `daily_digest._rankings_section` | ③B 表改为「动作 / 卖出数量 / 参考价 / 金额 / 权重」五列 |

## 影响

- **选股口径不变**：②A/②B/③C 与 `asof` 口径完全不动，变的只是 ③B 的可执行性。
- **回测不变**：`rules.py`、`backtest.py` 未触及；`DriftPolicy.band` 仍默认 `None`。
- **权重分母**取**账本市值合计**（不含现金），因为 `load_holdings` 只返回行、不返回 `account`。
  与总资产口径的差异是现金占比（本例 0.09pp），不改变整手结果。
- 边界不变：仍 **SIMULATE**、`liveTradingEnabled=false`、非投资建议。

## 验证

- `packages/research/tests/test_position_sizing.py` —— 8 条不变量：exit 取可卖数、
  不超 `available_qty`、超上限减到上限内且整手、`exit` 胜过 `trim`、
  **永不产生 add**、无价跳过、`total_value` 覆盖生效。
- 真机（2026-10-23 盘前）：③B 由 `stop_loss(-15.1%)` 一行变为
  `000533 退出 900 股 @8.670 = 7,803.00`、`588080 退出 400 股 @1.299 = 519.60`，合计 8,322.60 元。

## 未做（明确留白）

- 账本层面的 `target_weight` 与对称 drift（跌到目标以下补仓）：需要先定组合级目标权重口径，
  且必须带现金约束，否则会对着 14.93 元可用资金喊「加仓」。
- ETF 行情缺口：`market.db.daily_price` 里 588080 只到 2026-03-13，价格只能取账本快照，
  ⇒ ③B 的 ETF 结论**依赖人工更新账本**。这是数据侧问题，不属于本 ADR。
