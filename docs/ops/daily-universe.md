# 日用宇宙配置

> Phase E / M39 · ADR [0040](../architecture/0040-daily-universe-readable-reasons.md)

## 分层

| Tier | 用途 | 建议规模上限（软） |
|------|------|-------------------|
| `core` | 核心持仓/必看 | ≤ 50 |
| `watch` | 日用推荐默认 | ≤ 200 |
| `full` | 扩展扫描 | ≤ 800 |

空宇宙 **fail-closed**（`UniverseEmptyError`）。

## 样例

- CI / 离线小样：`packages/research/.../fixtures/universe_cn_sample.json`
- 日用分层样例：`packages/research/.../fixtures/universe_cn_daily.json`

```json
{
  "core": ["600519", "000001"],
  "watch": ["600519", "000001", "000858"],
  "full": ["600519", "000001", "000858", "300750"]
}
```

扁平 `{"symbols":[...]}` 仍支持（三层相同）。

## 东财限流

live 刷新经 `em_get` 时建议 `EM_MIN_INTERVAL>=1.0`（批量 1.5–2.0）。
**默认路径仍是 replay**；CI 零公网。

```powershell
python -c "from stock_platform_research import universe_size_guidance; print(universe_size_guidance('watch'))"
```
