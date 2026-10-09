# WorkBuddy 运行时性能限制（本机实测）

- 检测日期：2026-10-09
- 检测方法：读取 `~/.workbuddy/settings.json`、`app/`、`workspace/`、`logs/sandbox/`、`security/`，解析程序本体 `D:\soft\agent\workbuddy\resources\app.asar.unpacked\cli\product.json`，并实测本机硬件与电源状态。
- 适用范围：本机（Windows / WorkBuddy SaaS 版）；跨项目通用。

## 结论

**WorkBuddy 不限制 CPU、内存、磁盘，也没有请求级限流（rate limit）。** 真正的硬约束只有 5 处，全部是「单次动作的边界」，不是「算力配额」。

| # | 限制项 | 实测值 | 来源 |
|---|---|---|---|
| 1 | 单请求步数上限 | **100 步** | `product.json → requestMaxStepLimit` |
| 2 | 命令执行超时 | 默认 **120 s**；PowerShell 上限 **600 s** | `product.json → prompts`（工具契约） |
| 3 | 上下文压缩阈值 | 输入 **60% 告警 / 70% 严重 / 90% 强制压缩** | `product.json → tokenUsageThresholds` |
| 4 | 沙箱程序黑名单 | **6 个程序**（见 §4） | `workspace/sessions/*/permission.json` |
| 5 | 会话缓存上限 | **3000 MB (3 GB)** | `workspace/sessions/gc_config.json` |

---

## 1. 单请求步数上限 = 100

`requestMaxStepLimit = 100`。一次用户请求内，agent 循环（API 往返）最多 100 步；超出后本轮强制结束。

**影响**：超长任务要拆成多轮，或改用后台任务 / 子 Agent 承接。

## 2. 命令执行超时

| 工具 | 默认 | 上限 | 怎么突破 |
|---|---|---|---|
| Bash | 120 s | 由 `BASH_MAX_TIMEOUT_MS` 决定（未设置则用内置默认） | 显式传 `timeout` |
| PowerShell | 120 s | **600 s（10 min）** | 显式传 `timeout` |

- **120 s 是「每一次工具调用」的执行上限 —— 前台、后台都算。**
- 前台命令超时 → **不杀进程**，会自动转后台并返回 `task_id`（`sleep` 例外，不自动转后台）。
- 后台命令（`run_in_background=true`）若**没显式传 `timeout`**，同样在 ~121 s 被杀：
  **零输出、退出码非 0、耗时恒定 2m1s** —— 症状极像 OOM 或崩溃，实为超时。
- **跑长任务 = `run_in_background` ＋ 显式 `timeout`（PowerShell 最大 600000 ms）**，缺一不可。

### 实测证据（2026-10-09）

| 同一个 150 s 作业 | 参数 | 结果 |
|---|---|---|
| 第一次 | `run_in_background=true`，**不传** `timeout` | **failed · 2m1s · 零输出** ← 被 120 s 杀掉 |
| 第二次 | `run_in_background=true`，`timeout=300000` | **completed · 2m32s** ← 存活 |

**结论：`run_in_background` 本身不免除超时；必须显式调大 `timeout`。**
本文件初版曾写「用 `run_in_background` 不受限」，该说法已作废。

## 3. 上下文压缩阈值（以模型最大输入为分母）

| 阶段 | 阈值 |
|---|---|
| `inputTokens.preMessage` | 0.5 |
| `inputTokens.warning` | 0.6 |
| `inputTokens.critical` | 0.7 |
| `inputTokens.emergency` | 0.9 |
| `compact.emergency` | 0.4（deepseek 系 0.5） |
| `summary.emergency` | 0.15 |
| `request.emergency` | 0.9 |

**影响**：一次性读入大文件或把长日志内联到对话，会快速把输入推到 60%+，触发压缩/摘要，历史细节被丢弃。**长输出必须落盘，只回读 tail。**

## 4. 沙箱程序黑名单（`forbidden_programs`）

```
wsl.exe  wslconfig.exe  wmic.exe  sc.exe  reg.exe  schtasks.exe
```

被杀程序由 agent 侧**完全无法调用**（含任何子命令）。推论：

- 装 WSL2 / 查发行版 / 迁移 vhdx → **只能用户手动**
- 查/改 Windows 服务（`sc.exe`）、注册表（`reg.exe`）、计划任务（`schtasks.exe`）→ **只能用户手动** 或改走 PowerShell cmdlet（`Get-Service` / `Get-ItemProperty` / `Get-ScheduledTask`）
- 这条清单是**按会话**写入的（每个 session 一份 `permission.json`），换会话仍是同一份策略

附带机制：

- **文件写入走备份**：每次写盘触发 `ModifyBackup`（sandbox 逐次备份原文件），批量小文件写入有明显开销。
- **删除走 safe-delete**：`Remove-Item` 被接管，强制进回收站；对空目录可能返回 `Some operations were aborted` —— **看着像失败，其实已进回收站**。

## 5. 会话缓存上限 = 3000 MB

`gc_config.json → maxSizeMb: 3000`。会话产物/缓存总量上限 3 GB，超限触发 GC。

## 6. 模型输出上限（当前模型）

对话头声明本会话为 **DeepSeek-V4.1-Flash**。`product.json` 中的对应条目：

| 模型 | maxOutput | maxInput |
|---|---|---|
| deepseek-v4-flash | 50,000 | 1,000,000 |
| deepseek-v4-pro | 50,000 | 1,000,000 |
| minimax-m3 | 128,000 | 512,000 |
| glm-5.2 | 48,000 | 1,000,000 |

完整表见 `product.json → models`。

## 7. 明确「不存在」的限制

- ❌ 无 CPU 配额 / 无 CPU 亲和性限制
- ❌ 无内存配额
- ❌ 无请求限流（`rateLimit` / `rpm` / `tpm` 在 product.json 中均未定义）
- ❌ 无工具并发调用硬上限（并行调用受模型与权限控制）
- ⚠️ 唯一的「外部」限制是账户 **credits / 套餐配额**（`Billing: true`，错误码 6005 升级 Pro、14018 获取 credits）—— 属账号侧，非本机配置

## 8. 对本机硬件的实测（非 WorkBuddy 限制，但会拖慢回测）

| 项 | 实测 |
|---|---|
| CPU | 12th Gen Intel Core i7-12700KF，12 核 / 20 线程，基准 3.6 GHz |
| 内存 | 31.84 GB，当前空闲 16.42 GB |
| 磁盘 | C: 剩 261.9 GB；D: 剩 340.6 GB |
| **电源计划** | **平衡（Balanced）** ← 长时间满载会降频 |

---

## 9. 对 A 股交易系统建设的直接影响

1. **`market.db` 3.1 GB ≈ 会话缓存上限 3 GB** —— 行情库**绝不能**作为会话产物内联或整体拷贝；回测必须直接只读挂载 DB，中间结果写盘。
2. **单次回测若可能 > 2 min → `run_in_background` ＋ 显式 `timeout=600000`**（PowerShell 上限 10 min）。
   只加后台、不调 timeout，会在 121 s 被杀且**无任何输出** —— B1 全周期回测的两次「假失败」就是这个原因。
   **缓解（2026-10-09）**：行情库加载器已从 54.9 s 降到 12.5 s，全周期回测 **106 s → 65 s**，回到默认档以内；
   但参数扫描 / 多宇宙对比仍须用上面的组合。
3. **长日志写文件、只回读 tail**，否则触发上下文压缩丢历史。
4. **满速跑回测前，建议临时把电源计划切「高性能」**（平衡模式在高负载下会降频，直接影响回测耗时基线）。
5. **凡涉及服务 / 注册表 / 计划任务 / WSL 的操作，直接按「需用户手动执行」设计**，不要写成 agent 可自动完成的步骤。
