# ADR 0003：providers 包与 normalize_symbol 入口

- 状态：Accepted
- 日期：2026-09-13

## 背景

多仓各自实现 ticker 清洗，易漏港美拒绝与北交所 `920` 前缀。

## 决策

1. 可安装包名 `stock-platform-providers`，导入 `stock_platform_providers`。
2. CN 路径唯一入口：`normalize_symbol`；交易所前缀：`exchange_prefix`。
3. 拒绝港美与中文名（中文解析留待后续，避免 M1.1 拉 mootdx）。
4. 包版本与仓库根 `VERSION` 同步（CI 校验）。

## 后果

- M1.2 适配器必须先 `normalize_symbol` 再请求。
- 工作台/Agent 迁入时删除平行归一化实现。
