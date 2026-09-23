# Skills 软链与非运行时治理

> **SSOT**：本文说明 Skill / 文档仓如何被本仓引用。  
> **相关**：[upstream-archive.md](../upstream-archive.md) · [capability-domain-merge-roadmap.md](../plans/capability-domain-merge-roadmap.md) M-S1 · [workspace-projects-capability-inventory.md](../plans/workspace-projects-capability-inventory.md)

## 原则

1. **运行时唯一权威**：`packages/providers` + 能力矩阵。Skill 仓**不是**产品依赖。  
2. **软链或只读引用**：供 Cursor / Claude Code 助手激活文档与内嵌示例；不假装「已接入 Skill 运行时」。  
3. **fail-closed**：缺矩阵能力、缺 token → 显式失败；禁止用 Skill 脚本平行抓取冒充 live。

## 适用仓

| 仓 | 形态 | 典型本地路径 |
|----|------|----------------|
| `finance-quant-skills` | Agent Skills 文档 + 示例脚本 | `../finance-quant-skills` |
| `a-stock-data` | 自包含 `SKILL.md` | `../a-stock-data` |
| `global-stock-data` | 自包含 `SKILL.md` | `../global-stock-data` |
| `market-report-dashboard` | 情报 HTML 看板 Skill（三类模板） | `../market-report-dashboard` |

## 如何软链 / 只读引用（本机）

任选其一即可；**不要**写入产品 `pyproject` 依赖。

### A. Cursor / Claude Skills 目录软链（推荐）

PowerShell 示例（管理员或开发者模式允许符号链接时）：

```powershell
# Claude Code skills（按本机实际 skills 根目录调整）
New-Item -ItemType SymbolicLink `
  -Path "$env:USERPROFILE\.claude\skills\a-stock-data" `
  -Target "D:\workspace\git\a-stock-data"

New-Item -ItemType SymbolicLink `
  -Path "$env:USERPROFILE\.claude\skills\global-stock-data" `
  -Target "D:\workspace\git\global-stock-data"

New-Item -ItemType SymbolicLink `
  -Path "$env:USERPROFILE\.claude\skills\market-report-dashboard" `
  -Target "D:\workspace\git\market-report-dashboard"

# finance-quant-skills：按该仓 README / marketplace 指引链到 skills 子目录
# 或使用 npx skills add <repo> —— 仍属助手侧，非 stock-platform 运行时
```

无符号链接权限时：复制 `SKILL.md` 到 skills 目录亦可，但易漂移；优先软链。

平台侧只读配方副本（非运行时）：[`docs/upstream/market-report-templates/`](../upstream/market-report-templates/)；Workbench 入口见 `#intel-report`。合并里程碑：[`plans/market-report-dashboard-merge-milestones.md`](../plans/market-report-dashboard-merge-milestones.md)。

### B. 工作区只读打开

多根工作区已包含上述仓时，Agent 直接读兄弟仓文档即可；**禁止** `pip install -e` 进本仓 venv 当库用。

### C. 配方吸收流程（与运行时的关系）

```
Skill / 盘点缺口 →（M-D1）对照表 → 契约/ADR → 扩能力矩阵 → packages/providers 实现 → 测试
```

可选：平台改完后**回馈** Skill 文档字段说明（双写）；回馈不是把 Skill 变成依赖。

## 禁止项（写死）

| 禁止 | 说明 |
|------|------|
| `pip install` / path 依赖写入产品 `pyproject.toml` | finance-quant-skills、a-stock-data、global-stock-data、market-report-dashboard 均不得进入发行依赖 |
| 平行抓取主链 | 禁止在 agents/research/workbench 内再 exec Skill 内嵌 HTTP 当第二数据源 |
| 东财裸 `requests.get` | 一律 `em_get` |
| UI/文档宣称「已接入某某 Skill 运行时」 | 仅可写「配方来源 / 只读参考」 |
| 提交 token / skills 会话缓存 | 与全局密钥红线一致 |

## 与能力矩阵的关系

- Skill 端点清单 ≠ 矩阵已声明能力。  
- 缺口对照见 [`plans/m-d1-capability-gap-matrix.md`](../plans/m-d1-capability-gap-matrix.md)。  
- 未进矩阵的端点：产品路径必须 fail-closed，不得「临时调一下 Skill 函数」。

## 检查清单（PR 自检）

- [ ] 未新增对 Skill 仓的 pip/path 依赖  
- [ ] 未新增平行 HTTP 客户端打东财/腾讯等  
- [ ] 新数据能力先改矩阵再接线  
- [ ] 文档未声称 Skill 已是运行时模块  
