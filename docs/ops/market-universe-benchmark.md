# 全市场宇宙实测（X1）

> 实测日期：2026-10-10｜目标 tag：`v4.0.0`
> 契约：`docs/contracts/market-universe.md`｜ADR：`docs/architecture/0055-market-universe.md`
> 本机：i7-12700KF / 31.8 GB RAM / Windows（家机）；数据库读盘为内置 D 盘

所有数字由 `stock-platform-market-universe` 现场产出，**不是估算**。复现命令见 §4。

---

## 1. 被测对象

| 项 | 值 |
|---|---|
| `market.db` 路径 | `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db` |
| 文件大小 | **3.14 GB** |
| `daily_price` 行数 | **8 771 037** |
| 日期范围 | 2020-01-02 … 2026-09-08 |
| distinct code（全表） | 6 974（含历史遗留裸码形态，归一后更少） |
| 挂载方式 | 只读（`file:...?mode=ro`） |

---

## 2. 枚举实测（asof = 2026-09-03，窗口 120 自然日）

| 配置 | 代码数 | 耗时 | 峰值内存（tracemalloc） |
|---|---|---|---|
| `stock` + 排除 BSE（默认） | **5 227** | **0.208 s** | **1.04 MB** |
| `asset_type=all` | 5 241 | 0.202 s | 1.04 MB |
| `min_bars=60` | 5 194 | 0.200 s | 1.03 MB |
| `include_bse=True` | 5 227 | 0.201 s | 1.04 MB |

`counts` 明细（默认档）：`source=5241 → normalized=5241 → asset_matched=5227 → final=5227`。

要点：

- **枚举本身几乎不要钱**（0.2 s / 1 MB）—— 成本全在下游 panel / 回测。
- `include_bse` 与默认**完全一样**：这份 `market.db` **不含北交所数据**（无 `.BJ` 后缀码）。排除规则是为将来保留的，当前实际过滤 0 个。
- `all` 比 `stock` 多 14 个 = ETF / 场内基金（`51xxxx` 等），与 B4 资产分类一致。

### 2.1 为什么 SQL 必须走日期窗口

| 写法 | 耗时 |
|---|---|
| `GROUP BY SUBSTR(code,-2)`（对 code 做表达式 → 全表扫描） | **5.12 s** |
| `WHERE date BETWEEN ? AND ? GROUP BY code`（走 `idx_dp_date`） | **0.15 s** |

差 34 倍。`list_symbols` 因此只用日期窗口聚合，BSE / 6 位 / 裸码合并全部在 Python 侧做完。

---

## 3. 单日 PIT panel 实测（`build_cross_section_panel`）

| 规模 | 输入代码 | 输出行 | 耗时 | 峰值内存 |
|---|---|---|---|---|
| 抽样 | 500 | 499 | 2.03 s | 47.4 MB |
| **全市场** | **5 227** | **5 209** | **23.0 s** | **498.8 MB** |

- 5227 → 5209：**18 只在 asof 当日没有 bar**（停牌 / 退市边缘），被 PIT 严格口径剔除，属预期。
- 全市场单日 panel ≈ **23 s / 0.5 GB**，可以放进每日盘前调度（08:30 档）而不至于卡住；窗口拉长或叠加回测时按线性放大估算。
- 与 skill 记录的历史口径一致：Workbench 端点「加载 ≈13 s 固定 + 回测随窗口」。

---

## 4. 复现

```powershell
$py = 'D:\workspace\stock_trading\stock-platform\.venv\Scripts\python.exe'
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = 'D:\workspace\stock_trading\a-stock-engine\data_cache\market.db'
Set-Location D:\workspace\stock_trading\stock-platform

# 枚举（摘要）
& $py -m stock_platform_research.market_universe_cli --asof 2026-09-03
# 枚举 + 单日 panel 实测
& $py -m stock_platform_research.market_universe_cli --asof 2026-09-03 --probe-panel
```

---

## 5. ⚠️ 数据覆盖缺陷（重要，影响每日选股）

按交易日统计 `daily_price` 的当日代码数：

| 日期 | 当日有 bar 的代码数 |
|---|---|
| 2026-09-08 | **14** |
| 2026-09-07 | **14** |
| 2026-09-04 | **14** |
| 2026-09-03 | 5 223 |
| 2026-09-02 | 5 223 |
| 2026-08-07 | 5 305 |

**自 2026-09-04 起，日线覆盖从 ~5.2k 只塌到 14 只** —— 引擎侧导入在 9/3 之后中断（或只导入了个别标的）。

后果与处置：

- **宇宙枚举不受影响**：`list_symbols` 用 120 天窗口统计，9/4 之后仍能列出 ~5.2k 只。
- **单日 panel / 选股会几乎空**：PIT 要求 asof 当日有 bar，落到 9/4 之后只会得到 14 只 → 榜单形同虚设。
- 因此**每日选股的 `asof` 必须落在覆盖区内**（当前最后可用交易日 = **2026-09-03**）；`X3`（命中追踪）与 `X4`（选股↔回测闭环）开工前应先修引擎侧导入，否则闭环拿到的是残缺横截面。
- 这不是平台代码缺陷，`market.db` 属 a-stock-engine（已归档仓）资产，平台只读。

---

## 6. 结论

| 结论 | 依据 |
|---|---|
| 全市场宇宙（5.2k 只）在现有硬件上**可直接日用** | 枚举 0.2 s；单日 panel 23 s / 0.5 GB |
| 成本瓶颈是**下游 panel / 回测**，不是宇宙 | 枚举占比 < 1% |
| 当前库**无 BSE 数据**，排除规则当前过滤 0 个 | `include_bse` 结果一致 |
| 覆盖尾部断裂（≥2026-09-04）会毁掉选股当日横截面 | §5 |
