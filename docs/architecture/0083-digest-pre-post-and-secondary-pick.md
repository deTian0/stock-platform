# 0083 — 盘前 / 盘后简报分文件，二次精选只做展示

- Status: Accepted
- Date: 2026-10-28
- Supersedes: —
- Related: ADR 0049（brief 仓库）、ADR 0071（报告 HTML）、ADR 0079（两处都带 `-PrevSession -SettleAfter`）、
  ADR 0081（③B 可执行数量）、ADR 0082（A6 日线缓存形状与 000905 个股警告）

## 背景

08:30 与 15:30 共用同一条流水线参数（ADR 0079）。asof 都是 T-1，因为当日 bar 要等 18:30 回补才进 `market.db`。两份简报的差别只应是**展示用 session** 和**运行日行情**，不是两个选股截面。

读者需要：盘前回答「今天买什么」且行情列留空；盘后补上运行日开、收和自算涨跌；②A / ②B 各用一套展示规则做二次精选；③B 在股数之外写清可卖数量。这些都是呈现，不改评分、不改 `picks`、不改仓位建议。

## 决定

### 1. 流水线参数不动，只加展示参数

`daily` 与 `postmarket` 仍是 `-MarketDb -PrevSession -SettleAfter -Digest`。在此之上：

- 08:30 加 `-Session pre`，15:30 加 `-Session post`。任务 XML 与 `Invoke-ScheduledRun.ps1` 预设必须同时带上，因为计划任务直接调 `Invoke-DailyPipeline.ps1`。
- 包装脚本在 `-PrevSession` 把 `$Asof` 改成 T-1 **之前**记下 `$RunDate`，传给 daily CLI 与 digest CLI 的 `--run-date`。
- digest CLI 接收 `--session` 和显式 `--run-date`。两者都缺时 session 按 `pre`，行情列是 `—`，并写数据备注「未提供运行日，未取行情」。禁止用 `date.today()` 充当运行日。
- `hit_tracking.session_type` 仍为 `pre_market`。

### 2. brief 仍是一行一个 asof

`daily_briefs.asof` 保持 `UNIQUE(asof)`。工作台、A6、同日对照和 digest 都按「一个 asof 一行」读取。盘前与盘后各留磁盘文件，不改主键。

后一次写入覆盖库里的 `payload`（含 `session` / `runDate` / `quoteDate`）。盘前原文在 `data/digests/{asof}-pre.md`。`{asof}.md` 与 `latest.md` 是最后一次成功渲染的拷贝，不是第三套正文。另有 `latest-pre.*` / `latest-post.*`。

### 3. 盘后收盘来自外部日线，前收分两种

`quoteDate` = 运行日（若是 CN 交易日）否则该日之前最近的交易日。

- 收盘(T) 只用来自 `em_get` 的外部日线（`day_quote_cli._fetch_ohlc`）。禁止把引擎最后一根 bar 当成今日收盘。`day_quote._quote_row` 不用于这列。
- `quoteDate != asof` 时，涨跌分母是 asof 收盘（与表里「收盘(asof)」同一个数）。
- `quoteDate == asof` 时，分母是 asof **之前**那个交易日的引擎收盘，不能用「收盘(asof)」自己当自己的分母。
- 缺数显示 `—`。不读引擎 `pct_chg`。盘前三列恒为 `—`，即使有人传了取行情的开关也不写 0。
- 缓存沿用 A6：`data/quotes/ohlc-{quoteDate}.json` 只有 `asof` / `rows` / `count`，行内只有 open/high/low/close。只合并缺失代码。`_fetch_ohlc` 自己不读写缓存。源失败则空表加备注，digest 不因此让流水线失败。
- 行情模块 `quotes.py` 懒导入 `stock_platform_providers`。research 包顶层不新增对 providers 的 import。

### 4. 二次精选是展示口径

输入必须带齐 `rev_chg`、`vol20`、`rs20`、`amount`。缺字段落选，不把剩余权重重新归一。单位：`rev_chg` / `vol20` 是小数，`rs20` 是百分点 `(close/ma20-1)*100`，`amount` 是元。长线趋势位置取 `|rs20|` 的组内分位（越贴近 MA20 越好）。短线**不设 `rs20` 门槛、也不用位置钟形**，改用 20 日动量分位：引擎 lvrev 内核按构造只选 MA20 下方的票，任何 `rs20` 绝对下限都会把整板剔除（2026-10-27 实测 10 只全在 −3.4 ~ −6.5 百分点）。`short_term.items` 仍是生产榜 5 只；`short_term.pool` 默认 10，且排除 ②A 头部。同花顺文件仍是 `{asof}.txt` / `{asof}_short.txt`，导出生产榜。命中追踪只读 `items`。

000905 的汇总警告复用 A6：引擎里它解析为个股（厦门港务），「相对基准」不能读作指数超额。

③B 保留 ADR 0081 的数量列，并写出可卖 / 持仓 / 不可卖。T+1 半句只在 `asset_class=stock` 且 `market=CN` 且 `unsellable>0` 时出现。ETF / 基金不写 T+1。不写固定句「无 T+1 冻结」。美港不套用 A 股 T+1。

HTML：英雄区一个 `<h1>`。digest 渲染时去掉正文开头的 `# `，并把后文里单独的一级标题降成二级，避免命中追踪再出一个 H1。

### 5. 阈值按 2026-10-27 截面校准

首版按草案写的「成交额 ≥ 3000 万 + 短线 `rs20 ≥ -3`」，实测把 ②B 候选 **10 只全数剔除**：引擎 lvrev 内核按构造只选 MA20 下方的票，`rs20` 全在 −3.4 ~ −6.5 百分点，任何绝对下限必然全灭。故**删除 `rs20` 硬门槛**（它本是打分维度，再作门槛等于二次惩罚），成交额下限降到 1000 万只兜底极端地量。同轮把短线「位置钟形」换成动量维度 —— 原设计给该维度 50% 权重，而 `rs20` 恒为负使钟形恒 0 分，等于 50% 权重空转。

| 常量 | 现值 |
|---|---|
| 成交额下限 | `10_000_000` 元 |
| 长线 `rev_chg` 下限 | `< -0.25` |
| 短线 `rev_chg` 下限 | `< -0.15` |
| 长线权重 | 波动稳健 0.40 / 反转适度 0.30 / 趋势位置 0.20 / 流动性 0.10 |
| 长线打分 | 反转钟形中心 −0.10、半宽 0.15；趋势位置 = `\|rs20\|` 组内分位（越低越好） |
| 短线权重 | 动量 0.45 / 量能 0.30 / 波动活跃 0.25 |
| 短线打分 | 动量 = `rev_chg` 组内分位（越高越好）；波动活跃 = `vol20` 分位落在 `[0.50, 0.90]` 得满分，越出线性递减 |

两榜取向必须相反才有意义：长线买稳（低波动 + 反转 + 贴均线），短线买势（动量 + 量能 + 中高波动）。共用一套权重等于没区分。

执行层仍只有 SIMULATE。本 ADR 随 `v4.13.0` 发布；`T3`（数据质量体检）顺延 `v4.14.0`。

## 后果

- 盘前后各有一份文件；库里仍是一行。早上的 ③B 若被盘后覆盖，以 `{asof}-pre.md` 为准。
- 盘后涨跌在外部源失败时整列是 `—`，不回退到引擎最后一根。
- 二次精选可能入选很少甚至为空。这是展示结果，不补齐到 5，也不改生产榜。
- 阈值已按 `2026-10-27` 截面校准；后续再校准须同时改 `secondary_pick.py`、计划 §3.2 与本 ADR 的表，三处不一致视为缺陷。
