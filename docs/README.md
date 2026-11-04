# stock-platform 文档索引

本目录是产品文档的 **单一事实源（SSOT）**。先读 [`STATUS.md`](STATUS.md) 看现行版本和下一刀，再按需下钻。不要依赖 `.cursor/plans` 或兄弟仓才能读懂本仓。

正文按用途分在下面这些子目录里。仓库根只留 `README.md` / `AGENTS.md` / `CONTRIBUTING.md` / `CHANGELOG.md` 四个入口；各包自己的 `README.md` 只讲安装与硬约束，并链回 `STATUS.md`。

## 按类别导航

| 目录 / 文件 | 用途 |
|-------------|------|
| [`STATUS.md`](STATUS.md) | **现行快照**（版本、未完成项、下一刀、文档放哪） |
| [`ROADMAP.md`](ROADMAP.md) | 历史里程碑总表（M0–M47 / Phase A–E，均已 done） |
| [`plans/`](plans/) | 仍有效的计划：自有九域路线图、U 线、MR 线、选型与边界 |
| [`plans/trading-system-roadmap.md`](plans/trading-system-roadmap.md) | 自有主线（G/B/S/X/L/C/R/T/Y 九域）；开放项以 `STATUS.md` 为准 |
| [`plans/dual-line-responsibility.md`](plans/dual-line-responsibility.md) | 双线职责边界（引擎线 ↔ 平台线，`C1`） |
| [`archive/`](archive/README.md) | 已落地的历史交接；文中「下一块砖」作废 |
| [`architecture/`](architecture/) | ADR（编号递增） |
| [`contracts/`](contracts/) | 对外契约（数据集、能力矩阵、市场策略、东财 HTTP 等） |
| [`ops/`](ops/) | 运维：刷新、调度、live 启动、Skills 治理、诚实性说明 |
| [`engineering/`](engineering/) | OpenAPI、测试分层、CI |
| [`upstream/`](upstream/) | 上游配方只读归档（摘要副本，非运行时） |
| [`upstream-archive.md`](upstream-archive.md) | 上游仓总清单与红线 |
| [`versioning.md`](versioning.md) | 版本与 tag 规范 |
| [`release-checklist.md`](release-checklist.md) | 发版检查清单 |

## 从根入口进入

1. [`../README.md`](../README.md) — 产品概述与快速开始  
2. [`../AGENTS.md`](../AGENTS.md) — AI / 代理开发入口  
3. [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — 贡献与自检命令  

## 计划文档（原 `.cursor/plans`）

仍有效的正文在 [`plans/`](plans/)。已经完成的 v4.2–v4.4 交接在 [`archive/handoffs/`](archive/README.md)。Cursor 侧只保留指向本目录的短链，避免双 SSOT。

## 维护约定

- 改口径先写 ADR / 契约，再改代码。  
- 东财请求规范见 [`contracts/eastmoney-http.md`](contracts/eastmoney-http.md)。  
- 上游只读；禁止整仓拷贝进本仓。  
