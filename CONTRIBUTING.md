# 贡献指南

## 原则

1. **先契约后搬家**：数据集、能力矩阵、市场策略未写清前，不迁生产抓取代码。
2. **一条数据主链**：禁止平行第二套东财/腾讯/通达信实现。
3. **口径不混用**：涨跌幅小数/百分数、复权/原始价、交易日/自然日必须有单测护栏。
4. **小步提交**：完成小里程碑打 patch tag；完成大里程碑打 minor（或 major）tag。
5. **不覆盖无关改动**：PR 只做一件事。

## 开发流程

1. 从 `main` 拉特性分支：`feat/...`、`fix/...`、`docs/...`、`chore/...`
2. 改代码 / 文档 → 更新 `CHANGELOG.md` `[Unreleased]`
3. 合并前自检：文档链接有效、`VERSION` 与即将打的 tag 意图一致
4. 发版按 [`docs/versioning.md`](docs/versioning.md) 使用 `scripts/release_tag.ps1`

## 目录约定

| 路径 | 用途 |
|------|------|
| `docs/contracts/` | 对外契约；破坏性变更必须记 ADR |
| `docs/architecture/` | ADR，编号递增 |
| `packages/` | 可安装库（providers 等） |
| `apps/` | 可运行应用（workbench 等） |
| `scripts/` | 工程脚本，非业务逻辑 |

## Agent 协作

见 [`AGENTS.md`](AGENTS.md)。改版本号时同步：`VERSION`、`CHANGELOG.md`、相关 `pyproject.toml`（若有）。
