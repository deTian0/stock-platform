# v1.0 发版检查清单

发版前按序执行（PowerShell，仓库根目录）。

## 1. 工作区

- [ ] `git status` 干净（或仅含本发版提交）
- [ ] 当前分支 `main`
- [ ] `VERSION` 与拟打 tag 一致（无 `v` 前缀）

## 2. 文档

```powershell
.\scripts\check_docs.ps1
```

- [ ] `CHANGELOG.md` 含 `[X.Y.Z]` 节
- [ ] `docs/ROADMAP.md` 对应里程碑勾选
- [ ] `docs/upstream-archive.md` 仍与现实一致（M7+）

## 3. 版本对齐

```powershell
.\scripts\check_versions.ps1
```

- [ ] 根 `VERSION` = 各包 `pyproject.toml` / `__version__`

## 4. 测试

```powershell
python -m pip install -e ".\packages\providers[dev]"
python -m pip install -e ".\packages\research[dev]"
python -m pip install -e ".\packages\agents[dev]"
python -m pip install -e ".\packages\execution[dev]"
python -m pip install -e ".\apps\workbench[dev]"
python -m pytest packages apps -q
```

- [ ] 0 failed

## 5. Tag

```powershell
.\scripts\release_tag.ps1 -Version (Get-Content VERSION -Raw).Trim() -Kind major -Message "..." -DryRun
.\scripts\release_tag.ps1 -Version (Get-Content VERSION -Raw).Trim() -Kind major -Message "..."
```

- [ ] annotated tag `vX.Y.Z` 存在
- [ ] （可选）`git push origin main --follow-tags`
