# 贡献指南

## 原则

1. **先契约后搬家**：数据集、能力矩阵、市场策略未写清前，不迁生产抓取代码。
2. **一条数据主链**：禁止平行第二套东财/腾讯/通达信实现；东财只走 `em_get`。
3. **口径不混用**：涨跌幅小数/百分数、复权/原始价、交易日/自然日、CN 手 vs US/HK 股。
4. **小步提交**：小里程碑 patch tag；大里程碑 minor；**破坏契约自 1.0 起必须 major**。
5. **不覆盖无关改动**：PR 只做一件事。
6. **上游只读**：参考 [`docs/upstream-archive.md`](docs/upstream-archive.md)；禁止整仓拷贝。Skill / 文档仓软链与禁止 pip 见 [`docs/ops/skills-governance.md`](docs/ops/skills-governance.md)。

## 开发流程

1. 从 `main` 拉特性分支：`feat/...`、`fix/...`、`docs/...`、`chore/...`
2. 改代码 / 文档 → 更新 `CHANGELOG.md` `[Unreleased]`
3. 合并前自检：

```powershell
.\scripts\check_docs.ps1
.\scripts\check_versions.ps1
python -m pytest packages apps -q
```

4. 发版按 [`docs/versioning.md`](docs/versioning.md) 与 [`docs/release-checklist.md`](docs/release-checklist.md)

## 目录约定

| 路径 | 用途 |
|------|------|
| `docs/contracts/` | 对外契约；破坏性变更必须记 ADR |
| `docs/architecture/` | ADR，编号递增 |
| `docs/upstream-archive.md` | 上游归档权威清单 |
| `packages/` | 可安装库 |
| `apps/` | 可运行应用 |
| `scripts/` | 工程脚本 |

## Agent 协作

见 [`AGENTS.md`](AGENTS.md)。改版本号时同步：`VERSION`、各包 `pyproject.toml`、对应 `__init__.__version__`。
