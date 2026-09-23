# stock-platform 文档索引

本目录是产品文档的 **单一事实源（SSOT）**。不要依赖 `.cursor/plans` 或兄弟仓才能读懂本仓。

## 按类别导航

| 目录 / 文件 | 用途 |
|-------------|------|
| [`ROADMAP.md`](ROADMAP.md) | 里程碑总表（M0–M47 / Phase） |
| [`plans/`](plans/) | 能力盘点、能力域合并、可用推荐 U 线、情报报告 MR 线、选型清单 |
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

正式正文已迁至 [`plans/`](plans/)。Cursor 侧仅保留索引指针，避免双 SSOT。

## 维护约定

- 改口径先写 ADR / 契约，再改代码。  
- 东财请求规范见 [`contracts/eastmoney-http.md`](contracts/eastmoney-http.md)。  
- 上游只读；禁止整仓拷贝进本仓。  
