# 契约：能力矩阵（草稿）

> 状态：Draft（M0.2 定稿）  
> 运行时目标：能力矩阵是路由 **唯一权威**（对齐 tick-stock-panel `CAPABILITY_REGISTRY`）。

## 七项能力

| Capability | 数据集 | 说明 |
|------------|--------|------|
| `daily` | daily | 日线 |
| `adj_factor` | adj_factor | 复权 |
| `realtime` | realtime | 快照 |
| `minute` | minute | 分钟 |
| `depth5` | depth5 | 五档 |
| `financial` | financial | 财务 |
| `full_minute` | full_minute | 全历史分钟 |

## 路由规则

1. 每一项能力独立选择 Provider，禁止 `same_as_daily` 隐式跟随。
2. 前端/API 门控看 `usable`，不看某供应商套餐文案。
3. 缺能力：**fail-closed**（明确错误/降级提示），禁止静默换错源。
4. 通用路径禁止硬编码单一品牌源；专属能力须在矩阵标注 `exclusive`。

## Provider 槽位（规划）

| Provider ID | 来源 | 计划阶段 |
|-------------|------|----------|
| `astock_http` | a-stock-data 配方库化 | M1 |
| `tickflow` | TSP 现有（可选默认） | M2 |
| `global_http` | global-stock-data | M5 |
| `yaml_custom` | 用户 YAML | M2 |

## TBD

- [ ] `usable` 探测接口形状（同步函数 vs HTTP）
- [ ] 指数「核心合约」是否移出矩阵（TSP 特例）
