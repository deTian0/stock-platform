# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循本仓 [`docs/versioning.md`](docs/versioning.md)。

## [Unreleased]

### Added

- （无）

## [4.13.4] - 2026-10-30

### Fixed

- **盘后简报的「开盘(T) / 收盘(T) / 涨跌(T)」三列整列为空**（`2026-10-29` 盘后实测）。当日 15:31 跑盘后流水线时，东财返回 `ConnectionError: RemoteDisconnected`，`AStockHttpProvider` 的断路器随即打开，而 `_fetch_ohlc` 把**全部 70+ 只标的塞进一次 `get_daily` 调用** —— 断路器一开就整体抛出，已经把开/高/低拿到的那部分也一起丢掉，简报三列全部退化为 `—`，摘要行还写成「无可计算涨跌。基准不可用」（把「行情源挂了」错说成「基准不可用」）。三个彼此独立的缺陷，逐条修：
  - **`day_quote_cli._fetch_ohlc` 分批 + 重试**：按 `CHUNK_SIZE=30` 分批，单批失败只损失该批，并换一个**新建** `AStockHttpProvider`（断路器是实例级的）重试一次。
  - **`day_quote_cli._fetch_ohlc` 逐轮补齐**：`get_daily` 对**单只**的瞬时错误是静默跳过（只进 `symbol_errors`，不抛异常），一次调用常常「成功但少回几只」（同日实测 16 只只回 14 只）。改成 `FETCH_PASSES=3` 轮，只对仍然缺的代码再跑，直到补齐或轮次用尽。
  - **`quotes.load_ohlc` 增加引擎库收盘兜底**：外部源失败且 `quote_date` **严格晚于** brief 的 `asof`（即该交易日已收盘并已被 `18:30` 回补进 `market.db`）时，用引擎收盘填 `close`，让「收盘/涨跌」仍可读，只有「开盘」留 `—`。**边界刻意写死**：`quote_date == asof` 时绝不兜底（否则等于拿 asof 收盘冒充当日收盘，涨跌恒为 0）；兜底行也**不写入** `data/quotes/ohlc-<date>.json` 缓存（缓存只保留带开盘价的外部真值）。
  - **`quotes` 两个引擎读取函数补 `load_dotenv()`**：`resolve_engine_market_db()` 依赖 `.env`，进程未加载时静默返回 `None`，兜底会一声不响地失效（`daily_digest_cli` 直接调用时即如此）。
  - **摘要行文案**：无涨跌可算时改为「行情缺失，无可计算涨跌（外部日线源不可用且引擎库无该日 K 线；见顶部「数据备注」）」，不再谎报「基准不可用」。
  - 测试：新增 4 例（分批保留成功批、全批失败、引擎兜底仅在 `quote_date > asof` 时生效、兜底不入缓存）；`packages/research` 相关 71 passed。

## [4.13.3] - 2026-10-29

### Added

- **二次精选逐榜给出可复制的同花顺导入块**（ADR [0084](docs/architecture/0084-secondary-pick-import-blocks.md)）。此前二次精选只有表格没有代码块：②A 二次精选要人工从表里抄 5 个代码建自选，「一键导入」恰恰漏在取舍得最狠的那一榜上。
  - 新增块：`同花顺导入 · 二次精选（长线）`（②A 二次精选入选）、`同花顺导入 · 二次精选（短线）`（②B `pool` 二次精选入选）。标签刻意不写成「长线二次精选」—— 否则 `同花顺导入 · 短线` 会成为它的前缀，任何按标签切分的读取方都会撞车。
  - 新增文件：`data/ths_import/{reportDay}_quality_sec.txt` / `{reportDay}_short_sec.txt` + 对应 `latest_*` 指针；文件名后缀 `_quality_sec` / `_short_sec`，不与既有 `{reportDay}.txt` / `{reportDay}_short.txt` 冲突。
  - 生成逻辑收敛到 `_secondary_codes(record, profile)`：md 的块与 txt 都走同一个 `select_secondary`、同一份入参（二次精选结果不入 brief 存档，故必须共用函数，否则「块与 txt 一致」只是巧合）。
  - fail-closed：选不出标的不出块、不落盘；`short_term.pool` 缺失时正文写「无候选池，未做二次精选」。

### Fixed

- **②B 段 md 代码块与 `_short.txt` 内容不一致**（`v4.13.0` 遗留）。`v4.13.0` 起 md 里的「同花顺导入 · 短线」渲染的是**二次精选入选**，而 `data/ths_import/{reportDay}_short.txt` 按 ADR 0083 导出的是 **`short_term.items` 生产榜** —— 同一份报告里，复制一行和打开 txt 拿到两组不同代码，且生产榜那 5 只含 ST / 地量（二次精选才剔）。
  - 现在「短线」块回到生产榜（= `_short.txt` 内容），二次精选单列一块（= `_short_sec.txt` 内容），四个块与四份 txt 一一对应。
  - 生产榜与二次精选本就是两套取舍口径，代码可以不同 —— 这是设计，不是 bug。
- 测试：新增 4 个用例锁死「块与 txt 一一对应」「无 pool 不出块」「两块标签互不为前缀」；`test_digest_labels_both_lines_and_short_gets_a_copy_paste_block` 等原用例全部照旧通过。

## [4.13.2] - 2026-10-28

### Changed

- **同花顺导入 txt 的文件名改用报告日**（`v4.13.1` 遗留的表达错位）。`v4.13.1` 把 digest 本体改成 `{reportDay}-pre|post` 之后，`data/ths_import/{asof}.txt` / `{asof}_short.txt` 仍停在**选股基准日** ⇒ 报告标题写 10-28、导入文件却叫 10-27，同一种「标题与文件日期不一致」换了个位置复发。
  - `write_ths_import(..., day=...)`（原关键字 `asof`）改为接收**文件名日期**；`build_digest` 两个调用点统一传 `report_day`。
  - 产物：`data/ths_import/{reportDay}.txt` + `latest.txt`、`{reportDay}_short.txt` + `latest_short.txt`；**`latest*` 指针语义不变**。
  - **口径不变**：导入码仍取生产榜（长线 `picks` 10 只 / 短线 `short_term.items` 5 只），不是二次精选结果；文件内容与该文件叫什么都无关。
  - 历史文件不重命名 —— 文件名只承担「这是哪一天的报告」这一个用途，按新规则向前生效，不回改归档。
  - 测试：`test_build_digest_names_files_by_run_date` 增加 `thsPath` / `thsShortPath` 文件名断言；两处 `write_ths_import(...)` 调用同步改关键字。

## [4.13.1] - 2026-10-28

### Fixed

- **简报标题的日期与正文日期冲突**（`v4.13.0` 遗留）。标题原为 `# 每日简报 · 盘后 · {asof}`，而 `asof` 是**选股基准日**（T-1 收盘截面），正文第一列却是 `开盘(T) / 收盘(T) / 涨跌(T)` —— 10-28 跑出来的报告标题写着 10-27。三个定时任务都带 `-PrevSession`，`asof` 恒为 T-1，且 **10-28 的盘前与盘后共用同一个 `asof=10-27`**，两份产物因此都叫 `2026-10-27-pre/post`，读者无法从标题判断这份简报服务的是哪一天。
  - 标题改为「**报告日 = 运行日**」：`# 每日简报 · 盘后 · 2026-10-28（选股基准 2026-10-27）`；`run_date == asof`（回补场景）时不出现括注。
  - 产物文件名同步改为 `data/digests/{reportDay}-pre|post.md|html`，`{reportDay}.*` / `latest*.md` 别名不变；`build_digest` 返回值新增 `reportDate`，**`asof` 语义不变**（仍是选股基准日，brief 库主键不动）。
  - HTML `<title>` / `<h1>` / 副标题同步（副标题改为「报告日 … · 选股基准 asof …」）。
  - **口径不动**：选股截面仍是 T-1 收盘、`quoteDate` 仍按运行日解析。盘后若改用当日收盘选股，涨跌恒为 0，报告失去复盘意义 —— 这正是该设计保留 `-PrevSession` 的原因。同花顺导入 txt 仍按 `asof` 命名（那是选股批次的键）。
  - 新增 2 个测试锁死口径：`test_build_digest_text_title_uses_run_date_with_basis_note` / `test_build_digest_names_files_by_run_date`。

## [4.13.0] - 2026-10-28

### Added

- **每日简报盘前 / 盘后分线 + ②A/②B 双 profile 二次精选 + ③B 操作详解**（ADR [`0083`](docs/architecture/0083-digest-pre-post-and-secondary-pick.md)、方案 [`digest-pre-post-redesign.md`](docs/plans/digest-pre-post-redesign.md)）。
  08:30 与 15:30 此前跑的是**完全相同**的参数（同为 `-MarketDb -PrevSession -SettleAfter -Digest`），两份简报只有生成时间不同；「长线 10 只」与 ②A 质量榜**逐行相同**；理由被 80 / 60 / 40 字三处硬截断成 `...`；短线榜只有 `# / 代码 / 名称 / 备注`。
  - **展示分线**：流水线参数与 asof（仍 T-1）都不动，新增 `-Session pre|post`，`Invoke-DailyPipeline.ps1` / `Invoke-ScheduledRun.ps1` 的 `TASK_PRESETS` / 两个任务 XML 四处同步。包装脚本在 `-PrevSession` 改写 asof **之前**记下运行日并显式传 `--run-date`；digest **不调 `date.today()`**，缺运行日则不猜、行情列恒 `—`。
  - **产物**：`data/digests/{asof}-pre.*` 与 `{asof}-post.*` **双向保留**（此前只留最后一份）；`{asof}.*` / `latest.*` 降级为「最后一次成功渲染的别名」，另加 `latest-pre.*` / `latest-post.*`。brief 库仍是 `UNIQUE(asof)` 一行，不改主键、无需数据迁移。
  - **当日行情列**：`# / 代码 / 名称 / 综合分 / 收盘(asof) / 开盘 / 收盘 / 涨跌 / 入选理由`。开 / 高 / 低走东财 `em_get` 并复用 A6 同形缓存 `data/quotes/ohlc-<quoteDate>.json`（`quotes.py` 懒导入 providers，research 顶层不新增依赖）；涨跌幅一律自算 `close / prev_close − 1`，不读混合尺度的 `pct_chg`；`quoteDate == asof` 时分母取 asof **之前**那个交易日，不得自除。取不到显示 `—`，不补零、不猜。
  - **二次精选（纯展示层 `secondary_pick.py`）**：②A 10 进 N，②B 候选池扩到 10 后同样 10 进 N，各带**落选原因**与入选两只最强维度；**不足 N 只如实少给，绝不补齐**。生产侧零变动 —— `short_term.items` 仍宽 5、同花顺仍导生产榜、命中追踪与 picks 回测只读 `items`。
  - **③B 逐条展开**：触发规则、跌破几个百分点、成本 → 现价、持有天数、可卖 / 持仓 / 不可卖（T+1 半句仅在 A 股股票且确有冻结时出现，ETF 不写）、集中度（如 `90.24% → 0`，超单票 20% 上限）。
  - **理由全量展示**：三处截断全部移除；HTML 表格单元格允许换行（`white-space: normal`），长理由不再被压成一行。

### Fixed

- **②B 短线榜一度 10 进 0、整榜全灭**（设计硬伤，不是随机结果）：草案给短线设 `rs20 >= -3` 绝对门槛，而 `rs20` 实际是 `(close/ma20 − 1) * 100`（**不是相对强度 RS**），引擎 lvrev 内核按构造只选 MA20 **下方**的票 ⇒ 20 只候选的 `rs20` 全在 −3.4 ~ −6.5 百分点，门槛必然全杀；更矛盾的是表里写「_无入选_」却又给了 5 个导入码。修法：**删除 `rs20` 硬门槛**（它本是打分维度，再作门槛等于二次惩罚），成交额下限 3000 万 → **1000 万**只兜底极端地量。
- **短线「位置」维度 50% 权重空转**：该维度用钟形中心 `rs20 = +4` 打分，而候选 `rs20` 恒为负 ⇒ 恒 0 分。改为真正的**动量 45%**（20 日收益组内分位）+ 量能 30% + 波动活跃 25%，与长线的「低波动 + 反转钟形 + 贴近 MA20」形成可见口径分野 —— 两榜共用一套权重等于没区分。
- 同轮修复的展示层缺陷 11 处：空 `## 五榜概览` 标题、章节编号断档（③A/B/C 原是 H3 挂在 ②B 之下）、二次精选表序号乱序、②B 零入选却仍给导入码、`vol20=0.0119（小数）` 开发注记泄漏、「相对强弱 rs20」措辞错误、**③A / ③C 备注恒 `-`**（item 只有 `reasonSummary`，代码取了 `reason`）、命中追踪自带 H1 嵌套、③C 写「23 条」只列 10 条、止损线「8.0（百分点）」、表格单元格不换行。

### Verified

- 全量 `pytest packages apps -q`：**1293 passed**（基线 1269，+24 新用例：`test_secondary_pick.py` / `test_quotes.py` / `test_daily_digest.py` 与 `test_rankings.py` 扩充）。
- 真机双线（`--asof 2026-10-27`）：盘前 / 盘后均 `exit=0`、`COVERAGE asof=2026-10-27 ok`；②A **10 进 5**（畅联股份 / 浙商中拓 / 华锡有色 / 华润材料 / 清源股份），②B **10 进 5**（中国人保 / 春兰股份 / 致欧科技 / 苏豪弘业 / 森林包装）。
- OHLC 链路自算校验：`600301` 华锡有色 asof 收 44.78 → 运行日 `2026-10-28` 收 44.14 = **−1.43%**；Top10 当日平均 **−0.30%**，②B 池平均 **+0.87%**（基准 `000905` 仍不可用作指数，见下）。
- HTML 单 H1 实测 `h1=1`；`-pre` / `-post` 磁盘并存，`latest.md` 为最后渲染那份的别名。

### Known issues（本期记录、不修）

- `pytest packages/research`（**单包**跑）时 `test_persistence` 必挂：brief 库按 cwd 落到仓库 `data/`，会话级隔离守卫在全量口径下才生效。既存问题、与本里程碑无关，但说明**单包跑有污染生产数据的风险**，另立项查 conftest 加载顺序。
- PowerShell 工具内直接 `& .\scripts\ops\Invoke-DailyPipeline.ps1` 会 `exit=1` 且输出全空；须 `powershell -NoProfile -File` 子进程壳才拿得到输出。运维文档已按子进程写法给样例。

### Docs

- 新增 ADR `0083`，登记进 `scripts/check_docs.ps1` 的 `$required`；方案 `docs/plans/digest-pre-post-redesign.md` 与其索引状态同步为 `done`。
- `docs/ops/scheduler.md`、`docs/ops/daily-pipeline.md` 补 `-Session` 开关、新文件名与「`{asof}.*` 是别名」的语义；cron 示例与任务 XML 参数一并更新。

## [4.12.0] - 2026-10-23

### Added

- **盘后当日行情台账 `A6_day_quote`：开 / 高 / 低 / 收 + 涨跌 + 量化归因**（ADR [`0082`](docs/architecture/0082-day-quote-attribution.md)、契约 [`day-quote`](docs/contracts/day-quote.md)）。
  盘后台账此前只有账户层结论（`A3` 命中、`A4` 绩效），逐只标的的**开盘价 / 最高 / 最低 / 收盘价 / 涨跌幅**没有任何出口，更谈不上「为什么涨跌」。
  - 新单点 `stock_platform_research.day_quote`（纯函数：四价派生 / 四轴归因 / 汇总 / 渲染）+ CLI `stock-platform-day-quote`。
  - 四价分工：`close`/`volume`/`ma20` 走引擎 `market.db`（与主链同一截面）；`open`/`high`/`low` 走东财日线（经 `em_get`），落缓存 `data/quotes/ohlc-<asof>.json` ⇒ **同日复跑零网络且结果一致**。外部源不可用 → 该列 `—`、归因降级并在报告顶部标注，**不补零、不猜**。
  - **涨跌幅一律自算** `close / prev_close − 1`，不读 `daily_price.pct_chg`（该列在引擎库是混合尺度：股票多为小数、ETF 多为百分点，见 `pct_scale`）。
  - 「涨跌原因」= **量化归因**，四轴机械组合：分时形态（高开低走/低开高走/冲高回落/探底回升/窄幅整理/单边走强弱）、量价（放量/缩量 × 涨跌）、相对基准、均线位置（`vs MA20`）。payload 固定带 `attributionKind="quantitative"`，报告固定声明「平台无新闻/公告源，故不含且不编造消息面原因」。
  - 覆盖 = asof 归档 brief 的 picks + `data/holdings.json` 持仓；基准单独成行、**不参与**涨跌家数与平均涨跌统计。
  - 报告项注册进 `data/_reports/harness.py`（`--only A6_day_quote` 可单独跑）。

- **③B 操作建议给出可执行数量**（ADR [`0081`](docs/architecture/0081-concrete-order-sizing.md)）。
  ③B 长期只输出 `stop_loss(-x%)` 一行，没有股数、没有金额，读者无法据此下单。新增
  `position_sizing.plan_orders()`（**呈现侧**折算，`rules.py` / `backtest.py` **零改动**）：
  `exit` ⇒ 卖出全部**可卖**股数（`available_qty` 是硬约束，T+1 冻结部分记 `unsellable`）、
  单票上限 20% ⇒ 整手 `ceil` 减到上限内、`exit` 优先于 `trim`、**永不产生 `add`**
  （没有组合目标权重，买入量无处推导）、无价格的行跳过不猜。`rankings` ③B 条目补
  `suggestQty` / `suggestAmount` / `weightPct` / `weightAfterPct`，返回体增 `positionSizing`
  汇总；`daily_digest` ③B 表改为「动作 / 卖出数量 / 参考价 / 金额 / 权重」。
  真机（`2026-10-23` 盘前）：`000533` 退出 900 股 @8.670 = 7,803.00、`588080` 退出 400 股
  @1.299 = 519.60，合计 **8,322.60 元**。

### Fixed

- **③B 全 `hold` 不再渲染成空榜**：③B 长期显示「（0 条）/ 空（fail-closed）」，被读成数据故障；
  实际是**规则判定全部继续持有**（`held < min_hold=45` 时只有 −8% 硬止损能触发）。现 payload 增
  `holdingsReview`（`counts` + 逐只 `rows`），③B board **仍只收 `exit`/`trim`**（交易口径不变），
  但空榜时渲染「0 需操作 · N 只已复核」+ 逐只动作明细；`pending` 占满仍回落 fail-closed 文案。
  顺带补漏：**不在股票截面内、但账本自带 `price` 的标的**（典型是 ETF `588080`）此前被静默丢弃，
  现按 book 兜底列示；无价仍不列。
- **持仓快照价过期不得遮蔽 `asof` 收盘（③B 假阴性根因）**：`data/holdings.json` 的 `price` 是
  **券商截图快照价**，有效期只到文档顶层 `asof`。`enrich_holdings` 原先只在 `price is None` 时才用
  截面收盘补价 ⇒ 过期快照**永久遮蔽**最新收盘，把 −10.80% 的 `stop_loss` 抹成 `hold`，③B 报 0 条、
  看起来像「无需操作」。现 `load_holdings` 把顶层 `asof` 盖到每行（`holdings_asof`），
  `enrich_holdings(..., asof=)` 在 `holdings_asof < asof` 时弃用快照价、改用截面收盘
  （旧值留 `priceStaleSnapshot` 供审计）；同日/更新账本保留自己的价；截面无该代码（ETF）也保留 ——
  那是唯一价格。**教训：③B 报 0 条要先查账本 `asof` vs pipeline `asof`，别当「无需操作」。**
- **量能分母口径**：`volRatio` 用 `volume / mean(volume[t−20 .. t−1])`，**刻意排除当日**——否则当日爆量会把自己摊薄、比值被系统性压低。

### Known issues（本期记录、不修）

- **平台基准 `000905` 在引擎库里是「厦门港务」这只个股，不是中证500指数**。`A4.avgAlpha` 与 `A6.dayAlpha` 因此都是**相对该个股**的超额，**不能读作指数超额**。本版不改基准口径（改它会断掉历史台账可比性），改为在 `A6` 报告顶部**强制打印** `benchmarkWarning` 把缺陷显式化。
- 附带实测：`astock_http.get_daily` 对 `000001.SH` / `000905.SH` 会按代码规则回落成深市个股（后缀被 `normalize_symbol` 剥掉），**当前拿不到可靠指数序列**；`399006.SZ` 正常。修复（provider 支持强制市场后缀 + 基准口径迁移）另立里程碑。

### Verified

- 新增 `packages/research/tests/test_day_quote.py`：**20 passed**（四价派生、量能分母排除当日、MA20 窗口门槛、stale 标记、六类形态、相对基准三档、汇总去重与基准不入统计、渲染小节与警示）。
- 真机（`--asof 2026-10-22`，选股 10 + 持仓 4）：计涨跌 13 只，上涨 2 / 下跌 11 / 平盘 0，平均 −1.52%、中位 −1.75%；最强 `600963 岳阳林纸 +1.47%`、最弱 `000533 顺钠股份 −3.38%`；OHLC 命中 13/14（`588080` ETF 引擎库 0 行）。
- 全量 `pytest packages apps -q`：**1269 passed** / 0 failed（③B 呈现 +2、过期价 +2、可执行数量 +8、A6 +20，其余为既有用例）。


## [4.11.3] - 2026-10-16

### Fixed

- **推荐样本入账单点：盘前任务也带 `-SettleAfter`**（ADR [`0079`](docs/architecture/0079-settle-after-on-premarket.md)）。
  此前只有盘后任务（`15:30`）带 `-SettleAfter`，而 `-SettleAfter` 才是调 `_settle_after_pipeline` → `log_brief_decisions` + `settle_performance_log` 的开关。盘前与盘后**用的是同一个 T-1 `asof`**，所以盘前那次运行本已具备入账条件，只是没带开关 —— 结果是一个单点失效：**某天 15:30 盘后没跑成，该 `asof` 的推荐就永久丢失**（次日盘前的 `asof` 已前移，不会回头补）。
  - 真机实证：`runs.jsonl` 无 `2026-10-15 15:30` 的 `postmarket` 行，`recommend_decisions.jsonl` 因此缺 `2026-10-14`（33 行，应有 43 行）；同日 `10-15 08:31` 的 `daily` 成功（`exit=0`）却因没带开关而放过。
  - 修法：`daily` canonical 参数改为 `-MarketDb -PrevSession -SettleAfter -Digest`。两任务同 `asof`、写入幂等（`skip_existing=True`；结算只计 `settledNewly`）⇒ 是**冗余**而非重复：任一任务成功即入账，后跑的成为空操作。日线可见范围在 08:30 与 15:30 相同（都停在 T-1），结算结果不因提前而改变。
  - 边界不变：选股/`asof`/持有期（`5d`）/基准（`000905`）口径全部不动，仍 SIMULATE、`liveTradingEnabled=false`、纸面记账，`market.db` 仍只读（ADR 0058）。

### Added

- `packages/research/tests/test_scheduler_args_contract.py`：把 canonical 调度参数钉进测试（只读文本，不执行 PowerShell）—— 断言 `daily`/`postmarket` 预设都含 `-MarketDb -PrevSession -SettleAfter -Digest`、Windows XML 的 `<Arguments>` 与包装器预设一致、`Register-ScheduledTasks.ps1` 头注同步，且**活跃制品里不得残留旧参数** `-MarketDb -PrevSession -Digest`（历史记录 CHANGELOG / handoff 文档不受限）。这一缺陷的根因是「同一份 canonical 参数散在三处、只改一处不会报错」，Python 层测试此前无法覆盖。

### Changed

- 参数同步三处 + 文档：`scripts/ops/stock-platform-daily.xml`（任务计划程序实际执行的 `Arguments`）、`scripts/ops/Invoke-ScheduledRun.ps1` 的 `TASK_PRESETS['daily']`、`scripts/ops/Register-ScheduledTasks.ps1` 头注；`docs/contracts/ops-ledger.md` 任务登记表、`docs/ops/scheduler.md` 同步更新。

### Verified

- 新增测试 `test_scheduler_args_contract.py`：**5 passed**。
- 补录真机执行（`Invoke-ScheduledRun.ps1 -Task postmarket-catchup -Script .\scripts\ops\Invoke-DailyPipeline.ps1 -TargetArgs '-Asof 2026-10-14 -MarketDb -SettleAfter' -Asof 2026-10-14`，`exit=0`、14.8s、已入台账）：
  - `settleAfter.logged = 10`（`2026-10-14` 的 10 条以 `pending: true` 入账，`recommend_decisions.jsonl` 33 → **43** 行）；
  - 同一趟顺带结算了到期的 `2026-10-09` 批次（`settledNewly = 10`、`alphaSettledNewly = 10`、`settledCount 3 → 13`、`pendingCount = 30`）—— 该批次到期需 `2026-10-16` 截面，正是本次 18:30 回补补上的那天。
- 全量 `pytest packages apps -q`：**1235 passed**（v4.11.2 基线 1230 + 5 新用例，无回归）。

## [4.11.2] - 2026-10-16

### Fixed

- **日报「日期看起来没更新」——新增口径自证行**。盘前（08:30）/ 盘后（15:30）任务都带 `-PrevSession`，`asof` 恒为**上一交易日收盘截面**（当日 K 线要等 18:30 回补才进 `market.db`），但简报此前只在标题写「`# 每日简报 · 2026-10-15`」，**运行日无处可见** → 10-16 早上看到 10-15 的简报，极易被误读成「报告没更新 / 数据链滞后」。`daily_digest` 现在在标题下方输出一行口径自证，把「数据基准日」与「本简报实际生成时刻」并列：
  - `> **口径**：数据基准日（asof）**2026-10-15** —— 取该交易日**收盘截面**；本简报生成于 **2026-10-16 08:30:37 +08:00**。盘前/盘后任务取上一交易日收盘（当日 K 线尚未入库），这是设计约定，不是数据滞后。`
  - HTML 抬头同步：`数据基准日（asof）2026-10-15 · 环境 SIMULATE · 生成 2026-10-16 08:30:37 +08:00`。
  - 文件命名不变（`{asof}.md` / `latest.md`），仍是 asof 口径 —— 命名即真 asof，不撒谎。

### Changed

- `daily_digest.build_digest_text()` 的 `生成时间` 由**UTC 存档值**改为**本机时区**渲染（原 UTC 值保留在括号内，如 `2026-10-16 08:30:37 +08:00（存档值 2026-10-16T00:30:37+00:00）`）—— 旧值 `00:30` 看起来像凌晨，与 08:30 的实际运行时刻对不上。
- 新增 `daily_digest._human_ts()`：ISO 时间戳按本机时区渲染（`+0800` 规范为 `+08:00`），无法解析时原样回退，不影响其它字段。

### Verified

- 单元测试 `packages/research/tests/test_daily_digest.py`：**25 passed**。
- 全量 `pytest packages apps -q`：**1230 passed**（与 v4.11.1 基线 1230 一致，无新增、无回归）。
- 真实 `asof=2026-10-15` brief 重渲：`data/digests/latest.md` 与 `latest.html` 均正确显示「数据基准日 2026-10-15 / 生成 2026-10-16 08:30:37 +08:00」。

## [4.11.1] - 2026-10-15

### Added

- **早晨简报短线榜可复制代码块** —— `daily_digest` 现在为短线榜（②B）也产出「可直接复制的 6 位代码」区块（与长线当日推荐同源），并一并落成 `data/ths_import/{asof}_short.txt` + `latest_short.txt`（与长线 `latest.txt` 对称，每行 1 个 6 位裸码，供同花顺「导入自选 → 选择文件」直接导入）。长线 / 短线现在都有可整块复制的代码，满足「长线短线都要可以直接复制的代码」诉求。
- `daily_digest_cli` 增加 `--no-ths-short` 开关（与既有 `--no-ths` 对称），可关闭短线 txt 产出。

### Changed

- 短线榜区块渲染：在五榜概览的 ②B 短线榜后追加可复制代码块（fail-closed：无有效短线代码则整块省略）。

### Verified

- 单元测试 `packages/research/tests/test_daily_digest.py`：**25 passed**（新增 4 例，覆盖短线代码块与 `--no-ths-short`）。
- 全量 `pytest packages apps`：**1230 passed / 0 failed**（v4.11.0 基线 1226，+4 新用例）。
- 真实 2026-10-14 数据重渲简报：长线 `latest.txt` 与短线 `latest_short.txt` 均正确产出 6 位裸码。

### Docs

- `docs/ops/scheduler.md` / `docs/ops/daily-pipeline.md`：补充短线同花顺导入文件产出说明。

## [4.11.0] - 2026-10-15

### Added

- **收益归因 / 负收益根因诊断（`Y3`）—— `research.attribution` + CLI `stock-platform-attribution`**
  —— `Y1` 采纳闸门把「改进能不能进生产」解决后，暴露出一个此前无出口的问题：**为什么现在是亏的**
  （`R4` 近一年 `avgReturn=−0.38%`、`winRate=0.3735`；`Y1` 三窗基线**全部**跑输基准）。
  本模块把一段窗口的亏损分解成**互不重叠、各自可处置**的少数几项原因。
  - `build_signal_panel()` —— 逐日（当日截面）用 `score_lvrev` + `apply_entry_gates` 打分，
    **与生产 `screener_entry_provider` 同源**；每行携带 `fwd_{k}`（绝对前瞻收益）与
    `excess_{k}`（相对基准超额，基准缺日按日历 `ffill`）。
  - **两个样本集**：`gated`（全部过闸，用于评分单调性）与 `picks`
    （过闸且 `composite_score >= score_floor`，即候选池）。**曲线对两者各算一遍**——
    差值即**评分闸门本身**的贡献（`S3` 说 0.80 是全网格最差却始终无法证实处）。
  - **两口径硬分（真机教训）**：`horizon_curve()` 每行**同时**给出 `meanExcess`（相对）与
    `meanReturn`（绝对）；**边缘类**结论读 `meanExcess`（有没有技能），**持有期类**结论读
    `meanReturn`（拿在手里赚不赚钱）。近一年实测出现「绝对收益 10 日见顶后转负、而超额只在 40 日为正」
    —— 那是**熊市相对防守**，混用口径会给出「延长持有」的**错处方**，故必须分开归属。
  - `score_curve()`（Spearman = **秩的 Pearson 相关**，自实现，**不引 SciPy**：`research` 只依赖 numpy/pandas）、
    `cost_drag()`、`payoff_profile()`、`concentration()`（`by ∈ month/reason/assetClass/industry`，
    `reason` 按**规则名**分桶、行业按 `norm_code` 归一、`lossShare` 按亏损质量占比）。
  - **收益单位归一**：`book_replay` 的 `gross_ret` / `net_ret` 是**百分数**，模块内 ×
    `TRADE_RET_SCALE=0.01` 统一为小数（产物带 `"unit": "fraction"`）。
  - `diagnose()` —— **纯函数**（不碰 pandas / 引擎），7 类原因码 + **事前登记**阈值
    （`COST_SHARE_WARN=0.30` / `LOSS_CONCENTRATION_WARN=0.40` / `SPEARMAN_FLAT=0.05` /
    `PAYOFF_RATIO_WARN=1.0` / `WINRATE_WARN=0.50` / `MIN_MEANINGFUL_SAMPLE=20`）；
    排序键 = 严重度 → `_CAUSE_RANK`（事前登记；`impact` 跨量纲不可比，故**只作三级键**）→ |impact|；
    **样本不足的 horizon 标 `adequate=False` 且不参与结论**；`picks` 太薄时退用 `gated` 并写 `notes`；
    **单组分组永不构成「集中」**（`assetClass=stock` 恒 100% 的退化情形显式跳过）。
  - 报告 `data/strategy/attribution.{json,md,html}`（六节：信号有效性曲线 / 评分单调性 / 成本拖累 /
    赔率结构 / 亏损集中度 / 根因裁决）。
  - **只出归因**：`attributionNote` 显式声明**不改任何生产默认档、不写 brief / picks**；
    产出的「候选方向」仍须过 `Y1` 闸门 + 人工签核 ⇒ `Y3`（找方向）与 `Y1`（验方向）构成闭环。
- **架构 / 契约**：ADR [`0078`](docs/architecture/0078-loss-attribution.md) + 契约
  [`attribution`](docs/contracts/attribution.md)（输入 / 面板 / 各块 / 原因码与阈值 / 排序键 / 出口 / 边界）。
- **新公开面**：`attribution` 的 `build_signal_panel` / `select_set` / `horizon_curve` / `score_curve` /
  `cost_drag` / `payoff_profile` / `concentration` / `diagnose` / `render_attribution_markdown` /
  `attach_forward_returns` / `prepare_benchmark` + 常量（`SET_*` / `CAUSE_*` / `SEVERITY_*` / `BASIS_*` /
  `CONCENTRATION_KEYS` / `DEFAULT_*` / `TRADE_RET_SCALE` / `MIN_MEANINGFUL_SAMPLE`）进包公开面。
- **CLI**：`stock-platform-attribution`（`--years/--start/--end/--universe/--benchmark/--no-benchmark/
  --score-floor/--horizons/--buckets/--reference-horizon/--min-sample/--no-replay/--out-dir/--json/--no-write`）。

### Notes

- **真机实测（近一年 `2025-10-14`~`2026-10-14`，universe=stock，基准 `000905.SZ`）**：
  `gated=33450` 行 / `picks=11663` 行 / 85 笔成交。
  - 主因 **`hold_too_long`**：候选池**绝对**收益 3 日 +0.11%、5 日 +0.18%、**10 日见顶 +0.23%**、
    20 日 −0.86%、40 日 −1.63%，而**实际平均持有 32.5 天**。
  - 次因 `edge_only_long_horizon`（5 日超额 −0.89%，仅 40 日 +4.77% —— 基准同期跌更多，属**相对防守**）、
    `score_weak`（Spearman=−0.015，接近无关联）、`concentrated_loss`（`stop_loss` 占亏损 94%）。
  - **成本不是问题**（占毛收益 2.7%）、**赔率不差**（盈亏比 1.19、胜率 31.8%）⇒ 指向**持有期**。
- **跳号说明**：承接 `v4.10.0`（`Y1`）；`v4.8.0`（`R5` ETF 进宇宙）仍被**生产侧 ETF 回补**卡住而顺延。
  `T3` 数据质量体检两度顺延至 `v4.12.0`。
- 本轮实测发现并修掉两处**首版缺陷**：收益单位（百分数 vs 小数，读数放大 100 倍）与退化单组分组
  （`assetClass=stock` 恒 100% 被误判为「亏损集中」）。

## [4.10.0] - 2026-10-14

### Added

- **策略采纳闸门单点（`Y1`）—— `research.adoption_gate` + CLI `stock-platform-strategy-adoption`**
  —— `G/B/S/X/C/R/T` 七域把**研究侧**做到了相当完整，但**研究结论与生产默认档之间没有桥**：
  `S4` 行业中性化（单窗 `total_return` 0.3029 → 0.5257、`sharpe` 1.06 → 1.14）与
  `S3` 闸门（出厂 `min_pick_score=0.80` 的 `sharpe` 1.060 是**全网格最差**）都**实测改善却只诊断不改档**，
  `R4` 近一年 `avgReturn=−0.38%` 无出口 ⇒ **平台不改进 = 赚不到钱**。
  - `evaluate_adoption()` —— 基线档（= 生产档，`neutralize=None`）与候选档**共用同一引擎**
    （`run_neutralization_book` → `X4` 单点 `book_replay.replay_book`），在 `build_windows()`
    （默认近 3 个**互不重叠**的 1 年窗口）各跑一遍；**特征在全跨度上只算一次**（含 `ma20`/`ma60` 预热）
    再由 `slice_window()` 按日期切窗 ⇒ 边界**不损失**预热（`trade_date` 是 `datetime64`，
    两侧强制转 `Timestamp` —— 裸字符串比较会静默丢掉边界日）；
  - `AdoptionRule`（**事前登记**：`min_sharpe_margin=0.05` / `max_drawdown_tolerance=0.05` /
    `max_winrate_drop=0.05` / `min_trades=8` / `require_all_windows=True`）+
    `decide_adoption()`（**纯函数**，不碰引擎不碰 pandas）给 `adopt` / `reject` / `insufficient`；
    窗口 `pass` 需「夏普边际 + 回撤容差 + 胜率容差」**三项全过**，任一指标缺失**判否**；
    **样本不足不做结论**；
  - `CandidateSpec` + `BASELINE_SPEC` + `DEFAULT_CANDIDATES`（`neutralized` / `neutralized_capped` /
    `gate_070` / `neutralized_capped_gate_070`）+ `CANDIDATE_REGISTRY`；
  - 报告 `data/strategy/adoption_gate.{json,md,html}` —— 逐窗 `blockingChecks` 让**落选原因可读**；
  - **只出建议**：`adoptionNote` 显式声明**不改任何生产默认档、不写 brief / picks**
    （采纳是独立的人工签核步骤，计划中的 `Y2`）。
- **架构 / 契约**：ADR [`0077`](docs/architecture/0077-strategy-adoption-gate.md)（`Y` 域决定）+ 契约
  [`adoption-gate`](docs/contracts/adoption-gate.md)（候选 / 窗口 / 规则 / 裁决 / 出口 / 边界）。
- **新公开面**：`adoption_gate` 的 `AdoptionRule` / `BASELINE_SPEC` / `CANDIDATE_REGISTRY` /
  `DEFAULT_CANDIDATES` / `DEFAULT_RULE` / `DEFAULT_ADOPTION_OUT_DIR` / `DEFAULT_WINDOW_COUNT` /
  `DEFAULT_WINDOW_YEARS` / `CandidateSpec` / `build_windows` / `decide_adoption` /
  `evaluate_adoption` / `render_adoption_markdown` / `run_candidate` / `slice_window` 进
  `stock_platform_research` 顶层导出。

### Changed

- **路线图新增 `Y — 收益增强（Yield）` 域** —— `Y1` 策略采纳闸门（`v4.10.0`）/ `Y2` 采纳落地
  （`v4.10.1`，**须人工签核**）/ `Y3` 近期负收益根因诊断（`v4.11.x`）；
  `T3`（数据质量体检）目标 tag 因 `Y1` 先落地而**顺延至 `v4.11.0`**。

### 真机实测（2026-10-14 · 3 个互不重叠的 1 年窗口 · 全市场 stock 宇宙）

窗口：`2023-10-13~2024-10-12`（241 交易日 / 基线 106 笔）、`2024-10-13~2025-10-13`
（243 / 86）、`2025-10-14~2026-10-14`（243 / 84）。

| 候选 | 判定 | 通过窗 | Δ夏普(均) | Δ收益(均) | Δ回撤(均) | Δ胜率(均) |
|------|------|--------|-----------|-----------|-----------|-----------|
| 行业中性化 | **不采纳** | 0/3 | −0.241 | −2.61% | −0.090 | −9.23% |
| 中性化 + 行业上限 3 | **不采纳** | 0/3 | −0.232 | −2.55% | −0.091 | −9.11% |
| **闸门 0.70** | **不采纳** | **2/3** | **+0.274** | **+5.90%** | −0.025 | −1.66% |
| 中性化 + 上限 3 + 闸门 0.70 | **不采纳** | 0/3 | −0.327 | −4.82% | −0.105 | −9.42% |

**两条结论**：

1. **`S4` 中性化在样本外全窗恶化** —— 与其单窗（2024-09-02→2026-09-08 连续 2 年）
   「`total_return` 0.3029 → 0.5257」的结论**相反** ⇒ 单窗口的「大幅改善」**没有复现**。
   差异待归因（窗口切分方式 / 连续 2 年 vs 两段 1 年复利 / 起止日期），记为 `Y3` 的输入。
2. **`gate_070` 是唯一有正向证据的候选** —— w2（Δ夏普 **+0.846**、回撤 **−9.57% → −8.14%**）
   与 w3（**+0.374**、回撤 **−14.54% → −13.77%**）通过，仅 w1 未达标（−0.398、回撤恶化）；
   `require_all_windows=True` **如实拦下** —— 正是闸门的设计意图（单窗幸运不可挟持结论）。

⇒ **建议：维持生产基线** —— 本次没有候选能带着**样本外证据**进生产。
本次最大的价值不是「采纳了什么」，而是**拦住了一个在单窗看起来赢、样本外实际输的改动**。

## [4.9.1] - 2026-10-14

### Added

- **调度执行台账单点（`T2`）—— `research.ops_ledger` + CLI `stock-platform-ops-ledger`**
  —— `R3`/`T1` 的裁决只回答「循环**现在**健不健康」，**回答不了「任务到底跑没跑」**。
  真机事故（2026-10-13/14 `market.db` 连续两日无 bar、brief 停在 `10-12`）证明代价：
  排查**必须离开平台**去翻 Windows 任务计划程序，才发现 18:30 回补任务**压根没注册**。
  新增 append-only 台账 `data/logs/runs.jsonl`：
  - `record_run()` —— **本模块唯一写**，向台账**追加**一行
    `{ts,task,plannedAt,startedAt,endedAt,exitCode,durationSec,asof,note}`；
    **fail-open**（写失败返回 `recorded=false` + `reason`，绝不拖垮被调度的任务）、
    `task` 为空拒绝、超 `RUNS_MAX_RECORDS=400` 裁最旧；
  - `read_runs()` / `summarize_runs()`（**纯函数**）/ `collect_ops_ledger()` —— 逐任务给
    `lastRunAt` / `lastExitCode` / `lastDurationSec` / **`failureStreak`**（连续失败），
    汇总 `failingTasks`（≥`OPERATIONAL_FAILURE_STREAK=2`）+ `recent`；台账缺失 →
    `status="unavailable"`（fail-closed，**不假装有记录**）；
  - `render_ops_ledger_markdown()` —— 人读版（结论先行 + 逐任务表 + 最近执行表）。
- **调度包装器 `scripts/ops/Invoke-ScheduledRun.ps1`** —— 调度任务统一入口：从**任务预设**
  （`daily` 08:30 / `postmarket` 15:30 / `marketdb-backfill` 18:30）解析目标脚本与规范参数 →
  **子进程**运行目标（目标的 `exit` 无法绕过本层，**总能记到一行**）→ best-effort 追加台账
  （记失败**只报告、绝不改退出码**）→ **原样透传**目标退出码。
- **`loop_health` 新增两路信号**：`briefContinuity`（近 5 个**交易日**的 brief 覆盖，
  **缺日逐个列出** + `coverageRatio`；`status ∈ {ok,incomplete,empty,unavailable}`）与
  `opsLedger`（只读 `collect_ops_ledger` 的汇总）。
- **新公开面**：`ops_ledger.record_run` / `read_runs` / `summarize_runs` / `collect_ops_ledger` /
  `render_ops_ledger_markdown` / `default_ops_ledger_dir` / `default_ops_ledger_path` /
  `task_label` / `task_planned_at` / `TASK_SCHEDULES`（CLI `stock-platform-ops-ledger`）。
- **架构 / 契约**：ADR [`0076`](docs/architecture/0076-ops-run-ledger-and-brief-continuity.md)；
  契约 [`ops-ledger`](docs/contracts/ops-ledger.md)（台账格式 / 写入语义 / 失败判定 / 跳号说明）。

### Changed

- **裁决口径扩展：`briefContinuity` 与 `opsLedger` 两路信号并入 `roll_up_verdict`**，
  缺 brief 日 / 任务连续失败 → **`degraded`**。二者是**观测面**信号：说明流水线本身出问题，
  但过去的日子已跑完、当日仍能选股，没有 `coverage` 那种「物理上选不出票」的硬前提，
  故**只降级、永不 `blocked`**（与 hard-fail 不同档）。
- **出口同步**：API `LoopHealthResponse` 增 `briefContinuity` / `opsLedger`；
  Workbench `#health` 面板增两行 `kv`（brief 连续性 / 调度执行台账）；
  CLI `stock-platform-loop-health` 增 `--ops-ledger` / `--ops-recent` / `--brief-window`。
- **口径硬条款**：`ops_ledger` 的台账是**平台自有 `data/` 下的本地文件**，
  **永不写 `market.db` / 平台库**（承接 ADR 0058）；本模块**不 import** `loop_health`
  （保持单向依赖，`SECTION_*` 常量自持并有测试钉住与 `loop_health` 同字面量）。
- **跳号说明**：本里程碑编 `v4.9.1`（patch，加固），承接 `v4.9.0`（T1）；
  `v4.8.0`（`R5` ETF 进宇宙）因**生产侧 ETF 回补未完成**而顺延，按完成顺序直接编号。

## [4.9.0] - 2026-10-14

### Added

- **循环健康度出口与趋势台账（`T1`）—— 裁决可看、可追溯**
  —— R3 的 `research.loop_health` 只有 CLI 出口、且**无时间维度**（每次都是当下快照），
  日用循环「今天这样子是不正常，还是本来就是常态」无法回答。新增两块：
  - **只读 API 出口** `GET /api/ops/loop-health` —— 直接转发 `collect_loop_health()`；
    当 `coverage.status` 落在硬失败集合时 **fail-closed 返回 503**
    （`reason=loop_health_no_market_db`、`liveTradingEnabled=false`），不在无库时假装健康；
  - **趋势台账** `data/health/history.jsonl` —— 每次体检追加一行
    `{ts,asof,status,failed,warned}`；`summarize_history()` 按 `asof` 去重（同日重跑只算一次，
    取最新 `ts`）后给出 `daysRecorded` / `degradedStreak` / `blockedStreak` / `notOkStreak` /
    `streakSince` / `recent`，「连续几天 degraded」这类问题首次有数据可答。
- **Workbench `#health` 面板** —— 一键体检：绿/黄/红 裁决徽标 + 关键指标表 + 趋势文本 + 原始 JSON，
  失败时 fail-closed 显示中文提示。
- **新公开面**：`loop_health.default_loop_health_dir` / `default_loop_health_history_path` /
  `read_history` / `append_history` / `summarize_history`。
- **架构 / 契约**：ADR [`0075`](docs/architecture/0075-loop-health-export-and-history.md)；
  契约 [`loop-health`](docs/contracts/loop-health.md) 扩写（§4.6 趋势面字段 / §8 台账格式与读写规则 /
  §2 新增「台账例外（唯一写）」/ §5 coverage 判定表补 `error`+`unconfigured`）。

### Changed

- **裁决口径修复：`coverage` 硬失败集合补全**。v4.7.0 里 `coverage.status ∈ {error, unconfigured}`
  既不属于 fail 也不属于 warn，落入 `else` 分支被判 `ok` —— 即「**行情库打不开，却报供数正常**」。
  新增 `COVERAGE_HARD_FAIL`（`unavailable` / `empty` / `missing_table` / `error` / `unconfigured`）
  与 `COVERAGE_WARN`（`stale` / `thin`）常量，`roll_up_verdict()` 与 API 的 503 判定统一引用。
- **口径硬条款：台账是 `loop_health` 模块唯一的写操作**，只写平台自有 `data/` 目录，
  **永不触碰 `market.db`**；写失败 **fail-open**（不阻断体检），读失败 **不影响裁决**
  （`history` 不参与 `verdict` 计算，裁决仍只依赖六路信号快照）。

## [4.7.1] - 2026-10-14

### Added

- **绩效代理台账（`R4`）—— `research.performance_proxy` + CLI `stock-platform-performance-proxy`**
  —— 真实台账（`recommend_decisions.jsonl`）的 settled 样本受**日历硬约束**（每交易日 ≤ N 条
  + 必须等持有窗口走完），长期停在个位数 = `MIN_MEANINGFUL_SAMPLE(=20)` 的噪音区，
  「这套选股逻辑赚不赚钱」无法回答。新增只读单点把**回测成交**翻译成与真实台账
  **逐字段同形状**的决策行，一个 ≥1 年长窗即产出 ≥ 门槛的 settled 样本：
  - `trades_to_decision_rows()` —— `date`=建仓日（`equity_curve[entry_idx].date`）、
    `symbol`=`code`、`raw`=**扣费** `net_ret`（百分数字符串）、`holding`=`f"{held_days}d"`、
    `pending=false`、`source="backtest_proxy"`、`alpha=null`（**不编造**）；
  - `write_proxy_ledger()` —— **覆盖写**（代理是「一次回测的完整派生」，追加会重复计数）；
  - `build_proxy_view()` —— 真实 / 代理**并排视图**，两侧各跑一次 `performance_summary`
    （ADR 0068 单算术），各带 `ledgerKind` 与 `scale`；
  - `render_proxy_markdown()` —— 样本充分性 / 两侧指标 / **口径差异表**。
- **架构 / 契约**：ADR [`0074`](docs/architecture/0074-performance-proxy-ledger.md)、
  契约 [`performance-proxy`](docs/contracts/performance-proxy.md)（行形状 / **禁止混算**硬条款 /
  覆盖写语义 / CLI 出口）。
- 新增 CLI `stock-platform-performance-proxy`（`--years` 默认 1 / `--start` / `--end` /
  `--ledger` / `--briefs-dir` / `--universe` / `--real-log` / `--proxy-log` / `--out-dir` /
  `--no-write` / `--json`；只读 `market.db`），产出代理台账 + `data/performance/proxy_vs_real.{json,md,html}`。

### Changed

- **口径硬条款：真实与代理台账分栏陈列、禁止混算**。两者四维全不同（信号源 / 出场规则 /
  成本 / 窗口关系），`build_proxy_view` 顶层**不得出现**任何跨侧合并字段
  （`total` / `combined` / `merged` / `all` / `sum`），并显式 `comparability.combinable=false`；
  测试 `test_build_proxy_view_is_never_combinable` 逐名断言。
- 引擎与算术**零新增**：代理侧复用 `book_replay.replay_book`（ADR 0059 单循环）与
  `performance.performance_summary`（ADR 0068 单算术），本模块只做**翻译与呈现**。
- 路线图：`R4` 行标 done（`v4.7.1`）+ 修订记录；`docs/plans/README.md` 状态行推进到 `v4.7.1`。

## [4.7.0] - 2026-10-14

### Added

- **日用循环健康度单点（`R3`）—— `research.loop_health` + CLI `stock-platform-loop-health`**
  —— 平台日用循环由**五段**串成（供数 → 选股 → 命中记账 → 绩效结算 → 名称展示），
  每段各有守卫，却**没有任何单一入口**回答「今天的循环正不正常」。新增只读单点把
  **六路信号**聚合成**一个裁决**：
  - `coverage` —— **复用** `EngineSqliteProvider.coverage_snapshot()`（C2 单点，懒导入）；
  - `latestBrief` —— `open_brief_repository().list_recent(limit=1)`；
  - `hits` —— 两类 session 的 `summary()` 汇总（码数 / 累计次数 / 最近选日）；
  - `performance` —— `performance_summary()` 的 settled / pending / 样本量；
  - `symbolMaster` —— `open_symbol_master().stats()` 行数；
  - `nextSettlement` —— 由 brief asof 按交易日历推第 `holding` 个交易日（**提示，非承诺**）。
- **`roll_up_verdict()` 纯函数裁决**（`ok` / `degraded` / `blocked`）：coverage 的
  `unavailable` / `missing_table` / `empty` → **blocked**（没有供数就物理上选不出票），
  `stale` / `thin` → degraded；brief asof 落后供数（按交易日）→ degraded；
  绩效 `settledCount < MIN_MEANINGFUL_SAMPLE(=20)` → degraded；命中/名称缺失 → degraded。
- **人读报告** `render_loop_health_markdown()`：结论先行 + 「裁决明细」+「六路信号」+「缺失/异常说明」；
  CLI 默认写 `./data/health/loop_health.{json,md,html}`。
- **架构 / 契约**：ADR [`0073`](docs/architecture/0073-daily-loop-health-single-point.md)、
  契约 [`loop-health`](docs/contracts/loop-health.md)（段定义 / payload 形状 / 裁决规则表 / 边界）。

### Changed

- **`research` 顶层零 `providers` 依赖得到显式锁死**：`loop_health` 对
  `EngineSqliteProvider` / `get_trading_calendar` **只在函数内导入**；新增静态测试
  `test_providers_imported_lazily_only` 断言「所有 `stock_platform_providers` 出现处均缩进
  （即函数内）」。
- 路线图：`R3` 行标 done（`v4.7.0`）+ 修订记录；`docs/plans/README.md` 与 `docs/README.md`
  状态刷为「`C` 域全部收官 / `R` 域 `R1`–`R3` done / `P0` 线至 `v4.7.0`」。
- `check_docs.ps1` 登记两份新文档（`$required` 162 → 164）。

### Notes

- **CLI 退出码恒为 0** —— 体检**不是门禁**，裁决在 payload `verdict.status`；需要门禁的运维
  脚本读 JSON 判断。非 0 会与「循环可跑但需留意」的正常状态混淆。
- **硬约束**：零网络 / 只读（`market.db` 仍 `mode=ro`）/ fail-closed（缺件标 `unavailable`+`reason`，
  绝不用默认值冒充正常）/ **每段独立 try-except —— `collect_loop_health` 是 total function，永不抛**。
- **不替代既有守卫**：ADR 0070 的 ops asof 回落守卫仍在写 brief **之前**防伤害，体检是**事后**认伤害。
- **不抓数、不回补**：只如实报告供数滞后；成因治理仍归 `Invoke-MarketDbBackfill.ps1`。

### Verified

- 新增 `packages/research/tests/test_loop_health.py` **19 项**（fail-closed / 段隔离 /
  coverage 复用 C2 / 裁决规则表驱动 / 渲染 / providers 懒导入 / CLI 写与不写产物）。
- 真机一次运行（2026-10-14）：裁决 **`degraded`**，`warned=['coverage','performance']`
  —— `latestTradeDate=2026-10-12`（滞后 2 个交易日）、绩效样本 `3 < 20`；
  `hits=14 码 / 累计 20 次`、`symbolMaster=5237 行`、`nextSettlement=2026-10-19` 均正常。
- `scripts/check_versions.ps1` OK（`VERSION=4.7.0, packages=5`）；`scripts/check_docs.ps1` OK。
- 全量 `pytest packages apps`（`replay`）**1056 passed / 0 failed / 1 warning**（98.18s）。

## [4.6.2] - 2026-10-14

### Added

- **`C3` 重复实现收敛清单（[`docs/plans/duplicate-implementation-convergence.md`](docs/plans/duplicate-implementation-convergence.md)）**
  —— 承接 `C1` 双线边界，把「选股打分 / 因子库 / 入场闸门 / 回测引擎 / 交易规则 / 费用模型 / 资产类型 /
  榜单 / 命中追踪 / 行情抓取 / 行情真相源 / 基本面名称 / 多 Agent / 报告渲染 / 交易日历 / `.env` /
  调度 / 报告跑批」**18 项**逐条登记，每项标注 **平台侧权威单点｜引擎/上游参考实现｜判据｜处置**
  （**16 项已收敛、2 项按边界保留**）。**只定边界、不删代码**（承接 C 域约束）；收敛证据逐条给出
  （对象同一性断言 / 8 场景 sha256 逐位一致 / 跨线静态互测 / 只读派生）。

### Changed

- 路线图：`C3` 行标 done（由 `R2` 收口）—— **C 域（C1/C2/C3）全部收官**；`R2` 行标 done；
  修订记录追加一行。
- 新文档登记进 `scripts/check_docs.ps1` 的 `$required` 与 `docs/plans/README.md` 索引表。

### Verified

- `scripts/check_versions.ps1` OK；`scripts/check_docs.ps1` OK（新文档全部登记、无断链）。
- 全量 `pytest packages apps`（`replay`）**1037 passed / 0 failed**（R2 为纯文档收口，无新增测试）。

## [4.6.1] - 2026-10-14

### Added

- **ADR [`0072`](docs/architecture/0072-symbol-master-name-authority.md) —— 代码 ↔ 名称主数据表
  `symbol_master` 为名称解析的唯一权威**：补齐 `v4.6.0` 能力落地时缺失的架构决策记录
  （三层根因 / 存储只存真名 / 展示走 `display_name` / 未知 `—` / 四档优先级 / 历史回填）。
- **契约 [`symbol-naming`](docs/contracts/symbol-naming.md)**：`symbol_master` 表结构、解析优先级、
  出口清单，以及「**不做中英双语**」的诚实边界（只读源 `fundamentals` 实测无英文字段，
  故映射为 6 位代码 ↔ 中文简称，需要英文名须另找数据源、**不得臆造**）。

### Changed

- **`scripts/release_tag.ps1` 支持中文 tag 注释**：新增 `-MessageFile`（按 UTF-8 读入，经
  `git tag -a -F <utf8-tempfile>` 建 tag），绕开 PowerShell 5.1 原生参数按 ANSI/GBK 编码导致的
  中文乱码；`-Message` 亦改走同一 UTF-8 临时文件路径（向后兼容）。临时文件写在**仓库外**
  （`$env:TEMP`），不污染工作树、不影响 `release_tag.ps1` 的「工作树必须干净」前置检查。
- **路线图新增 `R` 域（收尾与加固）**：把「文档债 / 唯一未闭合的 `C3` / 绩效样本不足（3 条 < 20 = 噪音）/
  循环裁决面缺失」四个收尾项显式立项（`R1`–`R5`）；补 `v4.6.0` 修订记录行；
  `docs/plans/README.md` 状态列刷新为「G/B/S/X/L/C/**R** 七域」。

### Fixed

- **`v4.6.0` 文档债** —— 名称根治此前只改 `CHANGELOG`，**未落 ADR / 契约 / 路线图**
  （全库 grep `symbol_master` / `4.6.0` 零命中），违反本仓「改行为必须同步文档」硬规则；本次补齐。

### Verified

- `scripts/check_docs.ps1` 登记两份新文档（`$required` 160 → 162）。
- 全量 `pytest packages apps`（`replay`）**1037 passed / 0 failed**（R1 为纯文档 + 工具收口，
  无新增测试）。
- `release_tag.ps1 -MessageFile` 编码自检：`git cat-file tag` 以 UTF-8 解码，中文正文与 `tagger`
  姓名**均无乱码**。

## [4.6.0] - 2026-10-14

### Added

- **本地「代码 ↔ 名称」主数据表 `symbol_master`（名称显示根治）** —— 新增模块
  `stock_platform_research.symbol_master` + CLI `stock-platform-symbol-master`
  （`--refresh` / `--stats` / `--lookup` / `--list`）。表存平台 SQLite（与 brief 归档同库），
  数据源为引擎**只读** `market.db.fundamentals`（当前 5237/5237 代码全覆盖），刷新幂等。
  `display_name()` 是名称解析的**唯一入口**，优先级 = 记录里的真实名称 > 显式 `name_map`
  > 本地表 > 占位符 `—`；`daily_cli` 每次跑批顺带刷新该表（失败静默，名称是装饰性的）。
  `stock-platform-hits --backfill-names` 可回填历史行。

- **当日战绩报告（选股 → 次日收盘 · 1 日窗口）** —— 新增 `stock_platform_research.sameday`
  + CLI `stock-platform-sameday`：对归档 brief（当日实际下发的榜单）按 `holding=1d`
  结算，给出平均收益 / 胜率 / 最好最差 / `avgAlpha` / 跑赢基准率（基准默认中证500 000905）。
  `rolling_review` 同步补齐 `avgRawReturn` / `upRate` / `best` / `worst` / `avgAlpha` /
  `beatBenchmarkRate`（纯新增键，既有调用不变）。报告位 `A5_sameday`。

### Fixed

- **命中追踪「名称 = 代码」** —— `hit_tracking._clean_name()` 过去在名称缺失时**回退成代码**，
  于是「未知」被渲染成「看起来正确」的错值（A3 报告印 `000801 | 000801` / `601318 | 601318`）；
  又因 `hit_tracking` 按 `UNIQUE(code, session_type, pick_date)` 去重，后续跑批补齐的名称
  **永远写不回去**。现在：存储层只存真实名称（未知存空，绝不写代码），展示层统一走
  `display_name()`（未知显示 `—`）；已回填历史 14 行 `hit_summary` / 20 行 `hit_tracking`。
  修复后 A3 正确显示「四川九洲 / 中国平安 / 一拖股份」等中文名。

### Changed

- **panel CSV 代码前导零丢失修复（读取单点）** —— 新增 `batch.load_panel_csv()`，把 `symbol` / `code` /
  `ts_code` 固定按文本读入。此前 `stock-platform-rankings`、`stock-platform-brief`、
  `batch.score_cross_section_csv` 走裸 `pd.read_csv`，代码列被推断为 `int64`，**前导零被静默吃掉**
  （A2 报告印出 `801` / `2658` 而非 `000801` / `002658`），并使 ③A/③B 持仓匹配找不到截面行
  （例：持仓 `000533` 与 `588080` 无法进入 ③A）。三处调用统一改走该单点。

### Verified

- `packages/research/tests/test_batch.py` 新增 `test_load_panel_csv_keeps_zero_padded_codes`
  （回归锁：`000533` 不被读成 `533`，写回仍保留前导零）。
- 新增 `test_symbol_master.py`（12 例）、`test_sameday.py`（4 例）与 `test_hit_tracking.py`
  名称回归 6 例（含「未收录 → 占位符，绝不回显代码」「回填幂等」）。全量 `pytest`
  **1037 passed**；`scripts/check_versions.ps1` OK（VERSION=4.6.0, packages=5）。

## [4.5.2] - 2026-10-13

### Added

- **同花顺导入文件（txt）** —— `daily_digest` 新增单点 `write_ths_import(codes, *, asof, out_dir)`，
  在跑批时把当日推荐另落成 `data/ths_import/{asof}.txt` + `latest.txt`：**每行 1 个 6 位码**、无表头无名称，
  供同花顺「导入自选 → 选择文件」直接导入（用户实测 txt 通道可用）。`build_digest` 新增 `emit_ths`
  （**库默认 `False`**）+ `ths_dir`；CLI 默认产出（`--no-ths` 退回、`--ths-dir` 覆盖目录）。
  目录默认取 digest 目录的**同级** `ths_import`（`data/digests` ↔ `data/ths_import`）。无推荐则不产出
  （fail-closed，不生成占位文件）；并顺带清理目录内遗留的 `*.sel`（项目已统一只用 txt）。
  代码归一化复用 `_ths_codes`（同一去重/6 位裸码规则，与日报「同花顺导入」行**同源**）。

### Changed

- `scripts/ops/Invoke-DailyPipeline.ps1`：`-Digest` 语义不变但产物增加 ths txt；设 `PYTHONIOENCODING=utf-8`
  使子进程日志保持 UTF-8。

### Docs

- [`docs/ops/scheduler.md`](docs/ops/scheduler.md) / [`docs/ops/daily-pipeline.md`](docs/ops/daily-pipeline.md)：
  `-Digest` 行与「用户可读日报」小节补 ths 导入文件说明。

### Verified

- `packages/research/tests/test_daily_digest.py` 新增 **7 项**：`emit_ths` 产出 `{asof}.txt`+`latest.txt` /
  默认不产出 / `--ths-dir` 覆盖 / 清理遗留 `.sel` / 无代码返回 `None` / CLI 默认产出 / `--no-ths` 关闭。

## [4.5.1] - 2026-10-13

### Added

- **日报「同花顺导入」行** —— `daily_digest` 在「当日推荐」顶部新增可**整块复制**的 6 位代码块，
  直接粘进同花顺手机版「自选 → 导入」。**手机版一次仅支持导入 5 只** ⇒ 按 5 只/行分组
  （`THS_IMPORT_PER_LINE = 5`），超出自动换行、逐行粘贴；代码归一化为 6 位裸码（去 `.SZ` / `.SH`）、
  按推荐序去重、仅保留合法 6 位码；无有效代码则整块省略（fail-closed，不生成占位行）。
  Markdown 与 HTML 双份同步生效（代码块 → `<pre><code>`）。

### Docs

- [`docs/ops/scheduler.md`](docs/ops/scheduler.md)「用户可读日报（digest）」补「同花顺导入行」说明。

### Verified

- `packages/research/tests/test_daily_digest.py` 新增 **4 项**：导入行存在且为裸 6 位码 / 12 只按 5 分组为 3 行 /
  后缀剥离（`600519.SH` → `600519`）/ 无推荐时不出现导入块。

## [4.5.0] - 2026-10-13

### Added

- **报告 HTML 化（ADR [`0071`](docs/architecture/0071-report-html-theme.md)）** —— 新增**零依赖**渲染器
  `research/report_html.py`（`markdown_to_body` / `render_report_html` / `render_markdown_file`）：
  仅用 stdlib（**不引入 `markdown` / `jinja2`**），**先 `html.escape` 再套标签** ⇒ 用户文本永不产生原始
  HTML；畸形 Markdown fail-open，渲染永不抛。主题 `LOCAL_THEME` 的 `:root` 配色与仓内
  `static/report-templates/a-share-preopen.html` **逐 token 相同**（`--bg:#0b0e14` / `--accent:#4d8dff` /
  `--gold:#f5c451` / `--up:#ff4d4f` / `--down:#00b578`），并有测试直接读模板比对焊死防漂移。
  行内**带符号百分比**按 A 股约定自动着色（`+x%` 红 / `-x%` 绿，`(?<![\w>])` 反向断言避免误吞区间），
  `--no-color` / `colorize=False` 可关。
- **新 CLI `stock-platform-report-html`** —— `--in FILE` 单文件或 `--dir DIR` 整目录把 `.md` 重渲染为
  模板样式 `.html`；另有 `--title` / `--subtitle` / `--source` / `--badge` / `--theme`。
- **digest 双格式产出** —— `stock-platform-digest` **默认同时写** `{asof}.html` 与 `latest.html`
  （新增 `--no-html` 退回只写 Markdown）；`build_digest(emit_html=…)` 库默认仍为 `False`（纯增量），
  返回值新增 `htmlPath` / `latestHtmlPath`（**旧键全部保留**）。⇒ 两个计划任务与
  `Invoke-DailyPipeline.ps1 -Digest` **XML / 参数零改动**即开始出 HTML。

### Changed

- **报告跑批器改用单点** —— `stock-platform-report-sweep` 的跑批脚本删除私有浅色主题渲染器
  （`_CSS` / `md_to_html`），改为 import `stock_platform_research.report_html` ⇒ **样式只此一处定义**。
- `Invoke-DailyPipeline.ps1 -Digest` 的 trace 文案更新为「markdown + html」。

### Docs

- ADR [`0071`](docs/architecture/0071-report-html-theme.md)（新增，已登记进 `scripts/check_docs.ps1`）。

### Verified

- `packages/research/tests/test_report_html.py` 共 **8 项**：核心块渲染 / 用户文本转义 / 红涨绿跌 /
  hero+block+footer 结构 / 未知主题回落 `local` / **主题 token == 报告模板** / 单文件与整目录 CLI。
- 历史报告按新主题**重渲染**，每项 `.md` 与 `.html` 同目录、可离线打开（无 CDN / 无外链）。

## [4.4.0] - 2026-10-12

### Added

- **供数覆盖率守卫（默认开启）**（ADR [`0070`](docs/architecture/0070-daily-loop-self-sufficiency.md)）——
  `scripts/ops/Invoke-DailyPipeline.ps1` 在跑流水线**之前**复用 C2 单点
  `EngineSqliteProvider.coverage_snapshot()` 校验解析出的 `asof`：可用 → 照常；不可用 →
  **回落到 `latestTradeDate` 并 WARN**；回落目标也不可用 → **退出 1，拒绝写 brief**；
  `-StrictCoverage` → 不回退、直接失败（验收 / 取证用）。守卫只防「静默写空」，不改 CLI / 策略语义。
- **行情回补计划任务（成因端）** —— `scripts/ops/Invoke-MarketDbBackfill.ps1`（包一层引擎自己的
  `empirical/backfill_market_daily.py`，幂等 + 严格顺序 + CPU-safe）+ `stock-platform-marketdb-backfill.xml`
  （每日 **18:30**，`ExecutionTimeLimit=PT20M`）+ `Register-ScheduledTasks.ps1 -Backfill`。
  **边界不变**：写库的仍是引擎脚本、平台仅只读（ADR 0058）。
- **中文名直出（装饰性契约）** —— `backtest_cli.load_engine_names()`（读 `fundamentals.name`，**fail-open**）
  → `daily_cli._build_name_map()`（key 归一到 6 位核）→ `run_daily_pipeline(name_map=…)` →
  `build_premarket_brief` / `build_rankings`。**只有确实取到名称时才写 `item["name"]`**，取不到不写键
  ⇒ 「无 map」与「有 map 但未命中」两条路径下 brief、picks ledger、命中周期、绩效 JSONL **逐字节不变**。
- **持仓自动探测** —— `Invoke-DailyPipeline.ps1` 新增 `-Holdings` / `-NoHoldings`，默认探测
  `data\holdings.json`：存在则追加 `--holdings`，不存在则不传（③A / ③B 保持空，fail-closed 不猜）；
  `data/` 已 gitignore ⇒ 真实持仓天然不入库，计划任务 XML **零改动**。

### Fixed

- **「静默空 brief 遮蔽真 brief」** —— 此前供数滞后时面板为空，仍会写出一份 `picks=[]` 且 `asof`
  最新的 brief；日报 `list_recent(limit=1)` 取到它 ⇒ 早上看到「当日无推荐」，而真相是「数据没到」。
  覆盖率守卫在**写盘之前**拦下：回落到可用旧截面或响亮失败，**绝不写空**（ADR 0070 §P1）。
- **测试隔离守卫不自愈** —— 会话级 `conftest.py` 守卫原只在 import 时设一次；一个测试用
  `os.environ.pop` 收尾即让后续测试全部回落仓库 `data/`。改为 autouse 函数级 fixture **每个测试前
  重新断言**，并把该测试改用 `monkeypatch`（ADR 0069 修订）。

### Changed

- `daily_digest` 推荐表新增「名称」列（`| # | 代码 | 名称 | 综合分 | 收盘 | 理由 |`）。
- `scripts/check_docs.ps1` 登记 ADR `0070`。

### Verification

- 全量 `pytest packages apps`（`replay`）**995 passed / 0 failed**（989→995，**+6**）；
- 全量测试前后四类生产存储（`daily_briefs` / `hit_tracking` / `hit_summary` /
  `recommend_decisions.jsonl`）**行级逐位不变**；
- 守卫真机：`asof=2026-10-12`（已回补 / 5224 行）→ `COVERAGE ok` 照常；asof 超出库尾
  （`2026-10-13`）→ 回落 `latestTradeDate=2026-10-12` 且 `EXIT=0`；同输入 `-StrictCoverage` →
  `Write-Error` + `EXIT=1`（拒绝写 brief）；
- 日报重渲染 `data/digests/2026-10-12.md`：推荐表与五榜均带中文名（如 `000801 四川九洲`、
  `601318 中国平安`）。

## [4.3.1] - 2026-10-12

### Fixed

- **测试套件曾写入生产数据目录**（ADR [`0069`](docs/architecture/0069-test-data-isolation.md)）——
  `test_daily_pipeline.py::test_daily_cli_settle_after_logs_performance` 驱动**整个 CLI** 却只钉住
  `STOCK_PLATFORM_PERFORMANCE_LOG`，未钉 `STOCK_PLATFORM_DB_URL` → CLI 走 cwd 默认路径 +
  `persist_db=True`，把 fixture brief（`asof=2026-09-02`、`universeSize=3`）**upsert 进生产
  brief 存档** `./data/stock_platform.db`，并写入该 pick 的命中明细/汇总行。
- **日报被污染行遮蔽而变空**：被写入的 `asof=2026-10-12` 行（`picks=[]`）日期最新，于是
  `daily_digest` 的 `list_recent(limit=1)` 取到它 → `latest.md` 渲染「当日推荐（0 条）」，
  **真实 brief（`2026-10-09`、5235 只、10 条 picks）被遮蔽**（该行本身并未被删）。
- **命中汇总残留**：`hit_summary`（日报「命中追踪」实际读取的表）与 `hit_tracking`（周期明细）
  是两张表，只清明细表会让 fixture 代码继续显示。

### Added

- **仓库根 `conftest.py`（会话级数据隔离）**：import 时把 `STOCK_PLATFORM_DB_URL` /
  `STOCK_PLATFORM_PERFORMANCE_LOG` 重定向到会话临时目录，`atexit` 还原；
  `STOCK_PLATFORM_TEST_DATA_DIR` 可保留现场。
- **回归测试** `test_persistence.py::test_session_never_resolves_the_repo_data_dir`：
  会话解析出的 brief 库 / 绩效台账若落在仓库根 `data/` 下即失败。

### Changed

- `test_daily_cli_settle_after_logs_performance` 再显式钉住 `STOCK_PLATFORM_DB_URL`
  （**凡是驱动 CLI / pipeline / workbench 路由的测试都必须钉住存储位置**）。
- `scripts/check_docs.ps1` 补登记 ADR `0067`（此前遗漏）与 `0069`、`handoff-v4.3.1.md`。

### Verification

- 全量 `pytest packages apps`（`replay`）**989 passed / 0 failed**（988→989，+1）；
- 全量测试前后四类生产存储（`daily_briefs` / `hit_tracking` / `hit_summary` /
  `recommend_decisions.jsonl`）**行级逐位不变**；
- 数据清理（先备份、后独立复核）：brief 行 −2、命中明细 −2、命中汇总 −2；
  `data/digests/latest.md` 恢复渲染真实 brief（`2026-10-09`，命中追踪 10 只）。

## [4.3.0] - 2026-10-12


### Added

- **绩效 PnL 闭环（收益归因）** —— 从「计数」推进到「用户可见收益数字」，回答"这套推荐逻辑赚不赚钱"：
  - **基准 alpha**：`alpha = raw − benchmark`，基准默认 **中证500 `000905`**（`market.db` 无
    `000300`，`000905`/`000852` 完整）→ 环境变量 `STOCK_PLATFORM_BENCHMARK_SYMBOL` 可覆盖；
    `raw` 与 `alpha` 共用**同一** `_holding_window`（入场/出场日期一致，杜绝口径错配）
  - **alpha 回填**：已结算但 `alpha` 为 `null` 的历史台账，在下一次带基准的结算中补齐（`alphaSettledNewly`）
  - **收益归因 `build_attribution`**：`winRate` / `avgReturn` / `medianReturn` / `avgAlpha` /
    `beatBenchmarkRate` / `best` / `worst` + `byRank[]` / `byScore[]`（等数量分桶）/ `byDate[]` /
    `equityCurve[]`；`performance_summary` 增 `attribution` + `benchmarkSymbol`（原键不变）
  - **持有期单点** `DEFAULT_HOLDING = "5d"`：`brief_picks_to_pending` / `log_brief_decisions` /
    `align_fills_to_performance` 统一引用；`daily_cli` 不再硬写 `"1d"`（记账=结算=日报三口径合一）
  - **日报显示真数字**：`daily_digest.performance_summary` 增 `returns`（复用 research 单点 口径），
    「绩效台账」新增「收益概览（已结算 N 条 / 基准 …）：胜率 …，平均收益 …，跑赢基准 …，最好 …、最差 …」
  - **出口**：CLI `stock-platform-performance`（`--settle-daily` / `--benchmark` / `--no-benchmark`）·
    盘后任务 `-SettleAfter` 带基准结算 · `GET/POST /api/research/performance[/settle]`
  - **真机实测**：3 条 pending → `settledNewly=3`（`+0.38%` / `+2.96%` / `-1.76%`）；
    再结算 `alphaSettledNewly=3`（`+2.41%` / `+4.99%` / `-7.72%`）；`avgReturn` +0.53% /
    `beatBenchmarkRate` 0.667；日报出现真实收益行
  - 契约 [`docs/contracts/performance-pnl.md`](docs/contracts/performance-pnl.md) + ADR
    [`0068`](docs/architecture/0068-performance-pnl-closed-loop.md)；ADR `0033` 补「修订」节

### Changed

- `performance_summary` 返回体新增 `attribution` / `benchmarkSymbol` 键（**向后兼容**，旧键不变）；
  `settle_pending_entries` / `settle_performance_log` 新增 `benchmark_get_daily` / `benchmark_symbol`
  可选参数（缺省行为与 `v4.2.0` 逐位一致）
- 记账持有期统一为 `DEFAULT_HOLDING`（`5d`）：`daily_cli --settle-after` 原写 `1d`，本轮修正

## [4.2.0] - 2026-10-12

### Added

- **每日调度正式上线（双任务，本机已注册并实测触发成功）**
  - 盘前 `stock-platform-daily`（08:30）：`-MarketDb -PrevSession -Digest` —— 整市快路径选股 + 人读日报
  - 盘后 `stock-platform-postmarket`（15:30，新 XML）：`-MarketDb -PrevSession -SettleAfter -Digest` —— 绩效记账/结算 + 命中追踪 + 日报
  - `scripts/ops/Register-ScheduledTasks.ps1`：注册 / `-Status` / `-Unregister` / `-RunNow` 一体化，幂等可重跑，当前用户（InteractiveToken + LeastPrivilege）**无需管理员**
  - **实测**：任务计划器按需触发 → `result=0x0`；整市 brief（5210 行截面 / Top10）+ digest 全链产出
- **`-PrevSession`（调度必用）**：包装脚本用 `TradingCalendar` 把 asof 解析为**前一交易日** —— market.db 由生产侧晚间回补，早/午后时点绝无当日 bar，直接用今天必得空面板（实测 asof=2026-10-12 废 brief `panelSize=0` 即此因）
- **用户可读日报（第 2 块砖）**：新增 `daily_digest.py` + CLI `stock-platform-digest`
  - 从**权威 SQLite brief 仓库**（ADR 0049）渲染 Markdown：环境/数据源/宇宙概览、当日推荐表（综合分/收盘/理由）、五榜概览、命中追踪（X3 `format_hit_report` 单点渲染）、绩效台账 pending/settled 计数
  - 产物 `data/digests/{asof}.md` + `latest.md` 指针；查无 brief 时 **fail-closed 占位说明，不编造数字**
  - 绩效 JSONL 读取为 best-effort：缺失/损坏不阻断日报
  - 包装脚本 `-Digest` 开关接入；日报渲染失败**不翻转**流水线退出码
- 调度文档 `docs/ops/scheduler.md` 重写：双任务、注册脚本、digest、PrevSession 决策、**两个实测注册坑**（PS 5.1 GBK 误读 UTF-8 XML → 用 `ReadAllText`；`-Xml` 参数拒绝编码声明 → 剥 `<?xml … ?>`）

### Fixed

- `Invoke-DailyPipeline.ps1`：CLI 非零退出时此前仍可能走 digest 分支 / 错误透传 exit code —— 现在显式捕获 `cliEc`，失败即退出，成功才渲染 digest

## [4.1.8] - 2026-10-12

### Added

- **WorkBuddy MCP 桥接（补齐写缓存的那一半）**：新增 `packages/research/.../workbuddy_bridge.py` —— 调 `westock` CLI 取 `kline` / `quote`，解析其 Markdown 表，再经**已有的规范写入器** `write_daily_cache` / `write_realtime_cache` 落盘到 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`
  - **此前 `workbuddy` provider 只读缓存、但没有任何东西写入它**（docstring 提到一个从未实现的 "MCP bridge"）→ "workbuddy 模式"可启动、可路由，却永远拿不到真实数据
  - **schema 单点**：桥不自己拼 JSON，交给规范写入器，与 provider 读路径共享同一定义点，杜绝格式漂移
  - 字段映射：`last` → `close`（改名）；`change_pct` 为 percent 标度、带 `pct_unit="percent"`；**`exchange` 丢弃**（是换手率 %，不是交易所代码 —— 语义不同不得挪用）
  - 批量：`westock` 支持逗号分隔代码列表，桥按 40/30 一批合并调用（避免数千次进程启动）
  - **可单测**：解析与写入是纯函数；subprocess 经**可注入 runner**，测试零进程零网络
- **三条守卫（防静默错误数据）**
  - **无 `code` 列的多代码批** → 记 `warnings` 并**跳过**，绝不把 bar 静默安到第一个 symbol（只有单代码批允许无列归因）
  - **裸码碰撞**（`sh000001` 指数 vs `sz000001` 平安银行，都归一为 `000001`）→ 抓取前**拒绝**歧义对，其余 symbol 照常桥接
  - **显式 `--bin` 路径不存在** → 报错，绝不静默回落 PATH 上另一个二进制（裸命令名才走 PATH）
- **CLI**：`stock-platform-workbuddy-bridge`（`--symbols` / `--symbols-file` / 默认取平台宇宙、`--datasets daily,realtime`、`--limit`/`--start`/`--end`/`--period`/`--adjust`/`--asof`/`--timeout`/`--dry-run`/`--json`/`--fail-on-error`）
- **workbuddy 模式启动**
  - `scripts/ops/Invoke-WorkbuddyBridge.ps1` —— 两步编排：先 bridge 刷缓存，再以 `--provider workbuddy` 跑 daily（`-FromMarketDb -Top N` 从 `market.db` 取成交额 Top-N；默认缓存目录 `data/workbuddy_cache`）
  - `start-workbuddy.bat` —— 双击版，可选位置参数 `symbols` / `datasets`

### Changed

- **`daily_cli` 直接接受 `--provider workbuddy`**（别名 `workbuddy_mcp`），与 `market_db` 同一模式 —— 预设**本身不足以**让 daily 走 workbuddy：`Invoke-DailyPipeline.ps1` 把 `--provider` 默认成 `replay` 并显式传参，会覆盖 `STOCK_PLATFORM_PROVIDER_PRESET`（实测确认该覆盖）
  - 缺 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` 或目录不存在 → 中文 fail-closed 报错并指向 `stock-platform-workbuddy-bridge`
  - `--provider` 白名单错误信息补上 `workbuddy` / `market_db`

### Verified

- **真机 CLI**：`westock 0.0.4 channel=workbuddy`（`~/.local/bin/westock.exe`，2,600,960 B，SHA256 校验装自官方发布源）
- **真机桥接**：4 代码 × 2 数据集 → **8/8 ok / 124 bars / 0 failed**
- **真机往返**：bridge → `WorkbuddyProvider` → **90 契约行**，跨度 `2026-08-21 → 2026-10-09`，`source="workbuddy"`；percent→decimal `0.5741405808` → `0.005741405808`
- **真机碰撞守卫**：`sh000001`+`sz000001` → `WARN code collision on 000001` + 跳过，`600519` 照常桥接
- **真机全链路**：`Invoke-WorkbuddyBridge.ps1` → bridge 6/6 ok / 183 bars → daily `provider="workbuddy"`、`ok: true`、`stage="brief"`
- 全量 `pytest packages apps`（`replay`）**972 passed / 0 failed / 0 errors / 0 skipped**（943 → 972，+29）

### Docs

- 新增 ADR [`docs/architecture/0067-workbuddy-mcp-bridge.md`](docs/architecture/0067-workbuddy-mcp-bridge.md)
- 扩写 [`docs/contracts/data-source-adapters.md`](docs/contracts/data-source-adapters.md)：新增 §1.4（桥接 + 字段映射表 + 三条守卫 + 实测证据）与 §4.1（workbuddy 模式启动）

## [4.1.7] - 2026-10-10

### Added

- **缺口容忍（`P0-4` 修复）**：`RefreshItemResult.is_gap` / `RefreshReport.tolerate_gaps` / `gaps` / `hard_failures` —— 区分**数据缺口**与**真失败**
  - `EMPTY_BARS_MARKER = "empty daily bars"`（仅对 `dataset == "daily"` 抛出）、`TOLERABLE_GAP_DATASETS = frozenset({"daily"})`（放行集合**单点**）
  - `ok = bool(items) and not _hard_failure_items(items, tolerate_gaps)` —— **漏洞永不遮蔽真失败**（同轮内一缺口 + 一真错误 ⇒ `ok=False`）
  - `to_dict()` 增 `tolerateGaps` / `gapCount` / `gaps[]`；`failures[]` **只列 `hard_failures`**
- **能力注册表反查（`P0-4`）**：`daily_pipeline._declared_capabilities(provider)` —— 四级解析（`capabilities` → `supports()` → **`name` 查注册表** → `None`）
  - 复用 `stock_platform_providers.build_capability_matrix()` 为**唯一真源**，不在流水线里重抄 provider→datasets 表
  - 解析结果为空一律当 `None`（**永不静默收窄到零数据集**）
- CLI 开关：`daily_cli --refresh-tolerate-gaps | --no-refresh-tolerate-gaps`、`refresh_cli --tolerate-gaps | --no-tolerate-gaps`；环境变量 `STOCK_PLATFORM_REFRESH_TOLERATE_GAPS`（`0/false/no/off` 关）
  - 解析优先级：**显式 flag ＞ 环境变量 ＞ 默认 `True`**
  - 输出：CLI 逐条 `GAP <symbol> <dataset>: <error>` 写 stderr（区别于 `FAIL`），退出码仍 0；`daily_cli` JSON 摘要回带完整 `refresh` 块

### Changed

- **真机缺陷修复（`P0-4`，线上路径）**：`_effective_datasets` 原仅认 provider 的 `capabilities` 属性；线上 HTTP provider（`tushare_http` / `cn_tushare_http`）**只实现 `get_daily`、不声明任何能力** → 流水线请求全部 4 个数据集，每只票失败 3 个，整轮在 `stage="refresh"` 失败 —— 而这正是本机生产路径。此前真机验证只覆盖 `market_db`，回归静默上线
- **真机缺陷修复（`P0-4`，fail-closed 粒度）**：`RefreshReport.ok = all(i.ok for i in items)` —— 单只薄票（无当日 bar 的数据缺口）即否决整轮。下游 `panel.py` 本就容忍空数据（空 frame 跳过、严格 PIT 只要求 `asof` 当日有 bar），整轮 fail-close 与「生产可用」目标相悖
- 严格模式（`tolerate_gaps=False`）**完整保留**给验收/取证（断言完整性时用）

### Verified

- **真机定位**：`510300`（沪深300ETF）在 `market.db` 仅 65 行、最后 bar = **`2026-09-08`**（C2 ETF 退化，见 ADR `0058`）——`asof=2026-10-09` 时落入缺口
- **真机复现**：`lookback=5`（窗口内含 0 bar）默认档 `ok=True / gapCount=1 / failCount=0`（**整轮存活**）；严格档 `ok=False / failCount=1`（**旧行为保留**）；`lookback=120` 两档均 `ok=True`
- **真机端到端**：`run_daily_pipeline`（`market_db` 快路径 + 3 标的含薄票）→ `ok=True / stage="brief"`，`refresh={datasets:["daily"], okCount:2, gapCount:1, failCount:0, tolerateGaps:true}`
- **真机 CLI**：`refresh_cli --provider market_db` 返回 `{"ok": true, "failCount": 0, "gapCount": 0}`（`.env` 自动加载，免手动 export）
- 全量 `pytest packages apps`（`replay`）**942 passed / 0 failed / 0 errors / 0 skipped**（927 → 942，+15）

### Docs

- 更新 [`docs/contracts/refresh-throughput.md`](docs/contracts/refresh-throughput.md) 至 `v4.1.7`：新增 §5（能力解析四级 + 不变量）与 §6（缺口 vs 真失败：判定单点 / 报告与门禁 / 开关矩阵 / 可观测性）；§7 验收基线补 `market_db` 有界跑（含薄票）数字

## [4.1.6] - 2026-10-10

### Added

- **离线批量取数 provider（`P0-1` 修复）**：新增 `stock_platform_providers.market_db_bulk.MarketDbBulkProvider`
  - `PROVIDER_NAME = "market_db_bulk"`、`capabilities = frozenset({"daily"})`、`MARKET_DB_BULK_UNSUPPORTED = ("adj_factor","fund_flow","full_minute")`
  - 唯一入口 `bulk_daily(symbols, *, start, end, asset_type="stock") -> dict[str, list[dict]]` —— 对 `market.db` 的 `daily_price` 做**一趟分块 SQL**（`_CHUNK = 900`），行经 `normalize_daily_row` 归一；缺失 symbol → `[]`（**不报错**）
  - 代码归一**复用** X1/ADR`0055` 单点：`_bare_codes`（去重保序）+ `_engine_code_map`（`600519.SH` / `sh600519` / `600519` 折叠同键）
  - 包装 `EngineSqliteProvider`，**零网络**（延续 ADR `0054`：不直连 Markdown / 自然语言源）
- **`run_refresh` 并发与限速（`P0-1`）**：`workers` / `min_interval` / `bulk` / `persist` 四参数
  - `RateLimiter(min_interval, *, sleeper, clock)` —— **跨所有 worker 的共享锁**保证任意两次上游调用间隔 ≥ `min_interval`；**提高并发不得越过上游节流**（硬约束）；`min_interval <= 0` 为 noop
  - `_bulk_daily_allowed(provider, datasets, bulk)` 为路径选择**单点**：要求有 `bulk_daily` **且** 请求数据集 ⊆ `capabilities`；`bulk=False` 强制关闭；任一数据集不支持即 fail-closed
  - 默认 `workers=1` / `persist=True` —— **不改既有基线**；结果为 `(symbol, dataset)` 输入顺序（三条路径一致）
  - 环境变量 `STOCK_PLATFORM_REFRESH_WORKERS` / `STOCK_PLATFORM_REFRESH_MIN_INTERVAL`（后者回落 `EM_MIN_INTERVAL`）
- **`.env` 自动加载单点（`P0-2` 修复）**：新增 `stock_platform_research.dotenv`
  - `load_dotenv(path=None, *, override=False, env=None, required=None, force=False)` / `find_dotenv_path` / `parse_dotenv_text`
  - 路径优先级：显式 → `STOCK_PLATFORM_DOTENV` → 仓库根向上查找 → cwd；文件缺失**不报错**；**默认不覆盖**进程环境变量（调度器注入优先）
  - **pytest 守卫**：`PYTEST_CURRENT_TEST` / `PYTEST_VERSION` / `STOCK_PLATFORM_DOTENV_DISABLE` 任一成立即**跳过隐式加载**（防开发者真实 `.env` 泄漏进测试）；`force=True` 供加载器自测
  - 接入 **14 个 CLI** 的 `main()` 首行
- **流水线能力裁剪（`P0-1`）**：`daily_pipeline._effective_datasets(provider, datasets)` —— 请求数据集 ∩ provider `capabilities`；provider 未声明 capabilities → `None`（**行为不变**）
- `daily_cli` 新参数 `--refresh-workers` / `--refresh-min-interval` / `--refresh-persist|--no-refresh-persist`，并支持 `--provider market_db`
- `refresh_cli` 新参数 `--workers` / `--min-interval` / `--market-db`
- 契约 [`docs/contracts/refresh-throughput.md`](docs/contracts/refresh-throughput.md) · [`docs/contracts/dotenv-loading.md`](docs/contracts/dotenv-loading.md) · ADR [`0066`](docs/architecture/0066-refresh-throughput-and-env-loading.md)
- 测试 +40：新增 `test_dotenv.py`（解析/优先级/`required`/守卫/`force`/发现）与 `test_market_db_bulk.py`（纯 helper + `@needs_db` 真库）；扩 `test_refresh.py`（串行默认/并发/限速节流/noop/环境默认/bulk 单次调用/缺失 fail-closed/`bulk=False` 回落/数据集不支持不批量/顺序稳定）与 `test_daily_pipeline.py`（`_effective_datasets` 裁剪/无能力不变/全不支持/跳过/persist）

### Changed

- **真机缺陷修复（`P0-1`）**：`run_refresh` 原为**双层串行同步 HTTP**（`for symbol: for dataset:` 逐个阻塞调用），真机实测 307 只样例 **11m48s**、CPU 仅 **9.7s**（100% 网络 I/O）→ 外推全市场 5213 只约 **3 小时**，08:30 盘前窗口不可行。根因**不是并发不足**，而是**用 HTTP 重新拉取已在本机 `market.db`（ADR `0058` 全市场真相源）的数据**
- **真机缺陷修复（`P0-2`）**：`daily_cli._build_provider` 直读 `os.environ["STOCK_PLATFORM_TUSHARE_TOKEN"]`，而全仓仅 `start-workbench.bat` 注入 `.env` → 真机复现 `live provider='cn_tushare_http' requires STOCK_PLATFORM_TUSHARE_TOKEN`、**exit 1**；`schtasks` 不会注入环境变量 ⇒ **每日自动化必然失败**

### Verified

- **真机端到端**：全市场 5213 只 refresh = **115 s**（带 JSON）／`persist=False` ≈ 秒级；`daily_cli` 端到端 **12.78 s**（快路径）vs 129.94 s（带持久化，省 ≈117 s）；`Invoke-DailyPipeline.ps1 -MarketDb` = **14.78 s** —— 较外推 ~3 h 约 **94×–700×**
- `.env` 自动加载真机验证：token 自动加载（56 字符），`TushareHttpProvider()` **免手动 export** 构造成功；`--provider market_db` 运行返回 `ok: true`
- 全量 `pytest packages apps`（`replay`）**927 passed / 0 failed / 0 errors / 0 skipped**（887 → 927，+40）

### Docs

- 新增 `docs/architecture/0066-refresh-throughput-and-env-loading.md` + `docs/contracts/refresh-throughput.md` + `docs/contracts/dotenv-loading.md`（均登记 `scripts/check_docs.ps1`，files 146 → 149）
- 更新 `docs/ops/scheduler.md` 至 `-MarketDb` 快路径（替代旧 `--provider replay` + `-SkipRefresh` 默认）

## [4.1.5] - 2026-10-11

### Added

- **LLM 辩论进主路径（`S5`）—— 只读顾问侧车**：新增 `stock_platform_agents.debate_lane` **单点**
  - `DEBATE_LANE_ENGINES = ("off", "deterministic", "llm")`，**默认 `off`**（零 LLM、零副作用）；`normalize_lane_engine()` 对未知名抛 `AgentError`（HTTP 层 → **400**，**不静默回落默认值**）
  - `attach_debate_lane(provider, brief, *, engine, max_picks, budget, llm_call)` —— **只读** `brief`，返回车道载荷：`enabled`/`engine`/`requestedEngine`/`debates`/`debateCount`/`degraded`/`warnings`/`advisory`/`excludedFromPerformance`/`budget`
  - `debate_lane_summary()` —— manifest 裁剪（丢弃回合全文）
  - ADR [`0065`](docs/architecture/0065-llm-debate-lane.md)
- **预算提为一等公民**：`llm_debate._LlmBudget` → 公开 **`LlmBudget(max_calls=None, max_tokens_soft=None)`**（显式覆盖环境变量，缺省回落 `STOCK_PLATFORM_LLM_MAX_CALLS` / `STOCK_PLATFORM_LLM_MAX_TOKENS`）；`debate_brief_picks` 增 `budget` 形参
- **主链挂载走依赖注入**：`run_daily_pipeline(..., debate_runner=None, debate_engine=None, debate_max_picks=None)` —— `stock-platform-research` **不新增**对 `stock-platform-agents` 的依赖；产出 `{asof}/debates.json` + `manifest.debates` + `DailyPipelineReport.debates`；**best-effort**（异常落 `report.debates["error"]`，绝不破坏 brief）
- CLI `stock-platform-daily --debate-engine {off,deterministic,llm}` / `--debate-max-picks`
- API `POST /api/research/daily/debate`（**校验 400 先于面板探测 503**）
- 契约 [`docs/contracts/debate-lane.md`](docs/contracts/debate-lane.md)

### Changed

- **无行为变更**：默认 `off` ⇒ 主链默认路径逐位不变（`run_daily_pipeline` 在 `off` 时**不调用 runner**）。

### Verified

- **「误判不进绩效」不变量**（对齐 M-A2 评级边界口径）：开/关辩论两轮的 `brief.json` **字节**、`picks_ledger.jsonl` **字节**与命中块**逐位相等**，唯一差异是多出 `debates.json`（`test_daily_debate_lane.py::test_lane_leaves_brief_ledger_and_hits_identical`）；判决归一为 `Buy|Hold|Sell` 但**不再往下走**、不转 decision 行 `rating`
- 聚焦测试：agents `test_debate_lane`（10 项）+ research `test_daily_debate_lane`（5 项）+ workbench 端点/行为；全量 `pytest packages apps`（`replay`）**887 passed / 0 failed / 0 errors / 0 skipped**（junitxml 取证）

### Docs

- 新增 `docs/architecture/0065-llm-debate-lane.md` + `docs/contracts/debate-lane.md`（登记 `scripts/check_docs.ps1`，files 144 → 146）
- 路线图 `S5` 行标记 `done（2026-10-11）` + 目标 tag 顺延 `v3.14.4` → `v4.1.5`；**S 域（S1–S5）全部收官**
- **刻意不新增手动 UI 面板**：车道定位是主链自动化（CLI + API），手动面板会与既有 `TopN 辩论`（`/api/research/brief/debate`）重复

## [4.1.4] - 2026-10-11

### Added

- **实盘立项决议（`L1`）** —— ADR [`0064`](docs/architecture/0064-live-trading-charter.md)（状态 **`Accepted`**，2026-10-11 经用户确认）：
  - 券商选定 **华宝证券（国内）**（落选：富途 / 其它港美股通道 —— 跨境与外汇合规复杂度 + 1 万本金下无意义；同花顺真机通道不在本轮边界内）
  - 资金上限 **1 万元（账户总资产口径，含现有持仓）**；禁融资融券 / 场外配资
  - **合规边界 = Phase 0 纯模拟盘 —— 本次明确不解禁红线**（`liveTradingEnabled` 维持恒 `false`，`L2` / `L3` 不开工，`execution/profile.py` 的 `ProfileBlocked` 硬闸**零改动**）
  - **三阶段解锁条件**：P0 纯模拟（当前）／P1 半自动人工下单（**免报备**，须券商书面口径）／P2 `QMT` 全自动（**必须报备**）
  - **关键结论**：华宝 `QMT`/`PTrade` 门槛 ≈ 10 万（近 20 交易日日均证券资产）+ 6 个月 A 股经验 + 风险测评 C4/C5 → **1 万元拿不到终端 → 不能自动下单 → 法定定义上不算程序化交易 → 免报备**
  - 解除红线**影响面清单**（≈37 源文件 + 21 测试文件 + 3 份契约 + 路线图红线第 7 条）＋**失败回滚方案**（P2「状态未知」一律人工介入）
- 契约 [`docs/contracts/compliance-boundary.md`](docs/contracts/compliance-boundary.md)：四层边界 / 资金口径 / 免报备判据 / 阶段门禁 / P0 名义参数（Confirmed） / 监管依据 / 可断言不变量

### Changed

- （无）

### Docs

- 新增 `docs/architecture/0064-live-trading-charter.md` + `docs/contracts/compliance-boundary.md`（均登记 `scripts/check_docs.ps1`，files 142 → 144）
- 路线图 `L1` 行标记 `done（2026-10-11）`；**版本映射落定 `v4.1.4`**（`v5.0.0` 保留给「真正解除红线」的那次；`S5` 顺延 `v4.1.5`）
- **本段已收口**：`L1` 已于 2026-10-11 经用户确认置 **`Accepted`**（路线图 §3.5 要求已满足）；版本 `v4.1.4`、tag 见 `git tag`。

## [4.1.3] - 2026-10-10

### Added

- **行业中性化与风格暴露约束（`S4`）**：新增 `research.neutralization` **单点** —— `NeutralizeParams`（frozen dataclass：`industry_col` / `mode`(`demean`|`zscore`) / `clip` / `min_group_size` / `rescale`(`rank`|`none`) / `composite_demean` / `style` / `style_clip`）＋ `industry_neutralize_series` / `neutralize_factor_scores` / `residualize` / `resolve_groups` / `attach_industry` / `industry_exposure`。语义**承接** `a-stock-engine/src/factor_engine.py` 的 `_zscore`（行业分组 z + 组内去均值）；作用面是 `[0,1]` 因子分，`rescale="rank"` 把尺度还原，**下游 `min_pick_score` 语义不变**。ADR [`0063`](docs/architecture/0063-industry-neutralization.md)
  - `lvrev.score_lvrev(..., neutralize=None)`：**默认关 → 组合分逐位不变**；启用时「逐因子行业中性化 → 可选风格残差化 → 可选 `rank` 重标定 → 加权求和 → 可选组合分行业去均值」
  - **行业只读接入**：`backtest_cli.load_engine_industry()` 读 `fundamentals(code, industry)`（**缺表 fail-closed**）；`code` 两侧经 `portfolio.norm_code` 归一（实测 `daily_price` = `000001.SZ` 带后缀、`fundamentals` = `000001` 裸 6 位，**原始交集为 0** → 必须归一）；`attach_industry` 未映射码 → `__UNKNOWN__` 独立组（权重恒为 1）
  - **透传链（不复制中性化）**：`prepare_book_frame(..., industry_map=None)`（默认不加列）＋ `screener_entry_provider(..., neutralize=None, max_per_industry=None)`
  - **暴露约束** `max_per_industry`：在 `max_picks_per_day` **之前**按行业 `head(k)` 并按 `composite_score` 重排 —— 改「构成」不改「排序规则」
- 新增 `research.neutralization_ab`：`compare_neutralization_ab` / `neutralization_ab_from_bars` / `run_neutralization_book` —— 两臂消费**同一**特征帧、跑**同一个** `book_replay.replay_book`；`delta` / `review` / `sameDefinition` **直接复用 `strategy_ab`（`S1`）的实现**（不复制）；并附各臂**行业暴露画像**（`n_codes` / `n_industries` / `max_weight` / `max_industry` / `hhi`）
- CLI `stock-platform-strategy-neutralization`（`--db/--start/--end/--universe/--mode/--clip/--min-group-size/--rescale/--no-composite-demean/--style/--max-per-industry/--min-pick-score/--initial-capital/--max-positions/--json`，只读 `market.db`）
- API `POST /api/research/strategy/neutralization`（只读 `market.db`；非法 `mode` / `rescale` / `universe` / 窗口 → **400**，无 DB → **503** fail-closed；**校验 400 先于 DB 503**）
- Workbench `#neutralization` 面板（两臂指标 + `delta` 表 + 行业暴露表 + 原始 JSON，手写零新依赖）
- 契约 [`docs/contracts/industry-neutralization.md`](docs/contracts/industry-neutralization.md) + 实测 [`docs/ops/neutralization-benchmark.md`](docs/ops/neutralization-benchmark.md)

### Changed

- 版本号 `4.1.2` → **`4.1.3`**

### Verified

- **真机 `market.db` 验收**（2024-09-02 → 2026-09-08，489 交易日 / 2,949,567 行 / 6,789 码 / 111 行业 / 两轮合计 **95.9 s**）：
  - **仅中性化**：`total_return` 0.3029 → **0.5257**（+0.2228）、`sharpe` 1.0599 → **1.1430**、`final_equity` 65,146.49 → **76,287.46**；但 `max_drawdown` -0.1767 → **-0.2673**（更深）、`win_rate` 0.4659 → **0.3839**（更低）、笔数 176 → 224、平均持有 35.22 → 30.00 天
  - **中性化 + `maxPerIndustry=3`**：`total_return` **0.5850** / `sharpe` **1.2492** / `max_drawdown` -0.2423 —— 优于纯中性化
  - **「中性化 ≠ 更分散」**：持仓集合 HHI 反而 0.0225 → 0.0302（+cap 0.0312），如实记录，**不据此改档**
  - `raw` 臂两轮**逐位一致**（两臂只差处理项的直接证据）；出厂 `W_DEFAULT` / `min_pick_score=0.80` / `EntryGateParams()` **逐位未改**
- 聚焦测试：research 新增 `test_neutralization.py` + `test_neutralization_ab.py` **28 passed**（`test_gates` / `test_lvrev` 回归同绿）；workbench **185 passed**（端点目录 64 → **65**）

### Docs

- 新增 `docs/architecture/0063-industry-neutralization.md` + `docs/contracts/industry-neutralization.md` + `docs/ops/neutralization-benchmark.md`（均已登记 `scripts/check_docs.ps1`）
- 路线图 `S4` 标 `done（2026-10-10）`，目标 tag 顺延 `v3.14.3` → `v4.1.3`

## [4.1.2] - 2026-10-10

### Added

- **闸门参数敏感性扫描与稳健区间判定（`S3`）**：入场闸门常量**单点化** `gates.EntryGateParams`（frozen dataclass：`reversal_q` / `ma20_band` / `ma60_band` / `vol_filter`，默认值 = 原硬编码字面量**逐字**）；`apply_entry_gates(df, reversal_q=None, *, params=None)` —— 显式 `reversal_q` 覆盖 `params.reversal_q`，两者都缺用 `0.30`；`apply_entry_gates(df)` / `apply_entry_gates(df, reversal_q=0.30)` / `apply_entry_gates(df, params=EntryGateParams())` **三者逐位相同**。ADR [`0062`](docs/architecture/0062-gate-parameter-sensitivity.md)
  - 新增 `research.sensitivity` 扫描**单点**：`sweep_entry_gate`（单旋钮网格扫描，每点经 `book_replay.replay_book` X4 单循环 + **同一** `screener_entry_provider`，`feats` 只建一次 → 两点只差旋钮）/ `summarize_sweep`（**纯函数**，`robust` / `fragile` / `flat` / `insufficient` 四类判定 + `robustRange` + `stability` + `monotonic`）/ `build_sensitivity_report`（多旋钮汇总，任一 `fragile` → `overall=fragile`）
  - `summarize_sweep` 容差带语义：`sign·(obj − best) ≥ −tolerance × |best|`；`robustRange` = **包含最优点且连续**的一段网格值；连续点数 `< 2` → `fragile`（**孤峰** = 过拟合风险）；目标方向由 `OBJECTIVE_DIRECTION` 登记（`max_drawdown → min`），未登记默认 `max`
  - `book_replay.screener_entry_provider` 增 `gate_params` 透传（`reversal_q` 缺省 `0.30` → `None`，**有效值不变** → 既有调用逐位不变）
- CLI `stock-platform-strategy-sensitivity`（`--db/--start/--end/--universe/--knobs/--objective/--tolerance/--min-pick-score/--initial-capital/--max-positions/--reversal-q-grid/--min-pick-score-grid/--ma-band-grid/--json`，只读 `market.db`）
- API `POST /api/research/strategy/sensitivity`（只读 `market.db`；未知旋钮 / 非法 objective **400** / 无 DB **503** fail-closed）
- Workbench `#sensitivity` 面板（旋钮判定表 + 逐点指标表 + 原始 JSON，手写零新依赖）
- 契约 [`docs/contracts/gate-sensitivity.md`](docs/contracts/gate-sensitivity.md) + 实测 [`docs/ops/gate-sensitivity-benchmark.md`](docs/ops/gate-sensitivity-benchmark.md)

### Changed

- 版本号 `4.1.1` → **`4.1.2`**

### Verified

- **真机 `market.db` 验收**（2024-09-02→2026-09-08，489 交易日 / 2.52 M 行特征帧 / 3 旋钮 × 5 点 = 15 次完整回放 / **182.7 s**）：
  - `min_pick_score` → **`robust`**（`0.5`/`0.6`/`0.7` 的 sharpe 1.253/1.129/1.157 全在最优值 10% 容差内 → **稳健区间 3 点**，`stability=0.60`）
  - `reversal_q` → **`fragile`**（仅 `0.1` 达标，`robustRange=0.1–0.1`）；`ma_band` → **`fragile`**（仅 `0.9` 达标，`robustRange=0.9–0.9`）→ **`overall=fragile`**
  - 出厂值 `reversal_q=0.30`（sharpe 1.060）/ `ma_band=0.93`（1.060，**全网格最差**）/ `min_pick_score=0.80`（1.060）均**不**是最优 —— 但 `fragile` 判定明确拦下「照最优值调档」：正是「避免过拟合单点」
- 出厂闸门值**逐位不变**（`reversal_q=0.30` / `ma_band=0.93` / `min_pick_score=0.80`）；`apply_entry_gates` 既有调用逐位不变
- 聚焦测试：research `45 passed`、workbench `147 passed`（端点目录 63 → **64**）

### Docs

- 新增 `docs/architecture/0062-gate-parameter-sensitivity.md` + `docs/contracts/gate-sensitivity.md` + `docs/ops/gate-sensitivity-benchmark.md`（均已登记 `scripts/check_docs.ps1`）
- 路线图 `S3` 标 `done（2026-10-10）`，目标 tag 顺延 `v3.14.2` → `v4.1.2`

## [4.1.1] - 2026-10-10

### Added

- **因子库扩展与 IC/ICIR 正交准入（`S2`）**：新增 `research.factors` 因子库**单点**（`FACTOR_LIBRARY` / `FactorSpec`），在 lvrev 已加权的 `low_vol` / `reversal` 之外新增三个候选 —— `long_reversal`（6 个月反转，`-(close.shift(20)/close.shift(120)-1)`，**跳过最近一月**）/ `max_ret`（20 日单日最大涨幅·彩票偏好）/ `illiq`（Amihud 非流动性 `mean(|ret1|/amount)×1e9`）；`build_feature_frame` 复用 `compute_features` 唯一 PIT/复权点（仅 `keep_extra=("vol","amount")`）；`factor_correlation` **scipy-free**。ADR [`0061`](docs/architecture/0061-factor-library-admission.md)
  - `factor_ic` 增**准入闸门** `admit_factor`（`n_dates≥20` / `|IC|≥0.02` / `|ICIR|≥0.15` / **符号一致**，全过才启用）+ **正交选择** `select_enabled`（与已启用因子 `|Spearman ρ|≥0.70` 判**冗余** → 不启用）+ `build_factor_ic_report`
  - `compute_features` 加 `keep_extra`（**默认空** → 既有调用逐位不变）；`lvrev` 加 `W_S2` 且 `factor_scores` 补 `momentum` / `max_ret` / `illiq` 列（缺列填中性 `0.5`，默认权重 `0` → 基线精确等价）
- CLI `stock-platform-factor-ic`（`--db/--start/--end/--horizon/--sample-every/--min-names/--universe/--factors/--min-abs-ic/--min-abs-icir/--min-dates/--correlation/--json`，只读 `market.db`）
- API `POST /api/research/factor/admission`（只读 `market.db`；未知因子 **400** / 无 DB **503** fail-closed）
- Workbench `#factor-library` 面板（判定表 + 启用/冗余/否决 + 相关矩阵，手写零新依赖）
- 契约 [`docs/contracts/factor-library.md`](docs/contracts/factor-library.md) + 实测 [`docs/ops/factor-ic-benchmark.md`](docs/ops/factor-ic-benchmark.md)

### Changed

- 版本号 `4.1.0` → **`4.1.1`**

### Verified

- **真机 `market.db` 验收**（全周期，`horizon=20` / `sample_every=5` → **324 个采样截面**）：`long_reversal` IC **+0.033** / ICIR **+0.198**、`illiq` IC **+0.077** / ICIR **+0.798** **启用**（满足「≥2 个正交因子」）；`max_ret`（IC −0.094 / ICIR −0.572）与 `low_vol` 相关 **+0.876** → **冗余不启用**（`enabled=['low_vol','reversal','illiq','long_reversal']` / `redundant=['max_ret']`）
- 默认档 `W_DEFAULT`（`vol=0.5, rev=0.5`）**逐位不变**；`compute_features` 既有调用逐位不变
- 聚焦测试：research `45 passed`、workbench `146 passed`（端点目录 62 → **63**）

### Docs

- 新增 `docs/architecture/0061-factor-library-admission.md` + `docs/contracts/factor-library.md` + `docs/ops/factor-ic-benchmark.md`（均已登记 `scripts/check_docs.ps1`）
- 路线图 `S2` 标 `done（2026-10-10）`，目标 tag 顺延 `v3.14.1` → `v4.1.1`

## [4.1.0] - 2026-10-10

### Added

- **因子 / 闸门 A/B 完整版（`S1`，U7 遗留）**：让 A/B 与回测 / 推荐回放**同源** —— 两臂消费同一特征帧、跑**同一台** `book_replay.replay_book`（`X4` 单点定义），只由 entry provider 区分。ADR [`0060`](docs/architecture/0060-strategy-ab-full-engine.md)
  - `StrategyConfig` 增 `gates`（`min_pick_score` 缺省 `0.80`；接受扁平别名 `min_pick_score` / `minPickScore`）→ **闸门变更可表达**；`load_strategy_config` 现接受**裸 id**（`<id>` / `<id>.json`）
  - `strategy_ab` 新增 `config_entry_provider` / `run_config_book` / `compare_strategy_ab_engine` / `compare_strategy_ab_from_bars`
  - 每臂附 **`review` 复盘块**（`directionAccuracy` / `settledCount` / `pendingCount`，口径对齐 `performance` / U3；空仓为 `null`，不填 0）
  - `delta = B − A`（同口径无需二次归一）+ `sameDefinition` 身份块（`singleLoop` / `singleEntryProvider` / `singleMetrics` / `singleExitDefinition`）
- CLI `stock-platform-strategy-ab`（`--config-a/--config-b --start --end --universe --json`，只读 `market.db`）
- API `POST /api/research/strategy/ab-engine`（只读 `market.db`；未知配置 **404** / 无 DB **503** fail-closed）
- Workbench `#strategy-compare` 面板内新增「**A/B 同屏**」区块（两列指标 + Δ 列 + 复盘表 + 双净值曲线，手写 SVG 零新依赖）
- 契约 [`docs/contracts/strategy-ab.md`](docs/contracts/strategy-ab.md)；打包闸门演示臂 `lvrev-gate-strict-v1`

### Changed

- 打包策略配置 `lvrev-default-v1` / `lvrev-rev-heavy-v1` 补 `gates.min_pick_score = 0.80`
- 版本号 `4.0.5` → **`4.1.0`**（`S` 域首版；目标 tag 由陈旧的 `v3.14.0` 顺延）

### Verified

- **同源一致性**：baseline 配置 vs `run_portfolio_backtest` —— 曲线 / 成交 / 指标 / 未平仓**逐位一致**（`tests/test_strategy_ab_engine.py`）
- `sameDefinition` 四项全 `true`；严格闸门臂入场数 **≤** 宽松臂
- 真机 `market.db` 端到端（1 年窗，143 万行 / 6761 码 / 243 日）：两臂 87 vs 93 笔，指标 + 复盘 + delta 齐全
- 聚焦测试：research `19 passed`、workbench `145 passed`（端点目录 61 → **62**）

### Docs

- 新增 `docs/architecture/0060-strategy-ab-full-engine.md` + `docs/contracts/strategy-ab.md`（均已登记 `scripts/check_docs.ps1`）
- 路线图 `S1` 标 `done（2026-10-10）`；版本映射 `S` 域改 `v4.1.0` → `v4.1.4`

## [4.0.5] - 2026-10-10

### Added

- **双线职责边界（`C1`）**：新增 [`docs/plans/dual-line-responsibility.md`](docs/plans/dual-line-responsibility.md) —— 定边界 + 定归属 + 列判据（不做大规模代码合并）。
  - 日常调度主链 = **引擎线**（`a-stock-engine`，08:30 盘前 / 15:30 盘后）；历史行情真相源 = `market.db`·`daily_price`（平台**只读**）；产品 / 研究权威 = **平台线**
  - 5 组使用判据（日用 → 引擎；研究 / 回测 / 绩效 / 选股↔回测 → 平台；数据缺口 → 修生产侧；命中追踪 / 榜单 → 平台；实盘 → 都停）
  - 数据归属表（承接 ADR 0058）+ 双方红线（平台不代抓不补写 / 引擎冻结新功能）
  - 与路线图 / `ROADMAP` / `README` / ADR 0058 / `engine-market-db.md` 交叉链

### Changed

- **文档与 CI 一致性（`G3`）**：自有主线路线图 `trading-system-roadmap.md` 挂进 `docs/ROADMAP.md` 顶部焦点区与 `docs/README.md`；`docs/plans/README.md` 陈旧状态刷新
- **补齐 `scripts/check_docs.ps1` 的 `$required` 三处遗漏**：`trading-system-roadmap.md`（主路线图竟未登记）/ `b3-cost-model-milestone.md` / 新 C1 文档 —— `files` **128 → 131**
- 版本号 `4.0.4` → **`4.0.5`**

### Verified

- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.5，docs `files=131` / `md=158`）
- CI `monorepo` job 确认：5 包 editable 安装 + `pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）
- 全量 `pytest packages apps`（`replay`）= **786 passed / 0 failed**（纯文档里程碑，计数不变）

### Docs

- 新增 `docs/plans/dual-line-responsibility.md`（已登记 `scripts/check_docs.ps1`）
- 路线图 `G3` / `C1` 标 `done（2026-10-10）`；**G 域（G1–G3）全部收官**

## [4.0.4] - 2026-10-10

### Added

- **选股↔回测同引擎（`X4`）**：把逐日回放循环抽成**唯一定义** `research.book_replay.replay_book`（`entry_provider` 多态），`backtest.run_portfolio_backtest` 转薄封装、`picks_backtest.run_picks_backtest` 用**同一台引擎**跑推荐账本 —— 推荐绩效与回测口径**同源**（承接 B5）。ADR [`0059`](docs/architecture/0059-picks-backtest-parity.md)
  - picks 账本 append-only JSONL `{out}/picks_ledger.jsonl`（`(date, code)` 去重；`normalize_picks` 冻结为 `{date, code, rank?, score?}`）；流水线默认 `track_picks_ledger=True` 自动写入 ②A 头部
  - `replay_book` 新增 `open_positions[]` 出口（窗口结束仍持有的仓位：`code` / `entry_idx` / `entry_price` / `shares` / `target` / `peak` / `held_days`），两条路径都透出；`ok` 判据改为「形成至少一个持仓 = 已平仓 ∪ 未平仓」
  - 对照 `compare_picks_vs_screener`：同堆 bars 跑两侧，`delta = picks 指标 − 回测指标`（同口径无需二次归一），附 `sameDefinition` 身份块
- CLI `stock-platform-picks-backtest`（读 `--ledger` 或 `--briefs-dir`，只读 `market.db`）
- 流水线可选回放对照：`replay_picks` / `replay_bars` / `replay_against_screener` → 写 `{asof}/picks_replay.json`，`report.picksReplay` 为裁剪摘要（不含曲线/成交）

### Changed

- `backtest.py` 内联回放循环抽走 → 薄封装（新增 `prepare_book_frame` 共享 bars→特征帧，含 universe 过滤 + 窗口切片）；**默认档全周期逐位不变**
- `daily_pipeline` 默认自动写 picks 账本（`track_picks_ledger=True`；失败 best-effort，写进 `report.picksLedger` 绝不中断 brief）
- 版本号 `4.0.3` → **`4.0.4`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **786 passed / 0 failed**（761 → 786，**+25**）
- research 新增 3 测试文件（`test_book_replay.py` / `test_picks_backtest.py` / `test_daily_pipeline.py` 的 X4 项）共 **32 passed**
- **纯重构证据**：从重构前 `run_portfolio_backtest` 抓 8 场景（股票 / ETF / 混合 / 滑点 / 零费 / 冷静期 / 旧 `verbatim` 尺度 / 单码）曲线与成交 sha256 + 全部指标存 fixture，**8/8 逐位一致**
- **同引擎证明**：把回测 `trades` + `open_positions` 回灌成 picks schedule 后，`trades` / `equity_curve` / `metrics` / `open_positions` **逐位相等**
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.4）

### Docs

- 新增 ADR [`0059`](docs/architecture/0059-picks-backtest-parity.md) + 契约 [`docs/contracts/picks-backtest.md`](docs/contracts/picks-backtest.md)（均登记 `scripts/check_docs.ps1`）
- `docs/ops/daily-pipeline.md` 新增「X4：picks 账本与推荐↔回测对照」段

## [4.0.3] - 2026-10-10

### Added

- **数据真相源统一 + 覆盖守卫（`C2`）**：确认 `daily_price`（`market.db`）为唯一历史行情真相源，并把"摄取还在不在跑"变成**可查询的判据**。ADR [`0058`](docs/architecture/0058-market-db-source-of-truth.md)
  - `EngineSqliteProvider.coverage_snapshot(asof, lookback_days=30, min_rows=3000)`：**只读**双判据快照 —— ① 窗口内 CN 交易日是否齐全（含 `lagTradingDays`，**按交易日而非自然日**计滞后，周末/长假不误报）；② 每日行数是否 ≥ `min_rows`。裁决 `ok | thin | stale | empty | missing_table`；异常收敛为 `status="error"`，**永不抛给调用方**
  - `GET /api/ops/health` 新增 `marketDb` 块：`thin` / `stale` / `empty` / `missing_table` / `error` 会把整体 `status` 降级为 `degraded`；未配置时为 `unconfigured`**不降级**
- 派生库归属写明（ADR 0058 表）：引擎 `a-stock-engine.db` / `selections.db` / `history/picks.db`、平台 `stock_platform.db` —— 均**不得**作为历史行情输入

### Fixed

- **引擎 `market.db` 覆盖破相（静默一个月）**：`daily_price` 自 `2026-09-04` 起破相 —— `09-04` / `09-07` / `09-08` 各仅 **14 行**（引擎 `refresh_etf_daily_prices` 每日只写 14 只 ETF 的签名行数），`09-09`~`10-09` 共 **17 个交易日完全缺失**，最后全市场日停在 `2026-09-03`（5223 行）。已在生产侧回补 **20 个交易日 / 104,301 行 / 0 失败**，覆盖恢复（每日 ~5.2k 行，最新 `2026-10-09`）
- 摄取链路的两处结构缺陷已定位并写入 runbook：① 全市场写入只靠手动 `empirical/backfill_market_daily.py`，日常自动化随引擎归档停止后无人补；② `import_local_data.py` 的断点续传按**日期存在性**判定，**部分覆盖日被永久跳过**、无法自愈
- **已知遗留（本轮不改）**：`refresh_etf_daily_prices` 会删光 14 只 `WELL_KNOWN_ETFS` 的**全部历史**再写 65 根、`pct_chg` 全 0（实测各仅剩 `2026-06-09~09-08`；同表裸码 `518880` 仍有 1499 行）。修复路径已实测可用（`fund_daily`，14 次调用），待复权口径决策后单独处理

### Changed

- 版本号 `4.0.2` → **`4.0.3`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **761 passed / 0 failed**（747 → 761，**+14**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.3）
- 新增测试：`packages/providers/tests/test_engine_coverage.py`（9 项：窗口齐全 / 薄日 / 缺日 / **交易日滞后口径** / 空窗 / 缺表不抛 / 快照形状与只读 / asof 默认 / 非法 asof）、`apps/workbench/tests/test_ops_market_db.py`（5 项：未配置不降级 / 齐全 ok / 薄日降级 / 缺日降级 / 坏库**不 5xx**）
- 回补单位口径实测：`--validate` 对 `2026-09-03` 存量全市场日抽样 400 只，`close` / `pct_chg` / `vol` / `amount` 比值中位数**全为 1.0000**
- 覆盖复核：`2026-09-04`~`10-09` 每个交易日恢复 ~5.2k 行；全库 8,875,338 行 / 1638 交易日 / 6983 码

### Docs

- 新增 ADR `docs/architecture/0058-market-db-source-of-truth.md`（已登记 `scripts/check_docs.ps1`）
- `docs/ops/engine-market-db.md` 新增「摄取与覆盖自检（C2）」：刷新命令 / 单位口径 / 自检出口 / 三条已知坑

## [4.0.2] - 2026-10-10

### Added

- **命中追踪接入（`X3`）**：把 `a-stock-engine` 的选股命中周期**搬进平台 SQLite**，规则只有**一个定义** `research.hit_tracking.apply_hit`。契约 [`docs/contracts/hit-tracking.md`](docs/contracts/hit-tracking.md)、ADR [`0057`](docs/architecture/0057-hit-tracking.md)
  - 周期规则（**照搬引擎**）：首次命中启动周期 `cycle_end = pick_date + 14 日历日`（10 交易日≈14 自然日）；周期内再命中 **滑动延期** 14 天且 `cycle_hits += 1`；`pick_date == cycle_end` 算周期内（闭区间）；`total_cycles` 仅在新周期递增；`session_type ∈ {pre_market, post_market}` 两套计数独立
  - `SqliteHitTrackingRepository`：`hit_tracking` 明细表 + `hit_summary` 汇总表，建在 `STOCK_PLATFORM_DB_URL`（与 brief 存档**同库不同表**）；去重由引擎的「先查后插」升级为硬约束 `UNIQUE(code, session_type, pick_date)`
  - 代码归一为 6 位数字核（`600519.SH` / `sh600519` / `600519` 同键）；`HitTrackingConfig.cycle_calendar_days` 可配，默认 14
- **三类累计查询**：`hit_tracking_snapshot(repo, asof=...)` 一次返回 `pre_market` / `post_market` / `pre_market_in_cycle`（前两者为生命周期累计，后者仅统计窗口仍开着的代码——语义分离，契约写明不可混用）；`format_hit_report` 输出 markdown
- **CLI** `stock-platform-hits`：`--summary` / `--report` / `--details` / `--track-brief` / `--track-json`
- **Workbench**：`GET /api/research/hit-tracking`（只读三类累计 + 明细 + markdown，空库中文 `emptyMessage`）；`POST /api/research/hit-tracking/track`（显式把已存 brief 记入，幂等）；新增 `#hits` 面板（三块汇总 + 明细表 + 「同步命中」按钮）

### Changed

- `run_daily_pipeline(track_hits=True)`（默认）把 ②A 头部记入 `pre_market` 命中周期，结果落在 `report.hits`；**追踪失败记 `report.hits["error"]`，绝不中断 brief**（`hit_boards` 可覆盖榜单集）
- `stock-platform-daily --no-track-hits`：关闭默认命中追踪
- **写入口收敛**：`GET /brief` **不**隐式写命中——Workbench 的 /brief 也用于探索性选股（任意 asof / symbols），计进去会污染周期
- 版本号 `4.0.1` → **`4.0.2`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **747 passed / 0 failed**（719 → 747，**+28**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.2）
- 新增测试：`packages/research/tests/test_hit_tracking.py`（20 项：纯规则首次 / 滑窗 / 边界闭区间 / 新周期 / 可配天数、仓库同日去重 / 两 session 独立 / 代码归一 / 非法 session / `record_many`、三类累计快照 / 排除已结束周期 / 空库零值 / markdown / 明细筛选、brief 榜单→category 映射）、`apps/workbench/tests/test_hit_tracking_api.py`（5 项）；`test_daily_pipeline.py` 增命中周期回归（+1）
- `test_all_api_endpoints.py` 端点目录登记两新操作（59 → 61 ops）

### Docs

- 新增契约 `docs/contracts/hit-tracking.md`、ADR `docs/architecture/0057-hit-tracking.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

## [4.0.1] - 2026-10-10

### Added

- **榜单体系对齐（`X2`）**：brief 现在除 `picks[]` 外还产出与 `a-stock-engine` 同构的**五类榜单**，切分逻辑只有**一个定义** `research.rankings.build_rankings`。契约 [`docs/contracts/rankings.md`](docs/contracts/rankings.md)、ADR [`0056`](docs/architecture/0056-ranking-boards.md)
  - `②A_质量榜` 综合分 TopN（默认 10）／`②B_短线榜`（默认 5，**排除 ②A 头部**，带 `entry_ok` 列时优先取过闸门者、不足按分补足）／`③A_持仓`（持仓 ∩ 截面；**未过今日入场闸门的持仓也列示**，`composite_score=null`）／`③B_操作建议`（**完全委派 B5 `rules`**，只收 `exit`/`trim`，`reason` 原文透传）／`③C_观察名单`（②A 之后 23 只）
  - `RankingConfig` 为档位参数单点：`quality_top_n` / `short_term_top_n` / `watchlist_top_n` / `min_composite_score`（默认 0.0 关闭）
  - **`picks` 语义不变**（= ②A 头部），DB 存档 / 绩效日志 / intel-report 零迁移
- **CLI** `stock-platform-rankings`：`--panel`（原始特征面板或已评分面板）+ `--holdings` → `--md` / `--csv` / `--json`
- **Workbench**：`/api/research/brief?holdingsPath=`（默认 `STOCK_PLATFORM_HOLDINGS_PATH`，复用 `position_review_cli.load_holdings` 唯一读取器）；响应新增 `rankings` / `rankingsCounts` / `holdingsLoaded` / `holdingsNote`；`#recommend` 页新增「榜单」区块（五榜表格 + fail-closed 提示）

### Changed

- `build_premarket_brief` 改为对**全量**评分截面切榜单后再 `head(top_n)` 生成 `picks`（默认档逐位不变）
- `run_daily_pipeline(holdings=...)` / `stock-platform-daily --holdings`：流水线支持传入持仓以填充 ③A / ③B
- 版本号 `4.0.0` → **`4.0.1`**

### Verified

- 全量 `pytest packages apps`（`replay`）= **719 passed / 0 failed**（698 → 719，**+21**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.1）
- 新增测试：`packages/research/tests/test_rankings.py`（16 项：分榜切分 / ②B 优先 entry_ok / 门槛只切推荐类目 / 未过闸门持仓不丢 / ③B reason 来自 `rules` / 三种 fail-closed / CLI 三出口）、`apps/workbench/tests/test_rankings_api.py`（4 项：五榜结构 / 持仓填充 / 坏文件 fail-closed / UI 区块存在）

### Docs

- 新增契约 `docs/contracts/rankings.md`、ADR `docs/architecture/0056-ranking-boards.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

## [4.0.0] - 2026-10-10

### Added

- **全市场选股接入（`X1`）**：日线宇宙从 JSON fixture（`core`/`watch`/`full`，数十~数百代码）扩到 `market.db` **全市场**（排除 BSE）。宇宙解析只有**一个入口** `research.market_universe.resolve_universe(source=...)`，`UNIVERSE_SOURCES = ("config", "market_db")`，默认仍是 `config`（X1 不改变既有行为）。契约 [`docs/contracts/market-universe.md`](docs/contracts/market-universe.md)、ADR [`0055`](docs/architecture/0055-market-universe.md)
  - **providers** `EngineSqliteProvider.list_symbols`：仓库 → 代码列表的**唯一定义** —— 日期窗口聚合（走 `idx_dp_date`）、`min_bars`、BSE 排除（经 `symbol.is_bse_symbol` 单点）、6 位归一、**裸码与带后缀码合并计数**、脏码（非 6 位）丢弃
  - **research** `resolve_market_universe`：只做资产类别过滤（复用 B4 单点 `portfolio.asset_class`）、`limit`、出处与代价记录、fail-closed；**不重复** BSE 前缀表，也**不重排** provider 结果
  - `MarketUniverse` 随结果返回出处与代价：`counts`（source → normalized → asset_matched → final）、`elapsed_s`、`peak_memory_mb`（`tracemalloc`，默认关）
- **CLI** `stock-platform-market-universe`：`--db` / `--asof` / `--asset-type` / `--min-bars` / `--limit` / `--include-bse` / `--probe-panel` / `--json` / `--symbols-only`；文档里的每个实测数字都由它现场产出
- **流水线接线**：`run_daily_pipeline(universe_source="market_db", market_symbol_source=...)` 自动注入本次 `asof` / `lookback_days`，报告新增 `universe{source,size}`；`daily_cli` 新增 `--universe-source` / `--market-db` / `--asset-type` / `--min-bars` / `--limit` / `--include-bse`
- 新增测试 `packages/research/tests/test_market_universe.py`（fake source）与 `packages/providers/tests/test_engine_sqlite_universe.py`（合成 sqlite，含裸码 / BSE / 脏码 / 窗口外数据），**全程不碰 3.14 GB 真实库**

### Changed

- 版本号 `3.13.9` → **`4.0.0`**（**major**：能力边界从 watch 宇宙扩到全市场）

### Verified

- 实测（`market.db` 3.14 GB / 877 万行 / asof 2026-09-03，见 [`docs/ops/market-universe-benchmark.md`](docs/ops/market-universe-benchmark.md)）：
  - 全市场枚举（stock / 排除 BSE）= **5227 只**，耗时 **0.21 s**、峰值 **1.04 MB**
  - `asset_type=all` 5241 只；`min_bars=60` 5194 只；`include_bse=True` 与默认一致（库内无 BSE 数据）
  - **全市场单日 PIT panel**：5227 只 → **5209 行** / **23.0 s** / 峰值 **498.8 MB**
  - SQL 口径：日期窗口聚合 **0.15 s** vs `SUBSTR(code,-2)` 全表扫描 **5.12 s**（**34×**）
- 全量 `pytest packages apps`（`replay`）= **698 passed / 0 failed**（679 → 698，**+19**）
- `scripts/check_versions.ps1` / `scripts/check_docs.ps1` 双绿（VERSION=4.0.0）

### Docs

- 新增契约 `docs/contracts/market-universe.md`、ADR `docs/architecture/0055-market-universe.md`、实测 `docs/ops/market-universe-benchmark.md`，均已登记进 `scripts/check_docs.ps1` 的 `$required`

### Notes

- ⚠️ **发现数据覆盖缺陷（非平台代码问题）**：`market.db` 自 **2026-09-04** 起每日 bar 数从 ~5.2k 塌到 **14** 只（引擎侧导入中断），**最后可用交易日 = 2026-09-03**。宇宙枚举（120 天窗口）不受影响，但**当日横截面 / 选股会几乎空**（PIT 要求 asof 当日有 bar）。`X3` / `X4` 开工前应先修引擎侧导入 —— 平台只读，不代抓
- 当前库**不含北交所数据**：`include_bse=True` 与默认结果完全一致（实际过滤 0 个）；排除规则为将来保留
- `X1` 只做内核 + CLI + 文档，**未新增 Workbench API**；UI 接入留待 `X2`（榜单体系对齐）
- 与既有红线无关：`L1` 未立项前不触碰 `liveTradingEnabled`

## [3.13.9] - 2026-10-10

### Added

- **数据源适配层**：新增三个 provider（均实现 `MarketDataProvider`，缺源 fail-closed 中文报错），统一接入非默认数据源（详见 [`docs/contracts/data-source-adapters.md`](docs/contracts/data-source-adapters.md)、[`docs/architecture/0054-data-source-adapters.md`](docs/architecture/0054-data-source-adapters.md)）：
  - **`workbuddy`**（`daily`+`realtime`）：WorkBuddy MCP 数据能力（`westock-data` / `neodata-financial-search`）的 **JSON 缓存适配器** —— 读 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` 下 `daily_{code}.json` / `realtime_{code}.json`（与 `replay` fixture 同构）；`write_daily_cache` / `write_realtime_cache` 是 schema 唯一生产点
  - **`tdx`**（`daily`）：读通达信本地 `vipdoc/{sh,sz,bj}/lday/*.day`（32 字节定长记录，`struct` 零依赖）；`STOCK_PLATFORM_TDX_ROOT` 或自动探测；实时未映射（fail-closed）
  - **`futu`**（`daily`+`realtime`）：懒加载 `futu-api` 连 OpenD（默认 `127.0.0.1:11111`）；`request_history_kline` / `get_market_snapshot`；缺包/无网关 fail-closed
- 新增预设 `workbuddy` / `cn_tdx` / `cn_futu`（均 `is_default=False`），能力矩阵各声明对应数据集
- 新增测试 `test_workbuddy.py` / `test_tdx.py` / `test_futu.py`（合成 JSON / `struct.pack` 二进制 / fake module+context，**零网络**）

### Verified

- 新增适配器 + 既有 preset/capability 测试 **26 passed**
- 全量 `pytest packages apps`（`replay`）= 见下方 Notes 之最新计数
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.9）

### Notes

- 生产默认仍 `cn_astock_http`；三新源均不触碰 `liveTradingEnabled`，仅数据读路径
- `workbuddy` 的「MCP 兼容」= MCP 桥接方落 JSON 缓存 → provider 只读消费（刻意不直连 Markdown/自然语言，避免解析脆弱性）

## [3.13.8] - 2026-10-10

### Fixed

- **修复涨跌停判定因 `pct_chg` 标度混用而近乎失效**（B5 遗留缺陷，见 `docs/contracts/trading-rules.md` §7）：`daily_price.pct_chg` 绝大多数**股票**行是小数（`0.0123` == 1.23%），绝大多数 **ETF** 行是百分点（`1.23` == 1.23%），旧实现按 `|x|>0.5` 一刀切，把新股首日 +86.9%（小数）误判为百分点、把 ETF 0.94%（百分点）漏判，导致 `rules.is_limit_up/down`（阈值按百分点）**漏判 99.6%**（实测涨停 1007 次 → 归一后 104034 次）

### Added

- 新增 `pct_scale.py` 单点定义：`detect_pct_scale(bars)` 用 **`close` 序列拟合投票**逐 code 判定 `fraction` / `points`（剔除 |隐含收益|>21% 的除权日防污染，少于 10 个可投会话则回退 `asset_class` 先验）；`to_points` / `normalize_pct_chg` 归一为百分点（`rules` 契约标度）
- `backtest.compute_features` / `run_portfolio_backtest` 新增 `pct_scale="auto"|"verbatim"`（默认 `auto`）；`auto` 用归一后的百分点重建复权价并喂涨跌停判定，`verbatim` 锁定旧行为供对照
- 新增 `packages/research/tests/test_pct_scale.py`（12 用例：判据 / 边界 / 回退 / 单点一致）

### Verified

- 真机全周期 A/B（`market.db` 3.14 GB / 877 万行 / 6974 码）：`verbatim`（旧）与 B1–B6 基线**逐位一致**（0.902353 / 0.105348 / −0.171435 / 0.7511 / 630）；`auto`（新默认）→ 总收益 **+91.71%**（0.917123）/ CAGR 10.67% / 最大回撤 −17.30% / 夏普 0.7612 / 笔数 **628**（跌停顺延生效，−2 笔）/ 终值 **95,856.17**
- 全量 `pytest packages apps`（`replay`）= **660 passed / 0 failed**（648 → 660，+12）

### Notes

- **这是行为修复（策略变更），非纯重构**：默认档 `auto` 相对 B1–B6 基线**基线移动**（涨跌停约束从失效变生效）；`verbatim` 档保留旧行为供回放。报告任何数字须声明 `pct_scale` 档位。

## [3.13.7] - 2026-10-09

### Fixed

- **修复 `GET /api/research/intel-report/crosswalk` 与 `GET /api/research/intel-report/prefill` 在**不带 `asof`** 参数时的 500**：`TypeError: default_brief_asof() missing 1 required positional argument: 'state'`。`default_brief_asof` 在 `v3.10.1`（`c640b5c`）改为必需 `state`，而 `v3.12.5`（`0da5f2d`）新增的这两个调用点仍按**旧签名**写成 `default_brief_asof()` —— 该缺陷**自 `v3.12.5` 起潜伏五个版本**（`v3.12.5` → `v3.13.6`）。现两处统一走既有的 `_resolve_asof(request, asof)`，重复的兜底逻辑一并消除
- 复现条件恰是 UI 默认行为：`loadIntelCrosswalk()` 在 asof 输入框为空时**不发 query string**，故该端点在浏览器首屏必崩。此前全部用例都显式传 `asof`，**兜底分支零覆盖**，CI 与真实路径脱节

### Added

- 新增静态守卫 `apps/workbench/tests/test_signature_call_guard.py`：AST 扫描包内所有「模块级唯一定义函数」的调用点，**位置实参 + 关键字实参少于必填参数即失败**（`*args` / `**kwargs` / 重名函数一律跳过，以杜绝误报）。自带「有牙齿」用例，能复现并捕获本次这处历史缺陷。全包扫描当前**零违规** —— 说明该 bug 仅此一处且已清
- 行为端回归：`test_intel_crosswalk_default_asof` / `test_intel_prefill_default_asof` 覆盖**不带 `asof`** 的真实调用路径

### Verified

- 真机端到端（`D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，只读；实例起在 `3021` 以避开占用中的 `3018`）：两条**裸调用**均 **HTTP 200** · `asof=2026-09-02`（replay 夹具日）· `writesBriefSqlite=false`
- 全量 `pytest packages apps`（`replay`）= **648 passed / 0 failed / 38.00 s**（`643` → `648`，+5）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.7）

### Notes

- 纯缺陷修复：无指标 / 口径变化，**回测基线逐位不变**

## [3.13.6] - 2026-10-09

### Added

- **`B6` 回测可视化扩展**：Workbench `#backtest` 面板新增「组合净值曲线（B1 引擎 · 只读 market.db）」区块 —— **净值曲线 + 回撤带 + 逐日表三者共用同一份 `daily` 数组**，悬停图上某日即高亮对应表行、点表行也定位图上该点（逐日表联动）。仍是 Jinja + static，**未引入任何新前端依赖**（手写 `createElementNS` SVG，无 chart/echarts/plotly/d3）
- 新增组合指标 `portfolio.drawdown_series(equity_curve)`：逐点**瞬时**回撤（`equity / peak - 1`，每次创新高归零）的**单点定义**；非正权益日（停牌）跳过但保持**索引对齐**（图上第 i 点 == 表第 i 行）。`max_drawdown_from_curve` 改为返回该序列的最深点（同一模块内委派），**scalar 指标与图上回撤带不可能分叉**
- 新增 API `POST /api/research/backtest/portfolio`：只读 `STOCK_PLATFORM_ENGINE_MARKET_DB`，走与 `stock-platform-backtest` CLI **完全相同的代码路径**（`load_engine_bars` → `filter_universe` → `run_portfolio_backtest`）；返回对齐的 `daily[]`（`date` / `equity` / `ret` / `drawdown` / `n_positions` / `invested_ratio`）+ `B2`–`B5` 指标块 + `params`。无 DB / 非法 `universe` 一律 fail-closed（503 / 400 中文）

### Changed

- `apps/workbench`：`routes/research.py` 新增 `PortfolioBacktestRequest` + `_daily_from_curve()`；`openapi_models.py` 新增 `PortfolioBacktestResponse`；`templates/index.html` / `static/app.js` / `static/app.css` 扩展可视化。Workbench API 操作数 **58 → 59**（全量 API 目录测与计数断言同步）
- 包根 re-export `drawdown_series`

### Verified

- **零回归（纯重构）**：`drawdown_series` 落地后全周期（2020-01～2026-09）默认档指标与 `B5` 基线**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `max_drawdown` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64（加载 13.4 s + 回测 49.3 s）
- **pre-`B6` oracle 等价**：测试保留旧实现为 oracle，对 600 点（含停牌日）序列断言 `max_drawdown_from_curve` **逐位相等**，并把「最深处 == 序列最小值」写成不变量
- **真机端到端**（`D:\workspace\stock_trading\a-stock-engine\data_cache\market.db`，3.14 GB，只读）：`POST /api/research/backtest/portfolio`（2025-09-01～2026-09-03）= **HTTP 200 · 18.5 s** · 245 交易日 · 85 笔 · 终值 46,502.02；`daily[0].ret is None`；`metrics.max_drawdown` **-0.193254** 与 `min(daily[].drawdown)` **逐位相等**
- 测试：全量 `pytest packages apps`（`replay`）= **643 passed / 0 failed / 37.22 s**（B6 新增 10 个用例：`drawdown_series` 5 + API/UI 契约 5）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.6）

### Docs

- `docs/contracts/portfolio-metrics.md`：补 `drawdown_series` 口径与「最深处 = `max_drawdown_from_curve`」契约
- `docs/plans/trading-system-roadmap.md`：`B6` 标 done → **B 域（B1–B6）全部收官**
- `docs/ops/backtest-baseline.md`：补可视化端点入口与耗时口径

## [3.13.5] - 2026-10-09

### Added

- **`B5` 回测↔在线规则统一层**：新增 `rules.py` 作为交易规则的**单点定义**——`ExitPolicy` / `CooldownPolicy` / `DriftPolicy`（frozen dataclass）、`ExitDecision` / `DriftDecision`，纯函数 `evaluate_exit()` / `advance_peak()` / `evaluate_drift()`，以及共享交易限制 `limit_pct()` / `is_limit_up()` / `is_limit_down()`
- **在线路径**：新增 `position_review.review_positions()` —— 对当前持仓逐只给出 `hold` / `exit` / `trim` / `add`，**调用与回测完全相同的 rules 函数**（吸收 `V2-code-review-20260905` 检查重点 item 5）
- 新增 CLI `stock-platform-position-review`：自包含模式（holdings JSON 自带价）或富化模式（`--db` + `--asof` 只读 `market.db`，经 `compute_features` 取同源复权价与 `ma20`/`ma60`，并由 `entry_date` 定位 `held_days`）
- **冷静期**（`cooldown_days`）：出场后 N 会话内禁止同码再入场；**持仓偏差**（`drift_band`）：权重相对偏离超带即 `trim` / `add`。两者**默认关闭**（`0` / `None`）
- **口径契约**：`docs/contracts/trading-rules.md` —— 退出规则顺序与 reason 字符串 / 冷静期 / 持仓偏差 / 涨跌停判据 / T+1 / 单点定义双路调用契约 / 已知局限

### Changed

- `run_portfolio_backtest` 的**全部**交易判断改为委派 rules：退出走 `evaluate_exit()`、峰值走 `advance_peak()`、涨跌停走 `is_limit_up()` / `is_limit_down()`；删除内联退出逻辑与本地 `limit_pct()`，`_Position` 变为 `rules.PositionState` 的别名
- `params` 新增回显 `exit_policy` / `cooldown_days` / `drift_band`（供"两侧参数一致"断言）
- 包根 re-export `ExitPolicy` / `CooldownPolicy` / `DriftPolicy` / `evaluate_exit` / `evaluate_drift` / `review_positions` 等

### Verified

- **零回归（纯重构）**：默认档全周期指标与 `B4` 基线**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64；耗时 加载 13.3 s + 回测 47.0 s
- **冷静期对照**（`cooldown_days=10`）：`total_return` 0.898259（−0.41 pp）· `n_trades` 631 · `final_equity` 94912.95（**−204.69**，≈ −0.22%）· `sharpe` 0.7508 —— 低频组合同码快速再入场罕见，故影响小；属风险约束而非收益工具
- **单点定义断言**：`backtest.evaluate_exit is rules.evaluate_exit`、`backtest.ExitPolicy is rules.ExitPolicy`、`backtest._Position is rules.PositionState` 等全部为真（同一对象，非等价拷贝）
- **差分一致断言**：同一持仓状态下，在线路径给出的 `reason` 与回测所用规则函数的输出**逐字相同**；且回测 `params.exit_policy` 与 `rules.ExitPolicy()` 默认值相等
- 测试：`pytest packages/research` = **179 passed**（B5 新增 41 个用例）；全量 `pytest packages apps`（`replay`）= **633 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.5）

### Docs

- 新增 `docs/contracts/trading-rules.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/ops/backtest-baseline.md`：新增退出/冷静期参数口径与冷静期对照
- `docs/plans/trading-system-roadmap.md`：`B5` 标 done（**关键路径项** `G1 → B1 → B5 → X4 → L1`）

## [3.13.4] - 2026-10-09

### Added

- **`B4` ETF 与资产类型支持**：`portfolio.asset_class(code)` **单点定义** —— 按共享前缀表返回 `stock` / `etf` / `fund`（`etf` = 命中 `_ETF_PREFIXES`；`fund` = 其余 `1xxxxx` / `5xxxxx`，**保守**按应税处理）；分类与印花税豁免由同一张表驱动，不可能分叉
- `run_portfolio_backtest(..., universe=)`：`stock`（默认，与引擎一致整体排除基金）/ `etf` / `all`（股票 + ETF 混池）；非法档位 `ValueError` fail-closed；旧参数 `exclude_funds` 保留为别名（显式传入时覆盖 `universe`）
- CLI 新增 `--universe {stock,etf,all}`（默认 `stock`），运行时在 stderr 回显入选行数 / 码数
- **分资产报告**：`compute_metrics(...)["by_asset"]` 按类给出 `n_trades` / `win_rate` / `avg_net_ret` / `turnover_notional`；`trades` 新增 `asset_class` 字段；既无 `code` 也无 `asset_class` 的交易跳过，空输入 = `{}`（**不编造**）
- **口径契约**：`docs/contracts/asset-classes.md` —— 三分类判定 / `universe` 三档语义 / 与免税绑定 / `by_asset` / 跨线对齐 / 实测发现
- 测试：新增 `test_asset_class.py`（语义 + **跨线互测**：静态解析引擎 `_is_fund` / `_is_etf` 前缀表 + `by_asset` 报告）

### Changed

- `backtest.py` 的基金过滤由「一刀切 `exclude_funds`」改为 `universe` 选择；**默认档 `universe="stock"` 与旧默认 `exclude_funds=True` 完全等价**
- `backtest.py` 与包根 re-export `asset_class` / `UNIVERSES`

### Verified

- **零回归**：`universe="stock"` 全周期指标**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64
- **宇宙对照**（同区间同参数，1618 日）：`stock` **+90.24%** / 630 笔 · `all` **+102.58%** / 609 笔（**ETF 0 笔**）· `etf` **-16.31%** / 9 笔
- **免税路径贯通实测**：混池中真实 ETF `515250` 卖出成本率 **8.54e-05**（仅佣金）vs 股票参照 `600519.SH` **5.854e-04**（佣金 + 万5 印花税）
- **三条诚实发现**（已写入契约 §6）：① 默认门槛 `min_pick_score=0.80` 下 ETF 全部被挡（ETF 合成分中位上限 0.50 vs 股票 0.86）→ **混池 ≠ ETF 配置**；② 入场闸门截面分位取自当日入选帧，加入 ETF 会改变股票入选 → `all` 数字**不可与 `stock` 横比**；③ 原始 ETF 池含非标准 / 流动性枯竭条目 → 作宇宙前须先清洗（X 域议题）
- `pytest packages/research` = **138 passed**（B4 新增 18 个用例）；全量 `pytest packages apps`（`replay`）= **592 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.4）

### Docs

- 新增 `docs/contracts/asset-classes.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/ops/backtest-baseline.md`：新增 §3.2 资产类型 / 宇宙对照 + §6 已知限制补 ETF 名册未清洗
- `docs/plans/trading-system-roadmap.md`：`B4` 标 done

## [3.13.3] - 2026-10-09

### Added

- **`B3` 费用与摩擦模型配置化**：新增 `portfolio.CostModel`（frozen dataclass）—— `commission_rate` / `stamp_sell_rate` / `slippage_bps` / `min_commission` / `etf_stamp_exempt`，含 `trade_cost()`（比例）/ `costs()`（金额，含佣金下限）/ `fill_price()`（滑点后成交价）/ `zero()`（对标引擎 `--zero-cost`）
- **滑点**（此前完全缺失的摩擦项）：单边基点，**仅作用于成交价**（买入抬价、卖出压价）；选股 / 入场闸门 / 涨跌停判定 / 止损目标与移动止损**触发**一律读参考收盘价
- 回测引擎新增 `slippage_bps` / `min_commission` 参数；`trades` 的 `entry_price` / `exit_price` / `entry_value` / `exit_value` 改为**真实成交口径**（含滑点）
- CLI 新增 `--commission-rate` / `--stamp-sell-rate` / `--slippage-bps` / `--zero-cost`；运行时在 stderr 回显费用档
- **口径契约**：`docs/contracts/cost-model.md` —— 固化费率 / 滑点语义 / 比率与金额双 API / 免5 含义 / 跨线对齐 / 敏感性口径
- 测试：新增 `test_cost_model.py`（语义 + **跨线互测**：静态解析 `a-stock-engine/local_backtest.py` 的常量与 ETF 前缀表）

### Changed

- **费用单点定义**：费率常量、资产类型判定（`norm_code` / `is_fund` / `is_etf` / `_ETF_PREFIXES`）与 `trade_cost` 从 `backtest.py` 移入 `portfolio.py`；`backtest.py` 顶部 re-export，旧调用点 `from .backtest import ...` 不变（`backtest.CostModel is portfolio.CostModel` 为真）。这是 `B5`（回测↔在线规则统一层）的又一块铺路砖

### Fixed

- **买入侧计费不对称**：建仓与持仓成本基（`cost_basis`）原先硬用 `commission_rate`、绕过 `trade_cost()`，现统一走 `CostModel` 使买入腿与卖出腿对称。因 ETF 与股票买入佣金相同，**当前数值无害**，但消除了一引入滑点 / 分品种费率即漏计的隐性缺陷

### Verified

- **零回归**：默认档（滑点 0）全周期指标**逐位不变** —— `total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `final_equity` 95117.64 / `turnover_notional_per_year` 11.28 / `avg_hhi` 0.086483
- **成本敏感性**（全周期 1618 日 / 6964 码；权益差 vs 默认档）：零成本 **+1226.93** / 滑点 5 bps **−411.45** / 滑点 10 bps **−1442.73**（≈ 2.89% 收益）—— 费率拖累与 10 bps 滑点拖累同级，**摩擦不可忽略**
- **两线互测**：平台 `CostModel.trade_cost` 与引擎 `_trade_cost` 在 股票/ETF × 买/卖 四象限逐项相等；费率常量与 ETF 前缀表（30 项）一致
- `pytest packages/research` = **120 passed**（B3 新增 16 个用例）；全量 `pytest packages apps`（`replay`）= **574 passed / 0 failed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.3）

### Docs

- 新增 `docs/contracts/cost-model.md` 并登记进 `scripts/check_docs.ps1` required
- 新增 `docs/plans/b3-cost-model-milestone.md`（里程碑方案），`docs/plans/README.md` 登记
- `docs/plans/trading-system-roadmap.md`：`B3` 标 done
- `docs/ops/backtest-baseline.md`：新增成本敏感性小节

## [3.13.2] - 2026-10-09

### Added

- **`B2` 组合级指标补全**：`portfolio.compute_metrics` 新增 —— 成交额口径换手 `turnover_notional_per_year`（`Σ(entry_value+exit_value) / mean(equity) / years`）、持仓集中度 `avg_hhi` / `avg_top_weight`、真实暴露 `avg_invested_ratio`、持仓数 `avg_positions` / `max_positions`。缺失输入一律 `None`，**不编造**
- **`hhi()` 工具**：赫芬达尔-赫希曼指数，先归一化再平方求和（scale-free，对原始市值与权重同值；单票 = 1.0，n 只等权 = 1/n，空仓 = 0.0）
- 组合引擎净值曲线点新增 `hhi` / `top_weight` / `invested_ratio` **标量**（不引入 dict 列，CSV / JSON 输出不受影响）；`trades` 新增 `entry_value` / `exit_value` 成交额
- **口径契约**：`docs/contracts/portfolio-metrics.md` —— 固化年化基数（252）/ 无风险利率（0）/ 回撤符号 / 换手双口径 / 集中度口径 / 「不可横比」铁律
- 测试：`test_portfolio.py` 增补 HHI 与 B2 字段用例；`test_backtest.py` 增补曲线集中度与成交额用例

### Changed

- **指标实现单点化**：`compute_metrics` 移入 `portfolio.py` 作为唯一权威定义；`backtest.py` 改为顶部 `from .portfolio import compute_metrics` **re-export**（`backtest.compute_metrics is portfolio.compute_metrics` 为真），旧调用点 `from .backtest import compute_metrics` 不变。这是 `B5`（回测↔在线规则统一层）的铺路砖

### Verified

- `pytest packages/research` = **104 passed**（B2 新增 7 个用例）；全量 `pytest packages apps`（`replay`）= **558 passed / 0 failed / 19.00s**
- 全周期指标**逐位不变**：`total_return` 0.902353 / `cagr` 0.105348 / `mdd` -0.171435 / `sharpe` 0.7511 / `n_trades` 630 / `win_rate` 0.4619 / `avg_hold_days` 35.41 / `final_equity` 95117.64 —— **仅新增字段，旧口径未动**
- 全周期耗时 **61.8 s**（加载 11.5 s + 回测约 50 s），新增逐日 HHI 计算**无感**
- 新口径实测（2020-01～2026-09，1618 日 / 6964 码）：成交额换手 **11.28 倍/年**、平均 HHI **0.0865**、平均最大单票权重 **10.17%**、平均仓位 **80.0%**、平均持仓 **13.6 只**、最大并发 **15**

### Docs

- 新增 `docs/contracts/portfolio-metrics.md` 并登记进 `scripts/check_docs.ps1` required
- `docs/plans/trading-system-roadmap.md`：`B2` 标 done
- `docs/ops/backtest-baseline.md` §3 回填集中度 / 成交额换手

## [3.13.1] - 2026-10-09

### Changed

- **行情库加载器提速 4.4×**：`backtest_cli.load_engine_bars` 原用 `WHERE date BETWEEN ? AND ? ORDER BY code,date`，全周期窗口需 **54.9 s**。同一窗口实测：`ORDER BY date`（命中 `idx_dp_date`）50.6 s、不排序 + pandas 排序 52.8 s、**全表流式 `SELECT` + 内存过滤仅 12.5 s** —— 该表只有 `idx_dp_date`，投影列迫使回表，`WHERE` 与索引均无收益。改为全表读取后在 pandas 内过滤 / 排序。**全周期回测 106 s → 65 s**（加载 11.5 s + 回测 48.6 s）

### Added

- `packages/research/tests/test_backtest_cli.py`：锁定加载器的日期窗口 / 代码过滤 / 排序 / 只读语义与 BSE 过滤（**8 passed**）

### Fixed

- 修正 `[3.13.0]` 条目中的测试计数笔误（**556 → 543**，实测；该版发布时全量为 543 passed）

### Verified

- 性能改动**零行为变化**：全周期指标逐位不变（`total_return` 0.902353、`cagr` 0.105348、`mdd` -0.171435、`sharpe` 0.7511、`n_trades` 630、`win_rate` 0.4619、`avg_hold_days` 35.41），分年收益与卖出原因分布全同
- 全量 `pytest packages apps`（`replay`）= **551 passed**
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.1）

### Docs

- `docs/ops/backtest-baseline.md` §5 新增加载器问题条目、§6 更新耗时
- `docs/ops/workbuddy-runtime-limits.md` §9 补充"提速后回到默认档"说明

## [3.13.0] - 2026-10-09

### Added

- **`B1` 组合级回测引擎**：`packages/research/src/stock_platform_research/backtest.py`——在 `lvrev` + `apply_entry_gates` 同一内核之上补齐持仓层（entry/peak/shares）、持有期（`min_hold` 45）、硬止损 / 目标止盈 / 趋势破位 / 移动止损、并发上限与 100 股取整、**跌停顺延 / 涨停跳过**，以及对齐 `local_backtest.py` 的费用模型（佣金万0.854 双边、印花税万5 仅卖出、ETF 免）
- **指标层**：年化 / 最大回撤 / 夏普 / 索提诺 / Calmar / 换手 / 胜率 / 平均持有
- **`stock-platform-backtest` CLI**：只读挂载 `STOCK_PLATFORM_ENGINE_MARKET_DB`，批量加载 `daily_price` 并输出净值曲线 CSV
- **回测基线报告**：`docs/ops/backtest-baseline.md`——2020-01～2026-09 全市场（1618 交易日 / 6964 码）

### Changed

- **`gates.apply_entry_gates` 向量化**：原逐行 `iterrows` 在全市场回测中达 ~880 万次调用，导致全周期回测超命令超时；每个分支均为"拒绝"，等价改写为"任一条件命中即拒绝"。**全周期回测 200 s → 106 s**。等价性由 `packages/research/tests/test_gates.py` 以原逐行实现为 oracle 证明（12 组随机数据 + 缺列场景）
- **复权修正**：引擎库 `close` 为未复权价而 `pct_chg` 为真实涨跌幅（复现：`600551.SH` 单日 close 跳变 -32.6% 而当日 `pct_chg` 仅 -10%）。`compute_features` 改用 `pct_chg`（混用标度自动判定）重建复权价，修复后极值交易归零（最差 -15.2%，无 <-20%）

### Verified

- `pytest packages/research/tests/test_backtest.py packages/research/tests/test_gates.py` = **17 passed**
- 全量 `pytest packages apps`（`replay`）= **543 passed**（2026-10-09 实测更正，原记 556 有误）
- `scripts/check_docs.ps1` / `scripts/check_versions.ps1` 双绿（VERSION=3.13.0）

### Baseline

- 总收益 **+90.24%**｜CAGR **+10.53%**｜最大回撤 **-17.14%**｜夏普 **0.751**｜胜率 **46.2%**｜630 笔｜平均持有 35.4 天
- 与 `a-stock-engine` 差异全部归因于口径（持有期 / 区间 / L0 闸门 / ST 与生存者过滤 / 复权），**不宣称复现引擎数字**（遵循 `empirical/BASELINE.md` §5 铁律）

## [3.12.6] - 2026-10-09

### Added

- **自有推进路线图**：`docs/plans/trading-system-roadmap.md`——既有规划（M0–M47 / U1–U8 / MR-1–MR-5）执行见底后重开产品目标，定义 G/B/S/X/L/C 六域里程碑（工程地基 / 回测 / 策略深化 / 选股 / 实盘 / 双线收口）与关键路径 `G1 → B1 → B5 → X4 → L1`
- **WorkBuddy 运行时限额实测**：`docs/ops/workbuddy-runtime-limits.md`——单请求 100 步、命令默认 120s（PowerShell 上限 600s）、上下文压缩阈值 60/70/90%、沙箱 6 程序黑名单、会话缓存上限 3000 MB；含对回测阶段的设计约束

### Changed

- **`G1` 工程地基（环境恢复）**：5 个 `stock_platform_*` 包 editable install 恢复；`pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）**526 passed / 0 failed**
- **`G2` 外部路径与 env 治理**：全仓仓根路径 `D:\workspace\git\` → `D:\workspace\stock_trading\` 迁移（**14 个文件**：README × 4、`docs/ops` × 5、`docs/upstream` × 2、`templates/index.html`、`.env.example`、`scripts/ops/stock-platform-daily.xml`）；`.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 实测指向 `a-stock-engine/data_cache/market.db`（3.14 GB，冒烟 600519 → 406 交易日）；计划任务 `WorkingDirectory` 修正，XML 编码声明 `UTF-16`→`UTF-8`（原声明与文件实际 UTF-8 字节不符）

### Verified

- `scripts/check_docs.ps1`：**OK**（VERSION=3.12.6，112 required files，139 md）
- `scripts/check_versions.ps1`：**OK**（VERSION 与 5 个 pyproject + 5 个 `__init__` 一致）
- `pytest packages apps`：**526 passed / 1 warning / 14.14s**

## [3.12.5] - 2026-09-23

### Added

- **MR-3 情报 ↔ brief 对照**：ADR [`docs/architecture/0053-intel-report-brief-crosswalk.md`](docs/architecture/0053-intel-report-brief-crosswalk.md)；Workbench `#intel-report` 与向导/今日推荐互跳；`GET /api/research/intel-report/crosswalk`（asof/宇宙只读对照）
- **MR-5 平台数据部分预填**：`GET /api/research/intel-report/prefill`（json/html）+「用平台数据预填预览」；填日历 / 已存 brief picks / 可选 concept_blocks / ops；缺能力进 `missing` 中文说明，保留 `{{占位符}}`；**不写** brief SQLite
- Workbench 测：`tests/test_intel_report.py` + OpenAPI / 全量 endpoint 注册（现 **58** 个 path+method）

### Changed

- 里程碑 MR-3/MR-5 → done；版本 **3.12.5**；**未**引入 WebSearch 主链 / Skill 运行时 import / M-E4 实盘

## [3.12.4] - 2026-09-23

### Added

- **market-report-dashboard 配方吸收（MR-1/2/4）**：三类 HTML 模板只读归档至 `docs/upstream/market-report-templates/`；Workbench `#intel-report` 入口 + `static/report-templates/` 预览；Skills 治理挂接；里程碑 [`docs/plans/market-report-dashboard-merge-milestones.md`](docs/plans/market-report-dashboard-merge-milestones.md)
- **小测**：Workbench UI / 静态模板可访问断言

### Changed

- 上游 README / 能力盘点 / AGENTS / ROADMAP / `check_docs` 短链同步；**未**引入 WebSearch 第二数据主链；版本 **3.12.4**

## [3.12.3] - 2026-09-22

### Added

- **Workbench 全量 API 自动化测**：`apps/workbench/tests/test_all_api_endpoints.py` — OpenAPI 56 个 path+method 参数化「每接口至少一击」+ 覆盖门禁；`/docs` `/redoc` `/openapi.json` 额外 smoke；replay 零公网；fail-closed 路径有意识断言 4xx/5xx

## [3.12.2] - 2026-09-22

### Changed

- **文档整理**：`.cursor/plans` 正式正文迁入 `docs/plans/`（能力盘点 / 合并路线图 / U 线 / M-D1·R1·A1）；新增 `docs/README.md`、`docs/engineering/`、`docs/upstream/` 配方摘要；plans 目录仅留索引指针；交叉链接与 `check_docs` 路径列表同步；版本 **3.12.2**

## [3.12.1] - 2026-09-22

### Added

- **Workbench OpenAPI**：全部 HTTP 路由补齐 `summary` / docstring、响应 envelope（`openapi_models.py`）、常见错误码；`/docs` `/redoc` `/openapi.json` 可用
- **OpenAPI 契约测**：`tests/test_openapi_contract.py`（路径存在 + 200 schema 非空 object）
- **测试分层**：pytest markers `unit` / `integration`；wizard / brief→paper→broker 标 integration
- **CI**：`monorepo` job 跑 `pytest packages apps`（`STOCK_PLATFORM_PROVIDER_PRESET=replay`）；CONTRIBUTING 对齐

### Changed

- 文档：CONTRIBUTING / workbench README 写明分层命令与 `/docs` 入口；版本 **3.12.1**

## [3.12.0] - 2026-09-22

### Added

- **M-R5**：策略 A/B 进日用主路径旁路（`STOCK_PLATFORM_STRATEGY_AB` / `strategyAb`；**默认关闭**；不替换 picks）
- **M-U3**：ADR 0052 TSP UI 子集范围 **Accepted**
- **M-U4**：`#tsp-subset` 近 N 日 `direction_accuracy` SVG sparkline（零新前端依赖）
- **M-A4**：可选更深多角色 LLM 图（`STOCK_PLATFORM_DEEP_LLM_GRAPH`；非默认；fail-closed；禁 dataflows）
- **M-D6**：[`docs/ops/m-d6-batch-recipe-upstream-feedback.md`](docs/ops/m-d6-batch-recipe-upstream-feedback.md)
- **M-E3**：[`docs/ops/broker-port-honesty.md`](docs/ops/broker-port-honesty.md)（mock / experimental / 未接真实）
- **M-R4 深刀**：ICIR / `std_ic` / `summarize_factor_ic_from_rows` + `POST /api/research/backtest/factor-ic`

### Changed

- 能力域路线图 Later 余量收口（**M-E4 实盘仍门禁未开工**）；版本 **3.12.0**

## [3.11.1] - 2026-09-18

### Added

- **M-R3**：[`docs/ops/empirical-baseline-compare.md`](docs/ops/empirical-baseline-compare.md) + `compare_empirical_baseline`（只读对照，无双调度）
- **M-R4 薄刀**：`summarize_factor_ic` / Spearman rank IC（不进 brief 主路径）
- **M-A3**：`role_prompts`（政策/游资/解禁等）+ 所需 capabilities fail-closed
- **M-E2**：错哈希 / admission / order_guards 安全缺口回归测（SIMULATE）
- **M-D5**：[`docs/ops/m-d5-global-thin-gap.md`](docs/ops/m-d5-global-thin-gap.md)（美港薄缺口；不接期权/SEC）
- **M-S2**：[`docs/ops/skill-recipe-feedback-checklist.md`](docs/ops/skill-recipe-feedback-checklist.md)
- **Workbench**：`#concept-blocks` / `#pit-fundamentals` 只读面板

### Changed

- 能力域路线图 Later 首批收口；版本 **3.11.1**

## [3.11.0] - 2026-09-18

### Added

- **M-D3 `concept_blocks`**：能力矩阵第 13 项；`astock_http`（`slist`/`em_get`）+ `replay` fixtures；`GET /api/market/concept-blocks`；ADR 0051
- **M-D4 engine PIT 只读**：`get_fundamentals_pit` / `get_daily_basic_pit`；`GET /api/research/pit/fundamentals`；无 DB/缺表 fail-closed 中文；ADR 0050 → Accepted
- **M-R2 walk-forward 摘要**：`packages/research/walkforward.py` + `POST /api/research/backtest/walk-forward` + `#backtest` 折叠入口；契约 `docs/contracts/walk-forward-summary.md`
- **M-A2 评级边界**：`packages/agents/rating.py`（5 档 + 词边界矩阵测）；LLM 自由文本回退接线；禁 dataflows
- **M-U2**：绩效 `recentDays[]` 近 N 日 `direction_accuracy`；推荐页迷你 chips
- **M-E1**：[`docs/ops/v2-safety-test-mapping.md`](docs/ops/v2-safety-test-mapping.md)（不恢复 Futu）

### Changed

- 能力域合并路线图 Next 批次收口勾选；版本 **3.11.0**

## [3.10.7] - 2026-09-17

### Added

- **能力域合并 Now 批次（文档）**：M-D1 缺口对照表、M-D2 ADR 0050（engine PIT 只读草案）、M-R1 TSP 首刀选型（walk-forward 摘要）、M-A1 TA 可移植清单、M-S1 Skills 治理 SSOT（`docs/ops/skills-governance.md`）

### Changed

- **M-U1 Workbench 可读性**：导航 ①向导→②推荐→③纸面；向导步骤清单；推荐/历史/复盘空态与中文 tip；交叉锚点链接

## [3.10.6] - 2026-09-15

### Added

- **回测 ↔ 今日推荐打通**：`#backtest` 逐日表「看推荐」→ 跳转 `#recommend` 加载该日 picks（已存 SQLite 则回看+复盘，否则按同宇宙重生成）；回测 `days[]` 带 `pickSymbols`
- **推荐页绩效摘要条**：pending / settled / `direction_accuracy` + 回测/绩效/策略对比快捷链；空态/fail-closed 文案统一
- **策略对比接 engine 真面板**：`POST /strategy/compare` 无 body.panel 时优先 `build_multi_day_pit_panel`（engine/daily）；标注 `panelSource`；`requireEngine` 时无源 503；否则回退 fixture 并写 `panelNote`
- **日批一键 live+落库+结算**：`Invoke-DailyPipeline.ps1 -LiveDay`；CLI `--settle-after`（记入 JSONL + 结算）；`daily-pipeline.md` 更新

### Changed

- 里程碑计划：U8 联通切片收口；下一档见 Now/Next/Later

## [3.10.5] - 2026-09-15

### Added

- **U7 最小切片（回测进 Workbench）**：`POST /api/research/backtest/rolling-review` + `#backtest` 区；对 watch/full 宇宙按最近 N 日滚动推荐并用 `review_stored_brief` 汇总 `direction_accuracy` / 样本数；优先只读 `STOCK_PLATFORM_ENGINE_MARKET_DB`；无日线 fail-closed 中文提示
- **U6 轻量**：向导 / 今日推荐 / defaults 可选 `universeTier`（core|watch|full）；切层级重载 symbols；明示勿一次全市场
- `.env.example` 强化 `STOCK_PLATFORM_ENGINE_MARKET_DB` 中文说明（与 brief SQLite 分离）

### Changed

- 里程碑：U6/U7 最小切片收口为 done（轻量）；完整策略 A/B 与全市场仍后置

## [3.10.4] - 2026-09-15

### Added

- **pending 自动结算**：`GET /api/research/performance?autoSettle=true`（默认）与 `POST /performance/settle`；有足够后续日线时把 JSONL pending 结算进盘，`direction_accuracy` 反映每日推荐；CLI `--settle-daily`
- **a-stock-engine 日线适配**：`engine_sqlite` + `STOCK_PLATFORM_ENGINE_MARKET_DB`（只读 `market.db`/`daily_price`）；预设 `cn_engine_sqlite`；结算优先用本地库；文档 `docs/ops/engine-market-db.md`
- UI：`#performance` 显示本次新结算 / settle 源；「结算 pending」按钮

### Changed

- 里程碑 Next（pending 自动结算）收口为 done

## [3.10.3] - 2026-09-15

### Added

- **U3 复盘 UI**：历史推荐「回看 / 复盘」→ T+1/T+5 明细表（pending / 收益 / 方向对错）；汇总 `direction_accuracy` 与 performance 口径对齐
- **推荐 → 绩效闭环**：生成 brief 落库成功后自动 `log_brief_decisions`（同 asof+symbol 幂等跳过）；`#performance` 展示 pending；一键「记入当前 asof」；`POST /performance/log-brief` 支持 `fromStore`
- **U5**：`/api/ops/health` 增加 `providerPreset` / `briefFallback` / `supplementTokenConfigured`（仅布尔）；运维面板可见
- **U4**：`stock-platform-daily` / `Invoke-DailyPipeline.ps1` 支持 `-Provider tushare`（及别名）；`STOCK_PLATFORM_DAILY_PROVIDER`；缺 token fail-closed；`daily-pipeline.md`「真实日用」段
- 文档：`live-startup.md` 日用最小步骤；`.env.example` 日批 / 绩效路径说明

### Changed

- 里程碑计划按「商用可用最短路径」重排 Now（U3 UI → 闭环 → U5 → U4 → U1 冒烟）

## [3.10.2] - 2026-09-15

### Added

- **U2 每日 brief 持久化（SQLite）**：`STOCK_PLATFORM_DB_URL`（默认 `sqlite:///./data/stock_platform.db`）
  - 薄 repository：`stock_platform_research.persistence`（业务不绑死 SQLite 方言；日后可换 PG）
  - 权威存档字段：asof / provider / universe / picks / softGates / gatesRelaxed / dataNote / generatedAt / environment=SIMULATE
  - 同日重复生成：**按 asof 幂等覆盖**
  - Workbench：生成推荐默认自动落库；`GET /api/research/briefs` 历史列表；`GET /api/research/briefs/{asof}` 回看
  - UI「今日推荐」历史表；日批 `run_daily_pipeline` 与 Workbench 共用同一 writer
  - U3 雏形：`GET /api/research/briefs/{asof}/review`（T+1 收益 / pending；完整复盘后续）
  - 文档：ADR 0049 实现节；`.env.example` 已有中文说明；`*.db` / `/data/` 已在 `.gitignore`

### Fixed

- **可用的「今日推荐」路径**：向导 / `#recommend` 默认 asof 按数据源选择（live→最近 CN 交易日；replay→样例日 `2026-09-02`）；主按钮「生成今日推荐」；向导成功后跳转并渲染 TopN 卡片
- **live 日线失败显式回退**：`astock_http` 传输失败时，若已设 `STOCK_PLATFORM_TUSHARE_TOKEN` 则回退 `tushare_http` 并标注「已回退 Tushare」；仅当 `STOCK_PLATFORM_BRIEF_FALLBACK=replay` 才回退 fixtures（不静默假数据）
- **空 picks 可读说明**：截面为空或闸门滤尽时返回中文 `emptyPicksMessage` / `emptyPicksTip`；默认 `softGates` 在闸门过严时软化展示演示排序
- **友好错误**：ConnectionError 等上游中断返回中文 tip（非整段 traceback）

## [3.10.0] - 2026-09-15

### Added

- **Tushare 兼容 HTTP 补充源**（ADR 0048）：`TushareHttpProvider` / `tushare_http`
  - 首切片矩阵能力：`daily`（`api_name=daily`，不复权；成交额千元→元）
  - helper：`get_trade_cal`（`api_name=trade_cal`，不进矩阵）
  - raw HTTP POST，无 `tushare` SDK / MCP 硬依赖；可注入 `post_json`（CI 零公网）
  - 环境变量：`STOCK_PLATFORM_TUSHARE_TOKEN` / `STOCK_PLATFORM_TUSHARE_URL`（默认 `https://t.xiaodefa.top/`）
  - 预设 `cn_tushare_http`（daily→tushare_http，其余 CN 仍 astock_http）；**生产默认仍为 `cn_astock_http`**
  - **安全**：切勿把真实 token 提交进 git / CHANGELOG / ROADMAP；`.env.example` 仅占位符

## [3.9.5] - 2026-09-15

### Fixed

- **Workbench 向导 daily brief / 东财连接中断**：`em_get` 对 `RemoteDisconnected`/`ConnectionError` 退避重试（`EM_HTTP_RETRIES`）；会话复用并保持 `STOCK_PLATFORM_HTTP_TRUST_ENV=0`；`get_daily` 单标的失败可继续（全失败才报错）；向导返回 **503** 中文 tip（可设 `replay` 离线，不静默假数据）；交易仍 SIMULATE

## [3.9.4] - 2026-09-14

### Fixed

- **Workbench 日用纸面 UX**：向导 /「一键到纸面」/ 建草稿在无 active strategy 时自动 ensure 默认 SIMULATE 策略（幂等），状态文案「已自动激活默认纸面策略」；纸面区提供「激活默认策略」；常见执行错误改为中文 detail（仍不绕过时间窗等闸门，无实盘）

## [3.9.3] - 2026-09-14

### Changed

- **Workbench 行情查询结果可读性**：日 K OHLCV 表、实时快照卡片、资金流/财务万亿格式、五档买卖着色；中文表头；空态中文；原始 JSON 默认折叠；补 realtime 面板

## [3.9.2] - 2026-09-14

### Changed

- **Workbench UI 结构化扫读**：向导步骤条、运维/纸面/broker 键值、矩阵可用 pill、绩效 stat、辩论 rounds；实验区 JSON 默认折叠；导航高亮（ADR 0047 补全）

## [3.9.1] - 2026-09-14

### Changed

- **Workbench UI 日用抛光（ADR 0047）**：主流程（向导 / 推荐卡片 / 纸面）置顶；行情工具、运维矩阵、实验区折叠；推荐可读卡片（symbol / score / reasons）；原始 JSON 默认折叠；锚点自动展开祖先 `<details>`

## [3.9.0] - 2026-09-14

### Changed

- **M47 生产 live 行情默认**：Workbench 启动偏好默认 `cn_astock_http`（全 CN 能力 → `astock_http` / `em_get`）
  - CI / pytest：`STOCK_PLATFORM_PROVIDER_PRESET=replay`（fixture + GitHub Actions）保持零公网
  - 美港：`us_hk_global_http` 预设（daily/realtime → `global_http`）
  - 上游失败 fail-closed（熔断 503 / HTTP 502 / 缺方法 501）；不静默回退 fixtures
  - 默认 `STOCK_PLATFORM_HTTP_TRUST_ENV=0`（忽略坏系统代理）
  - 文档：`docs/ops/live-startup.md`；交易仍 paper / SIMULATE（`liveTradingEnabled=false`）

## [3.8.1] - 2026-09-14

### Fixed

- **日流水线 replay 默认可跑通**：样例宇宙（`600519`/`000001`/`510300`）对齐 providers fixtures；日线扩至 ≥60 根以支撑 lvrev；补齐 `fund_flow`/`adj_factor`/`full_minute`；文档命令与 `test_daily_pipeline_repo_fixtures_nonempty_picks` 断言 exit 0 + 非空 picks

## [3.8.0] - 2026-09-14

### Added

- **Phase E 日用稳定收口（M39–M46）**
  - M39：分层宇宙 + 可读推荐理由（ADR 0040）
  - M40：`stock-platform-daily` refresh→brief 流水线（ADR 0041）
  - M41：`sector_fund_flow` / `news`（ADR 0042）
  - M42：日历 2028+ + Task Scheduler/cron（ADR 0044）
  - M43：组合回测指标 + 纸面 fills 对齐绩效（ADR 0043）
  - M44：LLM 预算/截断/降级（ADR 0045）
  - M45：Workbench IA + 一键向导（ADR 0046）
  - 默认仍 paper + replay + SIMULATE；无 SPA；无真实券商；同花顺真实 transport 仍 backlog

## [3.7.0] - 2026-09-14

### Added

- **大里程碑 M45 完成**：Workbench IA + 一键向导
  - 顶栏分区：日用向导 / 推荐 / 纸面 / 运维；`#wizard` + `#ops`
  - `POST /api/research/wizard/daily`（refresh→brief→to-paper；分步可见失败）
  - ADR 0046；无 SPA；无实盘默认文案

## [3.6.0] - 2026-09-14

### Added

- **大里程碑 M44 完成**：LLM 成本/质量控制
  - 调用/token 预算；截断告警（含 Responses incomplete）；超限默认降级 deterministic
  - ADR 0045；默认仍 deterministic；`[llm]` 仍为可选 extra

## [3.5.0] - 2026-09-14

### Added

- **大里程碑 M43 完成**：组合回测加深 + 绩效对齐纸面成交
  - `portfolio_metrics` / `run_portfolio_pit`（回撤、换手、成交数）
  - `align_fills_to_performance` 从纸面 fills 回填 JSONL；`direction_accuracy` 口径不变
  - ADR 0043；默认 SIMULATE；CI fixtures

## [3.4.0] - 2026-09-14

### Added

- **大里程碑 M42 完成**：日历 2028+ + Task Scheduler/cron 运维包
  - CN/US/HK 静态休市日延伸至 2028+（provisional）
  - `scripts/ops/Invoke-DailyPipeline.ps1` + Task Scheduler XML + cron 样例
  - `docs/ops/scheduler.md` / `calendar-maintenance.md`；ADR 0044

## [3.3.0] - 2026-09-14

### Added

- **大里程碑 M41 完成**：板块资金流 / 新闻特征
  - 能力 `sector_fund_flow` / `news`；replay + `astock_http`（`em_get`）
  - 契约 + fixtures；workbench API/薄 UI；缺能力 fail-closed
  - ADR 0042；默认 replay；CI 零公网

## [3.2.0] - 2026-09-14

### Added

- **大里程碑 M40 完成**：定时 refresh→brief 日流水线
  - `run_daily_pipeline` + CLI `stock-platform-daily`；产物 `briefs/{asof}` + `latest.json`
  - 同 asof 幂等覆盖；失败 fail-closed 写 `failure.json`
  - `docs/ops/daily-pipeline.md`；ADR 0041；默认 replay

## [3.1.0] - 2026-09-14

### Added

- **大里程碑 M39 完成**：日用宇宙扩容 + 可读推荐理由
  - 分层宇宙 `core` / `watch` / `full`（`load_universe_tiers`）；样例 `universe_cn_daily.json`
  - brief `reasons[]` + `reasonSummary`（保留兼容 `reason`）；`#recommend` 展示中文摘要
  - `docs/ops/daily-universe.md`；ADR 0040；CI 仍用小 fixture；默认 replay + SIMULATE

## [3.0.0] - 2026-09-14

### Added

- **Phase D 同花顺模拟盘收口（M35–M38）**
  - M35：`BrokerPort` / `PaperBroker` / `resolve_broker`（ADR 0036）
  - M36：`ThsSimBroker` + mock transport；experimental HTTP 扩展点（ADR 0037）
  - M37：`GatedBroker` / admission 接到 `ths_sim`（ADR 0038）
  - M38：brief → broker E2E；`GET /api/broker/status`；`#broker` 只读面板（ADR 0039）
  - 默认仍 `STOCK_PLATFORM_BROKER=paper` + replay；SIMULATE；无实盘
  - 真实 THS HTTP：**experimental/pending**（无稳定公开零售模拟盘 API）

## [2.9.0] - 2026-09-14

### Added

- **大里程碑 M37 完成**：风控闸门接到外部模拟
  - `assert_sim_gates` / `GatedBroker`；ths_sim 复用 timing/window/idempotency/admission
  - ADR 0038

## [2.8.0] - 2026-09-14

### Added

- **大里程碑 M36 完成**：同花顺模拟盘适配器
  - `ThsSimBroker`；`MockThsTransport`（CI 零公网）；`ExperimentalThsHttpTransport` fail-closed
  - Env：`STOCK_PLATFORM_THS_MODE` / `STOCK_PLATFORM_THS_*`；ADR 0037

## [2.7.0] - 2026-09-14

### Added

- **大里程碑 M35 完成**：执行端口抽象
  - `BrokerPort` / `PaperBroker` / `ExternalSimBroker`；Order/Fill/Position/Account 契约
  - `STOCK_PLATFORM_BROKER=paper|ths_sim`（默认 paper）；ADR 0036

## [2.6.0] - 2026-09-14

### Added

- **Phase C 投研稳定收口（M32–M34）**
  - M32：推荐绩效 JSONL + `direction_accuracy` 口径（ADR 0033）
  - M33：可选 LLM 辩论（默认确定性；`[llm]` fail-closed；ADR 0034）
  - M34：策略配置版本化 + `run_pit_long_only` 对比入口（ADR 0035）
  - 默认仍 replay；SIMULATE；无同花顺 / 实盘 / SPA

## [2.5.0] - 2026-09-14

### Added

- **大里程碑 M33 完成**：可选 LLM 辩论挂在 TopN 之后
  - 默认仍 M12 确定性 `engine=deterministic`
  - `engine=llm` + `[llm]` optional-extra；缺依赖/密钥 fail-closed
  - `POST /api/research/brief/debate`；`GET /api/debate/report?engine=`
  - ADR 0034；mocked LLM 单测

## [2.4.0] - 2026-09-14

### Added

- **大里程碑 M32 完成**：推荐决策绩效统计
  - JSONL 决策日志 + `compute_performance`（`direction_accuracy` / `avg_return` / `up_rate` 口径）
  - CLI `stock-platform-performance`；`GET /api/research/performance`；工作台 `#performance`
  - ADR 0033；确定性 fixtures

## [2.3.0] - 2026-09-14

### Added

- **Phase B 运维稳定收口（M29–M31）**
  - M29：`stock-platform-refresh` 日 K / 复权因子 / 资金流 / full_minute 落盘（ADR 0030）
  - M30：live 偏好模板 + 东财熔断（ADR 0031）
  - M31：`GET /api/ops/health` + fixture 录制文档（ADR 0032）
  - 默认仍 replay；SIMULATE；CI 零公网

## [2.2.0] - 2026-09-14

### Added

- **大里程碑 M30 完成**：live 偏好模板 + 东财节流/熔断
  - 预设 `replay` / `cn_astock_http` / `us_hk_global_http`（启动默认仍 replay）
  - `EM_CIRCUIT_FAILURES` / `EM_CIRCUIT_COOLDOWN`；`EastmoneyClient.snapshot()`
  - workbench `GET /api/settings/presets` + `POST .../apply`

## [2.1.0] - 2026-09-14

### Added

- **大里程碑 M29 完成**：CN 日数据刷新 / full_minute 落盘
  - `run_refresh` / `stock-platform-refresh`；重试 + manifest；`STOCK_PLATFORM_REFRESH_DIR`
  - ReplayTransport 文件名；CI `--provider replay`；ADR 0030

## [2.0.0] - 2026-09-14

### Added

- **Phase A 产品稳定（M24–M28）**：日更选股推荐 + 纸面交易闭环
  - M24 宇宙 + PIT 截面面板（ADR 0029）
  - M25 盘前简报（`build_premarket_brief` / CLI / `GET /api/research/brief`）
  - M26 工作台「今日推荐」UI
  - M27 TopN → PaperLedger 草稿（SIMULATE；默认 CN）
  - 默认仍 replay；无同花顺/实盘；无 LLM；无 SPA

## [1.20.0] - 2026-09-14

### Added

- **大里程碑 M27 完成**：Recommend → PaperLedger
  - `POST /api/research/brief/to-paper`；UI 一键纸面草稿；SIMULATE only；默认 market=CN
  - 复用 timing/window/freshness；`liveTradingEnabled=false`

## [1.19.0] - 2026-09-14

### Added

- **大里程碑 M26 完成**：工作台「今日推荐」
  - UI `#recommend` + TopN 分数/理由表；链接日 K / 纸面；默认 replay

## [1.18.0] - 2026-09-14

### Added

- **大里程碑 M25 完成**：盘前简报批处理
  - `build_premarket_brief` / `stock-platform-brief`；`GET /api/research/brief`
  - lvrev + entry gates → TopN + reasons；默认 replay；CI 零公网

## [1.17.0] - 2026-09-14

### Added

- **大里程碑 M24 完成**：CN 宇宙 + PIT 日截面面板（ADR 0029；`load_universe` / `build_cross_section_panel` / CSV）
  - 空宇宙 fail-closed；注入 providers；默认仍无公网抓取

## [1.16.1] - 2026-09-14

### Added

- M24.1：CN 宇宙 + PIT 日截面面板（ADR 0029）
  - `load_universe` / `build_cross_section_panel` / `panel_to_csv`；空宇宙 fail-closed
  - 注入 daily（可选 adj_factor / fund_flow）；CI 零公网

## [1.16.0] - 2026-09-14

### Added

- **大里程碑 M23 完成**：CN 复权套价（`apply_adjust`；qfq 除 / hfq 乘；消费 daily + adj_factor）
  - ADR 0028；workbench API/UI；默认仍 replay；不新增能力 id；空因子 fail-closed

## [1.15.2] - 2026-09-14

### Added

- M23.2：workbench `GET /api/market/daily-adjusted` + UI `#daily-adjusted`；默认偏好 replay

## [1.15.1] - 2026-09-14

### Added

- M23.1：CN 复权套价 `apply_adjust`（ADR 0028）
  - qfq 除 / hfq 乘；空因子 fail-closed；不新增能力 id；CI 零公网

## [1.15.0] - 2026-09-14

### Added

- **大里程碑 M22 完成**：CN 全量分钟（能力矩阵 `full_minute`；replay + `em_get` 当日 1m 批量）
  - ADR 0027；workbench API/UI；默认仍 replay；与多频 `minute` 区分；无后台落盘 / get_intraday_latest

## [1.14.2] - 2026-09-14

### Added

- M22.2：workbench `GET /api/market/full-minute` + UI `#full-minute`；默认偏好 replay

## [1.14.1] - 2026-09-14

### Added

- M22.1：CN 全量分钟 `full_minute`（激活矩阵第七项；ADR 0027）
  - `ReplayProvider` / `AStockHttpProvider.get_full_minute`；东财 push2his `klt=1`（em_get）；fixtures；与多频 `minute` 区分；CI 零公网

## [1.14.0] - 2026-09-14

### Added

- **大里程碑 M21 完成**：CN 个股复权因子（能力矩阵 `adj_factor`；replay + 新浪 qfq/hfq HTTP）
  - ADR 0026；workbench API/UI；默认仍 replay；mootdx / 东财复权备胎 / apply_adjust 套价不做

## [1.13.2] - 2026-09-14

### Added

- M21.2：workbench `GET /api/market/adj-factor` + UI `#adj-factor`；默认偏好 replay

## [1.13.1] - 2026-09-14

### Added

- M21.1：CN 复权因子 `adj_factor`（激活矩阵第二项；ADR 0026）
  - `ReplayProvider` / `AStockHttpProvider.get_adj_factor`；新浪 qfq/hfq（非 em_get）；fixtures；CI 零公网

## [1.13.0] - 2026-09-14

### Added

- **大里程碑 M20 完成**：CN 个股财务报表（能力矩阵 `financial`；replay + 新浪三表 HTTP）
  - ADR 0025；workbench API/UI；默认仍 replay；mootdx / 东财财报备胎不做

## [1.12.2] - 2026-09-14

### Added

- M20.2：workbench `GET /api/market/financial` + UI `#financial`；默认偏好 replay

## [1.12.1] - 2026-09-14

### Added

- M20.1：CN 财务报表 `financial`（激活矩阵第六项；ADR 0025）
  - `ReplayProvider` / `AStockHttpProvider.get_financial`；新浪三表（非 em_get）；fixtures；CI 零公网

## [1.12.0] - 2026-09-14

### Added

- **大里程碑 M19 完成**：CN 个股五档盘口（能力矩阵 `depth5`；replay + `em_get` push2 stock/get）
  - ADR 0024；workbench API/UI；默认仍 replay；mootdx / 交易所官方备胎不做

## [1.11.2] - 2026-09-14

### Added

- M19.2：workbench `GET /api/market/depth5` + UI `#depth5`；默认偏好 replay

## [1.11.1] - 2026-09-14

### Added

- M19.1：CN 五档盘口 `depth5`（激活矩阵第五项；ADR 0024）
  - `ReplayProvider` / `AStockHttpProvider.get_depth5`；fixtures；量=手；CI 零公网

## [1.11.0] - 2026-09-14

### Added

- **大里程碑 M18 完成**：CN 个股分钟 K（能力矩阵 `minute`；replay + `em_get` push2his kline）
  - ADR 0023；workbench API/UI；默认仍 replay；`full_minute` / 腾讯备胎不做

## [1.10.2] - 2026-09-14

### Added

- M18.2：workbench `GET /api/market/minute` + UI `#minute`；默认偏好 replay

## [1.10.1] - 2026-09-14

### Added

- M18.1：CN 分钟 K `minute`（激活矩阵第四项；ADR 0023）
  - `ReplayProvider` / `AStockHttpProvider.get_minute`；fixtures；北京墙钟 naive；CI 零公网

## [1.10.0] - 2026-09-14

### Added

- **大里程碑 M17 完成**：CN 个股限售解禁（能力矩阵 `unlock`；replay + `em_get` datacenter）
  - ADR 0022；workbench API/UI；默认仍 replay；全市场解禁日历不做

## [1.9.2] - 2026-09-14

### Added

- M17.2：workbench `GET /api/market/unlock` + UI `#unlock`；默认偏好 replay

## [1.9.1] - 2026-09-14

### Added

- M17.1：CN 限售解禁 `unlock`（能力矩阵第十项；ADR 0022）
  - `ReplayProvider` / `AStockHttpProvider.get_unlock`；fixtures；空窗口不崩；CI 零公网

## [1.9.0] - 2026-09-14

### Added

- **大里程碑 M16 完成**：CN 个股龙虎榜（能力矩阵 `lhb`；replay + `em_get` datacenter）
  - ADR 0021；workbench API/UI；默认仍 replay；全市场日榜 / 交易所备胎不做

## [1.8.2] - 2026-09-14

### Added

- M16.2：workbench `GET /api/market/lhb` + UI `#lhb`；默认偏好 replay

## [1.8.1] - 2026-09-14

### Added

- M16.1：CN 龙虎榜 `lhb`（能力矩阵第九项；ADR 0021）
  - `ReplayProvider` / `AStockHttpProvider.get_lhb`；fixtures；空窗口不崩；CI 零公网

## [1.8.0] - 2026-09-14

### Added

- **大里程碑 M15 完成**：CN 日级资金流（能力矩阵 `fund_flow`；replay + `em_get`）
  - ADR 0020；workbench API/UI；默认仍 replay；分钟/板块资金流与龙虎榜不做

## [1.7.2] - 2026-09-14

### Added

- M15.2：workbench `GET /api/market/fund-flow` + UI `#fund-flow`；默认偏好 replay

## [1.7.1] - 2026-09-14

### Added

- M15.1：CN 日级资金流 `fund_flow`（能力矩阵第八项；ADR 0020）
  - `ReplayProvider` / `AStockHttpProvider.get_fund_flow`；fixtures；CI 零公网

## [1.7.0] - 2026-09-14

### Added

- **大里程碑 M14 完成**：多市场纸面 timing（CN/US/HK 日历 + 本地时区）
  - ADR 0019；`PaperLedger` / workbench 可选 `market`（默认 CN）；半日市 / 实盘不做

## [1.6.2] - 2026-09-14

### Added

- M14.2：PaperLedger / workbench /api/paper/* 可选 market（默认 CN）；草稿 marketId

## [1.6.1] - 2026-09-14

### Added

- M14.1：纸面 timing 支持 `market=`（CN/US/HK）；`market_now` / `daily_bar_final_at`（ADR 0019）
  - 默认仍 CN；`china_now` / `CHINA_TZ` 保留为别名

## [1.6.0] - 2026-09-14

### Added

- **大里程碑 M13 完成**：US/HK 静态交易日历（对标 CN；MarketStrategy 自动生效）
  - ADR 0018；纸面默认仍 CN timing；不拉交易所 API

## [1.5.2] - 2026-09-14

### Added

- M13.2：`MarketStrategy` US/HK 假日验收；`market-strategy` / providers README / upstream-archive 同步

## [1.5.1] - 2026-09-14

### Added

- M13.1：US/HK 静态休市日表 + `get_trading_calendar` 通用加载（ADR 0018）

## [1.5.0] - 2026-09-14

### Added

- **大里程碑 M12 完成**：确定性 Bull/Bear/Risk 轻量辩论（无 LLM）
  - `/api/debate/report` + UI；ADR 0017

## [1.4.2] - 2026-09-14

### Added

- M12.2：`GET /api/debate/report` + UI `#debate` 区

## [1.4.1] - 2026-09-14

### Added

- M12.1：确定性 `build_debate_report` / Bull·Bear·Risk（ADR 0017；无 LLM）

## [1.4.0] - 2026-09-14

### Added

- **大里程碑 M11 完成**：Workbench 最小 UI（`GET /` 单页操作台）
  - 能力矩阵 / 日 K / 纸面 status；ADR 0016

## [1.3.2] - 2026-09-14

### Added

- M11.2：UI 三区交互（矩阵 / 日 K / 纸面）；409 fail-closed 可见；可切 daily 偏好

## [1.3.1] - 2026-09-14

### Added

- M11.1：workbench `GET /` Jinja2 壳 + `/static`（ADR 0016）

## [1.3.0] - 2026-09-14

### Added

- **大里程碑 M10 完成**：CN 静态交易日历（休市日表 + timing / MarketStrategy 共用）
  - ADR 0015；US/HK 假日表见后续 M13 / ADR 0018

## [1.2.2] - 2026-09-14

### Added

- M10.2：`MarketStrategy.is_trading_day` 与纸面 `timing` 共用 CN 日历
- `completed_bar_cutoff` 回退跳过非交易日；execution 依赖 providers
- 修复：包内 `data/cn_closed_days.txt` 不再被根 `.gitignore` 的 `data/` 规则忽略

## [1.2.1] - 2026-09-14

### Added

- M10.1：`TradingCalendar` / `get_trading_calendar` + 静态 `cn_closed_days.txt`（ADR 0015）

## [1.2.0] - 2026-09-14

### Added

- **大里程碑 M9 完成**：可选美港 live HTTP（`GlobalHttpProvider` / Yahoo + 新浪）
  - workbench preferences 可切 `global_http`；默认仍 replay
  - ADR 0014；`a-stock-engine` 归档横幅

## [1.1.2] - 2026-09-14

### Added

- M9.2：workbench 注册 `GlobalHttpRouter`，preferences 可切 `global_http`（默认仍 replay）

## [1.1.1] - 2026-09-14

### Added

- M9.1：`GlobalHttpProvider` / `GlobalHttpRouter`（Yahoo 日 K + 新浪实时）
- ADR 0014；能力矩阵 `global_http` usable
- `a-stock-engine` README 归档横幅（指向 stock-platform）

## [1.1.0] - 2026-09-14

### Added

- **大里程碑 M8 完成**：可选 A 股 live HTTP（`AStockHttpProvider` via `em_get`）
  - 默认仍 replay；preferences 可切 live
  - ADR 0013

### Notes

- `global_http` 仍 pending；封禁时降级 replay，禁止裸东财 URL

## [1.0.2] - 2026-09-14

### Added

- M8.2 验收：workbench 注册 `astock_http` 实例，可通过 preferences 切换（默认 replay）

## [1.0.1] - 2026-09-14

### Added

- `AStockHttpProvider`：东财日 K / 实时经 `em_get`（ADR 0013）
- 能力矩阵 `astock_http` usable；单测注入 JSON，CI 不打公网

## [1.0.0] - 2026-09-14

### Added

- **大里程碑 M7 完成 / 产品 v1.0.0**
  - 上游归档说明与 v1 产品边界（ADR 0012）
  - 产品化文档与发版检查清单
  - 版本一致性脚本接入 CI

### Notes

- v1.0 = 可发布研究与纸面决策平台骨架（默认 replay；live HTTP / 实盘仍延期）
- 自本版本起破坏契约须 MAJOR

## [0.7.3] - 2026-09-14

### Added

- M7.3 验收：`release-checklist.md`、`check_versions.ps1`、CI version job

## [0.7.2] - 2026-09-14

### Changed

- README / CONTRIBUTING / AGENTS 按 v1.0 交付面改写
- 修复 upstream-archive 示例链接（避免 docs 自检断链）

## [0.7.1] - 2026-09-14

### Added

- `docs/upstream-archive.md`：上游参考仓归档总表与红线
- ADR 0012：v1.0 产品边界
- （同树预置）产品化 README / 发版清单 / `check_versions.ps1`，验收见 0.7.2 / 0.7.3

## [0.7.0] - 2026-09-14

### Added

- **大里程碑 M6 完成**：纸面执行安全模型
  - `packages/execution` broker-free 内核（吸 V2 结论，无券商 SDK）
  - SIMULATE-only / live=false；草稿≠激活；窗口外禁补单；draftId 幂等
  - workbench `/api/paper/*`

### Notes

- Admission 通过 ≠ 策略已证明；下一步 M7 产品收敛 / 上游归档

## [0.6.3] - 2026-09-14

### Added

- M6.3 验收：workbench 纸面路由与显式激活（无 live 开关）

## [0.6.2] - 2026-09-14

### Added

- M6.2 验收：`PaperLedger` decision_only / 窗口外零订单 / draftId 幂等回放

## [0.6.1] - 2026-09-14

### Added

- `packages/execution`：纸面执行安全内核（timing / transactional / profile / lifecycle / admission）
- ADR 0011；paper-only 闸门（SIMULATE + live=false）
- （同树）`PaperLedger` 与 workbench `/api/paper/*`，验收见 0.6.2 / 0.6.3

## [0.6.0] - 2026-09-13

### Added

- **大里程碑 M5 完成**：美港 Vendor + 市场策略表
  - `MarketStrategy` 分市场 settle / limit / 时区
  - `normalize_symbol(market=US|HK)` 与 CN 隔离
  - `GlobalReplayProvider` + 能力矩阵注册

### Notes

- 节假日日历仍为工作日 stub；live `global_http` 未接线
- 下一步 M6：纸面执行安全模型（吸 V2）

## [0.5.3] - 2026-09-13

### Added

- M5.3 验收：`GlobalReplayProvider`（AAPL / 00700 fixtures）
- 能力矩阵：`global_replay` usable、`global_http` pending

## [0.5.2] - 2026-09-13

### Added

- M5.2 验收：`normalize_symbol(market="US"|"HK")`；CN 路径继续拒港美

## [0.5.1] - 2026-09-13

### Added

- `MarketStrategy` / `get_market_strategy`：CN/US/HK 时区、会话、settle、limit
- US/HK 明确 `buy_to_sell_delay_days=0`、`has_limits=False`（不套用 A 股）
- ADR 0010；契约 `market-strategy.md` 美港表定稿
- （同树预置）US/HK `normalize_symbol` 与 `GlobalReplayProvider`，验收见 0.5.2 / 0.5.3

## [0.5.0] - 2026-09-13

### Added

- **大里程碑 M4 完成**：投研 Agent 插件化（无内嵌抓取）
  - `packages/agents` 仅经 `MarketDataProvider`
  - workbench 研报 / 复盘槽位 + 历史 asof 护栏
  - ADR 0009

### Notes

- TradingAgents-astock 完整 LangGraph 辩论仍可后续接入；不得把东财 URL 写回 agents
- 下一步 M5：美港 Vendor + 市场策略表

## [0.4.2] - 2026-09-13

### Added

- M4.2 验收：workbench 个股研报 / 复盘槽位经能力矩阵 `resolve("daily")`
- 路由测试覆盖 historical asof 告警与港股拒绝

## [0.4.1] - 2026-09-13

### Added

- `packages/agents`：`ResearchAgentPlugin` / `ReviewAgentPlugin`（仅经 providers）
- 历史 `asof` 跳过 realtime 护栏；ADR 0009；CI `agents` job
- workbench 预挂 `/api/research/report`、`/api/review/report`（M4.2 验收于 `0.4.2`）

### Notes

- TradingAgents 完整辩论图仍作参考；平台槽位以本插件为准

## [0.4.0] - 2026-09-13

### Added

- **大里程碑 M3 完成**：`packages/research` 选股/回测内核
  - lvrev 评分与入场闸门（迁自 a-stock-engine）
  - PIT long-only（T 信号 / T+1 open）+ 防未来函数
  - 盘前截面批处理 CLI `stock-platform-score`

### Notes

- a-stock-engine 视为参考实现；平台权威评分路径为本包
- 下一步 M4：TradingAgents 研报插件化（去内嵌抓取）

## [0.3.3] - 2026-09-13

### Added

- `score_cross_section_csv` + 控制台入口 `stock-platform-score`（盘前批处理）

## [0.3.2] - 2026-09-13

### Added

- `run_pit_long_only` + `assert_no_lookahead_columns`（信号日/成交日分离）

## [0.3.1] - 2026-09-13

### Added

- `packages/research`：`score_lvrev` / `apply_entry_gates` / `apply_risk_gates`（迁自 a-stock-engine）
- ADR 0008；CI `research` job

## [0.3.0] - 2026-09-13

### Added

- **大里程碑 M2 完成**：工作台最小壳经能力矩阵消费 Provider
  - FastAPI health / matrix / daily / realtime
  - 缺能力 409 fail-closed；禁品牌硬编码
  - API 与 replay 同标的同日口径对齐

### Notes

- 下一步 M3：迁入选股 / PIT 回测内核（lvrev）

## [0.2.3] - 2026-09-13

### Added

- M2.3 验收：同标的同日 API daily 与 `ReplayProvider` 批处理字段对齐测试

## [0.2.2] - 2026-09-13

### Added

- `PUT /api/settings/preferences`；minute/缺能力 **409** fail-closed 护栏
- 路由源码禁止品牌字面量扫描；ADR 0007

## [0.2.1] - 2026-09-13

### Added

- `apps/workbench`：FastAPI 最小壳（health / capability-matrix / daily / realtime）
- minute 缺能力时 409 fail-closed；ADR 0006；CI `workbench` job

## [0.2.0] - 2026-09-13

### Added

- **大里程碑 M1 完成**：可安装 `stock-platform-providers`
  - ticker 归一化与港美拒绝
  - daily/realtime 录制回放契约测试
  - 东财 `em_get` 限流单点 + 能力矩阵注册
  - 文档禁止裸东财 URL

### Notes

- Live HTTP 行情适配仍为 pending（`astock_http`）；下一阶段 M2 接入工作台壳

## [0.1.3] - 2026-09-13

### Added

- `em_get` / `EastmoneyClient`：东财串行限流单点（禁非 EM URL）
- `build_capability_matrix` / `register_builtin_providers`
- `docs/contracts/eastmoney-http.md`、ADR 0005

## [0.1.2] - 2026-09-13

### Added

- `ReplayTransport` / `ReplayProvider`：daily + realtime 录制回放
- `normalize_daily_row` / `normalize_realtime_row` 契约归一化
- ADR 0004；fixtures 与 pytest 覆盖

## [0.1.1] - 2026-09-13

### Added

- `packages/providers`：可安装包 `stock-platform-providers`
- `normalize_symbol` / `exchange_prefix` / `is_bse_symbol` + pytest
- ADR 0003；CI `providers` job（含与根 `VERSION` 对齐校验）

## [0.1.0] - 2026-09-13

### Added

- **大里程碑 M0 完成**：工程架子、契约 Accepted、CI/文档自检、SemVer tag 流程可协作

### Notes

- 仍无可运行行情/选股业务；下一阶段 M1（`v0.2.0`）开始 `packages/providers` 可安装实现

## [0.0.3] - 2026-09-13

### Added

- `scripts/check_docs.ps1`：必选文件、VERSION↔CHANGELOG、Markdown 相对链接检查
- CI：docs 自检 + `release_tag.ps1 -DryRun`

### Changed

- `release_tag.ps1`：`-DryRun` 不再因 tag 已存在或脏工作区失败
- README / versioning：补充 DryRun 与自检示例

## [0.0.2] - 2026-09-13

### Added

- ADR 0002：M0.2 数据集与市场口径冻结
- 契约定稿：`datasets` / `capability-matrix` / `market-strategy`（对齐 TSP）

### Changed

- 关闭 M0.2 关键 TBD（amount 元、ex_factor、asset_type、asof_ts、usable 形状、CN 规则表）

## [0.0.1] - 2026-09-13

### Added

- 仓库骨架：`apps/`、`packages/`、`docs/`、`scripts/`
- 目标架构 ADR、契约草稿、里程碑 ROADMAP、tag 升级规则
- `VERSION` 单一版本源与 `scripts/release_tag.ps1`
- Git 初始化（`main`）与首个工程 tag `v0.0.1`

[Unreleased]: https://github.com/local/stock-platform/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/local/stock-platform/compare/v1.0.2...v1.1.0
[1.0.2]: https://github.com/local/stock-platform/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/local/stock-platform/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/local/stock-platform/compare/v0.7.3...v1.0.0
[0.7.3]: https://github.com/local/stock-platform/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/local/stock-platform/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/local/stock-platform/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/local/stock-platform/compare/v0.6.3...v0.7.0
[0.6.3]: https://github.com/local/stock-platform/compare/v0.6.2...v0.6.3
[0.6.2]: https://github.com/local/stock-platform/compare/v0.6.1...v0.6.2
[0.6.1]: https://github.com/local/stock-platform/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/local/stock-platform/compare/v0.5.3...v0.6.0
[0.5.3]: https://github.com/local/stock-platform/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/local/stock-platform/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/local/stock-platform/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/local/stock-platform/compare/v0.4.2...v0.5.0
[0.4.2]: https://github.com/local/stock-platform/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/local/stock-platform/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/local/stock-platform/compare/v0.3.3...v0.4.0
[0.3.3]: https://github.com/local/stock-platform/compare/v0.3.2...v0.3.3
[0.3.2]: https://github.com/local/stock-platform/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/local/stock-platform/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/local/stock-platform/compare/v0.2.3...v0.3.0
[0.2.3]: https://github.com/local/stock-platform/compare/v0.2.2...v0.2.3
[0.2.2]: https://github.com/local/stock-platform/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/local/stock-platform/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/local/stock-platform/compare/v0.1.3...v0.2.0
[0.1.3]: https://github.com/local/stock-platform/compare/v0.1.2...v0.1.3
[0.1.2]: https://github.com/local/stock-platform/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/local/stock-platform/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/local/stock-platform/compare/v0.0.3...v0.1.0
[0.0.3]: https://github.com/local/stock-platform/compare/v0.0.2...v0.0.3
[0.0.2]: https://github.com/local/stock-platform/compare/v0.0.1...v0.0.2
[0.0.1]: https://github.com/local/stock-platform/releases/tag/v0.0.1
