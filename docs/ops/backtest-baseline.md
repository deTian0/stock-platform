# 回测基线报告（B1）

> **状态**：done（2026-10-09）｜**目标 tag**：`v3.13.0`
> **引擎**：`packages/research/src/stock_platform_research/backtest.py`
> **数据**：`a-stock-engine/data_cache/market.db`（只读，3.14 GB）
> **命令**：`stock-platform-backtest --start 2020-01-01 --end 2026-09-08 --out curve.csv`
> **口径**：SIMULATE｜`liveTradingEnabled=false`｜非投资建议
> **性能补强（2026-10-09）**：加载器优化，全周期 **106 s → 65 s**，指标逐位不变（见 §5 #5）

---

## 1. 为什么要做 B1

平台原有回测内核 `pit.run_pit_long_only` 是**每日全换仓**的骨架：每个交易日重新选 top-N、等权持有 **1 天**。
它能回答"信号排序有没有信息量"，但**回答不了"一个真实账户长什么样"**——没有持仓周期、没有费用、没有持仓状态。
`portfolio.py` 也只有 3 个指标（回撤 / 换手 / 终值）。

B1 在**同一套内核**（`lvrev.score_lvrev` + `gates.apply_entry_gates`）之上补齐了组合层与指标层。

---

## 2. 引擎能力（新增 `backtest.py`）

| 能力 | 说明 |
|---|---|
| 持仓状态 | 每仓 entry price / shares / running peak |
| 持有期 | `min_hold`（默认 45 天）约束主动卖出；`max_hold_days` 安全上限 |
| 风控 | 硬止损 `-8%`、目标止盈 `+5%`、趋势破位（MA20≤MA60）、移动止损（自高点 -6%，且曾盈利≥2%） |
| 仓位 | 最大并发 `15` 仓、等权、100 股取整 |
| 现实性约束 | **跌停卖不掉→顺延**；**涨停买不进→跳过**；停牌持有顺延 |
| 费用 | 佣金 **万0.854 双边**（免5）；印花税 **万5 仅卖出**；**ETF 免印花税**——与 `local_backtest.py` 逐值对齐 |
| 指标 | 年化 / 最大回撤 / 夏普 / 索提诺 / Calmar / 换手 / 胜率 / 平均持有 |

**参数默认值逐一对齐 `a-stock-engine` v4.31**：`MAX_PICKS_PER_DAY=8`、`MAX_POSITIONS=15`、`MIN_HOLD=45`、`STOP_LOSS=8.0`、`TARGET_BASE=5.0`、`TRAIL_STOP_PCT=6.0`、`REVERSAL_Q=0.30`、`MIN_PICK_SCORE=0.80`。

---

## 3. 基线结果（2020-01-02 ～ 2026-09-03）

**样本**：1618 个交易日 / 6964 只标的（全市场，已排除北交所）/ 初始 50,000 元

| 指标 | 值 |
|---|---|
| 总收益 | **+90.24%** |
| 终值 | 95,117.64 |
| 年化（CAGR） | **+10.53%** |
| 最大回撤 | **-17.14%** |
| 夏普 | **0.751** |
| 索提诺 | 0.722 |
| Calmar | 0.615 |
| 交易笔数 | 630 |
| 胜率 | **46.2%** |
| 平均持有 | 35.4 天 |
| 年换手（笔/年） | 98.1 |

### 分年收益

| 年 | 收益 |
|---|---|
| 2020 | +29.35% |
| 2021 | +28.06% |
| 2022 | **-10.40%** |
| 2023 | +0.64% |
| 2024 | +14.77% |
| 2025 | +14.05% |
| 2026（至 9/3） | **-7.42%** |

### 卖出原因分布（630 笔）

| 原因 | 笔数 | 占比 |
|---|---|---|
| 止损 | 251 | 39.8% |
| 目标止盈 | 222 | 35.2% |
| 趋势破位 | 120 | 19.0% |
| 移动止损 | 34 | 5.4% |
| 持仓上限 | 3 | 0.5% |

单笔净收益区间 **-15.21% ～ +82.03%**；无 >100% 或无 <-20% 的离群值。

---

## 4. 与 `a-stock-engine` 的一致性对照

| 项目 | 本基线（平台） | 引擎 `local_backtest.py` |
|---|---|---|
| 打分内核 | `lvrev` W_DEFAULT（vol 0.5 / rev 0.5） | 同（v4.29 canonical） |
| 闸门 | `apply_entry_gates` | 同源 |
| 费用 | 万0.854 / 万5 / ETF 免 | 同 |
| 持有期 | min_hold 45 | MIN_HOLD=45 |
| 宇宙 | 全市场 6964 码（排除 BSE） | 全市场（含 survivors/ST 过滤） |
| 区间 | 2020-01 ～ 2026-09（6.7 年） | 样本内全期 |
| **总收益** | **+90.24%** | **+23.05%**（lvrev mh45 样本内） |
| 夏普 | 0.751 | 0.34 |
| 最大回撤 | -17.14% | 11.2% |

**对照锚点（引自 `empirical/BASELINE.md` 与 `walk_forward_oos_result.json`）**：

- 引擎生产基线 = **path-C 行业轮动 tilt，OOS 几何 +53.24%**
- 引擎 walk-forward OOS calibration：+57.47% / CAGR 7.66% / MDD 19.72% / 夏普 0.52 / 胜率 34.4% / 平均持有 **5.1 天**
- **`BASELINE.md` §5 方法论铁律**：比较回测必须"同策略 + 同样本 + 同权重 + 同持有期"，跨口径横比是误读。

### 差异解释（逐条，不对齐处不掩盖）

1. **持有期口径不同（主因）**：本基线 `min_hold=45` → 平均持有 35.4 天、年换手 98 笔；引擎 OOS 台平均持有 **5.1 天**、6.2 年 10280 笔（≈1658 笔/年）。低换手 = 少成本 + 让盈利跑久，两者收益不可直接比。
2. **区间不同**：本基线 2020-01 起；引擎 calibration 为 6.2 年（约 2020-05 起）。
3. **L0 市场闸门**：引擎有宽基 MA200 + 估值分位的熊市闸门，本基线未启用（`regime=None`）→ 未做系统性回撤压制。
4. **ST / 生存者偏差**：引擎有 ST 黑名单与 `_compute_survivors`（排除上市<1 年新股）；本基线仅有 BSE 与基金前缀过滤。
5. **复权处理（本基线更干净）**：引擎用未复权 `close` 计算盈亏，**除权日会产生假亏损**；本基线用 `pct_chg` 重建复权价。

> **结论**：方向一致（低波反转 long-only、正收益、夏普 0.3–0.75 量级），**差异全部可归因于口径**。不宣称"复现引擎数字"。

---

## 5. 过程中发现并修复的数据 / 性能问题

| # | 问题 | 证据 | 处置 |
|---|---|---|---|
| 1 | **`close` 未复权** | `600551.SH` 单日 close 跳变 **-32.6%**，而同日 `pct_chg` 仅 -10%（涨跌停内）→ 该笔被记为 -36.24% 止损 | `compute_features` 用 `pct_chg` 重建复权价贯穿特征与盈亏；修复后极端值归零 |
| 2 | **`pct_chg` 标度混用** | 主流记录为小数（`0.1006` = 10.06%），异常记录为百分数（`99.SZ` = `-1.37`） | 按中位数量级自动判标度；`|pct|` 截断 ±60% |
| 3 | **闸门 `iterrows` 过慢** | 全市场 1621 天 × ~5400 码 ≈ **880 万次** `iterrows`，全周期回测 >120 s 被命令超时 kill | `apply_entry_gates` **向量化**（逐行循环每个分支都是"拒绝"，等价于"任一条件命中即拒绝"）；全周期回测 **200 s → 106 s** |
| 4 | **脏 code** | 6974 个 code 中 **1520 个**非标准（`159001`、`99.SZ`、`1.SZ`） | 基金/ETF 前缀（1/5）过滤；BSE（`.BJ` / 4/8 前缀）过滤 |
| 5 | **加载器 `WHERE date BETWEEN` 反而更慢** | 同一全周期窗口实测：`WHERE` + `ORDER BY code,date` **54.9 s**；`ORDER BY date`（走索引）50.6 s；不排序 + pandas 排序 52.8 s；**全表流式读 + 内存过滤仅 12.5 s** | `load_engine_bars` 改为**全表 `SELECT` + 内存内过滤/排序**（表只有 `idx_dp_date`，投影列迫使回表，索引帮不上忙）。全周期回测 **106 s → 65 s**（load 11.5 s + 回测 48.6 s），指标逐位不变；语义由 `tests/test_backtest_cli.py` 锁定 |

**向量化等价性**由 `packages/research/tests/test_gates.py` 用原逐行实现作为 oracle 证明（12 组随机数据 + 缺列场景，逐一比对）。

---

## 6. 已知限制（未做，不掩盖）

- **成交价 = 当日收盘价**：`market.db` 无 open/high/low，与引擎 `get_price_on_date` 同口径；**非 T+1 开盘成交**。
- **未启用 L0 熊市闸门**：需要宽基指数序列 + 估值分位，`regime` 参数已预留（调用方可注入）。
- **无 ST / 退市黑名单**：`fundamentals.name` 未接入。
- **无生存者偏差校正**：未按"上市满 1 年"过滤。
- **单进程 Python 循环**：1618 天 **65 s**（加载 11.5 s + 回测 48.6 s，2026-10-09 优化后）；扩到分钟级或大批量参数扫描仍需再优化或拆批。

---

## 7. 复现

```powershell
cd D:\workspace\stock_trading\stock-platform
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:/workspace/stock_trading/a-stock-engine/data_cache/market.db"

# 全周期基线
.\.venv\Scripts\stock-platform-backtest.exe --start 2020-01-01 --end 2026-09-08 --out curve.csv

# 测试（引擎 + 闸门等价性）
$env:STOCK_PLATFORM_PROVIDER_PRESET = "replay"
.\.venv\Scripts\python.exe -m pytest packages/research/tests/test_backtest.py packages/research/tests/test_gates.py -q
```

---

## 8. 下一步

- **B2 组合指标补全**：`research/portfolio.py` 扩展口径文档化并入 `docs/contracts/`
- **B3 费用模型配置化**：佣金/印花税/滑点做成配置项并与 `local_backtest.py` 互测
- **B4 ETF 支持**：混池净值报告
- **B5 回测↔在线规则统一层**：冷静期 / 退出条件 / 持仓偏差单点定义 + 双路调用（承接本报告 §3 的卖出原因表）
- **B6 可视化**：`#backtest` 面板净值曲线 + 回撤带
