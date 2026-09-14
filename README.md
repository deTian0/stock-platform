# stock-platform

可发布的量化**研究与纸面决策**平台：统一 Vendor、选股/PIT、工作台 API、投研 Agent 槽位、纸面执行安全模型，收敛在单一产品仓。

> 当前版本见 [`VERSION`](VERSION)。路线图 [`docs/ROADMAP.md`](docs/ROADMAP.md)；发版 [`docs/release-checklist.md`](docs/release-checklist.md)；上游归档 [`docs/upstream-archive.md`](docs/upstream-archive.md)。

## v1.0 交付面

| 组件 | 路径 | 能力 |
|------|------|------|
| Providers | `packages/providers` | CN/US/HK 归一化、replay、`em_get`、能力矩阵、`MarketStrategy` |
| Research | `packages/research` | lvrev / 闸门 / PIT / `stock-platform-score` |
| Agents | `packages/agents` | 研报/复盘插件（仅经 providers） |
| Execution | `packages/execution` | 纸面 SIMULATE、事务态、草稿≠激活 |
| Workbench | `apps/workbench` | FastAPI：行情 / 研报 / 纸面 API |

**默认运行时**：fixtures replay（离线可测）。`astock_http` / `global_http` live 仍为 pending。  
**明确不做（v1.0）**：实盘券商、第二套行情主链、把 Skill 仓当 pip 依赖。

## 快速开始

```powershell
cd D:\workspace\git\stock-platform
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\research[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
python -m pip install -e ".\apps\workbench[dev]"
python -m pytest packages apps -q
python -m stock_platform_workbench
# → http://127.0.0.1:3018/health
```

自检：

```powershell
.\scripts\check_docs.ps1
.\scripts\check_versions.ps1
```

## 仓库布局

```text
stock-platform/
├── apps/workbench/
├── packages/{providers,research,agents,execution}/
├── docs/
│   ├── ROADMAP.md
│   ├── upstream-archive.md
│   ├── release-checklist.md
│   ├── versioning.md
│   ├── architecture/          # ADR 0001–0012
│   └── contracts/
└── scripts/{check_docs,check_versions,release_tag}.ps1
```

## 里程碑摘要

| Tag | 里程碑 |
|-----|--------|
| v0.1.0–v0.7.0 | M0–M6（架子→数据→工作台→研究→Agent→美港→纸面执行） |
| **v1.0.0** | **M7 产品收敛 / 上游归档** |

细节见 [`docs/ROADMAP.md`](docs/ROADMAP.md)。

## 上游参考（只读）

见 [`docs/upstream-archive.md`](docs/upstream-archive.md)。新功能只进本仓。

## 许可

待定。合并上游代码前须核对各仓许可证（多为 Apache-2.0 / MIT）。
