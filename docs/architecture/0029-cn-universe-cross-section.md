# ADR 0029：CN 宇宙 + PIT 日截面面板

- 状态：Accepted
- 日期：2026-09-14

## 背景

M3 已交付 `score_lvrev` / 闸门 / PIT 回测内核，但评分输入仍依赖外部 CSV。
产品稳定阶段需要平台内可复现的「宇宙 → as-of 截面」链路，且必须经能力矩阵
providers，禁止平行抓取。

## 决策

1. **宇宙**：`load_universe` 读 config/fixtures（JSON 列表或 `{"symbols":[...]}`）；
   归一化为 6 位 A 股代码；**空宇宙 fail-closed**（`UniverseEmptyError`）。
2. **截面**：`build_cross_section_panel(asof, …)` 注入 `daily` provider（或
   `get_daily` callable）；按 lookback 拉历史日 K，严格要求 as-of 当日有 bar。
3. **特征**：`vol20` / `rev_chg`(≈20d) / `ma20` / `ma60` / `trend_up` / `rs20`，
   供 `score_lvrev` + `apply_entry_gates` 直接消费。
4. **可选**：注入 `adj_factor` + `apply_adjust` 后再算特征；注入 `fund_flow`
   时附加最新 as-of 净流入列（缺省不失败）。
5. **输出**：pandas DataFrame，可 `panel_to_csv`；无 HTTP、CI 零公网。
6. **不做**：全市场自动扩宇宙、后台落盘、默认 live、实盘、LLM/SPA。

## 后果

- 盘前简报 / 今日推荐可复用同一 PIT 面板。
- 调用方必须在 workbench 侧 `resolve("daily")` 后再注入；矩阵不可用则 409。
