# AI 开发入口

修改本仓库前先读：

1. [`CONTRIBUTING.md`](CONTRIBUTING.md)
2. [`docs/ROADMAP.md`](docs/ROADMAP.md)
3. [`docs/versioning.md`](docs/versioning.md)
4. [`docs/architecture/0001-target-architecture.md`](docs/architecture/0001-target-architecture.md)
5. [`docs/contracts/`](docs/contracts/)（M0.2 已 Accepted；改口径先写 ADR）

## 硬性规则

- 当前处于 **v0.1.x（M0 已完成）**：可开始 M1 providers；不虚构尚未实现的行情 API。
- 上游仓（tick-stock-panel、a-stock-data 等）仅作参考；迁入须走里程碑验收，禁止整目录复制。
- 版本号单一事实源：根目录 `VERSION`。打 tag 用 `scripts/release_tag.ps1`。
- 不提交密钥、行情缓存、SQLite 大数据。
- 保持改动最小；不处理无关问题。

## 完成标准

以 ROADMAP 中对应里程碑的验收清单为准；打 tag 前 `CHANGELOG.md` 必须有对应条目。
