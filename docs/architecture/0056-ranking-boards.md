# ADR 0056：榜单体系对齐（X2）

- 状态：Accepted
- 日期：2026-10-10
- 关联：`docs/contracts/rankings.md`、ADR 0055（X1 全市场宇宙）

## 背景

`X1` 把宇宙扩到全市场之后，brief 只有一个扁平的 `picks[]`（TopN），而生产引擎 `a-stock-engine`
实际产出的是**五类榜单**：②A 质量榜 / ②B 短线榜 / ③A 持仓 / ③B 操作建议 / ③C 观察名单。
两套语义并存会让「平台 brief」与「引擎日报」对不上号，也无法表达持仓与减仓。
`X2` 要求对齐这套榜单语义并**口径文档化**。

约束（延续既有红线）：

- 不得新增第二套可操作规则 —— 退出 / 冷静期 / 偏差的唯一定义是 `rules`（B5）。
- 不得让 `picks` 语义漂移（DB 存档、绩效日志、intel-report 都依赖它）。
- 缺持仓必须 fail-closed，绝不臆造一本书。

## 决策

1. **新增单点 `research.rankings`**：`build_rankings(scored, *, holdings, config, panel, asof, gated)`
   是榜单切分的唯一定义；`RankingConfig` 是档位参数的唯一定义。
2. **`picks` 语义不动**：`build_premarket_brief` 现在对**全量**评分截面切榜单，
   再 `head(top_n)` 生成 `picks` —— ②A 头部与旧 `picks` 逐位一致，老消费方零迁移。
3. **③B 完全委派 B5**：调用 `review_positions()`（与回测同一 `rules`），只收 `exit` / `trim`，
   `reason` 原文透传。
4. **有意差异：不复制引擎的中位数卖出规则**。引擎 ③B 的「评分低于截面中位数 ⇒ 减仓」是启发式，
   平台已有 B5 规则单点；再写一条就是第二套可操作来源。故该口径**降级为 ③A 行上的只读标记
   `belowMedian`**（信息，不是指令）。
5. **`min_composite_score` 值域隔离**：平台 `composite_score` 是 `[0,1]` 分位合成值，
   引擎是百分制 `60`。契约里显式写明「禁止照抄 60」，默认 `0.0`（关闭）。
6. **持仓未过闸门也要列**：③A 若只取「过闸门 ∩ 持仓」，会把已持有的票整只丢掉
   （实测：2 只标的截面下 600519 被闸门过滤 → 持仓榜空）。现改为：过闸门的带分数与截面排名，
   未过闸门的从 panel 补一行（`composite_score=null` + 中文说明）。**持仓是既成事实，不因买点闸门消失。**
7. **②B 的同源保证**：`entry_ok` 列存在时优先取；不存在时池本身已是「过闸门」集合（
   `apply_entry_gates` 已过滤），退化为按分取并记账说明 —— 绝不回到引擎旧版「买强」动量逻辑。
8. **接线**：`build_premarket_brief(holdings=...)` → `run_daily_pipeline(holdings=...)` →
   `stock-platform-daily --holdings`；新增 `stock-platform-rankings` CLI（panel CSV + 持仓 JSON →
   md / csv / json）；Workbench `/api/research/brief?holdingsPath=`（默认 `STOCK_PLATFORM_HOLDINGS_PATH`，
   复用 `position_review_cli.load_holdings` 这一唯一读取器）+ `#recommend` 页榜单区块。
9. **测试零网络**：research 侧合成截面 / fake 持仓；apps 侧 replay fixtures + 临时 book JSON。

## 后果

- brief 的 JSON 变大（③C 23 行 × reasons）。存档 SQLite 与绩效日志照旧，暂无体积红线；
  若日后成为问题，应加 `rankings=false` 开关而不是悄悄截断榜单。
- ③A 的「未过闸门持仓」行没有 `composite_score`，任何按分排序的消费方必须容忍 `null`。
- 未配置 `STOCK_PLATFORM_HOLDINGS_PATH` 时 ③A / ③B 恒空 —— 这是设计，不是缺陷；
  UI 已在区块说明里写明。
- 与既有红线无关：`L1` 未立项前不触碰 `liveTradingEnabled`。

## 备选方案（已否决）

| 方案 | 否决理由 |
|---|---|
| 把引擎 `categorize()` 直接搬进平台 | 会引入第二套退出/减仓判断（与 B5 冲突），并复制 `min_composite_score` 的百分制假设 |
| 只加 ②A/②B，持仓留给持仓复核页 | 日报口径仍对不上；③A/③B 正是「持仓与减仓建议」的验收项 |
| 让 `picks` 直接变成五榜嵌套 | DB 存档 / 绩效日志 / intel-report 都依赖 `picks` 为扁平 TopN，破坏面过大 |
| ③A 只取「过闸门 ∩ 持仓」 | 实测会把真实持仓丢空（见决策 6） |
