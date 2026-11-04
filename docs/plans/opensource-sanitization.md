# 开源化前的私密收束计划

> 日期：2026-11-04（拍板回写同日）  
> 现状版本：`v4.13.7`（`VERSION` / tag / `CHANGELOG` 对齐）  
> **状态：本地收束已落地；远端历史消毒进行中/已完成（见文末验收勾选）。公开开源发布仍延后**（无许可证、不发 GitHub Releases 叙事）。

相关入口：[`../STATUS.md`](../STATUS.md)、[`../README.md`](../README.md)、[`../contracts/dotenv-loading.md`](../contracts/dotenv-loading.md)、[`../architecture/0066-refresh-throughput-and-env-loading.md`](../architecture/0066-refresh-throughput-and-env-loading.md)、[`../architecture/0069-test-data-isolation.md`](../architecture/0069-test-data-isolation.md)、[`../architecture/0064-live-trading-charter.md`](../architecture/0064-live-trading-charter.md)、[`../contracts/compliance-boundary.md`](../contracts/compliance-boundary.md)、[`../versioning.md`](../versioning.md)。

## 已拍板决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | 私密目录名 | 就用 `local/` |
| 2 | 保留 tag | 11 个：`v1.0.0`、`v2.0.0`、`v3.0.0`、`v3.9.0`、`v3.12.6`、`v4.0.0`、`v4.1.6`、`v4.3.1`、`v4.9.1`、`v4.13.0`、`v4.13.7` |
| 3 | 历史作者 | 改写全部历史 author / committer 为 `63516` / `635161624@qq.com` |
| 4 | 旧提交正文 | 本机路径、持仓描述一并 `--replace-text` 脱敏（替换表放 `local/replacements.txt`，不入库） |
| 5 | 推送目标与分支 | 推到现有 `deTian0/stock-platform`（需 force push）；**仅保留一个分支**（实测为 `main`），其它本地/远端分支删除（见「分支策略」） |
| 6 | 远端 tag | 删除远端多余 tag（保留上表 11 个；改写后在新 SHA 上重打） |
| 7 | 文档里的券商 / 资金 / 具体持仓 | **不需要改动**正文。该建议已落 **DB + `stock-platform-init`**（见「产品 / 配置初始化」） |
| 8 | stash / 未跟踪草稿 | 必须实测列出（见「改写前工作区盘点」） |
| 9 | 公开许可证 / 开源发布 | **不着急**。产品还要迭代很多，等成熟了才开源。因此：仍可做私有目录 / 配置收口 / 历史作者改写 / 删多余 tag 与分支并 force push 到现有仓；**不等于宣布开源**（无许可证、不发 GitHub Releases 叙事） |

## 执行闸门

用户**已拍板**上表各项，但**尚未**说「现在执行改写」。下列动作一律停在草稿，标「确认后才跑」：

- `git filter-repo`（作者回调 + `--replace-text`）
- 删除本地 / 远端多余 tag
- 删除本地 / 远端多余分支
- `git push --force` 到 `origin`

**开始 filter-repo / 删 tag / force push 前，还需用户对草稿处置方案说一句确认**（例如：「先把文档改动提交成基线，再改写」；或「丢弃某批草稿后再改写」）。未听到这句确认前，不跑任何破坏性命令。

风险提醒（必须写清）：对现有 `deTian0/stock-platform` 做 force push + 删多余 tag/分支，是**远端历史消毒**，**不是**宣布开源；仓仍可保持私有或未挂许可证。公开开源发布（许可证、`LICENSE`、Releases 叙事）另开一轮，产品成熟后再做。

## 目标与非目标

### 目标

把仓库收成适合继续私有演进、且历史已消毒的形状（开源发布另议）：

1. 秘密、本机路径、真实运行时持仓与资金快照不出现在已跟踪文件和**改写后**的公开历史里（`--replace-text`）。
2. 运行时配置收成一处：`local/.env` + 一个 pydantic Settings。缺密钥时继续 fail-closed。
3. 数据库、行情缓存、digest、持仓、日志、健康度台账、SQLite、`.env` 进**一个**不追踪目录 `local/`。
4. tag 只留已拍板的 11 个 annotated tag；远端多余 tag 删除。
5. 全部历史的 author / committer 显示名改为 `63516`，邮箱定为 `635161624@qq.com`。
6. 正式正文继续只在 `docs/`（保持现有子目录）。仓库根和各包 README 留成短入口。
7. 仅保留 `main` 一条分支（本地 + 远端）。

### 非目标

- 不做 T3 数据质量体检，不改选股 / 回测 / 调度行为。
- 不解禁实盘。`liveTradingEnabled` 继续在代码里恒为 `false`，**不**做成 `.env` 开关。执行层默认仍是 SIMULATE / `STOCK_PLATFORM_BROKER=paper`。
- 不把 `min_pick_score`、榜单条数、东财节流间隔等业务阈值当成秘密。
- 不把仓外约 3.2 GB 的引擎 `market.db` 拷进本仓。
- **不**为开源而改写 ADR 0064 / `compliance-boundary` / CHANGELOG / STATUS 里已写明的券商、资金、具体持仓正文（已拍板：文档不改；配置进 DB / 初始化 CLI，见下）。
- **本轮不执行**任何删除 tag、删分支、`git filter-repo`、force push、远程 tag 删除、commit、push。下面的命令都是草稿，标题写明「确认后才跑」。过执行闸门前停手。
- **不**在本计划阶段选定许可证、不加 `LICENSE`、不发 GitHub Releases 开源叙事。

当前工作区还有一轮**未提交**的文档整理（见「改写前工作区盘点」）。实施历史改写前须按闸门确认如何处置这批草稿。

## 改写前工作区盘点

实测时间：2026-11-04（拍板回写轮）。命令：`git status -sb`、`git stash list`、对各 `stash@{n}` 的 `git stash show --stat` / `diff-tree` / `ls-tree`（含 `^3` untracked 父提交）、`git status --porcelain`、`git branch -a`、`git remote -v`、`git tag --list`（174）。

### stash（3 条，内容均为空）

| 条目 | 说明 | 类型 | 建议 |
|------|------|------|------|
| `stash@{0}` `wip-unrelated-before-m19`（2026-09-14，基线 `8801c9a` / M18） | index / worktree diff 为空；`^3` untracked 父提交存在，但 tree 为 git 空树 `4b825dc…`（**无文件**） | stash（空） | **丢弃**（`git stash drop`；改写前清掉即可，无可恢复草稿） |
| `stash@{1}` `wip-unrelated-before-m18` | index / worktree diff 为空；**无** `^3` untracked 父提交 | stash（空） | **丢弃** |
| `stash@{2}` `wip-before-m17-unrelated`（基线 `818f944` / M16） | index / worktree diff 为空；`^3` 亦为空树 | stash（空） | **丢弃** |

结论：用户问「改写前 stash 里的未跟踪草稿都有哪些？」——**三条 stash 都没有实质文件**（既无已跟踪改动，也无未跟踪文件内容）。可安全 drop；不要 push stash。

### 当前工作区未提交草稿（文档整理 + 本计划）

| 路径 | 类型 | 建议 |
|------|------|------|
| `AGENTS.md` | modified | **提交进消毒前基线**（文档指针整理） |
| `CHANGELOG.md` | modified | **提交进消毒前基线** |
| `CONTRIBUTING.md` | modified | **提交进消毒前基线** |
| `README.md` | modified | **提交进消毒前基线** |
| `apps/workbench/README.md` | modified | **提交进消毒前基线** |
| `docs/README.md` | modified | **提交进消毒前基线** |
| `docs/ROADMAP.md` | modified | **提交进消毒前基线** |
| `docs/architecture/0068-performance-pnl-closed-loop.md` | modified | **提交进消毒前基线** |
| `docs/engineering/README.md` | modified | **提交进消毒前基线** |
| `docs/plans/README.md` | modified | **提交进消毒前基线** |
| `docs/plans/trading-system-roadmap.md` | modified | **提交进消毒前基线** |
| `docs/upstream/README.md` | modified | **提交进消毒前基线** |
| `packages/agents/README.md` | modified | **提交进消毒前基线** |
| `packages/execution/README.md` | modified | **提交进消毒前基线** |
| `packages/providers/README.md` | modified | **提交进消毒前基线** |
| `packages/research/README.md` | modified | **提交进消毒前基线** |
| `scripts/check_docs.ps1` | modified | **提交进消毒前基线**（登记文档路径） |
| `docs/plans/handoff-v4.2.0.md` → `docs/archive/handoffs/handoff-v4.2.0.md` | renamed | **提交进消毒前基线** |
| `docs/plans/handoff-v4.3.0.md` → `docs/archive/handoffs/handoff-v4.3.0.md` | renamed | **提交进消毒前基线** |
| `docs/plans/handoff-v4.3.1.md` → `docs/archive/handoffs/handoff-v4.3.1.md` | renamed | **提交进消毒前基线** |
| `docs/plans/handoff-v4.4.0.md` → `docs/archive/handoffs/handoff-v4.4.0.md` | renamed | **提交进消毒前基线** |
| `docs/STATUS.md` | untracked | **提交进消毒前基线** |
| `docs/archive/README.md` | untracked | **提交进消毒前基线** |
| `docs/plans/opensource-sanitization.md` | untracked | **提交进消毒前基线**（本计划；与文档整理同批或紧随其后） |

未在上表、且已被 ignore 的本机运行时（`.env`、`data/`、持仓等）**不要** `git add`；迁入 `local/` 后继续忽略。

默认闸门话术（供用户确认）：**先把上表文档改动（含本计划）提交成消毒前基线，drop 三条空 stash，再执行历史改写。**

## 分支策略

实测（2026-11-04）：

| 范围 | 分支 | 处置 |
|------|------|------|
| 本地 | `main`（当前，跟踪 `origin/main`） | **保留**（唯一保留分支） |
| 远端 | `remotes/origin/main` | **保留** |
| 其它本地分支 | （无） | 无需删 |
| 其它远端分支 | （无） | 无需删 |

`git remote -v`：`origin` = `git@github.com:deTian0/stock-platform.git`（fetch / push）。与已拍板「推到现有 `deTian0/stock-platform`」一致。

若日后出现多余分支，删除草稿（**未执行**；确认后才跑）：

```powershell
# 确认后才跑 — 仅当实测仍有非 main 分支时
git branch -D <other-local-branch>
git push origin --delete <other-remote-branch>
```

改写并 force push `main` 之后，再扫一遍 `git branch -a` 与 `git ls-remote --heads origin`，确认只剩 `main`。

## 现状盘点（敏感面）

实测时间：2026-11-04。分支 `main`，跟踪 `origin/main`。远端 `git@github.com:deTian0/stock-platform.git`。`git tag` **174** 个，全部是 annotated tag（`objecttype=tag`）。`git ls-remote --tags origin` 约 348 行（annotated tag 加 peeled `^{}`），与 174 个本地 tag 一一对应：**远端已经有全部 tag**。

### 总表

| 发现 | 在哪 | 严重度 | 处理 |
|------|------|--------|------|
| Tushare token 已填写 | 仓库根 `.env`。`.gitignore` 第 11 行忽略 `.env`。`git log --all -- .env` 为空，**从未入库** | 高（本机秘密） | 挪到 `local/.env`，继续不追踪。计划不抄原文，也不抄长度 |
| 真实持仓与资金快照 | `data/holdings.json`（根 `/data/` 已忽略）。2 条持仓，字段含代码、数量、成本、市值、盈亏；`account` 是资金快照（总资产等），没有口令字段；另有按日期的变动键。`liveTradingEnabled` 为 false | 高 | 整文件进 `local/`，永不 `git add` |
| 平台运行时产物 | 根 `data/`：478 个文件、约 28 MB。含 `stock_platform.db`、`digests/`、`health/`、`logs/`、`quotes/`、`performance/`、`strategy/`、`reports/`、`ths_import/`、`backup/`、`recommend_decisions.jsonl`、`performance_proxy.jsonl`、`_probe_t2.py` | 高 | 整棵迁入 `local/`。目前已被 `/data/` 忽略，且 `git ls-files` 看不到它们 |
| 仓外行情库 | `.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB` 指向本仓之外的 `market.db`（文件名 `market.db`，父目录 `data_cache`，约 3.2 GB，不在本仓内） | 中 | 路径只留在 `local/.env`。文档与代码里的绝对路径改成「由该变量指向」 |
| 本机仓根写死在已跟踪文件 | 至少 34 个已跟踪文件含 `D:\workspace` 或 `D:/workspace`（README、包 README、`docs/ops`、`docs/plans`、`docs/archive/handoffs`、三份 `scripts/ops/*.xml`、`Invoke-MarketDbBackfill.ps1`、两个测试默认路径、`templates/index.html`、`.env.example`、`picks_backtest_cli.py` 文档字符串等） | 中 | 改成相对说明或环境变量。提交说明里也有这类路径，只改 HEAD 清不掉旧提交 |
| Windows 用户目录 | `docs/ROADMAP.md` 三处 `<local-cursor-plans>/...` | 中 | 改成「本地 Cursor 计划，已迁到 `docs/plans/`」 |
| 个人券商与资金、一笔具体持仓写进正文 | [`0064`](../architecture/0064-live-trading-charter.md)、[`compliance-boundary.md`](../contracts/compliance-boundary.md)、`docs/plans/trading-system-roadmap.md`、`CHANGELOG.md`、`docs/STATUS.md`。0064 含具体标的、股数和 ETF 市值 | 已拍板：**文档不改** | 正文保留。运行时建议值改落 DB（可改）+ 缺行 seed / 初始化 CLI（见「产品 / 配置初始化」）。旧 git **blob** 里的本机路径与持仓描述仍走 `--replace-text`，与「文档不改」不冲突：HEAD 文档可留事实句，历史替换表只清需要清的旧串 |
| git 身份 | 全历史 **1** 个 author、**1** 个 committer。`git shortlog -sn --all` 为 192。`HEAD` 189，另外 3 个在当前 `refs/stash`。邮箱是真实 qq.com，**已经等于**目标开源邮箱。显示名**不是**纯 `63516`，含真实中文姓名。已跟踪文件里没有该中文姓名，提交说明里也没有该姓名和邮箱 | 高（元数据） | 改写全部历史的 author 与 committer 显示名。邮箱回调写成同一目标，避免以后再混入别的邮箱 |
| 指定开源邮箱出现的位置 | 只在被 `/_*` 忽略的 `_chk/release.txt`（2 处），未跟踪 | 低 | 不用处理入库；`_chk/` 保持忽略 |
| `.workbuddy/` | 未跟踪。只写在 `.git/info/exclude`，**不在**共享的 `.gitignore` | 中 | 把 `.workbuddy/` 写进仓库 `.gitignore`，避免别人 `git add -A` 时收进代理记忆 |
| 通达信探测路径 | `packages/providers/src/stock_platform_providers/tdx.py` 的 `_COMMON_ROOTS`（`D:\new_tdx` 等通用安装位） | 低 | 可以留。未设置 `STOCK_PLATFORM_TDX_ROOT` 且探测失败时已经 fail-closed |
| `persistence.py` 里的 `/C:/Users/...` | SQLite URL 形状注释，不是本机用户目录 | 无 | 保留 |
| 示例与夹具 | `.env.example` 占位符、`packages/research/tests/fixtures/recommend_decisions.jsonl`、`packages/providers/.../data/*_closed_days.txt`、公开 URL `finance.qq.com` / `stockbuddy.qq.com`、报告 CSS 的颜色 token | 无 | 保留。不要全局忽略 `*.jsonl`，否则夹具会被忽略 |
| `CHANGELOG` 提到 token 已自动加载并写了字符长度 | `CHANGELOG.md`（无 token 原文） | 低 | 删掉长度，避免侧信道。不要把长度抄进本计划 |
| 业务阈值 | `min_pick_score` 出厂 0.80 / 备选 0.70、榜单条数、`EM_*` 节流 | 无 | **不是秘密**。可以有代码默认值；不必放进「必须抽走」清单 |
| pydantic Settings | 全仓没有 `BaseSettings` / `pydantic-settings`。Workbench 的 pydantic 只用于 HTTP 模型。research 的 `pyproject.toml` 没有 pydantic 依赖 | 缺口 | 见「配置收口」 |
| 文档散落 | 已跟踪 Markdown 约 180（不含 `.git`）。`docs/` 内约 171，且已分子目录。根 4 个入口 + 4 个包 README + `apps/workbench/README.md`。`.cursor/plans/` 另有 7 个 md，已是指向 `docs/plans/` 的短索引，且被 gitignore | 结构 | 见「文档怎么收」 |

### 必须抽走 vs 可以留

**必须抽走（不准进跟踪文件 / 改写后历史）：**

- `.env` 里的 token、LLM key、同花顺 token / 账号、本机 `market.db` 绝对路径。
- `data/holdings.json`（及迁入后的 `local/holdings.json`）以及 digest、健康度、日志、绩效 JSONL、SQLite、同花顺导入块、报价缓存——整棵进 `local/`，永不 `git add`。
- 已跟踪**脚本 / 帮助文本**里的本机绝对路径 `D:\workspace\...`、`<user-home>/...`（HEAD 脱敏属第 1 阶段普通提交）；旧提交 blob 靠 `--replace-text`。
- git 显示名中的真实中文姓名（filter-repo 作者回调）。
- `.workbuddy/` 与 `_chk/`（后者已被忽略）。

**已拍板可以留在文档正文：**

- ADR 0064 / `compliance-boundary` / CHANGELOG / STATUS / 路线图里的券商选型、资金上限、具体持仓叙述——**不改字**。对应「可改建议值」进 DB + 初始化 CLI（非本轮）。

**可以留（其它）：**

- `.env.example` 的空值和 `your_token_here`。
- 测试夹具、交易日历文本、replay fixtures。
- 东财必须走 `em_get`、美港不套用 A 股 T+1 / 涨跌停、执行层 SIMULATE。这些是产品红线，不是个人秘密。
- `min_pick_score` 等阈值、`EM_MIN_INTERVAL` 等带安全默认值的节流参数。
- 通达信通用安装位探测列表。
- `D:/tmp/...` 这类文档里的临时目录示例（`daily_digest_cli` 的帮助文本）。

### 仍被 git 跟踪的私有文件

`git ls-files` 对 `.env`、`*.db`、`holdings.json`、`data/` 下运行时文件的结果是空。根 `data/`、`.env`、`userinput.py`、`.cursor/`、`_*` 都已忽略。

被跟踪、但属于「看起来像数据、其实是产品夹具」的，继续跟踪：

- `packages/providers/src/stock_platform_providers/data/{cn,hk,us}_closed_days.txt`
- `packages/research/tests/fixtures/recommend_decisions.jsonl`
- `.env.example`

## 推荐目标布局

### 私有目录：`local/`

只用这一个目录装本机私有产物。整棵不追踪：

```gitignore
/local/
```

建议同时保留现有 `/data/`、`.env`、`*.db`、`/_*`，并**新增** `.workbuddy/`。不要把 `*.jsonl` 改成全局忽略。

```text
local/
  .env
  stock_platform.db
  holdings.json
  recommend_decisions.jsonl
  performance_proxy.jsonl
  digests/
  ths_import/
  quotes/
  health/
  logs/                 # runs.jsonl
  performance/
  strategy/
  reports/
  backup/
```

选 `local/` 的原因（**已拍板采用此名**）：

1. 包内日历已经占用 `packages/*/src/*/data/`，而且 `.gitignore` 故意只忽略根 `/data/`，避免把日历忽略掉。私有库若继续叫 `data/`，读者会把它当成夹具目录。
2. 一条 `/local/` 就能盖住库、缓存、digest、持仓、日志、台账和 `.env`。
3. 名字表示「本机运行时」，不是点目录，资源管理器里看得见，备份时不容易漏。
4. 引擎行情库留在兄弟仓库，只通过 `STOCK_PLATFORM_ENGINE_MARKET_DB` 指向，不搬进 `local/`。

迁移（实施阶段，现在不做）：

1. 先复制，后删除。把根 `data/**` 拷到 `local/**`，把根 `.env` 拷到 `local/.env`。确认进程能读新路径之后，再删旧 `data/` 和根 `.env`。
2. 改代码里的默认路径（见下表）。环境变量已设置时仍然优先，调度器注入继续压过文件（现有 `load_dotenv(override=False)`）。
3. 调度 XML 的 `WorkingDirectory` 改成导入前必须填写的占位，去掉 `<repo-root>`。`Invoke-MarketDbBackfill.ps1` 的 `-EngineRoot` 默认值改为空：未传且环境变量也空则 fail-closed，不再默认兄弟仓绝对路径。
4. 测试里的 `DEFAULT_ENGINE_PATH` / `DEFAULT_DB` 改为只认 `STOCK_PLATFORM_ENGINE_REPO` / `STOCK_PLATFORM_ENGINE_MARKET_DB`。文件不在就 `pytest.skip`（现在已经是这个行为，只是默认字符串还写着本机路径）。
5. `git status` 确认 `local/` 不出现在未忽略列表里。

| 现默认（cwd 或仓库相对） | 代码位置 | 迁到 |
|--------------------------|----------|------|
| `sqlite:///./data/stock_platform.db` | `persistence.py`、`hit_tracking.py` | `sqlite:///./local/stock_platform.db` |
| `./data/recommend_decisions.jsonl` | `performance.py`、`daily_digest.py` | `./local/recommend_decisions.jsonl` |
| `./data/performance_proxy.jsonl` | `performance_proxy.py` | `./local/performance_proxy.jsonl` |
| `./data/digests`、`./data/ths_import`、`./data/quotes` | `daily_digest.py` | `./local/` 下同名子目录 |
| `./data/health` | `loop_health.py` | `./local/health` |
| `./data/logs` | `ops_ledger.py` | `./local/logs` |
| `data/strategy`、`data/performance` | `adoption_gate.py`、`attribution.py`、`performance_proxy.py` | `local/strategy`、`local/performance` |
| 仓库根 `data/holdings.json` | `day_quote_cli.py` 的 `DEFAULT_HOLDINGS` | `local/holdings.json`（仍可用 `STOCK_PLATFORM_HOLDINGS_PATH` 覆盖） |
| 仓库根 `.env` | `dotenv.find_dotenv_path`、`start-workbench.bat`、`Invoke-WorkbuddyBridge.ps1` | 默认 `local/.env`。过渡期若根 `.env` 仍在，加载器先读 `local/.env`，没有再读根 `.env` |

### 测试隔离会不会破

[`conftest.py`](../../conftest.py) 在 import 时把 `STOCK_PLATFORM_DB_URL` 和 `STOCK_PLATFORM_PERFORMANCE_LOG` 指到临时目录，并在每条测试前用 autouse fixture 钉死（ADR 0069 / 0070）。它钉的是**变量值**，不依赖目录名叫 `data`。把默认字符串改成 `local/` **不会**让这两项重定向失效。

会破的是写死了旧字符串的断言，例如 `packages/research/tests/test_ops_ledger.py` 里 `default_ops_ledger_dir() == Path("./data/logs")`。实施时同步改断言和 CLI 帮助文本。

现在的守卫**没有**盖住 digest、health、logs、holdings、quotes、proxy 的默认写入。`docs/STATUS.md` 已写明：单包 `pytest packages/research` 仍可能写到仓库 `data/`。改名之后，这些漏网写入会落到 `local/`，洞还在。实施时把上述路径一并放进会话临时目录（扩大 `GUARDED_ENV`，或在检测到 `PYTEST_CURRENT_TEST` 时默认走 tmp）。全量 `pytest packages apps` 继续作为验收命令。

`load_dotenv` 在 `PYTEST_CURRENT_TEST` / `PYTEST_VERSION` / `STOCK_PLATFORM_DOTENV_DISABLE` 下跳过。这个守卫保留，避免开发者的 `local/.env` 漏进测试。

### `.env` 单点与 pydantic

单点放在：

`packages/research/src/stock_platform_research/settings.py`

类名 `Settings`，用 `pydantic-settings` 的 `BaseSettings`。research 已经拥有 `dotenv.py`，Workbench 已经依赖 research。providers / execution / agents **继续不 import research**（[`dotenv-loading.md`](../contracts/dotenv-loading.md) 第 7 节：providers 只做 I/O）。它们仍读 `os.environ`，但进程入口必须先 `get_settings()`，由 Settings 把 `local/.env` 载入环境。

research 今天没有 pydantic 依赖。实施时给 research 加上 `pydantic-settings`（Workbench 里现有的 pydantic 是 HTTP 模型，不能当成配置单点）。

加载规则沿用现有契约，并改默认文件：

1. 显式路径
2. `STOCK_PLATFORM_DOTENV`
3. `<repo>/local/.env`
4. 过渡：仓库根 `.env`
5. 文件缺失不报错，返回空（CI 的 replay 不需要 `.env`）
6. 默认不覆盖已存在的进程环境变量

`.env.example` 继续放在仓库根、继续被跟踪，只留占位符和中文注释。复制说明改成「复制为 `local/.env`」。删掉示例里的 `D:/workspace/...`。

`.gitignore` 已有 `.env` 与 `.env.*`，并放过 `!.env.example`。再加上 `/local/`。

#### 哪些入口已经加载 dotenv

research 的 26 个 console script 里，**23 个** `main()` 调用了 `load_dotenv()`：

`brief_cli`、`refresh_cli`、`daily_cli`、`performance_cli`、`backtest_cli`、`position_review_cli`、`market_universe_cli`、`rankings_cli`、`hit_tracking_cli`、`symbol_master_cli`、`picks_backtest_cli`、`strategy_ab_cli`、`factors_cli`、`sensitivity_cli`、`neutralization_cli`、`adoption_gate_cli`、`attribution_cli`、`workbuddy_bridge_cli`、`sameday_cli`、`day_quote_cli`、`loop_health_cli`、`ops_ledger_cli`、`performance_proxy_cli`。

契约文档仍写「14 个 CLI」，那是 `v4.1.6` 的数字。多出来的 9 个是后来的 symbol-master、adoption、attribution、workbuddy-bridge、sameday、day-quote、loop-health、ops-ledger、performance-proxy。实施时改契约，避免文档继续落后。

另外：

- `quotes.py` 在解析引擎库时补一次 `load_dotenv()`。pytest 守卫会跳过它，**不能**当成别的 CLI 的入口保证。
- `scripts/ops/Invoke-DailyPipeline.ps1` 只在探测 `market.db` 的内嵌 Python 里调用 `load_dotenv()`。
- `scripts/ops/Invoke-WorkbuddyBridge.ps1` 手写解析仓库根 `.env`（和 Python 解析器不是同一套规则）。
- `start-workbench.bat` 用 `for /f` 解析根 `.env`。注释写明 Workbench 自己不读 dotenv。这套解析不处理引号、`export` 前缀和行内注释。

#### 哪些漏了

| 入口 | 情况 |
|------|------|
| `stock-platform-digest`（`daily_digest_cli.py`） | `main()` 不加载。日批脚本用子进程 `-m stock_platform_research.daily_digest_cli` 调它。自定义 `STOCK_PLATFORM_DB_URL` 若只写在 `.env`，digest 看不到 |
| `stock-platform-workbench`（`__main__.py`） | 直接 `uvicorn`，不加载。只有双击 `start-workbench.bat` 才注入环境 |
| `stock-platform-score` | 只评 CSV，不读环境。可以不加载 |
| `stock-platform-report-html` | 只吃文件参数。可以不加载 |
| providers / execution / agents 库代码 | 没有自己的进程入口，靠调用方已经注入的环境 |

收口时：digest 与 workbench 的 `main()` 开头调用 `get_settings()`。bat 与 Workbuddy 的 PowerShell 改为调用同一个 Python 加载器，或假定子进程 CLI 自己加载。不要保留第三套解析器。

#### `.env.example` 有、本机 `.env` 未填的键

这些只是注释掉的模板，**不是**已经入库的秘密：`STOCK_PLATFORM_BRIEF_FALLBACK`、`STOCK_PLATFORM_DAILY_PROVIDER`、`STOCK_PLATFORM_DB_URL`、`STOCK_PLATFORM_DEEP_LLM_GRAPH`、`STOCK_PLATFORM_LLM_API_KEY`、`STOCK_PLATFORM_LLM_DEBATE`、`STOCK_PLATFORM_PERFORMANCE_LOG`、`STOCK_PLATFORM_STRATEGY_AB` 及 `_A` / `_B`、`STOCK_PLATFORM_THS_ACCOUNT`、`STOCK_PLATFORM_THS_BASE_URL`、`STOCK_PLATFORM_THS_MODE`、`STOCK_PLATFORM_THS_TOKEN`。

本机 `.env` 实际填写的键都在 example 里（预设、Tushare URL、Tushare token、东财节流五项、`STOCK_PLATFORM_HTTP_TRUST_ENV`、`STOCK_PLATFORM_BROKER`、引擎库路径）。其中只有 token 是秘密。

#### 代码里有、example 里还没有的键

实施时补进 `.env.example`（空值或安全默认的注释），不要发明新语义：

`STOCK_PLATFORM_DOTENV`、`STOCK_PLATFORM_DOTENV_DISABLE`、`STOCK_PLATFORM_BENCHMARK_SYMBOL`、`STOCK_PLATFORM_LOOP_HEALTH_DIR`、`STOCK_PLATFORM_OPS_LEDGER_DIR`、`STOCK_PLATFORM_HOLDINGS_PATH`、`STOCK_PLATFORM_PERFORMANCE_PROXY_LOG`、`STOCK_PLATFORM_PICKS_LEDGER`、`STOCK_PLATFORM_REFRESH_DIR`、`STOCK_PLATFORM_REFRESH_WORKERS`、`STOCK_PLATFORM_REFRESH_MIN_INTERVAL`、`STOCK_PLATFORM_REFRESH_TOLERATE_GAPS`、`STOCK_PLATFORM_TDX_ROOT`、`STOCK_PLATFORM_WESTOCK_BIN`、`STOCK_PLATFORM_WESTOCK_TIMEOUT`、`STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`、`STOCK_PLATFORM_FUTU_HOST`、`STOCK_PLATFORM_FUTU_PORT`、`STOCK_PLATFORM_LLM_FALLBACK`、`STOCK_PLATFORM_LLM_MAX_CALLS`、`STOCK_PLATFORM_LLM_MAX_TOKENS`、`STOCK_PLATFORM_LLM_MODEL`、`OPENAI_API_KEY`。

只给测试用、不要写进用户模板的：`STOCK_PLATFORM_TEST_DATA_DIR`、`STOCK_PLATFORM_ENGINE_REPO`、`STOCK_PLATFORM_FIXTURES`。

核对时丢掉误匹配：`STOCK_PLATFORM_THS`、`STOCK_PLATFORM_THS_`、`EM_MIN_INTERVAL_HINT` 是前缀或提示文案，不是独立变量。

### 产品 / 配置初始化（DB 行 + CLI；非本轮实施）

已拍板：文档里的券商、资金、具体持仓**不必改**。这些「建议值」应作为**可修改的数据库行**存在，而不是只靠 ADR 字面当唯一真相。

| 项 | 计划口径 |
|----|----------|
| 存什么 | 至少：券商选型建议、资金上限 / 名义本金、持仓相关默认（或指向 `local/holdings.json` 的约定）。具体表名 / schema 实施时定，优先落在现有 `stock_platform.db`（`local/` 下），避免第二套库 |
| 可改 | 用户或 agent 可 UPDATE；文档 ADR 仍是立项叙事，**运行时以 DB 为准**（若行存在） |
| 缺行 | 新库 / 空库：seed 填必填字段（可从安全默认或 `.env.example` 注释推导，**不**把实盘开关 seed 成 true） |
| CLI | 提供 `stock-platform-init`（名称可微调）供其他 agent 调用：检测目标库 → 无行则插入必填 → 有行则打印现状 / 支持显式覆盖标志。幂等 |
| 与 ADR 0064 | 0064 继续描述 L1 立项事实与解锁阶梯；**不**因本 CLI 改字。CLI / DB **不**解除 `liveTradingEnabled=false`，**不**引入 live 券商 |
| 与 `compliance-boundary` | 合规三层（监管 / 券商 / 平台）与 P0 SIMULATE 红线不变。DB 里的资金上限是**名义账本 / 建议**，不是报备替代 |
| 与 holdings | 真实持仓快照仍在被忽略的 `local/holdings.json`（或现有路径）；DB 行可存「默认持仓路径 / 名义仓」元数据，**不要**把完整实盘持仓 JSON 提交进 git |
| SIMULATE 红线 | `STOCK_PLATFORM_BROKER` 默认 `paper`；`liveTradingEnabled` **不进** Settings、不进 init seed 的可开项。本工作项只做配置落库与空库初始化 |

本工作项已随配置收口落地：`runtime_config.py` + `stock-platform-init`。

#### 默认值与 fail-closed

| 项 | 保留的行为 |
|----|------------|
| 文件缺失 | 不报错。生产预设仍是 `cn_astock_http`；日批 CLI 未设置时仍默认 `replay`，避免裸跑打公网 |
| `STOCK_PLATFORM_TUSHARE_TOKEN` 空且选择 tushare / `cn_tushare_http` | 非 0 退出，中文说明，不降级成 fixtures |
| `STOCK_PLATFORM_ENGINE_MARKET_DB` 空或文件不存在 | 结算 / 回测 / `market_db` provider fail-closed，不造假 K 线 |
| `STOCK_PLATFORM_THS_MODE` | 默认 `mock`。`experimental` 缺 `BASE_URL` 或 `TOKEN` 则失败。未知模式失败 |
| `STOCK_PLATFORM_BROKER` | 默认 `paper`。只允许 `paper` 与 `ths_sim` |
| LLM | 默认关。`STOCK_PLATFORM_LLM_FALLBACK` 默认 `deterministic`。缺 key 时按现有逻辑降级或拒绝，不写死一把 key |
| `STOCK_PLATFORM_HTTP_TRUST_ENV` | 默认 `0` |
| `STOCK_PLATFORM_STRATEGY_AB`、`STOCK_PLATFORM_DEEP_LLM_GRAPH` | 默认关 |
| 未知 `STOCK_PLATFORM_PROVIDER_PRESET` | 直接失败，不悄悄改预设 |
| `liveTradingEnabled` | **不进 Settings**。继续常量 `false` |
| `min_pick_score` 等 | 留在策略默认值（0.80）。Settings 可以提供可选覆盖，但空着就用代码默认，缺失不是错误 |

## 文档怎么收

### 实测分布

| 位置 | 数量 | 角色 |
|------|------|------|
| `docs/` 内（含 architecture 86、contracts 30、ops 20、plans 13、upstream 9、archive 5、docs 根 6、engineering 2） | 约 171 | 正式正文，已按用途分目录 |
| 仓库根 `README.md`、`AGENTS.md`、`CONTRIBUTING.md`、`CHANGELOG.md` | 4 | `check_docs.ps1` 的 `$required`；`CHANGELOG` 还要被版本节校验 |
| `packages/{agents,execution,providers,research}/README.md` | 4 | `pyproject.toml` 的 `readme`，也在 `$required` |
| `apps/workbench/README.md` | 1 | 同上 |
| `.cursor/plans/*.md` | 7 | 短索引，指向 `docs/plans/`，已被 `.gitignore` |
| `_chk/**/*.md`、`data/**/*.md`、`.workbuddy/**/*.md` | 本机才有 | 未跟踪。`check_docs.ps1` 递归所有 `*.md`（只排除 `.git`），这些文件里的坏链接也会让检查失败 |

### 推荐方案

正式正文只留 `docs/`，**保持** `architecture/`、`contracts/`、`ops/`、`plans/`、`archive/`、`engineering/`、`upstream/`。不把这些子目录打平成一个文件夹：相对链接数以百计，`check_docs` 的 `$required` 写的是子路径，打平的代价大于「一个文件夹」的观感。

散落在 `docs/` 之外的，按角色收成指针，不把文件搬走：

| 文件 | 建议 |
|------|------|
| 根 `README.md` | **留在根**。这是 GitHub 仓库首页。改成短指针：产品一句话、SIMULATE / `em_get` 红线、如何复制 `local/.env`、链到 `docs/README.md` 与 `docs/STATUS.md`。删掉 `cd D:\workspace\...` |
| `AGENTS.md` | 留在根。它是代理入口，`AGENTS.md` 约定和 `$required` 都指这里。正文继续指向 `docs/` |
| `CONTRIBUTING.md` | 留在根，只留贡献命令，链到 `docs/` |
| `CHANGELOG.md` | 留在根。`check_docs` 用它核对 `VERSION` 节，发版脚本也读它 |
| 各包 README 与 Workbench README | 留在包旁。各留一段安装 / 硬约束，并链到 `docs/STATUS.md`。这是 pip `readme = "README.md"` 的约定。删掉本机 `cd` 路径 |
| `.cursor/plans/` | 不入库，不搬进 `docs/`。已经是短索引。共享 ignore 继续盖住 `.cursor/` |
| 本计划 | 放在 `docs/plans/opensource-sanitization.md`。实施时把它加入 `scripts/check_docs.ps1` 的 `$required`，并在 `docs/plans/README.md` 加一行链接。**现在不要改脚本** |

### 若坚持「所有 md 都进一个文件夹」

可以做，代价要先接受：

1. `check_docs.ps1` 的 `$required` 含根上 4 个 md、5 个包 README，以及大量 `docs/<子目录>/...`。搬走后检查会红，除非改脚本（脚本改动是实施阶段的事）。
2. GitHub 首页没有根 `README.md` 时是空的。
3. 包的 `readme` 字段会断，PyPI / 源码安装说明不再在包旁。
4. `CHANGELOG` 被移走后，版本校验和发版清单要改路径。
5. 现有相对链接（包 README → `docs/`，文档之间的 ADR 互链）要整批重写。`check_docs` 会扫到每一个坏链。
6. 打平 `docs/architecture` 等子目录还会把编号 ADR 和契约混在一堆，现有「按用途分目录」的约定失效。

因此不推荐。推荐是：**正文在 `docs/` 且保持分类；根和包 README 变成短指针。**

另外，实施时让 `check_docs` 跳过 `local/`、`data/`、`.cursor/`、`_*`、`.workbuddy/`，只检查将要公开的 Markdown。否则本机私有 md 的链接会卡公开 CI。

## 分阶段实施顺序

历史改写会换掉**全部** SHA，包括这次收束产生的新提交。所以改写放在最后。前面的提交一旦改写，基于旧 SHA 的 tag、PR、本地克隆都会失效。**顺序保留；各破坏性命令仍标「确认后才跑」。**

0. **消毒前基线（普通提交；过执行闸门话术后）**  
   按「改写前工作区盘点」处置：文档整理 + 本计划提交进基线；三条空 stash drop。**本轮不 commit**——等用户说确认话术后再做。
1. **脱敏与 gitignore（普通提交，不改历史）**  
   脚本 / 帮助文本去掉本机绝对路径（**文档里的券商 / 资金 / 持仓正文不改**）；`.gitignore` 增加 `/local/` 与 `.workbuddy/`；把现有 `data/` 和根 `.env` 复制到 `local/`（复制是本地操作，目录已被忽略）。确认 `git status` 不出现这些文件。
2. **配置收口**  
   加 `Settings`，默认路径改到 `local/`，补上 digest / workbench 的加载，更新 `.env.example` 与 dotenv 契约，扩大测试隔离。业务阈值语义不变。实盘开关不加。  
   **已落地**：产品 / 配置初始化（DB 行 + `stock-platform-init` CLI），见上节与 `docs/ops/local-runtime.md`。
3. **文档指针**  
   根 README 与包 README 改短并链到 `docs/`。`docs/plans/README.md` 与 `check_docs` 的 `$required` 登记本计划。修正 STATUS 里「工作区干净」的过时句子。不打平 `docs/`。**不**为开源改写 0064 / compliance 持仓句。
4. **最后才改写历史并整理 tag / 分支**  
   见下一节。此步之前的提交都还在旧 SHA 上。此步之后，协作者的旧克隆作废，保留的 tag 要按新 SHA 重打；仅保留 `main`。

第 0–3 步可以用普通 commit。第 4 步不是普通 commit，见下。公开许可证与 Releases **延后**，不阻塞第 0–4。

## 保留 tag 清单与删除原则

174 个 annotated tag，从 `v0.0.1` 到 `v4.13.7`。按主版本计数：v0 共 30、v1 共 54、v2 共 10、v3 共 37、v4 共 43。没有 `v4.8.*`，不要补。

删除原则：

- 对外需要的是时代边界，不是每一次 patch。patch 与中间 minor 的说明已经在 `CHANGELOG.md`，删 tag 不删文字。
- **已拍板**：只保留下面 11 个。其余 163 个本地 tag 在过闸门之后删除；远端多余 tag 一并删除（已拍板）。
- 文档若写「见 tag vX.Y.Z」而该 tag 不在清单里，实施时改成「见 CHANGELOG 的 [X.Y.Z] 节」，避免悬空引用。
- 改写历史之后旧 tag 对象的 SHA 全部失效，保留清单要在新提交上重打 annotated tag（`scripts/release_tag.ps1` 的规则：annotated、`v` 前缀、不覆盖）。`versioning.md` 写过「禁止移动已推送 tag」；本次历史消毒是用户明确授权下的例外，只适用于这次，不改日常发版规则。**这不是发 GitHub Releases 开源叙事。**

### 已拍板保留（11 个）

| Tag | 留它的原因 |
|-----|------------|
| `v1.0.0` | M7 / ADR 0012，v1 产品边界 |
| `v2.0.0` | Phase A：日更选股 + 纸面闭环 |
| `v3.0.0` | Phase D：同花顺模拟盘收口；默认仍 paper，无实盘 |
| `v3.9.0` | M47：生产默认东财 live 行情；交易仍 SIMULATE |
| `v3.12.6` | G1/G2：依赖可安装、本机路径与 env 治理的基线 |
| `v4.0.0` | X1：全市场宇宙单点入口 |
| `v4.1.6` | dotenv 单点与刷新吞吐（生产可用 P0） |
| `v4.3.1` | 测试不得写入生产数据目录 |
| `v4.9.1` | T2：调度执行台账 |
| `v4.13.0` | 简报盘前 / 盘后分线 |
| `v4.13.7` | 现行版本，与 `VERSION` 一致 |

（曾列备选「只留 5 个 major + 现行」——**未采用**。）

## 历史改写步骤草稿

**确认后才跑。未过「执行闸门」前整节停手。**

身份事实（不展开邮箱列表）：全历史只有 1 组 author/committer，192 个提交（`--all`），其中 `HEAD` 189。邮箱已是 `635161624@qq.com`。显示名要改成纯 `63516`（已拍板）。因为姓名字节会变，**所有提交 SHA 仍会变**。`.mailmap` 只影响显示，不改对象，不够。

提交说明里没有该姓名和邮箱，但有 `D:\workspace` 路径。**已拍板**：同一次改写加 `--replace-text`，清旧 blob 里的本机路径与持仓描述。替换表放在 `local/replacements.txt`（被忽略），不要提交，也不要把原句抄进 `docs/`。HEAD 上 ADR / 契约正文按拍板**不改**；`--replace-text` 针对历史串，实施时列表明细，避免误伤仍要保留在 HEAD 的文档句（若某串与 HEAD 需保留句相同，则只依赖「第 1 阶段不改文档」+ 替换表审慎收录，或接受改写后需把保留句再提交回去——实施前在闸门里复核替换表）。

stash：已实测三条皆空（见盘点）。改写前 drop，勿 push。`git filter-repo` 默认处理所有引用。

`git filter-repo` 不是 Git for Windows 自带的。用上游单文件脚本，不要写进本仓依赖。它默认会**删掉 remote**，防止误推。推送前要重新添加 origin。它也会丢掉 reflog。

### 0. 备份（确认后才跑；任何删除之前）

```powershell
# 确认后才跑
git clone --mirror . <backup-dir>\stock-platform.git
```

镜像放在仓库外面，不提交、不上传。它含有改写前的姓名和全部 tag，是回滚源，本身也是私密副本。

### 1. 只删本地多余 tag（确认后才跑）

先确认镜像里 tag 计数仍是 174。然后在工作副本：

```powershell
# 确认后才跑
$keep = @(
  'v1.0.0','v2.0.0','v3.0.0','v3.9.0','v3.12.6',
  'v4.0.0','v4.1.6','v4.3.1','v4.9.1','v4.13.0','v4.13.7'
)
git tag --list | Where-Object { $keep -notcontains $_ } | ForEach-Object { git tag -d $_ }
```

这一步**不**碰 origin。

### 2. 改写全部历史的 author / committer + replace-text（确认后才跑）

在已经完成第 0–3 阶段普通提交、工作区干净、stash 已 drop 之后：

```powershell
# 确认后才跑
git filter-repo --force `
  --name-callback 'return b"63516"' `
  --email-callback 'return b"635161624@qq.com"' `
  --replace-text local/replacements.txt
```

这两个回调同时作用于 author 和 committer。`local/replacements.txt` 须事先准备好且位于已忽略目录。

改写后核对：

```powershell
# 确认后才跑（核对，只读）
git log --format="%an %ae%n%cn %ce" | Sort-Object -Unique
git for-each-ref refs/tags --format="%(refname:short) %(taggername) %(taggeremail)"
```

期望只看到 `63516` 与 `635161624@qq.com`。若 tagger 仍是旧显示名，删掉保留名单里的本地 tag，在新 SHA 上重打 annotated tag。`filter-repo` 会移动仍存在的 tag 指向新提交；tagger 身份要以上面的 `for-each-ref` 为准。

然后恢复远端名字（先不要推）：

```powershell
# 确认后才跑
git remote add origin git@github.com:deTian0/stock-platform.git
```

### 3. force push + 删远端多余 tag（确认后才跑；与第 2 步分开）

**已拍板**推到现有 `deTian0/stock-platform`。origin/main 已有旧历史，只能 force push。协作者旧克隆作废，必须重新克隆。  
再次强调：这是**远端历史消毒**，**不等于宣布开源**。

```powershell
# 确认后才跑
git push --force origin main
git push origin --tags
```

删除远端多余 tag（origin 上现有 174 个；确认后才跑）：

```powershell
# 确认后才跑
git push origin --delete <tag>
```

可以对不在 `$keep` 中的名字循环。先 `git ls-remote --tags origin` 核对，再删。同时确认远端 heads 只有 `main`（见「分支策略」）。

### 风险（改写与删 tag / force push）

- 所有 SHA 变化。未推送的本地分支、正在开的 PR、别人 fork 里的旧提交都对不上。
- GitHub 上旧提交在 gc 之前仍可能通过 fork、PR、旧 SHA 链接访问。force push **不能**保证旧对象立刻消失。
- 远端 tag 一旦删除，依赖某个 patch tag 的部署或笔记会断。CHANGELOG 还在，tag 不在。
- `filter-repo` 失败或推错远程时，用镜像恢复。已 force push 之后，恢复等于再 force push 一次镜像里的旧历史，GitHub 仍可能留着两套对象。
- **已拍板**在现有 `deTian0/stock-platform` 上 force push：扰动已有克隆与全部远程多余 tag。这是消毒，不是开源发布；许可证仍可 `LicenseRef-Pending`，不发 Releases 叙事。
- 备份镜像含真实显示名和旧路径，丢失或误传都会把收束前的身份重新泄露。
- `--replace-text` 若与 HEAD 仍保留的文档句撞车，改写后可能需再提交还原保留句——替换表要在闸门阶段人工审。

### 回滚

尚未推送时：扔掉改写后的工作目录，从镜像克隆。

```powershell
# 确认后才跑（回滚用）
git clone <backup-dir>\stock-platform.git stock-platform-restored
```

已经 force push 时：只有再从镜像 force push 才能把 origin/main 拨回去，而且远程缓存和 fork 不会自动跟上。不要用 `git reset --hard` 指望恢复被 `filter-repo` 丢掉的 reflog。

## 验收

实施第 0–3 阶段后（仍是普通历史）：

- `pwsh -File scripts/check_docs.ps1`
- `pwsh -File scripts/check_versions.ps1`
- `pytest packages apps`（环境 `STOCK_PLATFORM_PROVIDER_PRESET=replay`）
- `git status` 不列出 `.env`、`local/`、`data/*.db`、`holdings.json`、`*.sqlite`
- `git ls-files` 仍包含 `.env.example`、日历文本、测试夹具 jsonl
- 已跟踪脚本 / 帮助里搜不到 token 原文、本机 `D:\workspace` / `C:\Users\63516`（**0064 等文档持仓句按拍板可仍存在**）
- `liveTradingEnabled` 仍恒为 false；没有新的实盘开关
- digest 与 `stock-platform-workbench` 在不借助 bat 的情况下能读到 `local/.env`
- 未设置 token 时 tushare 路径仍非 0 退出
- 单包 pytest 不再往 `local/` 或 `data/` 写生产文件
- （配置初始化落地后另验）空库跑 `stock-platform-init` 能插入必填行且不打开 live

实施第 4 阶段后额外确认：

- `git log --format` 的 author 与 committer 只有 `63516 <635161624@qq.com>`
- 本地 tag 只剩已拍板的 11 个，且 `git show <tag>` 的提交是新历史里的对应版本
- `git branch -a` / `git ls-remote --heads origin` 只有 `main`
- 若用户已同意推送：远端 main 与远端 tag 和本地一致；远端多余 tag 已删
- 仓库仍无开源许可证叙事（延后）

## 许可证（延后）

公开许可证**不着急**。产品还要迭代很多，等成熟了才开源。

- 当前可保持 `LicenseRef-Pending`（或不加 `LICENSE`）。
- **不**因本计划发 GitHub Releases「开源」说明。
- 本地收束、配置收口、历史作者改写、删多余 tag/分支、force push 消毒**可以继续**，且不阻塞于许可证选型。
- 真要公开开源时另开一轮：选许可证、加 `LICENSE`、更新 README 法律段、再议是否公开仓库可见性。

## 已关闭的决策 / 仍须闸门确认

**已拍板（见顶部表）**：`local/`、11 tag、作者改写、`--replace-text`、推现有仓 + 仅 `main`、删远端多余 tag、文档券商/资金/持仓不改（改走 DB/init CLI）、公开开源延后。

**仍须用户一句话才开跑（执行闸门）**：

1. 草稿处置确认（默认建议：文档改动 + 本计划先提交成基线，空 stash drop，再 filter-repo）。
2. 开始跑 filter-repo / 删本地多余 tag 的明确指令。
3. force push + 删远端多余 tag 的明确指令（可与 2 分开）。

**实施时仍要做、但不阻塞拍板**：

- `check_docs` 登记本文件并跳过 `local/` 等私有目录（现在不改脚本，除非用户另开实施轮）。
- `stock-platform-init` / DB seed 工作项（非本轮）。
