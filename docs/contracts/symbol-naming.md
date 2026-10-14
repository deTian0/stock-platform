# 契约：代码 ↔ 名称显示（Symbol Naming）

> 里程碑 **R1** · 能力落地 `v4.6.0` / 文档收口 `v4.6.1` ·
> 代码单点：`packages/research/src/stock_platform_research/symbol_master.py`
> 相关 ADR：[0072](../architecture/0072-symbol-master-name-authority.md) ·
> 承接：[hit-tracking](hit-tracking.md)、[rankings](rankings.md)

## 1. 目的

把「**代码 → 人可读名称**」的解析收敛到**一处**，让命中追踪、日报、报告在任何情况下
**都不会把代码当成名称显示**。此前该逻辑分散在 `rankings._display_name`、`brief._lookup_name`、
`daily_cli._build_name_map` 等处，命中追踪更是**没有**接入，导致 A3 报告印出 `000801 | 000801`。

**验收**（路线图 R1）：`display_name()` 单一入口；存储层缺名存空、展示层未知显示 `—`；
历史脏行回填干净；`symbol_master` 全量可查。

## 2. 单点定义

名称解析只有一个实现：`symbol_master.display_name(code, *, stored=None, name_map=None)`。
仓库层（`hit_tracking` / 报告）只**消费**该函数，不得自写回退逻辑。

## 3. 存储：`symbol_master`

平台 SQLite（与 brief 归档同库）的 `symbol_master` 表：

| 列 | 含义 |
|---|---|
| `code` | **主键**，裸 6 位代码（`000001`，无交易所后缀） |
| `name` | 中文简称（来自引擎只读 `fundamentals.name`） |
| `market` | 板块 / 市场（来自 `fundamentals.market`） |
| `source` | 出处标记，如 `engine:fundamentals` |
| `updated_at` | 最近刷新时间 |

**来源**：`refresh_from_engine(market_db, db_url)` 读**只读** `market.db.fundamentals`
（实测 **5237/5237** 覆盖），`ON CONFLICT(code) DO UPDATE` **幂等**。
`daily_cli` 每次跑批顺带刷新一次（**fail-open**）。

**映射口径**：本表是 **6 位代码 ↔ 中文简称** 映射。源表**没有英文名字段**，
故不提供中英双语；需要英文名须另找数据源（见 ADR 0072「非目标」）。

## 4. 解析优先级（唯一入口）

`display_name(code, stored=None, name_map=None)` 按序取第一个**非空**值：

1. **`stored`** —— 记录里的真实名称，且 **`stored != code`**；
2. **`name_map`** —— 调用方显式传入的映射（可选）；
3. **本地 `symbol_master`** —— 查主表；
4. **`UNKNOWN_NAME = "—"`** —— 占位符。

**两条硬规则**：

- **存储层**：`clean_name(value)` 在缺名时返回**空串**，**绝不返回 code**；
- **展示层**：未知一律 `—`。**任何路径下都不得把 code 当名称输出。**

## 5. 出口

| 出口 | 行为 |
|---|---|
| `stock-platform-symbol-master --refresh` | 从引擎刷新主表（幂等），`--stats` 看行数/覆盖 |
| `stock-platform-symbol-master --lookup CODE` | 单码查名（未收录 → 占位符，不回显代码） |
| `stock-platform-hits --backfill-names` | 回填 `hit_summary` / `hit_tracking` 的历史脏行（幂等） |
| `stock-platform-hits --report` | A3 报告名称列走 `display_name`（未知显示 `—`） |
| `daily_cli` 跑批 | 顺带刷新主表（fail-open，不阻断） |

## 6. 非目标

- **不提供中英双语名称**（源无英文字段，不得臆造）。
- **不把名称当语义输入** —— 名称不参与打分 / 闸门 / 绩效。
- **不写回引擎库** —— 平台对 `market.db` 只读（ADR 0058）。
- **不改变 brief payload 语义** —— `name` 仍为装饰性契约（ADR 0070）。

## 7. 免责

名称仅用于**人可读输出**；平台全程 SIMULATE（`liveTradingEnabled=false`），
本契约不构成任何投资建议。名称陈旧与源库同步节奏一致，不影响任何计算口径。
