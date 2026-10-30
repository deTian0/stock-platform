# ADR 0086：westock CLI 作为第四源与可选 provider（WorkBuddy 侧数据源）

- 状态：已采纳
- 日期：2026-10-30
- 里程碑：`v4.13.6`
- 关联：[0085 多源兜底](0085-ohlc-multi-source-fallback.md) · [0082 当日行情台账](0082-day-quote-attribution.md) · 契约 [`day-quote`](../contracts/day-quote.md) · [Skills 治理](../ops/skills-governance.md)

## 1. 背景

`v4.13.5` 给当日 OHLC 建了「东财 → 腾讯 → 新浪」三源链，前提假设是**三者互相独立**。
2026-10-30 盘后实测把这个假设打破了：东财 `CircuitOpenError` 的同时，腾讯
`qt.gtimg.cn` 与新浪 `hq.sinajs.cn` 也是空响应 —— **三源同时不可达**，说明故障在
本机出口/链路层，而非某一家厂商。这种情况下再加源、再加轮次都是空转。

WorkBuddy 侧有一条**完全不同的取数链路**：`westock` CLI（Go 二进制，经
`stockbuddy.qq.com` 分发、SHA256 清单校验、装到 `~/.local/bin`）。它是**本地进程**，
云侧是另一套后端，因此不受上述出口故障影响。

关键区分（决定能不能进流水线）：

| 能力 | 形态 | 能否被定时流水线的 python 子进程调用 |
|---|---|---|
| `westock` CLI | 本地可执行文件 | **能**（`subprocess`） |
| `neodata-financial-search` | 需 Agent 在线经 `connect_cloud_service` 换 tempToken | 不能 |
| `futu` OpenAPI | 本地 OpenD 常驻网关 + 账号行情权限 | 能，但运行时未就绪 |

因此**只有 westock 能在不改调度形态的前提下落到运行时**。`neodata` 继续只用于
Agent 会话内的探索性查询，不写成管道（见 §3 第 6 条）。

## 2. 决策

分两层接入，互不耦合：

### 2.1 P0 —— `day_quote` 的第四源（仅兜底）

```
东财 push2his/kline/get（主源）
  └─ 腾讯 qt.gtimg.cn
       └─ 新浪 hq.sinajs.cn
            └─ westock CLI（前三源对该批标的**颗粒无收**时才触发）
                 └─ 都没有 → 留 —，数据备注写明四源均失败
```

新增 `stock_platform_providers.westock`：

| 项 | 取值 |
|---|---|
| 入口（兜底） | `fetch_day_snapshot(symbols, day, *, runner=None)` → `(rows, note)`，与 `snapshot.fetch_day_snapshot` 同签名，调用方可互换 |
| 入口（provider） | `WestockProvider.get_daily` / `.get_realtime` |
| 底层命令 | 兜底与实时用 `quote [--date <day>]`；历史用 `kline --period day --start --end --fq qfq` |
| 批量粒度 | `QUOTE_CHUNK = 60`（实测 60 只/次稳定）；`KLINE_CHUNK = 20`（保守） |
| 输出形态 | **Markdown 表格，无 `--json`** → 本模块自带 `parse_md_table` |
| 二进制解析 | `STOCK_PLATFORM_WESTOCK_BIN` → `~/.local/bin/westock[.exe]` → `which westock` |
| 失败语义 | 兜底函数**永不抛出**；provider 仅在二进制缺失时抛中文 fail-closed 提示 |

### 2.2 P1 —— 正式参与能力矩阵

- `capabilities.register_builtin_providers()` 增加 `westock` 声明：`daily` + `realtime`。
- `presets.py` 增加 `cn_westock`（`daily`/`realtime` → `westock`，其余能力保持 `replay`）。
- **不改生产默认**：`DEFAULT_STARTUP_PRESET` 仍是 `cn_astock_http`。

## 3. 硬约束

1. **列名寻址，绝不按位置**。`quote` 的列顺序在不同市场/命令之间**不稳定**（实测两次
   调用的字段集就不同），按位置取值必然错位。`parse_md_table` + `_pick(head, cells, name)`
   是唯一读取方式。
2. **日期必须相等**。只接受 `time == quote_day` 的行。厂商在收盘后仍会返回上一交易日
   的完整 K 线，不校验就会让「涨跌」恒为 0（与 ADR 0085 §3.1 同一条原则）。
3. **停牌整行丢弃**。`open <= 0` 或 `close <= 0` 整行舍弃，绝不补零。
4. **复权口径锁死为 qfq**。见 §4 实测：引擎 `market.db` 的 `close` 是**前复权**序列，
   只有 qfq 与之逐点相等；`bfq` 服务端直接报错，`hfq` 差两个数量级。故 `get_daily`
   显式传 `--fq qfq`，不依赖「默认值恰好是 qfq」这一实现细节。
5. **只补「颗粒无收」**。第四源不负责补前三源的零星缺口（那是快照的职责）。这条是
   使用者明确要求的语义：westock 是「最后一命」，不是日常主力，避免把外部依赖变成
   隐形主源。
6. **不进 pyproject 依赖、不平行抓取**。CLI 是外部可执行文件，不是 pip 依赖；
   `research` 包顶层仍禁止 import `providers`（懒导入，有测试锁）。这与
   [`skills-governance`](../ops/skills-governance.md) 的「运行时唯一权威」一致 ——
   接入形态是 **provider**，不是「在 agents/research 里 exec 一个 skill 脚本」。
7. **不新增写库**。兜底行照旧落 `data/quotes/ohlc-<date>.json`，同日复跑零网络。

## 4. 验证（2026-10-30 真机实测）

### 覆盖率与延迟

| 项 | 结果 |
|---|---|
| 批量容量 | 60 只/次（5 批 × 60） |
| 覆盖率 | **300/300 = 100%**，无缺行 |
| 单批延迟 | 1.9 – 4.8 s |
| 必需字段 | `open/high/low/price/prev_close/volume/amount` 全在（表共 48 列） |
| 当日可用性 | 15:30 即可取到当日 `2026-10-30` 完整 OHLC（无需等 18:30 回补） |

### 复权口径（决定性）

| 检查 | 结果 |
|---|---|
| `--fq bfq` | **服务端报错** `code=1620053001 msg=service error`（帮助文本列了 bfq，实际不支持） |
| `--fq nofq/qfq/hfq` | 均可用 |
| 省略 `--fq` 等价于？ | **等于 qfq**（4 只票逐日相同，`默认==qfq: True`） |
| qfq vs 引擎库 `close` | **120 点 0 不一致** |
| hfq vs 引擎库 `close` | **120 点 120 不一致**（例：000001 引擎 11.54 / hfq 2302.59） |
| `prev_close` 口径 | 与引擎库**前一交易日** `close` 完全相等（600519→1354、000533→8.66、600104→10.85） |

结论：引擎库是前复权序列 ⇒ provider 必须用 qfq。

### 端到端

- **四源降级演练**（强制东财 + 腾讯 + 新浪全失败，只留 westock）：6/6 只补齐，
  数据备注为
  `东财不可达（…）；腾讯/新浪快照亦不可用（…）；6/6 只改用 westock CLI 当日快照`。
- **provider 真实路径**：5 只 × 8 日 = 40 行，与引擎库 `close` **0 不一致**。
- 单测：`packages/providers/tests/test_westock.py` 24 例（表格解析、列序打乱、跨日
  拒收、停牌丢弃、单/多代码 kline 身份回退、批量分片、provider 映射、`asof_ts` 定点、
  `pre_close` 回填、二进制缺失 fail-closed、CLI 错误外露）；`test_quotes.py` 新增 4 例
  并给 autouse fixture 加桩 `_westock_fill`（**单测绝不 shell 出去**）。全量 **1351 passed**。

## 5. 为什么不选其它方案

| 方案 | 否决理由 |
|---|---|
| 接 `neodata-financial-search` | 需 Agent 在线换 tempToken，定时流水线的 python 子进程拿不到 → 进不了 15:30/08:30 |
| 接 `futu` OpenAPI | provider 代码已就绪，但需 futu-api + OpenD 常驻 + 富途账号 A 股行情权限，运行时未就绪 |
| 只把 westock 写进脚本直调 | 违反 `skills-governance`「禁止平行抓取主链」；必须先扩矩阵再接线 |
| 让 westock 当主源替代东财 | 外部 CLI 的稳定性/时效/复权口径会变成隐形单点；且会绕开 `em_get` 的限流与断路器口径 |
| 吸收 `a-share-daily-review` 作运行时 | 该技能全目录只有 `SKILL.md` + 7 个 references，**零数据代码**，属「报告配方」而非数据源 |

## 6. 遗留

- **Markdown 表格是脆弱契约**。厂商改表头就会静默少列 —— `_pick` 返回 `None` 时
  该字段为 `None`，不会崩溃但会降级。若 westock 后续提供 `--json`，应优先切过去。
- **全市场 `get_daily` 不可行**：`KLINE_CHUNK = 20` ⇒ 5218 只要 261 次调用（约 10
  分钟以上）。定位是「小批量补当日/校验」，不替代 `engine_sqlite` 的历史回补。
- **基准 `000905` 的口径缺陷未修**：`westock` 里 `sh000905` 是**中证500 指数**
  （2026-10-30 收 6266.19），而 `exchange_prefix("000905")` 推出的是 `sz000905`
  = **厦门港务**个股 —— 与引擎库、`normalize_symbol` 的现有行为一致。这是平台的
  既有缺陷（报告顶部 `benchmarkWarning` 就在说这件事），本次**不改口径**，
  是否改用 `sh000905` 需单独决策。
- 覆盖的是 `daily` / `realtime` 两项能力；`minute` / `depth5` / `fund_flow` 等
  westock 亦有对应命令，但未验证契约形状，暂不声明（未声明 = fail-closed）。
- **沪市 `5xxxxx` 基金/ETF 前缀映射缺陷（既有，未修，独立里程碑）**：
  `exchange_prefix("588080")` 返回 **`sz`**（规则只认 `6`/`9` 开头为沪市，漏了 `5`），
  `em_secid` 因此得 `0.588080`。实测对照：

  | 调用 | 结果 |
  |---|---|
  | `westock quote sh588080` | 有数据（10-29 开 1.30 / 高 1.302 / 低 1.251 / 收 1.252） |
  | `westock quote sz588080` | `未找到行情数据` |

  影响面是**全部共用 `exchange_prefix` 的 provider**（东财 `em_secid`、腾讯/新浪快照、
  futu、本次 westock），所以沪市 ETF（588080 软件ETF嘉实、510300、563300 中证2000增强…）
  在四源里**一律取不到**，`--asof 2026-10-29` 冒烟时 `12/13` 补齐、唯一缺口正是 588080。
  这**不是本次接入引入的**（`snapshot` 时代已存在），修它要动共享权威并补前缀测试，
  按「改动最小、不处理无关问题」另立版本处理。

## 7. 与既有 `workbuddy_bridge` 的分工（不是重复实现）

仓里已有一个同源模块 `stock_platform_research.workbuddy_bridge`（`v4.1.8`，
2026-10-12），它同样 shell 出去调 westock、同样解析 Markdown 表格。**两者不是
重复，而是不同职责**：

| | `workbuddy_bridge`（research） | `westock`（providers） |
|---|---|---|
| 职责 | **缓存写入器**：批量刷新 → `daily_{code}.json` / `realtime_{code}.json` | **运行时适配器**：同步返回行，供兜底链与 provider 直接消费 |
| 产出 | 磁盘缓存（`WorkbuddyProvider` 只读消费） | 内存行 dict，零落盘 |
| 粒度 | 每标的一份文件 + `BridgeReport` 逐标的成败 | 当日一根 / 一段窗口 |
| 表格解析 | `parse_markdown_tables`，**识别多张表**（批响应宽度不一致时切表） | `parse_md_table`，只管第一张表 |
| 额外职责 | 二进制版本探针、bare-code 撞码拒收、`dry_run` | 单日 `trade_date` 校验收口、停牌丢弃 |
| 触发 | 手工/批量回补 | 15:30 盘后兜底、矩阵路由 |

**为什么不能让 providers 复用 bridge**：依赖方向是 `providers ← research`，
`providers` 不能 import `research`（会成环）。所以 provider 侧必须自带一份最小
适配器 —— 这不是疏忽，是分层约束的必然结果。

**为什么 P0 不绕道缓存**：兜底要快且无副作用。走 bridge 就要「写盘 → 再读盘 →
还要先配好 `STOCK_PLATFORM_WORKBUDDY_CACHE_DIR`」，多两层 I/O 和一处配置前置，
而兜底本身是故障态下的最后一条路，前置条件越少越好。

**已知代价**：两处各自维护一份 Markdown 表格解析与 CLI 调用。若将来 westock 提供
`--json`，两处都应切过去（那时重复才真正消失）。合并两者需要先给 bridge 找到新的
分层位置，属独立重构，不在本次范围。

