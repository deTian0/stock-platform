# 实测：行业中性化 A/B（`S4`）

> **复现时间**：2026-10-10　**机器**：家里台式机（i7-12700KF / 31.84 GB / Windows）
> **契约**：[`docs/contracts/industry-neutralization.md`](../contracts/industry-neutralization.md)　**ADR**：[`0063`](../architecture/0063-industry-neutralization.md)
> **数据**：只读 `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`（3.38 GB）
> **口径**：SIMULATE；不进每日推荐主路径；非投资建议。

---

## 1. 复现命令

```powershell
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = "D:\workspace\stock_trading\a-stock-engine\data_cache\market.db"
# 运行 1：仅行业中性化（无暴露上限）
python -m stock_platform_research.neutralization_cli `
    --start 2024-09-02 --end 2026-09-08 --min-group-size 5
# 运行 2：中性化 + 每行业候选上限 3
python -m stock_platform_research.neutralization_cli `
    --start 2024-09-02 --end 2026-09-08 --min-group-size 5 --max-per-industry 3
```

等价 HTTP：`POST /api/research/strategy/neutralization`（body 同名 camelCase 参数）。

---

## 2. 数据面

| 项 | 实测值 |
|----|--------|
| 窗口 | 2024-09-02 → 2026-09-08 |
| 交易日 | **489** |
| `daily_price` 载入 | **2,949,567** 行 / 6,799 码 |
| BSE 过滤后 | 2,949,361 行 / **6,789** 码 |
| `fundamentals.industry` | **5,228** 码 / **111** 个细分行业 |
| 参数 | `mode=demean` / `rescale=rank` / `min_group_size=5` / `composite_demean=True` / `style=()` |
| 耗时 | 两轮合计 **95.9 s**（含两次全量载入 + 4 次账本回放） |

---

## 3. 运行 1：仅行业中性化（`maxPerIndustry=None`）

| 指标 | 原始（`raw`） | 中性化（`neutral`） | `delta = neutral − raw` |
|------|--------------:|--------------------:|------------------------:|
| `total_return` | 0.3029 | **0.5257** | **+0.2228** |
| `cagr` | 0.1461 | **0.2432** | **+0.0971** |
| `max_drawdown` | **-0.1767** | -0.2673 | -0.0906（**更深**） |
| `sharpe` | 1.0599 | **1.1430** | **+0.0831** |
| `win_rate` | **0.4659** | 0.3839 | -0.0820（**更低**） |
| `n_trades` | 176 | 224 | +48 |
| `avg_hold_days` | 35.22 | 30.00 | -5.22 |
| `final_equity` | 65,146.49 | **76,287.46** | **+11,140.97** |

`winner = neutral`（`nIndustries=111`，`industryAvailable=true`）。

### 行业暴露画像（各臂「持有过的全部码」等权）

| 臂 | 选股数 | 行业数 | 最大行业权重 | 最大行业 | HHI |
|----|-------:|-------:|-------------:|----------|----:|
| `raw` | 180 | 73 | 0.0500 | 建筑工程 | **0.0225** |
| `neutral` | 201 | 66 | 0.0746 | 电气设备 | **0.0302** |

---

## 4. 运行 2：中性化 + 每行业候选上限 3

| 指标 | 原始（`raw`） | 中性化（`neutral`） | `delta` |
|------|--------------:|--------------------:|--------:|
| `total_return` | 0.3029 | **0.5850** | +0.2821 |
| `cagr` | 0.1461 | **0.2679** | +0.1218 |
| `max_drawdown` | -0.1767 | -0.2423 | -0.0657 |
| `sharpe` | 1.0599 | **1.2492** | +0.1893 |
| `win_rate` | 0.4659 | 0.3955 | -0.0704 |
| `n_trades` | 176 | 220 | +44 |
| `final_equity` | 65,146.49 | **79,249.78** | +14,103.29 |

| 臂 | 选股数 | 行业数 | 最大行业权重 | 最大行业 | HHI |
|----|-------:|-------:|-------------:|----------|----:|
| `raw` | 180 | 73 | 0.0500 | 建筑工程 | 0.0225 |
| `neutral` | 196 | 65 | 0.0765 | 电气设备 | 0.0312 |

> `raw` 臂两轮完全一致（逐位相同），是「两臂只差处理项」的直接证据。

---

## 5. 观察（**按证据说话，不据孤点改档**）

1. **中性化在这段窗口里是「高收益 / 高波动」的交换**：收益 +22.3 pp、夏普 +0.083，但回撤从 -17.7% 加深到
   -26.7%、胜率从 46.6% 掉到 38.4%。**不是单调改善**。
2. **「行业中性化」并不等于「更分散」**：持仓集合的 HHI 反而从 0.0225 升到 0.0302（运行 2：0.0312）。
   原因是中性化后**各行业内部的相对排序**成了主导，反而让少数行业的头部反复入选。
   这正是「必须实测、不能靠直觉」的例证。
3. **候选上限是有效的补充**：`max_per_industry=3` 在收益 / 夏普上优于纯中性化（0.5850 vs 0.5257 /
   1.2492 vs 1.1430），回撤也更浅（-24.2% vs -26.7%），但 HHI 仍高于原始臂。
4. **成交更密**：中性化臂笔数 176 → 224（+27%）、平均持有 35.2 → 30.0 天。换手上升，成本敏感性
   建议用 `--slippage-bps` 复跑（`B3` 已支持）。
5. **出厂权重与闸门不动**：`W_DEFAULT`、`min_pick_score=0.80`、`EntryGateParams()` 全部**逐位未改**。
   `S4` 只交付「可表达 + 可对照」，改档须另立里程碑并做样本外验证。

---

## 6. 已知局限

| 项 | 说明 |
|----|------|
| 单一窗口 | 仅 2024-09-02 → 2026-09-08（489 日）；未做滚动 / 样本外（`walkforward` 未接）。 |
| 风格仅 `vol20` | size / value 需 join `daily_basic_pit`，本里程碑未接（契约 §10）。 |
| 暴露口径 | `exposure` 是**持仓集合**等权画像，非逐日权重加权；不能作风险归因。 |
| `min_group_size=5` | 成员 < 5 的行业保持原值（不中性化）；换值即换口径，跨值不可横比。 |
| 空帧怪癖 | `prepare_book_frame(空 frame)` 返回 **0 列** frame（`compute_features` 既有行为，仅 `.empty` 判据有效）；`attach_industry` 已加空帧守卫。 |
