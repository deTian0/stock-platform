# B3：费用与摩擦模型对齐（里程碑方案）

> **状态**：**done（2026-10-09）** — 已发布 `v3.13.3`
> **目标 tag**：`v3.13.3`（B 域第 3 块；`B1`·`B2` 已 done）
> **前置**：`B1`（回测基线 `v3.13.0`）、`B2`（指标权威层 `v3.13.2`）
> **量级**：**S**（≤1–2 人日）
> **上游约束**：不改写 [`trading-system-roadmap.md`](trading-system-roadmap.md) §3.2 的域边界；费用口径须与 `a-stock-engine/local_backtest.py` 对齐（红线 8：`B5` 前回测不得作为策略取舍唯一依据，故本刀只做**口径可信**，不做策略调优）。

---

## 0. 一句话

把费用与摩擦从**散落的模块级常量**收成**一个可配置的 `CostModel`**，补齐**滑点**这一当前完全缺失的摩擦项，并用**互测**锁死本平台与 `a-stock-engine` 两个引擎的费率一致——默认档（滑点=0）必须让 B1 基线**逐位不变**。

---

## 1. 现状对照（两线费用模型）

| 项 | `stock-platform` · `research/backtest.py` | `a-stock-engine` · `local_backtest.py` | 判定 |
|----|-------------------------------------------|----------------------------------------|------|
| 佣金（双边） | `DEFAULT_COMMISSION_RATE = 0.0000854` | `COMMISSION_RATE = 0.0000854` | **一致** |
| 印花税（卖出侧） | `DEFAULT_STAMP_SELL_RATE = 0.0005` | `STAMP_SELL_RATE = 0.0005` | **一致** |
| ETF 免印花 | `is_etf()` → `_ETF_PREFIXES` 前缀表 | `_is_etf()` → 前缀 | 数值一致，**前缀表未互测** |
| 最低佣金（免5） | 无（纯比例 = 免5 语义） | 无 | **一致**（华宝 万0.854 免5） |
| **滑点** | **无** | **无** | 两线**都缺** |
| 成本归零开关 | 无 | `--zero-cost`（置 `COMMISSION_RATE=STAMP_SELL_RATE=0`） | 平台缺 |
| 函数参数化 | `trade_cost(commission_rate=, stamp_sell_rate=)` + `run_portfolio_backtest(...)` 已暴露两参数 | 模块级全局 + CLI `--zero-cost` | 平台**函数可配、CLI 不可配** |
| 买入侧计费口径 | **硬用 `commission_rate`**（建仓 `px*(1+commission_rate)`；`cost_basis` 同上）**未走 `trade_cost()`** | `_trade_cost(code, is_buy=True)` 统一入口 | **平台存在不对称** |

**结论**：费率数值两线已对齐，缺口集中在 **①滑点缺失 ②配置化不足 ③买入侧绕过统一计费 ④无互测护栏**。

---

## 2. 缺口清单

**P0（本刀必做）**

1. **无滑点** —— 回测把成交价等同于收盘价，系统性高估收益（当前基线 `+90.24%` 未含摩擦）。
2. **买入侧绕过 `trade_cost()`** —— 建仓与 `cost_basis` 直接乘 `(1+commission_rate)`。当前因 ETF 与股票买入佣金相同而数值无害，但**一旦引入滑点或分品种费率即漏计**，是隐性缺陷。
3. **配置化不足** —— 默认值写死在模块顶层、CLI 无参数；无法不改代码做成本敏感性。
4. **无互测** —— 两线费率"看起来一致"靠人眼，无断言护栏。

**P1（建议）**

5. ETF 前缀表与引擎 `_is_etf()` 对齐并互测（`B4` 会深挖 ETF 语义，本刀先对齐常量）。
6. 口径契约 `docs/contracts/cost-model.md`：定义各字段语义、单位、默认值、与账户实际的对齐关系。

**P2（可选）**

7. 成本敏感性对照：滑点 0 / 5 / 10 bps 的成绩与成本拖累量化，回填 `docs/ops/backtest-baseline.md`。

---

## 3. 设计：`CostModel`

单一权威对象，落在 `research/portfolio.py`（与 `B2` 指标权威层同址，继续为 `B5` 单点定义铺路）。

```python
@dataclass(frozen=True)
class CostModel:
    commission_rate: float = 0.0000854   # 万0.854 免5，双边
    stamp_sell_rate: float = 0.0005      # 万5，仅股票卖出
    slippage_bps: float = 0.0            # 单边滑点(基点)；默认 0 = 与 B1 基线一致
    min_commission: float = 0.0          # 单笔最低佣金(元)；0 = "免5"（无门槛）
    etf_stamp_exempt: bool = True        # ETF/场内基金免印花

    def trade_cost(self, code, *, is_buy: bool) -> float: ...     # 比例成本（含最低佣金折算逻辑预留）
    def fill_price(self, px: float, *, is_buy: bool) -> float: ...  # 滑点后成交价
    @classmethod
    def zero(cls) -> "CostModel": ...      # 对标引擎 --zero-cost
```

**兼容性铁律**

- `trade_cost(code, *, is_buy, commission_rate=, stamp_sell_rate=)` 的**现有签名与默认值保持不变**（薄包装到 `CostModel`），`backtest.py` 的 `DEFAULT_*` 常量继续 re-export。
- `run_portfolio_backtest(...)` 保持现有 `commission_rate` / `stamp_sell_rate` 参数可用；**新增** `slippage_bps=0.0` / `min_commission=0.0`，默认值保证零回归。
- 滑点语义：**只改成交价，不改策略信号**（止损 / 目标 / 均线判定仍用参考收盘价），并在文档与 docstring 中显式声明。

---

## 4. 子任务拆分

| ID | 任务 | 交付物 | 验收 |
|----|------|--------|------|
| **B3.1** | `CostModel` 落地 `portfolio.py` + `trade_cost`/`fill_price`/`zero()` | 代码 + 单测 | 现有 `trade_cost` 语义逐位不变（4 象限：股票/ETF × 买/卖） |
| **B3.2** | 滑点贯穿买卖两侧；**修复买入侧绕过 `trade_cost()`** | 代码 | 建仓 / 平仓 / `cost_basis` 三处均走统一计费；滑点=0 时逐位不变 |
| **B3.3** | CLI 暴露 `--commission-rate` / `--stamp-sell-rate` / `--slippage-bps` / `--zero-cost` | `backtest_cli.py` | 4 个参数生效且有 CLI 测锁定 |
| **B3.4** | 两线互测：断言平台 `CostModel.trade_cost` 与引擎 `_trade_cost` 数值一致 | 新增测试 | 股票/ETF × 买/卖的合规费率与非佣金项（印花）逐项相等 |
| **B3.5** | 口径契约 `docs/contracts/cost-model.md`；全周期回归 + 敏感性对照 | 文档 + 基线回填 | 默认档指标逐位不变；滑点 0/5/10 bps 对照入 baseline |

---

## 5. 验收标准

- [ ] **零回归**：默认档（`slippage_bps=0`）全周期指标**逐位不变** —— `total_return 0.902353` / `cagr 0.105348` / `max_drawdown -0.171435` / `sharpe 0.7511` / `n_trades 630` / `win_rate 0.4619`。
- [ ] **滑点生效**：`slippage_bps=10` 时收益低于默认档，且差额可归因于摩擦（成本拖累量化）。
- [ ] **口径统一**：平台 `CostModel.trade_cost` 与引擎 `_trade_cost` 四象限 + ETF 互测通过。
- [ ] **配置化**：CLI 四参数可用，`--zero-cost` 等价于 `CostModel.zero()`；均有测。
- [ ] **契约**：`docs/contracts/cost-model.md` 落地并被 `check_docs` 覆盖。
- [ ] **门禁**：`check_docs.ps1` + `check_versions.ps1` 双绿；`pytest packages apps`（replay）全绿。
- [ ] **发布**：`v3.13.3` 收口（CHANGELOG + VERSION 11 处 + 路线图 B3 标 done + `release_tag.ps1` + `push --follow-tags`）。

---

## 6. 回归与验证方案

1. **数值护栏**：`slippage_bps=0` 跑全周期，与 `docs/ops/backtest-baseline.md` 的 B2 基线**逐位对拍**（脚本化，不靠肉眼）。
2. **互测方式**：引擎侧常量是模块级全局且被 `--zero-cost` 以 `global` 覆写，互测**静态读常量 / 复刻纯函数**，不实例化 `LocalBacktest`（避免依赖 `market.db` 与实例状态）。
3. **敏感性对照**：滑点 0 / 5 / 10 bps 三档各跑一次，产出「换手 × 摩擦 = 成本拖累」表格。
4. **单测范围**：`test_backtest.py`（费率 4 象限 + 滑点价）、`test_backtest_cli.py`（4 参数 + zero-cost）、新增 `test_cost_model.py`（`CostModel` 语义与 `zero()`）。

---

## 7. 风险与坑

| 风险 | 说明 | 应对 |
|------|------|------|
| 滑点污染信号 | 若把滑点写进 `entry_price` 会影响止损/目标判定 | 明确「滑点只改成交价」；判定用参考价，成交用滑点价，docstring + 契约双声明 |
| 买入侧改动引入回归 | 买入改走 `trade_cost()` 后数值可能变 | 当前 ETF 与股票买入佣金相同 → 数值不变；用「逐位不变」护栏锁定 |
| 互测依赖引擎 DB | 实例方法需 DB 与全局状态 | 只读常量 + 复刻纯函数，不实例化 |
| 最低佣金语义歧义 | 「免5」= 无最低门槛，非「5元封顶」 | 契约文档显式定义；`min_commission=0` 即免5 |
| 基线报告口径漂移 | 新档数字混入旧基线 | 基线报告分「默认档（零回归）」与「含摩擦对照档」两节，互不覆盖 |

---

## 8. 后续排队（非本刀）

| 顺序 | 里程碑 | 与 B3 的关系 |
|------|--------|--------------|
| 下一刀 | **B4** ETF 与资产类型支持 | 复用 B3 的 `etf_stamp_exempt` 与 `is_etf()` 前缀一致性 |
| 之后 | **B5** 回测↔在线规则统一层 | 承接 B2（指标）+ B3（费用）的单点定义，是**关键路径** |
| 收尾 | **B6** 回测可视化扩展 | 依赖 B2 指标；净值曲线 + 回撤带 |

---

## 9. 参考（只读）

- 平台：`packages/research/src/stock_platform_research/{backtest.py, backtest_cli.py, portfolio.py}`
- 引擎：`a-stock-engine/local_backtest.py`（`COMMISSION_RATE` / `STAMP_SELL_RATE` / `_trade_cost` / `_is_etf` / `--zero-cost`）
- 基线：`docs/ops/backtest-baseline.md`；指标口径：`docs/contracts/portfolio-metrics.md`
- 路线图：`docs/plans/trading-system-roadmap.md` §3.2 / §6 红线 8
