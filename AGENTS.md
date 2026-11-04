# AI 开发入口

修改本仓库前先读：

1. [`CONTRIBUTING.md`](CONTRIBUTING.md)
2. [`docs/STATUS.md`](docs/STATUS.md)（现行快照：版本、未完成项、下一刀）
3. [`docs/README.md`](docs/README.md)（文档分类索引；正文只在 `docs/`）
4. [`docs/ROADMAP.md`](docs/ROADMAP.md)（M0–M47 已全部 done，不要从旧焦点开工）
5. [`docs/plans/`](docs/plans/)（仍有效的计划；历史交接在 [`docs/archive/`](docs/archive/README.md)）
6. [`docs/versioning.md`](docs/versioning.md)
7. [`docs/upstream-archive.md`](docs/upstream-archive.md) · [`docs/upstream/`](docs/upstream/)（含 [`market-report-templates/`](docs/upstream/market-report-templates/)）
8. [`docs/architecture/0001-target-architecture.md`](docs/architecture/0001-target-architecture.md)
9. [`docs/architecture/0012-v1-product-boundary.md`](docs/architecture/0012-v1-product-boundary.md)
10. [`docs/contracts/`](docs/contracts/)（改口径先写 ADR）
11. [`docs/engineering/`](docs/engineering/)（OpenAPI / 测试 / CI）
12. [`docs/ops/skills-governance.md`](docs/ops/skills-governance.md)（Skill 软链；禁止 pip / 平行抓取）

## 硬性规则

- **产品仓**：`stock-platform` 是唯一运行时主链；上游仓只读参考。
- 改版本号时同步：根 `VERSION`、各包 `pyproject.toml`、对应 `__init__.__version__`（可用 `scripts/check_versions.ps1`）。
- 东财请求必须经 `em_get`；美港不得套用 A 股 T+1/涨跌停。
- 执行层默认 SIMULATE；禁止引入 live 券商开关。
- 不提交密钥、行情缓存、SQLite 大数据。
- 保持改动最小；不处理无关问题。
- **文档 SSOT**：正式正文在 `docs/`，现行状态只写 [`docs/STATUS.md`](docs/STATUS.md)。`.cursor/plans` 仅索引指针。历史交接在 `docs/archive/`，不要按其中的「下一块砖」开工。

## 完成标准

M0–M47 以 [`docs/ROADMAP.md`](docs/ROADMAP.md) 为准（已全部 done）。自有线以 [`docs/STATUS.md`](docs/STATUS.md) 与 [`docs/plans/trading-system-roadmap.md`](docs/plans/trading-system-roadmap.md) 为准。打 tag 前：`check_docs` + `check_versions` + pytest 全绿，且 `CHANGELOG` 有对应节。发版步骤见 [`docs/release-checklist.md`](docs/release-checklist.md)。
