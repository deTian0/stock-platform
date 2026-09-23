# market-report-dashboard 合并里程碑（MR 线）

> **状态**：done（MR-1…MR-5；**M-E4 实盘仍门禁 / 刻意不做**）（**v3.12.5**：MR-3 / MR-5；文档日：2026-09-23）  
> **版本基线**：约 **v3.12.4** → **v3.12.5**（brief 对照 + providers 部分预填）  
> **编号**：`MR-1`–`MR-5`（Market Report 线；**不改写** M0–M47 / U1–U8 / 能力域 M-* 已 done 叙事）  
> **源仓**：`../market-report-dashboard`（Skill；无 pip 运行时）  
> **扫描报告**：[../upstream/market-report-dashboard-capability-report.md](../upstream/market-report-dashboard-capability-report.md)  
> **关联**：[capability-domain-merge-roadmap.md](capability-domain-merge-roadmap.md) · [skills-governance.md](../ops/skills-governance.md) · [upstream-archive.md](../upstream-archive.md) · ADR [0053](../architecture/0053-intel-report-brief-crosswalk.md)

---

## 1. 总则

| 原则 | 含义 |
|------|------|
| **吸收什么** | HTML 看板**视觉/信息架构**、三类报告内容清单与质量标准、Skill 工作流说明 |
| **不吸收什么** | WebSearch 当产品数据源、整仓 merge、定时 automation 当平台调度、可编程交易策略（源仓本无） |
| **运行时权威** | 行情 / 基本面 / brief **仅** `packages/providers` + 能力矩阵；缺能力 fail-closed |
| **引用形态** | Skills **软链 / 只读**；模板副本进 `docs/upstream/market-report-templates/` 与 Workbench static |
| **与 brief** | 盘前语义可对照；**不得**用情报 HTML 冒充 lvrev 推荐或反向；**不得** WebSearch 写入 brief SQLite |

---

## 2. Now / Next / Later

| 档 | 内容 | 一句话 |
|----|------|--------|
| **Now（v3.12.4）** | MR-1 模板入库 · MR-2 Workbench 入口 · MR-4 Skill 软链文档 | 配方可见、入口诚实、无第二数据链 |
| **Now（v3.12.5）** | MR-3 brief 对照 · MR-5 providers 部分预填 | ADR + 互跳 + 预填预览；缺能力中文列出 |
| **Later / 门禁** | M-E4 实盘等 | 仍刻意不做 |

---

## 3. 里程碑明细

### MR-1 — 三类 HTML 模板只读入库 · **done（v3.12.4）** · 量级 **S**

**验收标准**

- [x] 复制源仓 `templates/*.html` → [`docs/upstream/market-report-templates/`](../upstream/market-report-templates/)  
- [x] 同目录 `README.md`：来源、三类说明、禁止项、与 brief 关系  
- [x] Workbench `static/report-templates/` 同步副本（便于浏览器预览布局）  
- [x] 标注配方来源；**未**写入任何 `pyproject` 对源仓的 path/pip 依赖  

---

### MR-2 — Workbench「情报报告」入口 · **done（v3.12.4）** · 量级 **S**

**验收标准**

- [x] `#intel-report` 面板：三类模板说明 + 源路径 + Skill 用法摘要  
- [x] 链到静态模板预览；文案写明「只读配方 / 非 Skill 运行时 / 数据走 providers」  
- [x] 导航短链；静态 UI 单测断言 `id="intel-report"` 等  
- [x] **未**新增 WebSearch / 平行 HTTP 抓取客户端  

---

### MR-3 — 与 brief 盘前联动 · **done（v3.12.5）** · 量级 **M**

**验收标准**

- [x] ADR：[0053-intel-report-brief-crosswalk.md](../architecture/0053-intel-report-brief-crosswalk.md) — 情报看板字段 ↔ brief / 推荐卡片**对照关系**（非替换）  
- [x] Workbench「情报报告」与「今日推荐/向导」互相跳转 + asof/宇宙对照条（`GET /api/research/intel-report/crosswalk`）  
- [x] 数据填充经能力矩阵 + providers；缺能力 fail-closed  
- [x] **不得**把 Skill WebSearch 结果写入 brief SQLite 冒充截面事实（预填 `writesBriefSqlite=false`）  

---

### MR-4 — Skills 软链 / 文档挂接 · **done（v3.12.4）** · 量级 **S**

**验收标准**

- [x] [`skills-governance.md`](../ops/skills-governance.md) 适用仓表增加 `market-report-dashboard`  
- [x] [`upstream/README.md`](../upstream/README.md)、能力盘点、AGENTS / docs README 短链  
- [x] 本里程碑文件入库；`plans/README` + `check_docs` 路径列表同步  

---

### MR-5 — providers 驱动情报看板（产品侧） · **done（v3.12.5）** · 量级 **L**（本轮为部分预填）

**验收标准**

- [x] 可填字段映射：日历、已存 brief picks、可选 `concept_blocks`、ops health；指数/情绪等进 `missing` 中文说明  
- [x] `GET /api/research/intel-report/prefill` + Workbench「用平台数据预填预览」；无公网 WebSearch 依赖  
- [x] 回归测 + 中文空态；仍非投资建议；**未** `import` Skill 运行时  
- [x] 无能力不静默假数据填满（保留 `{{占位符}}`）  

---

## 4. 总览表

| ID | 名称 | 档 | 状态 |
|----|------|----|------|
| MR-1 | 模板只读入库 | Now | **done（v3.12.4）** |
| MR-2 | Workbench 情报报告入口 | Now | **done（v3.12.4）** |
| MR-3 | 与 brief 盘前联动 | Next→Now | **done（v3.12.5）** |
| MR-4 | Skills / 文档挂接 | Now | **done（v3.12.4）** |
| MR-5 | providers 填模板产品看板 | Later→Now | **done（v3.12.5，部分预填）** |

---

## 5. 刻意不做（本阶段）

- 整仓 merge / `pip install` Skill  
- WebSearch 第二行情主链  
- 源仓设想的外部 `automation-task-manager` 当平台调度权威  
- 用情报 HTML 替换 lvrev 今日推荐  
- 实盘 / SPA（仍属能力域 / U 线 Later；**M-E4 门禁**）  
- 全市场情绪/指数看板完整填满（能力未齐；诚实 `missing`）

---

## 6. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-09-23 | 初版：MR-1/2/4 随 v3.12.4 落地；MR-3/5 标未做 |
| 2026-09-23 | v3.12.5：MR-3/MR-5 done（ADR 0053 + crosswalk/prefill API + UI） |
