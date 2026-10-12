# 0070 — 日常循环自足：供数守卫 + 中文名直出 + 持仓自动探测

- Status: Accepted
- Date: 2026-10-12
- Supersedes: —
- Related: ADR 0049（SQLite brief 权威）、ADR 0058（market.db 是唯一历史真相源）、
  ADR 0044（日历/调度）、ADR 0066（refresh 吞吐与 .env 加载）、ADR 0069（测试数据隔离）

## 背景

v4.3.0/v4.3.1 让 PnL 闭环在真实循环里跑起来了，但把「无人值守的日常循环」真正
焊死之前，有三个各自独立、又同属「循环不自足」的缺口：

### P1 — 供数链路没有守卫（危害最大）

`stock-platform-daily`（08:30）以 `-PrevSession` 把 asof 解析为**日历上的前一交易日**，
面板再从 `market.db` 构建。但本机**没有任何行情回补计划任务**——供数靠人工或外部触发。
一旦生产侧没把该日 bar 写进库，后果不是「报错」，而是**静默写出一份空 brief**：

- 空 brief 的 `asof` 是**最新的**；
- 日报渲染走 `repo.list_recent(limit=1)`（最新优先）→ 空 brief **遮蔽**上一份真 brief；
- 结果：早上打开日报，看到「当日无推荐」，而真相是「数据没到」。

实测证据（2026-10-12）：`market.db` 尾部止于 2026-10-09 时，asof 解析到 2026-10-12 →
面板为空 → 写出 `asof=2026-10-12, picks=[]` 的 brief，把 `asof=2026-10-09` 的真 brief 挡住。
该污染行已清除，日报用真 brief 重渲染。

### P2 — 输出只有代码，没有中文名

`picks` / 榜单 item / 命中追踪的名称列全部缺位（命中追踪的「名称」列直接回落成代码）。
人读成本高，且日报表格里的「名称」列恒为 `-`。数据其实就在引擎库里：
`fundamentals(code, name, industry)` 有 5228 行，`code` 是**裸 6 位**，而
`daily_price.code` **带交易所后缀**。

### P3 — 持仓从没进入日报视野

`stock-platform-daily` 有 `--holdings`（JSON，含 `code`/`entry_price`），
但 `Invoke-DailyPipeline.ps1` 没有对应参数、计划任务也没传 →
③A 持仓 / ③B 操作建议**恒为空**。简报在推荐新票，却对既有仓位一言不发。

## 决定

### 1. 覆盖率守卫放在 ops 包装脚本里，复用 C2 单点

守卫是**运维语义**（「今天该看哪天」），不是策略语义，所以放
`scripts/ops/Invoke-DailyPipeline.ps1`，不进 CLI（CLI 还要服务 replay/fixtures/测试）。

判定**复用** `EngineSqliteProvider.coverage_snapshot()`（ADR 0058）——它本来就是
「warehouse 覆盖率」的唯一定义，且**永不抛异常**（`ok|thin|stale|empty|missing_table`）。
守卫只看一件事：**解析出的 asof 本身是否可用**（≤ `latestTradeDate`，且不在
`missingDays` / `thinDays` 里）。窗口整体的 `status=stale`（例如 20 天前有个洞）
不阻断——我们只关心当日截面。

- asof 可用 → 照常跑；
- asof 不可用 → **回落到 `latestTradeDate`** 并 WARN（用一份更旧但真实的截面）；
- 回落目标本身也不可用（或库里没有任何可用交易日）→ **退出 1**，拒绝写 brief；
- `-StrictCoverage` → 不回退，直接失败（验收 / 取证用）。

**为什么不静默回退、也不静默写空**：空 brief 是「看起来成功的错误」，比失败更毒。
宁可用旧截面并在日志里写明，也不要让人读到一份「今天没票」的假结论。

### 2. 供数守卫的成因端：新增回补计划任务

守卫只防「伤害」，不治「成因」。新增：

- `scripts/ops/Invoke-MarketDbBackfill.ps1` —— 包一层**引擎自己的**
  `empirical/backfill_market_daily.py`（幂等：只补行数 < 3000 的交易日，
  `INSERT OR REPLACE`，严格顺序 + 调用间隔，CPU-safe）。
- `scripts/ops/stock-platform-marketdb-backfill.xml` —— 每日 **18:30** 触发
  （收盘后、次日 08:30 之前），`ExecutionTimeLimit=PT20M`。
- `Register-ScheduledTasks.ps1` 增加第三个任务槽 `-Backfill`。

**边界不变**：平台**仍然只读** `market.db`（ADR 0058）。写库的是**引擎的脚本**，
计划任务只是把它按日唤醒——不是平台去抓数。

### 3. 中文名走「装饰性、可缺省」契约

名称**绝不承载语义**。因此：

- 取数：`backtest_cli.load_engine_names(db)` —— 复用 `load_engine_industry` 的读法，
  但**fail-open**（表/列缺失 → `{}`）。区别于 `load_engine_industry` 的
  fail-closed（行业缺口会静默关掉中性化，必须抛），名称缺失只影响可读性。
- 传递：`daily_cli._build_name_map()` 把 key 归一到 6 位核（`rankings.code_key`），
  `replay` 直接跳过（fixtures 与引擎库无关）；再经
  `run_daily_pipeline(name_map=…) → build_premarket_brief(name_map=…) → build_rankings(name_map=…)`。
- **写入规则**：只有**确实取到**名称时才写 `item["name"]`，取不到**不写这个键**。
  于是「没有 name_map」与「有 map 但没命中」两条路径下，brief / picks ledger /
  命中周期 / 绩效 JSONL 全部**逐字节不变**（与 ADR 0065 的「误判不进绩效」同一种
  保守姿态）。
- 出口：日报 picks 表新增「名称」列；②A/②B/③C item 带 `name`；
  命中追踪本就有 `name` 列（`track_brief_hits` 读 `it.get("name")`）→ 自动补齐。

### 4. 持仓：脚本自动探测，调度零改动

`Invoke-DailyPipeline.ps1` 新增 `-Holdings`，**默认探测** `data\holdings.json`：

- 文件存在 → 追加 `--holdings <path>`；
- 不存在 → 不传，③A/③B 保持空（fail-closed，**绝不猜**）；
- `-NoHoldings` 显式跳过。

`data/` 整个目录在 `.gitignore` 里（`/data/`），所以真实持仓文件天然不进版本库；
计划任务的 XML **不需要改**，加一个文件即可启用。

### 5. 补 ADR 0069：隔离守卫改成**自愈**的

ADR 0069 的 `conftest.py` 只在 **import 时**设一次重定向。这条假设在本次被证伪：
新增的一个测试用 `os.environ.pop("STOCK_PLATFORM_DB_URL")` 收尾（而不是
`monkeypatch`），于是**之后所有测试**都回落到了仓库真实 `data/`——一轮全量跑下来，
`hit_tracking` / `hit_summary` 里 `pick_date=2026-09-02` 的 fixture 残留**又回来了**
（2 + 2 行），同时 `test_session_never_resolves_the_repo_data_dir` 如期变红。

修复两层：

1. 该测试改用 `monkeypatch`（自动还原，不破坏会话级守卫）；
2. `conftest.py` 增加 **autouse 函数级 fixture**，在**每个测试前重新断言**两个
   `GUARDED_ENV`。守卫从「设一次、信一次」变成**幂等 + 自愈**——任何测试显式改/删环境
   变量都无法再污染后续测试。

教训：**进程级的环境变量守卫必须每次重新断言**，否则它只是「第一个守规矩的测试」
到「第一个不守规矩的测试」之间的一段错觉。残留行已按 ADR 0069 的同款流程
（先备份 → 断言只删该 pick_date → 独立只读连接复核）清除。

## 后果

**正面**

- 供数滞后从「静默空简报」降级为「用旧截面 + 明确 WARN」或「响亮失败」。
- 名称是纯增量，任何数字口径都不动；`fundamentals.name` 成为唯一名称来源。
- 持仓接入从「改 XML + 改脚本」变成「放一个文件」。

**代价 / 已知边界**

- 守卫会让盘前 asof **不再是严格的 T-1**（供数滞后时更旧）。报表里的 asof 就是真
  asof，不撒谎；但要接受「今天的简报可能是两天前的截面」。这是刻意的取舍：宁可
  旧数据也不要空数据。
- **ETF 不会被 ③A 列出**：brief 的宇宙是 `asset_type=stock`，ETF 不在截面里；
  且 `market.db` 的 ETF 日线只到 2026-09-08（65 行）。持仓里若含 ETF，只能靠
  `review_positions` 对全 book 的复核（无现价 → `pending`）。属既有限制，未解。
- 回补任务默认 `EngineRoot` 写死为 `D:\workspace\stock_trading\a-stock-engine`；
  换机需改 XML/参数。

## 验证

- 守卫：`-Asof 2026-10-12`（已回补，5224 行）→ `COVERAGE asof=2026-10-12 ok`；
  asof 超出库尾部时回落到 `latestTradeDate`；无可用日时退出 1。
- 名称：新增 `test_display_names.py`（6 例）锁死「有 map 就带名、无 map 不带键、
  部分 map 只补命中项、日报渲染名称列、`load_engine_names` fail-open」。
- 全量：`STOCK_PLATFORM_PROVIDER_PRESET=replay pytest packages apps -q` 全绿。
- `check_docs.ps1` / `check_versions.ps1` 双绿。
