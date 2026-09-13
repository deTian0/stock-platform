# stock-platform

单一产品仓：把既有 A 股/全球数据、选股回测、工作台、投研 Agent、执行安全模型，逐步收敛成一个可发布的量化研究与决策平台。

> 当前版本见根目录 [`VERSION`](VERSION)。里程碑与 tag 路线见 [`docs/ROADMAP.md`](docs/ROADMAP.md)、[`docs/versioning.md`](docs/versioning.md)。

## 第一版范围（架子）

- 工程目录与 Git 管理
- 目标架构与数据契约（M0.2 Accepted）
- 里程碑 / SemVer tag 升级路线（文档 + 脚本 + CI）
- `packages/providers` 与 `apps/workbench` 占位（尚无可运行业务）

**明确不做（v0.1.x → M1 前）**：行情抓取实现、选股、回测、UI、券商对接。  
**已完成（M0 / v0.1.0）**：仓库工程化、契约定稿、里程碑与 tag 流程、CI 冒烟。  
**已完成（M1 / v0.2.0）**：可安装 providers、ticker、replay daily/realtime、`em_get`、能力矩阵。  
**进行中（M2）**：工作台壳 — v0.2.1 起 FastAPI 最小可跑。

## 仓库布局

```text
stock-platform/
├── apps/
│   └── workbench/          # FastAPI 最小壳（M2.1+）
├── packages/
│   └── providers/          # 统一 Vendor（M1+）
├── docs/
│   ├── ROADMAP.md          # 大/小里程碑与验收
│   ├── versioning.md       # tag 与发版规则
│   ├── architecture/       # ADR
│   └── contracts/          # 数据集 / 能力矩阵 / 市场策略
├── scripts/
│   ├── check_docs.ps1      # 文档/链接/VERSION 自检
│   └── release_tag.ps1     # 打 tag 辅助脚本
├── VERSION                 # 单一版本事实源
├── CHANGELOG.md
├── CONTRIBUTING.md
└── AGENTS.md
```

## 吸收来源（只读参考，勿整仓拷贝）

| 来源仓 | 目标角色 |
|--------|----------|
| tick-stock-panel | 工作台壳 + Provider 契约 |
| a-stock-data / global-stock-data | 统一 Vendor 配方 |
| a-stock-engine | 选股 / PIT 回测内核 |
| TradingAgents-astock | 研报 Agent 插件（去数据层） |
| V2-code-review | 执行安全模型（设计吸收） |
| finance-quant-skills | Agent 技能文档（不进运行时） |

## 快速开始（当前）

```powershell
cd D:\workspace\git\stock-platform
Get-Content VERSION
.\scripts\check_docs.ps1
Get-Content docs\ROADMAP.md
```

文档自检与发版 DryRun（不创建 tag）：

```powershell
.\scripts\check_docs.ps1
.\scripts\release_tag.ps1 -Version (Get-Content VERSION -Raw).Trim() -Kind patch -Message "dry-run" -DryRun
```

正式打 tag（小里程碑用 `patch`，大里程碑用 `minor`）：

```powershell
# 1) 更新 VERSION + CHANGELOG + ROADMAP 验收勾选并 commit
# 2) 再执行：
.\scripts\release_tag.ps1 -Version 0.0.3 -Kind patch -Message "M0.3: CI and docs checks"
```

详见 [`docs/versioning.md`](docs/versioning.md)。

## 许可

待定。合并上游代码前须核对各仓许可证（多为 Apache-2.0 / MIT）。
