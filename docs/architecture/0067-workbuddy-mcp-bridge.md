# 0067 — WorkBuddy MCP 桥接（westock CLI → JSON 缓存）与 workbuddy 模式启动

- **状态**：Accepted
- **日期**：2026-10-12
- **里程碑**：数据源接入（目标 tag `v4.1.8`）
- **相关**：ADR [`0054`](0054-data-source-adapters.md)（数据源适配层）·
  ADR [`0066`](0066-refresh-throughput-and-env-loading.md)（取数吞吐 / env 自动加载）·
  契约 [`docs/contracts/data-source-adapters.md`](../contracts/data-source-adapters.md)

---

## 1. 背景：provider 存在，但从未有人给它写数据

用户当前的主线目标未变：**系统要做到生产可用、真实可用 —— 完成每日选股、盘前盘后信息收集，最终目标是盈利**。本轮请求：**"数据源可以使用 workbuddy 的某些合适的 mcp。然后记得为此增加一个专门的 workbuddy 模式 启动"**。

排查后发现一个**结构性缺口**：

- `workbuddy` provider（`packages/providers/.../workbuddy.py`）是一个**纯只读的 JSON 缓存适配器**，读 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR/{daily,realtime}_{code}.json`；
- `workbuddy` **预设**存在（`presets.py`，`is_default=False`）、**能力声明**存在（`capabilities.py`，`datasets={"daily","realtime"}`）；
- 但 **写缓存的那一半（"MCP bridge"）从未实现** —— provider 的 docstring 提到它，代码里却没有。也就是说："workbuddy 模式" 可以启动、可以路由，但**永远拿不到真实数据**，只会读到空目录。

## 2. 候选数据面与被选中的那一个

WorkBuddy 的金融数据能力（`finance-data@cb_teams_marketplace` 插件 v1.6.0）提供：

| 能力 | 形态 | 是否可作确定性数据源 |
|---|---|---|
| `neodata-financial-search` | HTTP + **自然语言**问答 | ❌ 面向 agent，非机器可调用 OHLC |
| `westock-tool`（选股） | 条件/策略筛选 | ❌ 是「选股」不是「取行情」 |
| **`westock-data`（`westock` CLI）** | Go 二进制，输出**结构化 Markdown 表** | ✅ **选中** |

**决策：用 `westock` CLI 作为数据面。** 理由：

1. 它的 `kline` / `quote` 输出是**稳定表格**（列名固定），可确定性解析；
2. `kline` 支持批量（逗号分隔代码）与日期/条数/复权参数，一次进程取多只；
3. 二进制由插件的 `setup.{cjs,ps1,sh}` 安装，带 **SHA256 清单校验 + 固定版本信任根**（供应链可信）；
4. 它**不联网时读缓存、联网时取行情**，仍属于「公开发行数据」，不触碰任何实盘/下单能力。

## 3. 决策

### 3.1 补齐写的一半：`workbuddy_bridge`

新增 `packages/research/.../workbuddy_bridge.py`：

```
westock kline <codes> --period day --limit N --fq qfq   ─┐
westock quote  <codes> [--date D]                        ─┴─► parse Markdown table
                                                              ▼
                                          write_daily_cache / write_realtime_cache
                                                              ▼
                                       STOCK_PLATFORM_WORKBUDDY_CACHE_DIR/*.json
```

**关键：schema 只在一个地方。** 桥不自己拼 JSON —— 它把解析出的 raw bar 交给
**已有的规范写入器** `write_daily_cache` / `write_realtime_cache`。这与 provider
的读路径共享同一个 schema 定义点，避免「两套格式漂移」。

### 3.2 字段映射的一条硬规则

实测 `kline sh600519 --period day --limit 5` 的输出列是
`date | open | last | high | low | volume | amount | exchange | change_pct`。

- `last` → `close`（**改名**，westock 用 `last` 表示收盘）；
- `change_pct` 是 **percent 标度**（`0.5741405808` == +0.574%），带 `pct_unit="percent"`，由 `normalize_daily_row` ÷100；
- **`exchange` 丢弃**：它是**换手率（%）**，不是交易所代码。语义不同，绝不挪用同名/近名字段 —— 这是本项目一以贯之的「语义边界」纪律。

### 3.3 三条守卫（防止静默错误数据）

| 场景 | 风险 | 处置 |
|---|---|---|
| **多代码批出现无 `code` 列的行** | bar 被安到错误的 symbol | 记 `warnings` 并**跳过**；只有单代码批才允许无列归因 |
| **`sh000001`（指数）vs `sz000001`（股票）** | 两者都归一为 `000001`，同写一个文件 → bar 静默交错 | 抓取前**拒绝**歧义对，其余 symbol 照常桥接 |
| **显式 `--bin` 路径不存在** | 静默回落 PATH 上另一个二进制，难排查 | 路径不存在即**报错**；裸命令名才走 PATH |

第三条尤其重要：平台的 `normalize_symbol` **有意丢弃交易所前缀**（这是全 provider 层依赖的契约），所以裸码碰撞是**领域事实**而非 bug —— 桥必须拒绝，而不是让一个来源覆盖另一个。

### 3.4 workbuddy 模式启动

预设**本身不足以**让 daily 走 workbuddy：`Invoke-DailyPipeline.ps1` 把
`--provider` 默认成 `replay` **并显式传参**，会覆盖 `STOCK_PLATFORM_PROVIDER_PRESET`。
实测确认了这一覆盖。

因此：

1. `daily_cli` 的 `--provider` **直接接受 `workbuddy`**（别名 `workbuddy_mcp`），与 `market_db` 同一模式；缺 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR` 或目录不存在 → 中文 fail-closed 报错并指向 `stock-platform-workbuddy-bridge`；
2. 新增两步编排 `scripts/ops/Invoke-WorkbuddyBridge.ps1`：先 bridge 刷缓存，再以 `--provider workbuddy` 跑 daily；
3. 新增双击版 `start-workbuddy.bat`，可选位置参数 `symbols` / `datasets`；
4. 默认缓存目录 `data/workbuddy_cache`（可跨重启留存）；`-FromMarketDb -Top N` 从 `market.db` 取成交额 Top-N 作为默认宇宙。

## 4. 后果

### 正面

- "workbuddy 模式"从「能启动但拿不到数据」变成**真能端到端跑通**；
- 数据面走 **SHA256 校验过的官方发行二进制**，供应链可控；
- 桥的解析层**零网络可单测**（注入 runner），实测层另有证据；
- **零 `liveTradingEnabled` 触碰**：只用公开发行行情，不涉及下单。

### 负面 / 代价

- 依赖外部 CLI 与 CDN（`stockbuddy.qq.com`）；已装 `v0.0.4`，未来可升级；
- `workbuddy` 是**有限缓存**，不是全市场 —— 桥到多少只，横截面就有多少只。全市场仍需 `market_db` 路径（ADR 0055 / 0058）；
- 单代码响应无 `code` 列这一 westock 行为，是解析器必须记住的隐式契约（已在契约文档 §1.4 / §4.1 显式记录）。

## 5. 实测证据（2026-10-12，本机）

| 项 | 结果 |
|---|---|
| `westock --version` | `westock 0.0.4 channel=workbuddy`（`~/.local/bin/westock.exe`，2,600,960 B） |
| 桥 4 代码 × 2 数据集 | **8/8 ok / 124 bars / 0 failed** |
| bridge → `WorkbuddyProvider` 往返 | **90 行**，跨度 `2026-08-21 → 2026-10-09`，`source="workbuddy"` |
| percent→decimal | `0.5741405808` → `0.005741405808` |
| 碰撞守卫 | `WARN code collision on 000001` + 跳过，其余照常 |
| 全链路（launcher） | bridge 6/6 ok / 183 bars → daily `provider="workbuddy"`、`ok: true` |
| 测试 | **972 passed / 0 failed**（较 v4.1.7 的 943 增 29） |
