# 本机运行时目录 `local/`

> 状态：Accepted｜配套 [`../plans/opensource-sanitization.md`](../plans/opensource-sanitization.md)  
> 相关：[`../contracts/dotenv-loading.md`](../contracts/dotenv-loading.md)

平台自有产物（brief SQLite、digest、持仓快照、日志、健康度、绩效 JSONL、`.env`）默认落在仓库根下的 **`local/`**。整棵目录被 `.gitignore` 的 `/local/` 忽略，**永不提交**。

仓外引擎 `market.db` **不**搬进 `local/`；只用 `STOCK_PLATFORM_ENGINE_MARKET_DB` 指向。

## 从旧 `data/` 迁移

若本机仍有仓库根 `data/` 私有产物：

```powershell
# 在仓库根执行；先复制、确认进程可读后再删旧目录
New-Item -ItemType Directory -Force -Path local | Out-Null
Copy-Item -Path data\* -Destination local\ -Recurse -Force
if (Test-Path .env) { Copy-Item .env local\.env -Force }
# 确认 CLI / Workbench 正常后：
# Remove-Item -Recurse -Force data
# Remove-Item .env   # 仅当已改用 local/.env
```

默认路径对照：

| 旧默认 | 新默认 |
|--------|--------|
| `sqlite:///./data/stock_platform.db` | `sqlite:///./local/stock_platform.db` |
| `./data/recommend_decisions.jsonl` | `./local/recommend_decisions.jsonl` |
| `./data/digests` 等 | `./local/` 下同名子目录 |
| （新）多策略影子账本 | `./local/shadow/`（`STOCK_PLATFORM_SHADOW_DIR`；**禁止**混入主绩效 JSONL；见 [`shadow-board.md`](shadow-board.md)） |
| （新）本仓模拟舱 | `./local/paper_cabin/state.json`（`stock-platform-paper`；见 [`paper-cabin.md`](paper-cabin.md)） |
| （新）补充行情库 | `./local/aux_market/aux_market.db`（见 [`aux-market.md`](aux-market.md)） |
| 仓库根 `.env` | `local/.env`（过渡期仍可读根 `.env`） |

## 配置初始化 CLI

空库或缺配置行时：

```powershell
stock-platform-init
# 或显式：
stock-platform-init --db-url sqlite:///./local/stock_platform.db
stock-platform-init --force --broker 华宝证券 --capital-limit 10000
```

- 幂等：已有 `platform_runtime_config` 单行则只打印现状；`--force` 才覆盖。
- **不**打开 `liveTradingEnabled`（恒为 false / SIMULATE）。
- 券商建议、资金上限、持仓路径元数据落库可改；真实持仓 JSON 仍在被忽略的 `local/holdings.json`。
- **该文件是 ③A / ③B 的唯一真源**（ADR [`0097`](../architecture/0097-holdings-single-source-and-post-close.md)）：`Invoke-DailyPipeline.ps1` 默认读它，`data/holdings.json` 残留**不再**兜底（缺失即两榜为空，fail-closed）。迁移前的残留已归档到 `local/backup/holdings-legacy-2026-10-28.json`；**不要让 `data/` 下再出现同名文件**。
- 文档 ADR 0064 / compliance 正文不因本 CLI 改字；运行时以 DB 行为准（若存在）。

## `.env`

```text
copy .env.example local\.env
# 填写 STOCK_PLATFORM_TUSHARE_TOKEN、STOCK_PLATFORM_ENGINE_MARKET_DB 等
```
