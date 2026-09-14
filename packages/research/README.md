# packages/research

选股 / 回测研究内核。安装名：`stock-platform-research`。

## 状态

| 版本 | 能力 |
|------|------|
| **M3.1 / v0.3.1** | `score_lvrev` / gates |
| **M3.2 / v0.3.2** | `run_pit_long_only` + 防未来函数 |
| **M3.3 / v0.3.3** | `stock-platform-score` 批处理 CSV |
| **M24.1 / v1.16.1** | `load_universe` + `build_cross_section_panel`（ADR 0029） |
| **M25 / v1.18.0** | `build_premarket_brief` + `stock-platform-brief` |
| **M29 / v2.1.0** | `run_refresh` + `stock-platform-refresh` |
| **M32 / v2.4.0** | `performance` JSONL + `stock-platform-performance` |
| **M34 / v2.6.0** | 策略配置版本化 + `compare_strategy_configs` |

## 安装

```powershell
cd D:\workspace\git\stock-platform\packages\research
python -m pip install -e ".[dev]"
python -m pytest -q
```

## 来源

- `lvrev.py` / `gates.py` ← a-stock-engine `src/lvrev_scorer.py` + `apply_risk_gates`
- 权重锁定 W_DEFAULT / W_VALUE（engine v4.29）

## 约束

- 评分不得使用 `fwd_*` / `next_*` 等未来列（`assert_no_lookahead_columns`）
- 信号日与成交日分离：信号用 T 收盘特征，成交用 T+1 open
- 跨除权日比价前先经 `stock_platform_providers.apply_adjust`（M23）；本包不内嵌抓取
- 宇宙空列表 / 空文件 **fail-closed**（`UniverseEmptyError`）；截面经注入 provider，CI 零公网
- 日刷新 CLI 默认 `--provider replay`；live HTTP 不在本包内嵌

刷新：

```powershell
stock-platform-refresh --asof 2026-09-02 --universe fixtures\universe_cn_sample.json --out $env:TEMP\sp-refresh --provider replay --fixtures path\to\fixtures
```
