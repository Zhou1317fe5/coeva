---
id: historical-session-harvesting
type: submodule-design
title: 多 Agent 历史会话归因挖掘与证据驱动冷启动过渡规范
parent: companion-phase-2-growth-core-and-chronicle
status: active
version: 0.1
tags: [chronicle, history-harvesting, codex, hermes, pi-desktop, evidence-cold-start, privacy-invariant]
---

# 多 Agent 历史会话归因挖掘与证据驱动冷启动过渡规范

## 1. 核心目标与问题定义

### 1.1 问题现状
伴生体在 Phase 2A/2B/2C 完成了证据库、行为模式挖掘和假说校准的核心闭环。然而，系统在真实落地时面临“冷启动数据匮乏”的瓶颈：
- **模式挖掘启动门槛（SPEC §8）**：要求“持久化 Episode 累计 ≥ 100 且跨度 ≥ 4 周”，若完全依赖桌宠上线后的日常增量积累（每日约 1~2 个会话），用户需等待 2~3 个月才能看到有效的共同认知画像；
- **冷启动天数僵化**：此前 `ColdStartPolicy` 仅按日历天数线性推移，无法识别用户过往长期使用 Coding Agent 的真实协作成熟度。

### 1.2 解决途径：收割多 Agent 既有真实资产
用户在当前机器上已经拥有沉淀数月的真实 Agent 交互日志：
- **WSL Codex CLI**：`~/.codex/sessions/2026/` 下 475 个独立会话 `.jsonl`；
- **WSL Hermes**：`~/.hermes/state.db` 下 15 个长链路会话、7,466 条结构化消息；
- **Windows PI-Desktop**：`~/.pi-desktop/sessions/` 下 31 个会话 `.jsonl`。

通过构建安全、离线、零隐私泄露的**历史会话收割器（Historical Session Harvester）**，将异构历史日志归一化为标准的 `AgentEvent` 并导入 `ChronicleStore`，瞬间跨越数据冷启动期，并在心智层实现**证据驱动的冷启动过渡**。

---

## 2. 系统核心硬约束（Invariants & Principles）

本模块严格执行以下四项架构铁律：

### 2.1 铁律 1：零 Prompt、零推理、零输出泄露（Invariant 2 & Privacy-First）
依据 `docs/concepts/04_attribution_design_v0.1.md` §35：
- **绝不提取、绝不转储用户的任何 Prompt 文本内容**；
- **绝不提取任何大模型的思维链（CoT / Reasoning）**；
- **绝不提取任何工具调用的执行返回详情或控制台大段输出**；
- 仅提取行为骨架元数据：`timestamp`（时间戳）、`event_type`（事件枚举）、`session_id`（会话隔离）、`agent_id`（来源标示）、`tool_name`（工具名称）及简短错误代码。

### 2.2 铁律 2：时间序因果一致性（Strict Temporal Causality）
- 导入历史数据时，必须保持各事件在会话内的严格时间递增（`timestamp ASC`）；
- 用户指令（`USER_PROMPT`）与工具报错（`TOOL_FAILURE`）的时间先后顺序必须忠实还原，确保 `PatternBuilder` 能准确区分“报错后主动纠偏”与“给予充分空间自主修复”。

### 2.3 铁律 3：完全幂等导入（Idempotent Ingestion）
- 依托现有 `event_id(event)` 的 SHA-1 稳定散列去重机制；
- 无论导入工具被执行多少次，数据库内的 `events` 与 `evidence` 行数严格保持幂等，绝不产生重复事件。

### 2.4 铁律 4：透明可审计与 Dry-Run 优先
- 提供显式 CLI 工具与 `--dry-run` 预览模式；
- 在真实落盘前，向用户清晰展示扫描到的各来源会话数、事件数、时间跨度范围，由用户掌控导入。

---

## 3. 异构数据源与路径拓扑

### 3.1 数据源拓扑表

| 来源标识 | 宿主系统 | 物理路径 | 格式特征 | 预估规模 |
| :--- | :--- | :--- | :--- | :--- |
| `pi-desktop` | Windows | `%USERPROFILE%\.pi-desktop\sessions\*.jsonl` | 行式 JSONL，以 `type` 标定记录类型 | 31 会话 |
| `codex` | WSL | `\\wsl$\Ubuntu-24.04\home\zhou\.codex\sessions\2026\**\*.jsonl` | 每行一个事件，`session_meta` 标记会话头 | 475 会话 |
| `hermes` | WSL | `\\wsl$\Ubuntu-24.04\home\zhou\.hermes\state.db` | SQLite 数据库，`sessions` 与 `messages` 表 | 15 会话 / 7.4k 消息 |
| `codex-win` | Windows | `%USERPROFILE%\.codex\sessions\2026\**\*.jsonl.zst` | Zstandard 压缩包（可选扩展） | 10 会话 |

---

## 4. 异构日志映射算法规范

各数据源通过统一的 `BaseSessionParser` 接口转译为标准的 `AgentEvent` 流：

### 4.1 PI-Desktop Parser
1. **会话边界**：
   - 提取首行 `{"type": "session", "sessionId": sid, "createdAt": ts}` $\to$ `AgentEventType.SESSION_START`；
   - 末尾记录最大时间戳 $\to$ `AgentEventType.SESSION_END`。
2. **事件映射**：
   - `{"type": "message", "role": "user", "createdAt": ts}` $\to$ `AgentEventType.USER_PROMPT`（忽略 `blocks` 文本）；
   - `{"type": "message", "role": "assistant"}` 中每个 `tool_call`：
     - 发起时 $\to$ `AgentEventType.PRE_TOOL_USE`，记录 `tool_name`；
   - 工具执行反馈：
     - 若状态标为报错/失败 $\to$ `AgentEventType.TOOL_FAILURE`（错误码简写）；
     - 若正常返回 $\to$ `AgentEventType.POST_TOOL_USE`。

### 4.2 Codex CLI Parser
1. **会话边界**：
   - `{"type": "session_meta", "payload": {"session_id": sid, "timestamp": ts}}` $\to$ `AgentEventType.SESSION_START`；
   - `{"type": "event_msg", "payload": {"type": "task_completed"}}` 或文件结束 $\to$ `AgentEventType.SESSION_END`。
2. **事件映射**：
   - `payload.type == "message"` 且 `role == "user"` $\to$ `AgentEventType.USER_PROMPT`；
   - `payload.type == "function_call"` $\to$ `AgentEventType.PRE_TOOL_USE`，记录 `tool_name`（如 `exec_command`, `apply_patch`）；
   - `payload.type == "function_call_output"`：
     - 检查退出码（exit_code != 0 或包含 error/timeout 标记） $\to$ `AgentEventType.TOOL_FAILURE`；
     - 正常完成 $\to$ `AgentEventType.POST_TOOL_USE`。

### 4.3 Hermes DB Parser
1. **会话边界**：
   - 读取 `sessions` 表中的 `id`, `started_at`, `ended_at` $\to$ 分别生成 `SESSION_START` 与 `SESSION_END`。
2. **事件映射**（按 `session_id` 过滤 `messages` 表，按 `timestamp ASC` 排序）：
   - `role == 'user'` $\to$ `AgentEventType.USER_PROMPT`，时间戳转为 ISO-8601；
   - `role == 'assistant'` 且 `tool_calls` 非空 $\to$ 遍历 tool_calls 触发 `PRE_TOOL_USE`；
   - `role == 'tool'`：
     - 若 `finish_reason == 'error'` 或内容判定报错 $\to$ `AgentEventType.TOOL_FAILURE`；
     - 否则 $\to$ `AgentEventType.POST_TOOL_USE`。

---

## 5. 证据驱动冷启动过渡机制（Evidence-based Cold Start Transition）

引入历史数据后，冷启动策略升级为**“双轨制”**，兼顾事实成熟度与情感陪伴节奏：

```text
               ┌────────────────────────────────────────────────────────┐
               │ 历史会话收割完成 (500+ Episodes, 跨度数月)               │
               └───────────────────────────┬────────────────────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
┌───────────────────────────────────────┐   ┌───────────────────────────────────────┐
│ 轨 A：认知成熟度 (Cognitive Track)    │   │ 轨 B：相处克制性 (Relational Track)   │
│ - 样本充分性校验: Episodes ≥ 30       │   │ - 伴生体物理陪伴天数依然自然递增      │
│ - 跨度校验: Span ≥ 14 天              │   │ - 每日发言配额遵循 80% 沉默 (1-3次)   │
│ ──> allows_psychological_analysis=True│   │ - 绝不因为数据充足就变得啰嗦多嘴      │
│ ──> PatternBuilder & Hypothesis 解锁  │   │ - 守住 Clean Stage 与 Sanctuary 底线  │
└───────────────────────────────────────┘   └───────────────────────────────────────┘
```

1. **认知成熟度判定**：
   - 若 `store.count_episodes() >= 30` 且历史时间跨度 $\ge$ 14 天，系统认定已具备足够的事实证据链；
   - `ColdStartPolicy.allows_psychological_analysis` 直接解除锁定，允许在 `ChronicleViewerWindow` 中生成与校准心理假说，消除了空置等待期；
2. **相处克制性保持**：
   - 伴生体每日的气泡发言限额（1~3 次/天）与三道门介入策略**保持不变**，绝不因历史数据丰富而变成频繁打扰用户的监控说教者。

---

## 6. 模块架构与 CLI 接口设计

### 6.1 模块结构
```text
src/connectors/history/
├── __init__.py
├── base.py              # BaseSessionParser 抽象基类与通用解析辅助
├── pi_desktop.py        # PiDesktopParser
├── codex_cli.py         # CodexCliParser (支持 WSL 与 Windows 本地路径)
├── hermes_db.py         # HermesDbParser (读取 SQLite state.db)
└── harvester.py         # MultiAgentHistoryHarvester (聚合收割器与协调逻辑)
```

### 6.2 CLI 命令接口
```bash
# 1. 安全预览模式 (统计各来源会话数、事件数、时间跨度，不落盘)
uv run python -m src.connectors.history.harvester --dry-run

# 2. 指定来源与限制量导入
uv run python -m src.connectors.history.harvester --sources pi,codex,hermes --limit 100

# 3. 全量安全收割并触发假说预热
uv run python -m src.connectors.history.harvester --all
```

---

## 7. 验收标准（Acceptance Criteria）

- **AC-1 零文本泄漏（硬约束）**：无论导入任何来源的日志，`events` 表中的记录均不包含原始 prompt 字符串、思考链、或工具大段标准输出；
- **AC-2 幂等性断言**：同一批历史日志连续运行导入两次，`ChronicleStore.stats()["total_events"]` 与 `total_evidence` 严格一致；
- **AC-3 时间序因果断言**：导入的所有会话中，每个会话内部的事件时间戳必须单调非递减；
- **AC-4 规模有效性**：完成全量导入后，`list_episodes()` 数量应 $\ge 100$，时间跨度覆盖数周以上；
- **AC-5 模式挖掘自动点亮**：导入后调用 `PatternBuilder.build_patterns()`，能成功挖掘出至少 2 种行为模式，且支撑 Episode 数量具备统计意义；
- **AC-6 证据驱动冷启动解禁**：在历史 Episode 充足的条件下，`ColdStartPolicy` 正确解锁心理分析权限。
