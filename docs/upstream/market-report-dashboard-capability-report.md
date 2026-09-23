# market-report-dashboard 能力扫描报告

> **状态**：只读上游扫描归档（非正式运行时依赖）  
> **扫描日期**：2026-09-23  
> **源路径**：`D:\workspace\git\market-report-dashboard`  
> **形态**：Cursor / Claude **Agent Skill** 文档包（非 pip 包、非 HTTP 服务）  
> **平台权威**：本文件为 stock-platform 侧 SSOT；源仓可自持 `CAPABILITY-REPORT.md` 副本  
> **禁止**：把本 Skill 当第二数据主链；禁止 `pip install` / 平行 WebSearch 冒充 providers live

---

## 1. 项目定位

**一句话**：面向 AI 助手的「股市情报 HTML 看板」生成 Skill——按标准流程产出 A 股盘前 / A 股盘中 / 美股盘前三类深色金融终端风格的**单文件 HTML**，强制带可证伪的机会与风险研判。

**包 / README 说明**：

- 无独立 `README.md`、无 `pyproject.toml` / `package.json`。
- 权威入口为根目录 `SKILL.md`（frontmatter：`name: market-report-dashboard`，`version: 1.0.0`，`author: CodeBuddy AI`，`created/updated: 2026-09-17`）。
- `description` 摘要：基于实时搜索的真实数据，输出含盘前机会与风险提示的可视化行情看板；关键词含 A 股盘前、盘中速报、美股盘前、行情看板等。
- 配套设想：由外部 `automation-task-manager` 按交易日定时触发（08:00 盘前、盘中多点、16:00 美股盘前）；本仓内**未见**该自动化实现代码。

---

## 2. 目录与技术栈

### 2.1 目录树（全量，共 7 个文件）

```
market-report-dashboard/
├── SKILL.md                          # Skill 入口与工作流
├── references/
│   ├── dashboard-spec.md             # 视觉/技术规范
│   ├── research-guide.md             # WebSearch 关键词与信源
│   └── report-specs.md               # 三类报告数据清单与质量标准
└── templates/
    ├── a-share-preopen.html          # A股盘前模板
    ├── a-share-intraday.html         # A股盘中模板
    └── us-preopen.html               # 美股盘前模板
```

- **无** `strategies/`、`reports/`、`src/`、`tests/`、`scripts/`、`.git`（扫描时本地目录未初始化 git）。
- **无** 可执行 Python/JS 应用代码。

### 2.2 技术栈

| 维度 | 实际 |
|------|------|
| 语言 | Markdown（规范）+ HTML/CSS（模板）；无应用语言运行时 |
| 框架 | 无；Agent Skills 形态 |
| 入口 | `SKILL.md`（助手按描述触发） |
| 依赖 | **无**第三方包声明；运行时依赖助手侧 **WebSearch** + 文件读写 |
| 配置 | 无独立 config；涨跌色、命名、时段规则写在 Skill/规范内 |
| 输出物 | 单文件 `.html`（CSS 全内联，禁止 CDN/外链） |

---

## 3. 功能模块（按目录分组）

### 3.1 `SKILL.md` — 编排与红线

- 触发条件与三类报告路由表。
- 标准工作流：交易日判断 → WebSearch 采集 → 分析加工 → 填模板 → `present_files` 交付 + 摘要 + 免责声明。
- 硬性规范：数据真实、零外部依赖 HTML、A/美股涨色区分、必须交付文件、禁止空模板。
- 扩展指引：新报告类型需同步模板 + `report-specs` + 路由表。

### 3.2 `references/report-specs.md` — 内容契约

- **A股盘前**：昨日指数/板块/涨停、隔夜美股与中概、盘后异动、资讯 → 核心观点 + 机会 2~4 + 风险 2~3 + 板块持续性（延续/分化/退潮）。
- **A股盘中**：实时指数/量能/板块/情绪/资讯 → 盘面快照 + 资讯影响 + 机会 + 节奏建议 + 风险；强调相对上次推送的变化。
- **美股盘前**：经济日历（须预期值）、联储、财报、期货、资讯、A 股收盘参考 → 展望 + 机会 + 风险 + 北京时间节点。

### 3.3 `references/research-guide.md` — 采集配方

- WebSearch 句式模板与按类型的 5~8 次搜索清单。
- 推荐信源：东财/同花顺/新浪、财联社/华尔街见闻、金十/汇通、官方政策站等。
- 校验：交叉验证、时点对齐、节假日陷阱、冬夏令时、搜不到写「暂未获取」。

### 3.4 `references/dashboard-spec.md` — 视觉契约

- 深色金融终端 tokens；A 股红涨绿跌 / 美股绿涨红跌。
- 组件：hero、区块、指数卡、机会/风险卡、表格、footer。
- 交付前自检清单（占位符、外链、涨色、数字一致性等）。

### 3.5 `templates/` — 三类 HTML 模板

见第 5 节；结构即「可渲染报告骨架 + `{{占位符}}`」。

---

## 4. 交易策略

**未发现。**

- 仓内无 `strategy/`、无量化信号、无回测、无仓位/调仓规则、无参数 YAML。
- 「机会 / 风险 / 持续性研判」是**叙事研判模板**（结论 + 原因 + 失效信号），由助手基于搜索结果填写，**不是**可编程交易策略。
- 与 stock-platform 的 lvrev / PIT / paper 执行链无代码级耦合。

---

## 5. 报告模板

### 5.1 格式

- **格式**：单文件 HTML5 + 内联 `<style>`；可选 `@media print`。
- **占位符**：`{{...}}` 自然语言字段名（非 Jinja/Mustache 引擎；由助手手工替换）。
- **涨色**：A 股模板 `--up:#ff4d4f` / `--down:#00b578`；美股模板覆写为绿涨红跌。

### 5.2 三类模板字段摘要

| 模板文件 | 报告类型 | 主要区块 |
|----------|----------|----------|
| `templates/a-share-preopen.html` | A股盘前 | hero 观点；昨日三大指数；隔夜美股三大指数；强势板块表；涨停/连板 chips；科技巨头/中概/盘后；资讯；机会卡；板块持续性；风险卡；footer |
| `templates/a-share-intraday.html` | A股盘中 | hero + 情绪条；实时三大指数与分时特征；量能 chips + volbar；领涨/领跌；资金进出；涨跌家数/炸板；资讯影响；机会；节奏建议；风险 |
| `templates/us-preopen.html` | 美股盘前 | hero；盘前期货；盘前异动个股；经济日历表；联储；财报表；资讯；机会；风险；时间节点 chips；当日 A 股收盘参考 |

机会卡统一结构：`结论` / `原因` / `失效信号`；风险卡：`原因` / `影响`。

### 5.3 生成链路

```
用户话术或定时任务
  → Skill 路由选模板
  → Step 0 交易日/时段判断（休市则不生成）
  → Step 1 WebSearch（4~8 次，见 research-guide）
  → Step 2 分析（观点 + 机会 + 风险 + 持续性/节奏）
  → Step 3 复制模板 → 替换 {{占位符}} → 增删卡片
  → Step 4 present_files 推送 HTML + 对话摘要 + 免责声明
```

### 5.4 输出位置与命名

| 类型 | 文件名规范 | 示例 |
|------|------------|------|
| A股盘前 | `A股盘前情报日报_MMDD.html` | `A股盘前情报日报_0917.html` |
| A股盘中 | `A股盘中速报_MMDD_HHMM.html` | `A股盘中速报_0917_1030.html` |
| 美股盘前 | `美股盘前情报日报_MMDD.html` | `美股盘前情报日报_0917.html` |

- Skill 写明复制到 `/workspace/` 再推送；**仓内无**示例产出物或 `reports/` 归档目录。
- 本地预览可用任意静态打开或简单 HTTP 服务（规范建议「python 起服务自测」），无专用 CLI。

---

## 6. 数据源 / API / 配置

### 6.1 数据源（文档约定，非代码客户端）

| 用途 | 约定来源 |
|------|----------|
| A/美股行情、板块、涨跌停 | 东方财富、同花顺、新浪财经等（经 WebSearch） |
| 快讯/政策 | 财联社、华尔街见闻、证券时报；政策以官网为准 |
| 经济/财报日历 | 金十、汇通、investing 中文站等 |
| 美股/中概 | 新浪美股、富途、雪球、TradingView 中文等 |

**无**仓内 HTTP client、`em_get`、SDK、MCP、数据库。

### 6.2 API

**未发现**可编程 API / OpenAPI / CLI。接口即 Skill 工作流与模板字段。

### 6.3 配置

- 无 `.env` / YAML。
- 行为参数固化在文档：限流式「搜索次数建议」、交易时段、冬夏令时开盘（夏 21:30 / 冬 22:30 北京时间）、涨色 tokens、定时触发表（依赖外部 automation，本仓未实现）。

---

## 7. 与 stock-platform / 兄弟仓关系

| 关系 | 结论 |
|------|------|
| 代码引用 | **无**。全仓无对 `stock-platform`、`a-stock-data`、`TradingAgents-astock` 等的 import / path / pip 依赖 |
| 平台侧既有文档 | 扫描前 `docs/upstream-archive.md` 与能力盘点**未收录**本仓（本报告为首次归档） |
| 能力对照 | 平台 `build_premarket_brief` / `stock-platform-brief` 是 **lvrev 截面打分 + 闸门 TopN**（结构化简报）；本 Skill 是 **新闻/盘面情报 HTML 看板**。同属「盘前」语义，**数据链与产物形态不同** |
| 与 a-stock-engine | 引擎有 HTML 简报历史；本仓是 Skill 模板，非引擎管线 |
| 与 finance-quant-skills / a-stock-data | 同属 Skill/文档形态；本仓**不内嵌 Python 取数**，取数靠助手 WebSearch |
| 治理建议 | 按 `docs/ops/skills-governance.md`：软链或只读参考；禁止平行抓取主链 |

---

## 8. 如何本地运行

文档**未提供**传统「安装依赖 → 启动服务」步骤。实际用法：

1. 将本目录作为 Cursor / Claude Skill 挂载（软链到 skills 目录，或工作区打开后由助手读 `SKILL.md`）。
2. 用自然语言触发：「生成今天的 A 股盘前报告」等。
3. 助手按工作流搜索并填充模板，产出命名规范的 HTML。
4. 预览：浏览器直接打开生成的 `.html`（离线可用）。

**不适用**：`pip install`、`npm start`、`uvicorn`、Docker。

---

## 9. 缺口与可合并价值（相对 stock-platform）

### 9.1 缺口（相对产品仓）

| 缺口 | 说明 |
|------|------|
| 无运行时 | 无 providers、无矩阵能力、无确定性复现 |
| 无结构化数据契约 | 占位符为自然语言，难做回归测试 |
| WebSearch 易漂移 | 与平台「一条数据主链 + em_get」冲突若直接并入运行时 |
| 无盘中/板块矩阵能力 | 平台 M29 等仍延期的全市场情绪/板块资金流，本 Skill 靠搜索补叙事，不能替代矩阵 |
| 无自动化实现 | 定时表仅文档；无 Task Scheduler / cron 脚本 |
| 与 brief 未打通 | 未消费 `build_premarket_brief` / Workbench API |

### 9.2 可合并价值评估

| 维度 | 价值 | 说明 |
|------|------|------|
| **HTML 看板视觉与信息架构** | **中** | 深色终端 tokens、机会/风险卡、A/美涨色分表，可作 Workbench「可读简报」UI 配方（非整页 SPA） |
| **报告内容清单 / 质量标准** | **中** | `report-specs` 的盘前映射链、情绪阶段、美股日历「必须有预期值」等，可反哺 agents 研报提示或 brief 叙事层（ADR 后再接） |
| **WebSearch 采集流程** | **低** | 不得作为产品数据源；仅助手侧 Skill |
| **交易策略 / 执行** | **低 / 无** | 无可迁代码 |
| **整仓并入运行时** | **低（禁止）** | 与 Skill 治理红线一致 |

**总评**：相对 stock-platform **中（文档/UI 配方） / 低（代码）**。建议：上游只读归档 + Skills 软链；若产品要「情报看板」，应另开里程碑，数据强制走 `packages/providers`，模板可借鉴本仓 HTML，禁止把 WebSearch 写进发行依赖。

---

## 10. 文件清单校验

| 路径 | 角色 |
|------|------|
| `SKILL.md` | 入口 |
| `references/dashboard-spec.md` | 视觉规范 |
| `references/research-guide.md` | 搜索指南 |
| `references/report-specs.md` | 内容规范 |
| `templates/a-share-preopen.html` | A股盘前模板 |
| `templates/a-share-intraday.html` | A股盘中模板 |
| `templates/us-preopen.html` | 美股盘前模板 |

扫描结论：**仓内能力仅以上 7 文件**；无隐藏策略实现或 API 客户端。
