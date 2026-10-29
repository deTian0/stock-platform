# 每日简报「盘前 / 盘后」重构方案

> 状态：**已随 `v4.13.0` 发布**（2026-10-28）。阈值已按 `2026-10-27` 截面校准，见 §3.2。
> 目标版本：`v4.13.0`（已完成）
> 口径：SIMULATE，`liveTradingEnabled=false`，非投资建议。
> 版本槽说明：按「完成顺序编号」而非「计划号回填」—— 本重构先落地，故占 `v4.13.0`；原划给 `T3`（数据质量体检）的槽**顺延 `v4.14.0`**。`v4.12.0` 已由 A6 占用。判据只认根 `VERSION` 与 `git tag --list`。

`docs/ROADMAP.md` 没有这条重构的验收项（仅有已完成的 M3.3 / M25）。不要把本计划写进 `docs/ROADMAP.md`。开工时要补的文档见 §8。

## 0. 目标与非目标

### 0.1 目标

同一交易日的 08:30 与 15:30 各留一份可读简报。选股截面仍是上一交易日收盘（asof = T-1）。盘前回答「今天买什么」，运行日行情列留空。盘后补上运行日的开、收、自算涨跌。长线 Top10 保留；②A / ②B 各用一套展示层规则做二次精选，并写出落选原因。理由不截断。③B 在现有可执行数量之外，逐条展开触发规则、成本、持有天数、可卖数量和集中度。

### 0.2 非目标

- 不把 asof 拆成两天，不去掉任一侧的 `-PrevSession` / `-SettleAfter`（ADR 0079）。
- 不改评分、不改 `picks`、不回写生产档。
- 不改 `hit_tracking.session_type`（仍为 `pre_market`），不把盘后记成 `post_market`。
- 不改 `boards.short_term.items` 的宽度（仍是 5）。`short_term.pool` 只给展示。
- 不改绩效台账、picks 回测、命中累计的统计口径。
- 不引入实盘开关。执行层只有 SIMULATE。
- 不改同花顺导入上限。手机端一次 5 只是既有约束（`docs/ops/scheduler.md`），本计划不调整 `THS_IMPORT_PER_LINE`。
- 不把 `000905` 改成真正的中证 500。基准警告沿用 A6，迁移另立里程碑。
- 不提交 `data/` 下的行情缓存、digest 或 SQLite。

## 1. 现状与约束

流水线参数保持与 ADR 0079 一致。`scripts/ops/Invoke-ScheduledRun.ps1` 里 `daily` 与 `postmarket` 都是 `-MarketDb -PrevSession -SettleAfter -Digest`。asof 是 T-1，因为当日 bar 在 18:30 回补之后才进 `market.db`（`docs/ops/scheduler.md`）。两套任务的差异只加两样：**展示用 session**，以及**运行日行情**。不要为了区分盘前盘后去改 asof。

由此带来的展示问题（实现时对着这些文件改，不要另找一套数据源）：

| # | 事实 | 位置 |
|---|---|---|
| S1 | 标题不分会话 | `daily_digest.py` 正文标题、stub 标题、HTML `title` 都是 `# 每日简报 · {asof}` |
| S2 | 同一 asof 的 `{asof}.md` 被后一次渲染覆盖；`latest.md` 是该文件的拷贝 | `daily_digest.build_digest` |
| S3 | 长线 Top10 与 ②A 是同一段 `head(10)` | `brief.py` 的 `scored.head(top_n)`（流水线默认 `top_n=10`）；`rankings.py` 的 `quality_top_n=10` |
| S4 | 理由在 80 / 40 / 60 字处截断 | `daily_digest.py` 的 `_picks_table`、③B 备注、通用榜备注 |
| S5 | ②B 生产榜 5 条，渲染成 4 列（`# / 代码 / 名称 / 备注`） | `rankings.py` 的 `short_term_top_n=5`；先丢掉 ②A 头部再取 5 |
| S6 | ③B 在有 `suggestQty` 时已有股数、参考价、金额、权重；备注仍是截断后的 `stop_loss(-12.3%)` 这类规则串 | `rules.evaluate_exit`；`daily_digest.py` 操作建议表。成本与持有天数在 `holdingsReview.rows`，可卖数量在 `position_sizing` 的 `available` / `unsellable` |
| S7 | HTML 有两个 H1 | `report_html.render_report_html` 写 `<h1>`，`markdown_to_body` 再把正文 `# ` 渲成 `<h1>` |
| S8 | brief 表 `asof` 唯一，后一次 upsert 覆盖前一次 | `persistence.py`：`UNIQUE(asof)`，`ON CONFLICT(asof)`。`get_by_asof` 被 workbench、A6、sameday、digest 当成一日一行 |

数据层约束：

- 引擎 `daily_price` 的读取只有 `close, pct_chg, vol, amount`（`engine_sqlite.py`）。开高低不在这张表里（ADR 0082）。
- `panel.py` 在缺 open/high/low 时用 close 兜底。简报的「开盘」禁止读 panel 的 open。
- `pct_chg` 是混合尺度。涨跌一律自算 `close / prev_close − 1`，不读库内 `pct_chg`。
- 因子单位（二次精选和文案必须按此比较，禁止把百分点当小数）：
  - `rev_chg`：小数。−10% 存成 `-0.10`。定义是 `close / close.shift(20) − 1`（`panel.py`）。
  - `vol20`：日收益标准差，小数。不是「1.11」这种百分数。
  - `rs20`：百分点，等于 `(close / ma20 − 1) * 100`。`rs20 = 8` 表示收盘在 MA20 上方 8 个百分点，**越高离 MA20 越远**，不是「越贴近」。
  - `amount`：元（`providers.normalize`：`amount=元`）。3000 万写成 `30000000`，不要和「万」直接比。

`research` 源码顶层目前没有 `import stock_platform_providers`。这不是全包测试锁死的（现有懒导入测试只覆盖 `loop_health.py`）。本计划新增的行情模块继续懒导入，并给**该模块自己**加一条顶层 import 测试。

## 2. 展示规格

### 2.1 会话与运行日

| 字段 | 规则 |
|---|---|
| `session` | `pre` 或 `post`。写入 `brief.payload["session"]`，表示**这一行最后由哪个会话生成**。老 brief 没有该字段时，渲染按 `pre` |
| `runDate` | 任务运行日，由包装脚本传入。写入 `payload["runDate"]`。digest 进程**禁止**调用 `date.today()` 充当运行日 |
| `quoteDate` | 运行日是交易日则为运行日，否则为 `last_trading_day(run_date)`。写入 `payload["quoteDate"]`。列头用这个日期，例如 `开盘(10-28)` |

调度侧：`Invoke-DailyPipeline.ps1` 增加 `-Session`，默认 `pre`。`Invoke-ScheduledRun.ps1` 的 `daily` 加 `-Session pre`，`postmarket` 加 `-Session post`。其余参数不动。包装脚本用当天日期拼 `--run-date`，不要让 Python 自己猜。

渲染进程是单独的：`Invoke-DailyPipeline.ps1` 在流水线成功后执行 `python -m stock_platform_research.daily_digest_cli`。因此 **`daily_digest_cli.py` 必须接受 `--session` 和 `--run-date`**。解析顺序：命令行 > payload 里已有的 `session` / `runDate`。两者都没有时，session 按 `pre`，运行日视为缺失：OHLC 三列写 `—`，顶部 `dataNote` 写「未提供运行日，未取行情」。不允许落到今天。

### 2.2 文件

| 文件 | 含义 |
|---|---|
| `data/digests/{asof}-pre.md` / `.html` | 盘前。后一次盘后渲染**不得删除** |
| `data/digests/{asof}-post.md` / `.html` | 盘后。不得删除盘前文件 |
| `data/digests/{asof}.md` / `.html` | **最后一次成功渲染的别名**（拷贝，不是第三套正文） |
| `data/digests/latest.md` / `latest.html` | 仍是最后一次成功渲染 |
| `data/digests/latest-pre.*` / `latest-post.*` | 各会话最新指针，增量，不替换 `latest.md` |

要改的读者文档与测试：`docs/ops/scheduler.md`、`docs/ops/daily-pipeline.md`、`packages/research/tests/test_daily_digest.py`（现有断言仍写 `{asof}.md` 与 `# 每日简报 · {asof}`）。实现时搜 `data/digests/{asof}` 与 `latest.md` 的文档引用，避免只改一处。

### 2.3 brief 库的取舍（不改主键）

`daily_briefs.asof` 保持 `UNIQUE`。不改成 `UNIQUE(asof, session)`。

代价已经明确：改唯一约束要重建表，并且 workbench 多条路由、A6、sameday、digest 的 `get_by_asof` 都要决定读哪一行。盘前与盘后的**选股截面相同**（同一个 T-1），生产榜只应有一份权威行。

取舍写死：

- 库里一个 asof 只留**最新一条**。15:30 跑批覆盖 08:30 写入的那一行。`payload["session"]`、`runDate`、`quoteDate` 描述的是最后一次写入。
- 盘前、盘后各留一份的是 **digest 文件**（§2.2），不是两行 brief。
- 覆盖之后，库里不再有上午的 `generated_at`。若两次跑批之间 `holdings.json` 变了，上午的 ③B 也不能从库里找回，以已经写出的 `{asof}-pre.md` 为准。
- 重渲另一会话靠命令行：`--session pre --run-date <那天>`。因子与 picks 仍来自这唯一一行（同一 asof 截面）。盘前渲染不填运行日 OHLC。

### 2.4 正文骨架

保留现有块，只改标题、列和二次精选。不要删掉口径自证、环境/数据源/宇宙、同花顺代码块、命中追踪、绩效台账。

```markdown
# 每日简报 · 盘前 · {asof}
> **口径**：数据基准日 asof={asof}（T-1 收盘截面）；报告类型：盘前；运行日 {runDate}；报价日 quoteDate={quoteDate}；生成于 {本地时间}。
> 盘前：运行日行情尚未作为本报告的报价使用，开盘/收盘/涨跌留空（—）。盘后报告补齐。

- 环境：SIMULATE（非投资建议）
- 数据源、宇宙、截面、TopN、数据备注、生成时间（与现 digest 相同）

## 一、今日 Top10 · 长线
（同花顺长线代码块：生产 picks，10 只）
| # | 代码 | 名称 | 综合分 | 收盘(asof) | 开盘(quoteDate) | 收盘(quoteDate) | 涨跌(quoteDate) | 入选理由 |
理由列用完整 `reasonSummary`，不截断。

## 二、②A 二次精选（10 进 N）
一句口径：二次精选是呈现口径，不参与评分、不改 picks、不改变仓位建议。
（入选表 + 「未入选及原因」表）
报告内附 §3.3 的 profile 对照，让读者看到长线惩罚偏离、短线要站上但别追高。

## 三、②B 短线 · 二次精选（10 进 N）
（同花顺短线代码块：生产 `boards.short_term.items`，5 只，不是二次精选结果）
（入选表列与长线相同 + 落选表）

## 四、③A 持仓
## 五、③B 操作建议
## 六、③C 观察名单
## 命中追踪
## 绩效台账
```

盘前：三列行情全部为 `—`，不联网。表下写「盘后报告补齐 quoteDate 行情」。

盘后：三列填 §4 的真实报价。列头带 `quoteDate`。长线 Top10 与 ②B **候选池 10 只**（不是二次精选后的 5 只）各加一行汇总：`N 只 quoteDate 平均涨跌 x%，相对 000905 上涨家数 y/N`。N 是实际有涨跌的只数。基准句必须复用 A6 的 `benchmarkWarning`：引擎库里的 `000905` 解析成个股（现为厦门港务）时，写明这是相对该个股，**不能读作中证 500 指数超额**。基准行情取不到时，汇总只写个股平均涨跌，并写「基准不可用」，不要编造指数超额。

标题三处一起改：markdown 第一行、`_stub_text`、`render_report_html` 的 `title`（`每日简报 · 盘前|盘后 · {asof}`）。digest 调用 HTML 时去掉正文开头那个 `# ` 再交给 `markdown_to_body`，或给 `render_report_html` 增加只被 digest 打开的 `strip_leading_h1=True`。页面上只留英雄区一个 H1。stub 没有会话时标题用 `# 每日简报 · {asof}` 即可，但不要再和英雄区叠两个 H1。

### 2.5 同花顺

导入码仍用**生产榜**：长线 = `picks`（10），短线 = `boards.short_term.items`（5）。文件名改用**报告日** `data/ths_import/{reportDay}.txt`、`{reportDay}_short.txt` 以及 `latest.txt` / `latest_short.txt`，不按 session 分线。报告里代码块旁边加一句：「导入码来自生产榜，不是二次精选结果。」手机一次只能导入 5 只，长线块继续按现有每行 5 只折行；本计划不改这个上限。

> **2026-10-29 增补（ADR [0084](../architecture/0084-secondary-pick-import-blocks.md)）**：二次精选也要能一键导入，故在生产榜两块之外再加 `同花顺导入 · 二次精选（长线|短线）`，对应 `{reportDay}_quality_sec.txt` / `{reportDay}_short_sec.txt`。生产榜的块与 txt 命名不变（ADR 0083 结论保留），②B 段会同时出现两块，按标签区分口径。

### 2.6 ③B 说明块

表格保留 ADR 0081 的列（代码、名称、动作、股数、参考价、金额、权重），备注列不再 `[:40]`。每只在表下追加一块，数据只来自两处，按代码对齐：

- `rankings.holdingsReview.rows`：`entry_price`、`price`、`ret_pct`、`held_days`、`reason`、`peak`、`target`、`asset_class`
- `rankings.holdingsReview.exitPolicy`：`stop_loss`、`take_profit`、`min_hold`、`trail_stop_pct` 等（百分点，与 `rules.py` 一致：`-8.0` 表示 −8%）
- `positionSizing` 的订单：`available`、`unsellable`、`heldQty`、`weightBefore`、`weightAfter`、`capWeight`

文案规则：

- 可卖性只写「可卖 {available} / 持仓 {heldQty}，不可卖 {unsellable}」。**禁止**固定句「无 T+1 冻结」。
- 仅当 `asset_class == stock`、本简报 `market` 为 CN、且 `unsellable > 0` 时，可以补半句「不可卖数量按 A 股 T+1 理解」。
- `asset_class` 为 `etf` 或 `fund` 时禁止出现 T+1。
- 非 CN 标的只报数量，不套 A 股 T+1 / 涨跌停。本简报主链是 CN；没有市场字段就不要猜美港规则。
- 触发规则引用 `reason` 与 `exitPolicy`，例如止损线是配置值，实际收益是 `ret_pct`。`take_profit == 0` 写「已关闭」。不要编造未出现在规则层的条件。
- `held_days < min_hold` 且原因不是止损/止盈时，注明未到最短持有、故非到期退出。止损不受 `min_hold` 限制（`rules.py` 已如此），文案不要写成「因为未满 45 天才止损」。

## 3. 二次精选规格

新模块 `packages/research/src/stock_platform_research/secondary_pick.py`。纯函数，无 IO，不用运行日行情，不用未来 bar。

```python
select_secondary(items, *, profile: Literal["quality", "short"], top_k: int = 5)
    -> {"selected": [...], "rejected": [...], "stats": {...}, "profile": {...}}
```

### 3.1 输入行必须带齐因子

`select_secondary` 的每一行至少要有：`symbol`、`name`、`close`、`vol20`、`rev_chg`、`ma20`、`rs20`、`amount`，以及现有的 `composite_score`、`reasonSummary`。

来源：

- 这些列在 `panel` / `scored` 上已经算好。`brief.py` 的 pick 已有 `vol20`、`rev_chg`、`ma20`、`close`；补上 `rs20` 与 `amount`。
- ②A 的 board item 今天只有 rank、代码、分、收盘、理由（`rankings._item_from_row`）。**必须把上述因子抄进 item**。只改 pick、不改 board item，不能当作二次精选的输入。
- ②B：`items` 仍按现在的规则取 5 条，并带上同样的因子（供全列表格和同花顺，不供二次精选吃这 5 条）。另写 `boards.short_term["pool"]`：与现有 `passed` / `remain` 相同的排除逻辑，宽度 `short_term_pool_n = 10`（新配置，默认 10）。**不动** `short_term_top_n = 5`。二次精选读 `pool`；没有 `pool` 的老 brief 不做短线二次精选，落一句「无候选池，未做二次精选」，禁止偷偷拿 `items` 的 5 条冒充「10 进 5」。

缺字段的处理（禁止「丢掉这一维、权重重新归一、继续当有效排名」）：

1. 硬性门槛用到的字段缺失 → 该只进入落选，原因是「缺 `{字段}`，不参与二次精选」。不要把它当成 0 成交额或 0 跌幅再套门槛。
2. 打分用到的任一字段缺失 → 同样落选，原因写缺哪个字段。不把该维权重摊给其他维。
3. 通过硬性门槛且字段齐全的不足 2 只 → **不做组内分位**。`selected` 为空，`stats.note` 为「可评分样本不足 2，不做有效排名」。
4. 齐全且不少于 2 只 → 只在这批行里做 `rank(pct=True)`，再取最多 `top_k`。不足 `top_k` 就少给，不把已落选的补回来。标题写 `10 进 N`（10 是输入条数，不足 10 就写实际输入条数）。附一行「剔除后仅 N 只符合条件，按规则不补齐」。

### 3.2 阈值（按 2026-10-27 截面校准）

下表是**已按 `2026-10-27` 截面校准**的现值，常量在 `secondary_pick.py`，与下表数字一致。首版按草案写「成交额 ≥ 3000 万 + 短线 `rs20 ≥ -3`」，实测把 ②B 候选 10 只全数剔除（lvrev 内核按构造只选 MA20 下方的票），故删掉 `rs20` 硬门槛、成交额降到 1000 万。

#### ②A 长线 profile（`quality`）：惩罚过分离散

硬性排除：

| 规则 | 初值 | 落选原因 |
|---|---|---|
| E1 风险警示 | 名称含 `ST`（含 `*ST`） | 风险警示股，二次精选剔除 |
| E2 流动性 | `amount < 10000000`（元） | 成交额低于 1000 万元 |
| E3 跌幅过深 | `rev_chg < -0.25` | 20 日收益低于 −25% |

四维，权重和为 1。组内分位只在通过 §3.1 的行上计算。钟形 `max(0, 1 - abs(x - center) / halfwidth)`，小于 0 的记 0。

| 维度 | 权重 | 打分 | 方向 |
|---|---|---|---|
| 波动稳健 | 0.40 | `-vol20` 的组内分位（`vol20` 仍是小数） | 波动越低越好 |
| 反转适度 | 0.30 | 钟形，`center=-0.10`，`halfwidth=0.15`（都是小数） | 越接近 −10% 越高；太浅或太深都降分 |
| 趋势位置 | 0.20 | `abs(rs20)` 的组内分位（`rs20` 单位是百分点） | **惩罚偏离 MA20**。绝对值越小分越高 |
| 流动性 | 0.10 | `amount` 的组内分位 | 成交额越高越好 |

#### ②B 短线 profile（`short`）：站上但别追高

硬性排除比长线严：

| 规则 | 初值 | 落选原因 |
|---|---|---|
| S1 风险警示 | 名称含 `ST` | 风险警示股，短线不参与 |
| S2 流动性 | `amount < 10000000` | 成交额低于 1000 万元 |
| S3 接刀 | `rev_chg < -0.15` | 20 日收益低于 −15% |

`rs20` 在短线里**不设门槛、也**不进打分：候选池天然全在 MA20 下方（内核按构造如此），`rs20` 在此既不能当过滤条件（会全灭），也不能当位置信号（恒为负，钟形恒 0 分）。短线改由 20 日收益的组内分位表达动量。

| 维度 | 权重 | 打分 | 方向 |
|---|---|---|---|
| 动量 | 0.45 | `rev_chg` 的组内分位（`rev_chg` 是小数） | 20 日收益越高越强。与长线的「反转钟形」刻意相反 |
| 量能 | 0.30 | `amount` 组内分位 | 越高越好 |
| 波动活跃 | 0.25 | `vol20` 的组内分位 `p`：`p` 落在 `[0.50, 0.90]` 记 1，否则 `max(0, 1 - d / 0.50)`，`d` 是 `p` 到该区间的距离 | 中高波动，不要极端 |

### 3.3 报告里怎么写理由

每只入选理由用得分最高的两个维度，带上原始值和单位，例如「20 日收益 −8.1%（`rev_chg=-0.081`），靠近 −10%」或「`rs20=+4.2` 个百分点，靠近短线中心 +4」。落选清单每只一句，用 §3.2 的原因模板。

报告里用一张小表对照两个 profile 的取向：长线是「低波动 + 反转钟形 + 贴近 MA20」，短线是「20 日动量 + 量能活跃 + 中高波动」。不要写「长线也是 rs20 越高越好」，也不要写成两榜只差权重比例。

两榜入选互不重叠，靠的是 pool 的构造（②B pool 排除 ②A 头部），不是靠两套权重。测试锁的是排除关系，外加「同一批输入、两种 profile、排序不同」。

固定一行：「二次精选是呈现口径，不参与评分、不改 picks、不改变仓位建议；入选不是更强的推荐。」

## 4. 盘后行情规格

15:30 时引擎没有运行日 T 的 bar，回补在 18:30。因此：

- **收盘(quoteDate)** 只用外部东财日线在 `quoteDate` 当天的 `close`。路径是已有的 `day_quote_cli._fetch_ohlc` → `AStockHttpProvider`（东财走 `em_get`）。禁止直接请求东财。
- **禁止**套用 A6 的 `_quote_row`：那边在引擎已有最后一根时用引擎 close，外部 close 只在引擎 close 为空时才填。15:30 的最后一根是 T-1，套用会把昨天收盘印成今天收盘。
- **收盘(asof)** 始终是选股截面价（brief / 引擎的 asof close），与报价列分开。
- **开盘(quoteDate)** 用同一条外部日线的 `open`。禁止用 panel 的 open。

前收，单独规定，不要和「收盘(asof)」混用：

| 情况 | 前收 |
|---|---|
| 正常盘后：`quoteDate` 是交易日，且 asof 就是它的前一交易日 | 前收 = asof 收盘（与「收盘(asof)」同一数字） |
| 运行日非交易日，`quoteDate` 回落到 asof（两个日期相同） | 前收 = **asof 的前一交易日**的引擎收盘。涨跌的分母禁止用「收盘(asof)」 |
| 前收或外部收盘缺失 | 涨跌写 `—`。有开盘无收盘时收盘也是 `—`。禁止补 0 |

涨跌 = `外部收盘(quoteDate) / 前收 − 1`。盘前不计算。

缓存：

- 路径 `data/quotes/ohlc-{quoteDate}.json`（与 A6 相同目录和文件名规则；日期是报价日，不是把 brief asof 误当成文件名——两者在正常盘后本来就不是同一天）。
- JSON 只有这三个顶层字段：`asof`（此处等于 quoteDate）、`rows`、`count`。`rows` 的值只有 `open` / `high` / `low` / `close`。这是 `day_quote_cli` 现有写法。
- `_fetch_ohlc` **不读不写**缓存。缓存的读、合并、写在调用方。
- 合并：先读已有文件，只对缺失代码调用 `_fetch_ohlc`，再把旧行和新行写回**同一个形状**。禁止另写一套字段名，否则会破坏 A6 同日复跑。
- 允许把 `_cache_path` / `_read_cache` 提成 `day_quote` 的公开函数给两边用。不允许复制出第二套键名。
- 异常或空结果：返回空 dict，报告照出，三列 `—`，`dataNote` 说明外部日线不可用。不抛到流水线退出码（digest 今天已经是 best-effort）。

行情模块放在 `research` 的新文件（建议 `quotes.py`）或 digest CLI 内部函数。`import stock_platform_providers` 只能出现在函数体内。`get_trading_calendar` 同样懒导入。给这个新文件加测试：源码里每一行 `stock_platform_providers` 都必须缩进。不要声称全 `research` 包已有这种测试。

`--ohlc`：盘后默认开，盘前默认关。盘前即使误开，也不得把运行日未收盘的报价写成 0；取不到仍是 `—`。

## 5. 阶段任务

### P0 · 会话、标题、文件名（不取行情）

| 位置 | 改动 |
|---|---|
| `daily_cli.py` / `daily_pipeline.py` | `--session`，写入 `payload["session"]`、`runDate`、`quoteDate` |
| `daily_digest_cli.py` | `--session`、`--run-date`。禁止 `date.today()` 充当运行日 |
| `Invoke-DailyPipeline.ps1` | `-Session`；`$digestArgs` 带上 `--session` 与 `--run-date` |
| `Invoke-ScheduledRun.ps1` | `daily` → `-Session pre`；`postmarket` → `-Session post`。`-MarketDb -PrevSession -SettleAfter -Digest` 保持不动 |
| `daily_digest.py` | 正文标题、stub 标题、写出 `{asof}-pre\|post`、`{asof}` 别名、`latest`、`latest-pre\|post` |
| `report_html.py` | digest 路径去掉双 H1 |

验收：同一 asof 连跑 pre 与 post，两份文件都在，标题不同，`{asof}.md` 与 `latest.md` 等于后一次，盘前文件仍在。库里仍是一行 brief。

### P1 · 行情列与理由

按 §4 实现取数与前收。`_picks_table` 改为八列，理由不截断。盘前三列为 `—`。盘后涨跌用 §4 的公式，单测里用假外部 close，不联网。

### P2 · 二次精选

1. **校准（写代码前）**：按 §3.2 目视一个历史截面，把采纳的数字写回本文件或 ADR。
2. 扩展 `_item_from_row` 与 pick 字段；增加 `short_term.pool`。
3. 实现 `select_secondary`，渲染 §2.4 的第二节和第三节。
4. `stats` 可放进当次渲染用的内存结构；不必为了复盘去改 brief 主键。若要落盘，只附加在**不改变** `UNIQUE(asof)` 的 payload 字段里，并接受后一次覆盖前一次。

验收：②A 入选表与长线 10 只不同构；pool 为 10 且与 ②A 头部无交集；`items` 仍为 5；缺 `rs20` 的行落选且不会靠「剩余权重归一」挤进榜。

### P3 · ②B 全列与 ③B 详解

短线入选表与长线同一套列。同花顺块留在二次精选表之后，代码仍是生产 5 只。③B 按 §2.6 追加说明块，去掉 `note[:40]` 与通用表的 `note[:60]`（观察名单若仍用备注，也不再截断）。

### P4 · 文档与版本

见 §8。全量 pytest 不低于当前 `v4.12.0` 基线（CHANGELOG 记载 1269 passed）；只要求不少于开工时的通过数，不把 1269 写成永久上限。

## 6. 测试与验收

| 类型 | 位置 | 断言 |
|---|---|---|
| 改 | `test_daily_digest.py` | 新标题；`{asof}-pre` 与 `{asof}-post` 共存；`{asof}.md` 等于最后一次；`latest.md` 仍在 |
| 新增 | 同上 | 盘前三列是 `—`；未传 `--run-date` 且 payload 无 `runDate` 时不出现「今天」的伪造报价；理由长文完整，不断成 `...`；HTML 只有一个 `<h1>`；③B 含触发规则、持有天数、可卖/不可卖、集中度，且无固定句「无 T+1 冻结」；ETF 样例不出现 T+1 |
| 新增 | `test_secondary_pick.py` | ST 两套 profile 都剔除；`amount` 按元比较（`29999999` 落选，`30000000` 不因流动性落选）；`rev_chg=-0.26` 触发 E3，`rev_chg=-0.25` 不触发；`rs20=-3.01` 触发 S4，`rs20=-3` 与 `rs20=-0.03` 都不触发；不足 5 只不补齐；同一输入两种 profile 排序不同；长线在 `|rs20|` 更大时趋势分更低；缺字段的行落选，且结果不等于「删掉该维再归一」的排名；可评分不足 2 只时 `selected` 为空 |
| 新增 | `test_rankings.py` | `pool` 宽 10，`items` 宽 5；pool 的代码与 ②A 头部不相交；`hit_tracking` 仍只读生产 items |
| 新增 | `test_quotes.py` | 缓存命中不调用 `_fetch_ohlc`；写入 JSON 的键只有 `asof`/`rows`/`count`；源失败返回空 dict；`quoteDate == asof` 时前收不是 asof 收盘；新模块源码无顶层 `stock_platform_providers` |
| 回归 | 全量 | `pytest packages apps -q`。开工时记下实际通过数 |

验收清单：

- [x] 盘前/盘后标题可分；`-pre`/`-post` 都保留；`{asof}.md` 与 `latest.md` 是最后一次
- [x] 调度参数仍含 `-PrevSession -SettleAfter`；asof 仍是 T-1
- [x] 盘后开/收来自外部日线的 quoteDate，不是 panel，也不是引擎最后一根
- [x] 涨跌自算；`quoteDate == asof` 时分母是前一交易日
- [x] 理由无 `...` 截断；HTML 单 H1
- [x] ②A 为 10 进 N 加落选原因；②B pool 为 10、items 为 5；同花顺仍是生产 10 与生产 5
- [x] 两种 profile 的 `rs20` 用法符合 §3.2（长线惩罚偏离，短线钟形中心 +4）
- [x] ③B 说明含规则、成本、持有天数、可卖数量、集中度；无全市场 T+1 固定句
- [x] 汇总行在 `000905` 解析为个股时复用 A6 警告，不写指数超额
- [x] `hit_tracking` 仍写 `pre_market`
- [x] ADR 0083 已进入 `scripts/check_docs.ps1` 的 `$required`；`check_versions` 与全量 pytest 通过

不写进验收：某一天的命中只数、某一份 HTML 的行号、某一天 panel 里四价相等。

## 7. 风险

| 风险 | 处理 |
|---|---|
| 东财失败 | `em_get` 统一限流；整列 `—` + `dataNote`；缓存命中则同日不再请求 |
| 外部 close 与引擎 asof close 的复权不一致 | 正常盘后前收规定用引擎 asof close，报价用外部 T 日 close。两者相除是规格，不是 A6 的「收盘也走引擎」。除权日可能难看，失败时整列 `—`，不改规则去混用 |
| 覆盖 brief 丢掉上午 ③B | 已在 §2.3 写明。上午内容以 `{asof}-pre.md` 为准。不为此改主键 |
| `{asof}.md` 旧读者 | 别名保留为最后一次。文档与测试按 §2.2 改。盘前原文只在 `{asof}-pre.md` |
| 二次精选被当成加仓建议 | 报告固定 §3.3 那一行。同花顺仍导出生产榜 |
| pool 被误当成生产榜 | `items` 宽度测试锁死；命中与回测不读 `pool` |
| 阈值被拍脑袋定死 | 已用 `2026-10-27` 截面校准，并记录了首版门槛导致 ②B 10 进 0 的实证；常量、§3.2、ADR §5 三处必须一致 |
| 手机导入仍是 5 只一行 | 非目标。长线 10 只继续折行 |
| `000905` 不是指数 | 复用 A6 `benchmarkWarning`，不在本计划改基准 |
| 缓存 schema 被写歪 | 测试锁住三个顶层键；只合并不换结构 |

回滚：展示层与 payload 增字段。磁盘多出来的 `-pre`/`-post` 可以留着。brief 表结构不变，不需要数据迁移。

## 8. 文档与版本

实现收口时改这些，现在不要改路线图正文：

| 交付 | 要求 |
|---|---|
| ADR `docs/architecture/0083-digest-pre-post-and-secondary-pick.md` | 写明 §2.3 的单行 brief 取舍、§4 的前收，以及 §3.2 初值未经校准已入代码 |
| `scripts/check_docs.ps1` 的 `$required` | **必须**列入 0083。0082 已在列；只在 `docs/architecture/` 新建文件，检查不会因此失败 |
| `CHANGELOG.md` | 已写入 `v4.13.0` 节 |
| 版本号 | 已同步根 `VERSION` 与五个包共 11 处至 `4.13.0` |
| `docs/ops/scheduler.md`、`docs/ops/daily-pipeline.md` | 写上 `-Session`、新文件名、`{asof}.md` 仍是最后一次的别名 |
| `docs/plans/trading-system-roadmap.md` | 已在 §8 修订记录追加 `v4.13.0` 一行；`T3` 改记顺延 `v4.14.0` |

不改 `docs/ROADMAP.md`。不提交 `data/quotes`、`data/digests` 或数据库。
