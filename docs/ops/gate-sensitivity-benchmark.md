# 实测：闸门参数敏感性扫描（`S3`，2026-10-10）

> 真机 `market.db` 端到端复现记录。口径见 [`docs/contracts/gate-sensitivity.md`](../contracts/gate-sensitivity.md)；
> 决策见 ADR [`0062`](../architecture/0062-gate-parameter-sensitivity.md)。
> 数字**全部由 CLI 现场产出**，文档内不含估算值。

## 1. 复现命令

```powershell
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = 'D:\workspace\stock_trading\a-stock-engine\data_cache\market.db'
& $venv -m stock_platform_research.sensitivity_cli `
    --db $env:STOCK_PLATFORM_ENGINE_MARKET_DB `
    --start 2024-09-02 --end 2026-09-08 `
    --universe stock `
    --knobs reversal_q,min_pick_score,ma_band `
    --objective sharpe --tolerance 0.10
```

（等价的 console script：`stock-platform-strategy-sensitivity …`。省略 `--knobs` 即默认三旋钮全扫。）

## 2. 数据面

| 项 | 实测 |
|---|---|
| 库 | `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`（只读） |
| 窗口 | `2024-09-02` → `2026-09-08` |
| 加载（窗口内） | `rows=2,949,567` / `codes=6,799` |
| 过滤（丢 BSE 等） | `rows=2,949,361` / `codes=6,789` |
| 特征帧 | `rows=2,518,046` / `codes=5,303` / **`dates=489`** |
| universe | `stock` |
| 目标 / 容差 | `sharpe`（max）/ `0.10`（相对最优值） |
| 网格 | 三旋钮各 **5 点**（`DEFAULT_GRIDS`）→ 共 **15 次完整回放** |

> 特征帧**只构建一次**、跨 15 个网格点复用，因此点与点之间**只差旋钮**。

## 3. 逐点指标与判定

### 3.1 `reversal_q`（截面超卖分位）

| value | trades | sharpe | total_return | max_drawdown | calmar |
|---|---|---|---|---|---|
| 0.100 | 150 | **1.529** | 0.4222 | −0.1222 | 1.629 |
| 0.200 | 170 | 0.928 | 0.2524 | −0.1652 | 0.744 |
| 0.300 ← **默认** | 176 | 1.060 | 0.3029 | −0.1767 | 0.827 |
| 0.400 | 179 | 1.220 | 0.3620 | −0.1467 | 1.177 |
| 0.500 | 179 | 1.220 | 0.3620 | −0.1467 | 1.177 |

`verdict=**fragile**`｜`best=0.1`｜`robustRange=0.1–0.1 (1 点)`｜`stability=0.20`｜`monotonic=0`

### 3.2 `min_pick_score`（composite 分数下限）

| value | trades | sharpe | total_return | max_drawdown | calmar |
|---|---|---|---|---|---|
| 0.500 | 197 | **1.253** | 0.5628 | −0.2137 | 1.211 |
| 0.600 | 195 | 1.129 | 0.3754 | −0.2361 | 0.756 |
| 0.700 | 192 | 1.157 | 0.3859 | −0.2284 | 0.802 |
| 0.800 ← **默认** | 176 | 1.060 | 0.3029 | −0.1767 | 0.827 |
| 0.900 | 145 | 1.125 | 0.2780 | −0.1193 | 1.130 |

`verdict=**robust**`｜`best=0.5`｜**`robustRange=0.5–0.7 (3 点)`**｜`stability=0.60`｜`monotonic=0`

### 3.3 `ma_band`（距均线拒绝下限，越**大**越严）

| value | trades | sharpe | total_return | max_drawdown | calmar |
|---|---|---|---|---|---|
| 0.880 | 184 | 1.473 | 0.5025 | −0.1470 | 1.589 |
| 0.900 | 185 | **1.843** | 0.6567 | −0.1184 | 2.510 |
| 0.930 ← **默认** | 176 | 1.060 | 0.3029 | −0.1767 | 0.827 |
| 0.960 | 156 | 1.194 | 0.3149 | −0.1785 | 0.849 |
| 0.980 | 149 | 1.498 | 0.3840 | −0.1406 | 1.297 |

`verdict=**fragile**`｜`best=0.9`｜`robustRange=0.9–0.9 (1 点)`｜`stability=0.20`｜`monotonic=0`

## 4. 总判

```
overall = fragile
robust   = ['min_pick_score']
fragile  = ['reversal_q', 'ma_band']
flat     = []
```

**结论（避免过拟合单点）**：

- **`min_pick_score` 稳健**：`0.5–0.7` 三个**相邻**网格点的 sharpe（1.253 / 1.129 / 1.157）
  都在最优值 10% 容差内 → 这是一个**高原**，该旋钮不存在孤峰依赖；窗口内把分数下限放在
  0.5–0.7 区间，结果对大方向不敏感。
- **`reversal_q` / `ma_band` 脆弱**：两者都只有**最优点本身**落在容差内，相邻点立即劣化 →
  该"最优值"**不可信**，**不得**据以把出厂值调成 `0.1` / `0.9`。
- **默认档恰好都不在孤峰上**：`reversal_q=0.30`（sharpe 1.060）、`ma_band=0.93`
  （sharpe 1.060，**全网格最差**）、`min_pick_score=0.80`（1.060，也在稳健区间外）。
  三者都不该"照最优值调"——这正是 `fragile` 判定要拦下的动作。
- 换一个 objective（如 `calmar` / `total_return`）**不改变** `reversal_q` 的孤峰结论，
  因为 `0.1` 在多数目标上都是离群高点；这也**不**等于"应该调到 0.1"。

## 5. 关键观察（录制）

| 观察 | 含义 |
|---|---|
| `reversal_q=0.40` 与 `0.50` 的指标**完全相同**（179 笔 / sharpe 1.220） | 网格在高位**饱和**（该窗口内超卖分位提高到 0.4 以上不再改变入选集）；单调性因此判 0 |
| `min_pick_score` 越高**成交越少**（197→145），但 sharpe 非单调 | 分数下限同时压缩了笔数与波动；高原特征来自"少而稳"与"多而散"的折中段 |
| `ma_band` **默认 0.93 是全网格最差点** | 出厂带宽在本窗口**不是**局部最优；但邻域是孤峰结构 → 只诊断、不据此改档 |
| `0.90 → 0.93` 一步把 sharpe 从 1.843 打到 1.060 | 带宽是**硬拒绝**阈值，对 `close/ma` 分布的尾部极敏感 |

## 6. 耗时

| 项 | 实测 |
|---|---|
| 端到端（3 旋钮 × 5 点 = 15 次回放，489 交易日窗口） | **182.7 s** |
| 单次完整回放（含 2.52 M 行特征帧） | ≈ **11 s 量级** |
| 加载（窗口内 2.95 M 行，只读流式扫） | ≈ 13 s 固定量级 |

> 复杂度线性于「网格点数 × 窗口长度」；`feats` 复用使每点只付**回放**成本。

> 非投资建议。本报告只做**诊断**：`fragile` 表示"该最优值不可信"，
> **不**触发任何出厂参数改动（`reversal_q=0.30` / `ma_band=0.93` / `min_pick_score=0.80` 逐位不变）。
