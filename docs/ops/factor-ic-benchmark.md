# 实测：因子 IC/ICIR 与正交准入（`S2`，2026-10-10）

> 真机 `market.db` 端到端复现记录。口径见 [`docs/contracts/factor-library.md`](../contracts/factor-library.md)；
> 决策见 ADR [`0061`](../architecture/0061-factor-library-admission.md)。
> 数字**全部由 CLI 现场产出**，文档内不含估算值。

## 1. 复现命令

```powershell
$env:STOCK_PLATFORM_ENGINE_MARKET_DB = 'D:\workspace\stock_trading\a-stock-engine\data_cache\market.db'
& $venv -m stock_platform_research.factors_cli `
    --db $env:STOCK_PLATFORM_ENGINE_MARKET_DB `
    --universe stock --horizon 20 --sample-every 5 --min-names 30 `
    --correlation --json
```

（等价的 console script：`stock-platform-factor-ic …`。）

## 2. 数据面

| 项 | 实测 |
|---|---|
| 库 | `D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`（只读） |
| 加载 | `rows=8,875,338` / `codes=6,983` |
| 过滤（丢 6 位脏码等） | `rows=8,875,132` / `codes=6,973` |
| universe | `stock`（排除 BSE） |
| horizon | 20 交易日 |
| 采样 | `sample_every=5` → **324 个采样截面** |
| `min_names` | 30 |

## 3. 判定表（`nDates=324`）

| factor | label | mean_ic | ICIR | n_dates | 判定 |
|---|---|---|---|---|---|
| `low_vol` | 低波动 | −0.0970 | −0.4783 | 319 | **ENABLED**（基线） |
| `reversal` | 短期反转 | −0.0681 | −0.4288 | 320 | **ENABLED**（基线） |
| `long_reversal` | 6 个月反转 | **+0.0328** | **+0.1976** | 300 | **ENABLED**（新增） |
| `illiq` | Amihud 非流动性 | **+0.0770** | **+0.7976** | 320 | **ENABLED**（新增） |
| `max_ret` | 极端收益 MAX | −0.0938 | −0.5721 | 320 | **disabled**（过 IC/ICIR，但**冗余**） |

**结论**：

- 新增因子中 **2 个启用**（`long_reversal` / `illiq`）→ 满足验收「≥2 个正交因子」。
- `max_ret` 的 IC 与 ICIR 都很强（|IC| 0.094 / |ICIR| 0.572，且符号与意图一致），
  但**正交性不过** → 记冗余、**不启用**（"不达标不启用" 的第二类不达标）。

```
enabled   = ['low_vol', 'reversal', 'illiq', 'long_reversal']
redundant = ['max_ret']
rejected  = []
```

## 4. 因子相关矩阵（Spearman）

|  | low_vol | reversal | long_reversal | max_ret | illiq |
|---|---|---|---|---|---|
| **low_vol** | 1.000 | 0.108 | −0.134 | **0.876** | −0.222 |
| **reversal** | 0.108 | 1.000 | 0.079 | 0.335 | −0.051 |
| **long_reversal** | −0.134 | 0.079 | 1.000 | −0.074 | 0.187 |
| **max_ret** | **0.876** | 0.335 | −0.074 | 1.000 | −0.224 |
| **illiq** | −0.222 | −0.051 | 0.187 | −0.224 | 1.000 |

- `long_reversal` 与两个基线的 |ρ| 都 ≤ 0.134 → **真正交**（且是"跳过最近一月"的独立窗口）。
- `illiq` 与所有因子的 |ρ| ≤ 0.224 → **正交**。
- `max_ret` 与 `low_vol` 相关 **+0.876 ≥ 0.70** → 判冗余。

## 5. 关键取舍（录制）

| 观察 | 处理 |
|---|---|
| A 股 12-1 动量 IC 实测**为负**（−0.030，与"动量正"的直觉相反） | 改按**长期反转**命名 `long_reversal`、方向声明 `+1`；符号一致性闸门通过 |
| `max_ret` 与 `low_vol` 高度共线（0.876） | 交由**正交约束**拦下 → 冗余不启用（不靠人工剔除） |
| `pandas.corr(method="spearman")` 需要 `scipy`（未装） | `factor_correlation` 改 `frame.rank().corr()` |

## 6. 耗时与内存

- 加载（8.88 M 行全表流式扫，只读）≈ **13 s 固定**（与 `market.db` 其它端点同量级）；
  特征构建 + 324 截面 IC ≈ **数十秒**量级，随窗口增长。
- 因子计算全部在 pandas 内完成，无逐码 Python 循环。

> 非投资建议。本报告仅用于研究：`enabled` 只表示"有资格进组合"，
> 新因子在 lvrev 中的**权重仍为 0**（`W_DEFAULT` 逐位不变）。
