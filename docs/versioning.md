# 版本与 Tag 工程规范

## 单一事实源

| 文件 | 作用 |
|------|------|
| `VERSION` | 当前发布版本，**无** `v` 前缀，如 `0.0.1` |
| `CHANGELOG.md` | 人类可读变更 |
| Git annotated tag | `v` + `VERSION`，如 `v0.0.1` |

发版前三者必须一致。禁止只打 tag 不改 `VERSION`。

## SemVer 映射里程碑

本仓采用 [Semantic Versioning 2.0](https://semver.org/lang/zh-CN/)：

| 变更类型 | 版本位 | 对应里程碑 | 示例 |
|----------|--------|------------|------|
| 大里程碑完成（M0、M1…） | **MINOR** +1，PATCH 归零 | 大 tag | `0.0.3` → `0.1.0` |
| 小里程碑 / 修文档修脚本 | **PATCH** +1 | 小 tag | `0.0.1` → `0.0.2` |
| 对外破坏性契约或正式产品就绪 | **MAJOR** +1 | 仅 M7 或明确破坏 | `0.7.0` → `1.0.0` |
| 预发（可选） | 预发布标签 | RC | `v0.2.0-rc.1` |

**0.x 阶段**：MINOR 表示大里程碑，不承诺稳定 API。  
**1.0.0 起**：破坏契约必须 MAJOR，并写迁移说明。

## Tag 命名

- 正式：`vMAJOR.MINOR.PATCH`（annotated）
- 预发：`vMAJOR.MINOR.PATCH-rc.N`
- 禁止：轻量 tag、随意名（`release`、`final`）、移动已推送 tag

## 发版检查清单

1. `main` 干净，验收项已勾选（`docs/ROADMAP.md`）
2. `CHANGELOG.md` 将 `[Unreleased]` 收成新版本节，日期为当天
3. 写入 `VERSION`（无 `v`）
4. 提交：`chore(release): vX.Y.Z`
5. 执行：

```powershell
.\scripts\release_tag.ps1 -Version X.Y.Z -Kind patch|minor|major -Message "简短说明"
```

6. 确认：`git tag -l vX.Y.Z` 与 `git show vX.Y.Z`
7. 需要远程时：`git push origin main --follow-tags`

## 脚本行为

`scripts/release_tag.ps1`：

- 校验 `VERSION` 文件与 `-Version` 参数一致
- 拒绝覆盖已存在 tag
- 创建 **annotated** tag：`vX.Y.Z`
- 支持 `-DryRun` 只打印将执行的命令

## 分支策略（起步）

- 默认分支：`main`
- 特性分支短生命周期；大里程碑可用 `release/0.2` 短分支收尾（可选）
- 不在 tag 上直接开发

## 与上游仓版本的关系

本仓版本 **独立**，不继承 tick-stock-panel `0.2.3` 或 TradingAgents `0.5.17`。  
CHANGELOG / ROADMAP 中可注明「吸收自 xxx@tag」，但不共用版本号。
