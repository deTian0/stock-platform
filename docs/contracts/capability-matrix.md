# 契约：能力矩阵

> 状态：**Accepted（M0.2）** · 语义对齐 tick-stock-panel `CAPABILITY_REGISTRY`  
> 运行时：能力矩阵是路由 **唯一权威**；UI 不硬编码能力清单。

## 能力清单（顺序即设置页/文档展示序）

| id | 中文 | 数据集 | 说明 | TSP 默认源（参考） | TickFlow 档位门槛（参考） |
|----|------|--------|------|-------------------|---------------------------|
| `daily` | 日K | daily | 历史 K 与实时覆写 | tickflow | none（免费通道可有日K） |
| `adj_factor` | 除权因子 | adj_factor | 前复权计算基准 | tickflow | starter |
| `realtime` | 实时行情 | realtime | 全市场快照 | tickflow | starter |
| `minute` | 分钟K | minute | 分时与分钟回测 | tickflow | pro |
| `depth5` | 五档盘口 | depth5 | 封单/深度 | tickflow | pro |
| `financial` | 财务数据 | financial | 指标与三表 | tickflow | expert |
| `full_minute` | 全量分钟 | full_minute | 盘中全市场当日落盘 | tickflow | expert |
| `fund_flow` | 日级资金流 | fund_flow | 个股主力/大小单日级净流入（**元**） | —（平台扩展，ADR 0020） | — |
| `lhb` | 龙虎榜 | lhb | 个股上榜记录 + 买卖席位 TOP5 + 机构动向（**元**） | —（平台扩展，ADR 0021） | — |

前七项对齐 TSP `CAPABILITY_REGISTRY`；`fund_flow` / `lhb` 为本仓平台扩展，不绑定 TickFlow 套餐文案。

本仓 **不绑定** TickFlow 套餐文案；上表档位仅作迁入 TSP 时的对照。新 Provider（如 `astock_http`）用自身 `usable` 探测，不继承套餐词。

## 路由规则（与 TSP 一致）

1. **每能力独立选源**：禁止 `same_as_daily` 隐式跟随（复权与日 K 一致性靠校验告警，不做路由耦合）。
2. **candidates**：只含「当前确实可提供该能力」的源；未就绪源进 `pending` 并带原因。
3. **usable**：生效源是否真能提供该能力。页面门控只看 `usable`，不看供应商营销档位。
4. **fail-closed**：缺能力 → 明确错误/引导配置；禁止静默换错源。
5. **通用路径禁止硬编码品牌**；专属能力在矩阵标注 `exclusive: true`。
6. **指数特例（产品级）**：核心宽基指数可作为固定合约，**不强制**进入用户可改的路由矩阵；自定义源可另实现 `get_realtime_indices`。细节在 M2 工作台 ADR 敲定。

## `usable` 探测形状（M0.2 冻结文字契约）

运行时（M1/M2）实现须满足：

```text
CapabilityStatus {
  id: string           # 七项之一
  preferred: string    # 用户选择的 provider id
  effective: string | null
  usable: bool
  candidates: [{ name, display, kind, available, status, note? }]
  pending:    [{ name, display, reason }]
}
```

- 同步库：`build_capability_matrix(preferences) -> list[CapabilityStatus]`
- HTTP（工作台）：`GET /api/settings/capability-matrix` 返回同上（字段名稳定）

## Provider 槽位（规划）

| Provider ID | 来源 | 阶段 | 预期 datasets |
|-------------|------|------|----------------|
| `replay` | fixtures | **M1.2 已实现**；**M15 fund_flow**；**M16 lhb** | daily, realtime, fund_flow, lhb（CN） |
| `astock_http` | a-stock-data 配方 | **M8.1 已实现**；**M15 fund_flow**；**M16 lhb**（em_get） | daily, realtime, fund_flow, lhb |
| `global_replay` | fixtures | **M5.3 已实现** | daily, realtime（US/HK） |
| `global_http` | Yahoo + 新浪（Skill 配方） | **M9.1 已实现** | daily, realtime（US/HK） |
| `tickflow` | TSP 内置 | M2 | 按档位 |
| `yaml_custom` | 用户 YAML | M2 | 声明集 |

运行时：`stock_platform_providers.build_capability_matrix` / `register_builtin_providers`。

## 插件失败隔离

加载失败不得拖垮未启用插件的主流程；失败源不得出现在该能力的 `candidates` 正向列表（可进 `pending`）。

## 已关闭的原 TBD

| 原问题 | 决定 |
|--------|------|
| `usable` 形状 | 上文 `CapabilityStatus`；双入口（库函数 + HTTP）字段一致 |
| 指数是否出矩阵 | 核心指数可为产品固定合约；其余走 `asset_type=index` + 能力路由 |

## 参考

- tick-stock-panel：`backend/app/data_providers/capabilities.py`
- tick-stock-panel：`CONTRIBUTING.md` 数据源插件化章节
