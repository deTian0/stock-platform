# 0084 — 二次精选逐榜给出可复制的同花顺导入块

- Status: Accepted
- Date: 2026-10-29
- Amends: ADR 0083 §4（「同花顺文件导出生产榜」）
- Related: ADR 0081（③B 数量化）、ADR 0083（盘前/盘后分文件 + 二次精选）

## 背景

ADR 0083 把二次精选定为**展示口径**，同花顺导入块仍按生产榜导出。落地后 `v4.13.0`~`v4.13.2` 的简报里出现两处错位：

1. **②A 二次精选没有可复制的块**。长线只有「一、今日 Top10」那一块（= 生产榜 `picks`），而 ②A 二次精选取的是 `quality.items` 里剔掉 ST / 地量后的 5 只。读者看完二次精选表，还得自己从表里抄 5 个代码去建自选，这正是「一键导入」本该省掉的手工步骤。
2. **②B 的块与 txt 不一致**。`v4.13.0` 起 md 里的「同花顺导入 · 短线」块渲染的是**二次精选入选**，而 `data/ths_import/{reportDay}_short.txt` 按 ADR 0083 导出的是 **`short_term.items` 生产榜**。同一份报告里，复制一行和打开 txt 拿到的是两组不同的代码。

生产榜与二次精选是**两套取舍口径**：生产榜保留 ST 与地量（只剔北交所，ADR 0083 §5），二次精选在 `_gate` 里剔 ST、剔成交额 < 1000 万。二者本就不该混用，但也不该只给其中一份可复制的形态。

## 决定

### 1. 每一份榜都自带导入块，块与 txt 一一对应

| 榜 | md 代码块标签 | txt 文件 | 代码来源 |
|---|---|---|---|
| 长线 Top10（生产榜） | `同花顺导入 · 长线` | `{reportDay}.txt` | `picks` |
| ②A 二次精选 | `同花顺导入 · 二次精选（长线）` | `{reportDay}_quality_sec.txt` | `quality.items` → `select_secondary(profile="quality")` |
| ②B 生产榜 | `同花顺导入 · 短线` | `{reportDay}_short.txt` | `short_term.items` |
| ②B 二次精选 | `同花顺导入 · 二次精选（短线）` | `{reportDay}_short_sec.txt` | `short_term.pool` → `select_secondary(profile="short")` |

- 每份都配 `latest{kind}.txt` 指针，命名沿用 ADR 0083 的 `reportDay` 规则。
- 标签名取 `二次精选（长线）` / `二次精选（短线）` 而非 `长线二次精选`，是为了与既有的 `长线` / `短线` 标签**不构成前缀关系** —— `"同花顺导入 · 短线"` 若被 `"同花顺导入 · 短线二次精选"` 包含，任何按标签切分的读取方都会撞车。
- 生成逻辑收敛到 `_secondary_codes(record, profile)`：md 的块由 `build_digest_text` 现场重算的 `select_secondary` 产出，txt 由同一个 `select_secondary` 以同一入参再算一次。**二次精选结果不入 brief 存档**，所以两处必须共用函数而不是复制逻辑，否则「块与 txt 一致」只是巧合。

### 2. 生产榜的块照旧，不因新增块而消失

ADR 0083 的「导出生产榜」结论不变：`{reportDay}.txt` / `{reportDay}_short.txt` 仍是生产榜。②B 段里生产榜的块重新出现在二次精选块之后，并在 txt 侧保持原文件名，避免既有下游脚本失效。

### 3. fail-closed 不变

`select_secondary` 选不出任何标的一律不出块、不落盘、不生成占位行（与全篇一致）。`short_term.pool` 缺失时不出②B 二次精选块，正文显式写「无候选池，未做二次精选」。

## 后果

- 同一天最多 4 份导入 txt；文件名带 `_quality_sec` / `_short_sec` 后缀，不会互相覆盖。
- ②B 段里会出现两个块，读者须按标签区分「生产榜」与「二次精选」。两者的代码可以不同，这是设计而不是 bug。
- 后续若再调二次精选阈值，md 块与 txt 会自动同步（同一函数），无需额外对账。
