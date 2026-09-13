# stock-platform

单一产品仓：把既有 A 股/全球数据、选股回测、工作台、投研 Agent、执行安全模型，逐步收敛成一个可发布的量化研究与决策平台。

> 当前版本见根目录 [`VERSION`](VERSION)。里程碑与 tag 路线见 [`docs/ROADMAP.md`](docs/ROADMAP.md)、[`docs/versioning.md`](docs/versioning.md)。

## 第一版范围（架子）

- 工程目录与 Git 管理
- 目标架构与数据契约草稿
- 里程碑 / SemVer tag 升级路线（文档 + 脚本）
- `packages/providers` 与 `apps/workbench` 占位（尚无可运行业务）

**明确不做（v0.0.x）**：行情抓取、选股、回测、UI、券商对接。

## 仓库布局

```text
stock-platform/
├── apps/
│   └── workbench/          # 未来工作台（吸收 tick-stock-panel）
├── packages/
│   └── providers/          # 未来统一 Vendor（吸收 a-stock-data / global）
├── docs/
│   ├── ROADMAP.md          # 大/小里程碑与验收
│   ├── versioning.md       # tag 与发版规则
│   ├── architecture/       # ADR
│   └── contracts/          # 数据集 / 能力矩阵 / 市场策略
├── scripts/
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
Get-Content docs\ROADMAP.md
```

打 tag（示例）：

```powershell
.\scripts\release_tag.ps1 -Version 0.0.2 -Kind patch -Message "docs: tighten contracts"
```

## 许可

待定。合并上游代码前须核对各仓许可证（多为 Apache-2.0 / MIT）。
