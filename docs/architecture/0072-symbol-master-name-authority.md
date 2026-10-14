# 0072 — 代码 ↔ 名称主数据表：名称解析的唯一权威（`symbol_master`）

- Status: Accepted
- Date: 2026-10-14
- Supersedes: —
- Related: ADR 0057（命中追踪）、ADR 0058（market.db 只读真相源）、
  ADR 0069（测试数据隔离）、ADR 0070（日常循环自足）、ADR 0071（报告 HTML 化）

## 背景

`v4.6.0` 修复的真实缺陷：A3 命中追踪报告印出 `000801 | 000801`（名称列与代码列
**一模一样**）。三层根因叠加：

1. **回退成代码** —— `hit_tracking._clean_name()` 在名称缺失时把 **code 当 name 返回**，
   于是「未知」被渲染成「看起来正确」的错值（`000801 | 000801` / `601318 | 601318`）。
2. **去重挡住回填** —— 命中明细按 `UNIQUE(code, session_type, pick_date)` 去重，
   后续跑批即使已拿到真名，也**永远写不回去**。
3. **平台没有名称主表** —— 名称只散落在 brief payload（**装饰性、可缺**）与引擎
   `fundamentals.name`（**只读、另一仓**）；且两侧 `code` 口径不同：`daily_price.code`
   带交易所后缀（`000001.SZ`），`fundamentals.code` 是**裸 6 位**。

**结论**：名称需要一张**平台自有的本地主数据表**，并让「显示」与「存储」各守一条硬规则。

## 决策

### D1 — 新增本地主数据表 `symbol_master`

存平台 SQLite（与 brief 归档**同库不同表**）：`code`（**主键**，裸 6 位）/ `name` / `market` /
`source` / `updated_at`。

### D2 — 数据源 = 引擎只读 `fundamentals`，刷新幂等

`refresh_from_engine(market_db, db_url)` 读只读库 `market.db.fundamentals(code, name, market)`
（实测 **5237/5237** 全覆盖），按 `ON CONFLICT(code) DO UPDATE` 落库，`source` 记
`engine:fundamentals`。`daily_cli` 每次跑批顺带刷新一次（**fail-open**：名称是装饰性的，
刷新失败**不阻断**主流程）。

### D3 — `display_name()` 是名称解析的**唯一入口**

优先级：**记录里的真实名称（≠ code）> 显式 `name_map` > 本地 `symbol_master` > 占位符 `—`**。
两条硬约束：

- **存储层** `clean_name()` 名称缺失时返回**空串**，**绝不返回 code**；
- **展示层** 未知一律 `UNKNOWN_NAME = "—"`，让「未知」可见，而不是伪装成代码。

### D4 — 历史脏行一次性回填

`stock-platform-hits --backfill-names` 把 `name IS NULL OR TRIM(name) = '' OR name = code`
的行按主表回填（**幂等**）。实测修复 **14 行 `hit_summary` + 20 行 `hit_tracking`**，
回填后脏行 **0**（`WHERE name IS NULL OR TRIM(name)='' OR name = code` 计数为 0）。

### D5 — 新增 CLI `stock-platform-symbol-master`

`--refresh` / `--stats` / `--lookup CODE` / `--list` / `--limit` / `--json-out`；
引擎库路径取 `.env` 的 `STOCK_PLATFORM_ENGINE_MARKET_DB`。

## 非目标

- **不做中英双语名称** —— 只读源 `fundamentals` 实测列包含
  `code` / `name` / `industry` / `area` / `list_date` / `market` / `pe` / …，**没有英文名字段**。
  故本表映射的是 **6 位代码 ↔ 中文简称**；若需要英文名，**须另找数据源，不得臆造**
  （原始诉求「中英文映射表」在当前数据面下只能兑现为「代码（拉丁/数字符号）↔ 中文名」）。
- **不改 brief payload 语义** —— `name` 仍是**装饰性契约**（ADR 0070）：取不到就**不写键**，
  「无名称」路径下 `brief.json` / `picks_ledger.jsonl` / 命中周期 / 绩效 JSONL **逐字节不变**。
- **不做名称的语义消费** —— 名称**不参与**打分、闸门、绩效归因；它只影响人可读输出。

## 后果

- **正向**：命中追踪 / 日报 / 报告的名称显示有了**单一权威源**；`—` 让未知可见而不是伪装成代码；
  刷新幂等、回填幂等、CLI 可查可审计。
- **代价**：多一张表 + 跑批内一次秒级刷新（单机 SQLite）。
- **边界**：平台**只读**引擎库（ADR 0058）；`symbol_master` 归平台自有，**不写回引擎**。
  主表与 `fundamentals` 是**单向只读**依赖 —— 引擎不更新则名称陈旧（可接受：名称极少变）。
