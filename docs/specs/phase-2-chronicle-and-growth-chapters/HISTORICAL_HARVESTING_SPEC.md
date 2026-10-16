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

## 5. 证据储备与真实相处冷启动铁律（Information vs. Trust Asymmetry）

### 5.1 核心哲学：信息与信任的不对称性（The Trust Deficit Principle）
在引入历史数据时，必须保持高度的心理学与人机关系清醒：
> **机器通过读取历史日志单方面获得了海量信息，但用户今天是第一次下载这款软件、第一次在桌角见到这只小动物。**  
> **在用户主观世界里，彼此依然是素未谋面的陌生人。**

若因为收割了 500 个历史会话，宠物在 Day 1 刚见面就表现出一副“我早看透你了”的熟络姿态，或在头顶气泡抛出深刻的心理分析，用户获得的绝不是“被理解的感动”，而是**毛骨悚然的被窥视感与隐私侵犯感（Creepy Surveillance Horror）**。

**“信任不能被数据快进，只能由真实共同生活的时间来沉淀。”**

### 5.2 历史数据角色定位：静默储备（Silent Historical Reserve）
历史会话导入后，严格作为心智底层的**“静默沉淀池”**：
1. **用途**：当未来双方相处成熟后，为模式挖掘提供充沛的样本底座，消除“阈值靠猜”的算法困境；
2. **边界**：**绝不作为快进相处节奏的借口**。前台桌宠的言行分寸、亲密感与发言配额，**100% 物理锁死在用户真实的相处天数（Physical Companion Days）上**。

### 5.3 双轨分离与物理陪伴天数锚定（Physical Cold Start Anchor）

```text
               ┌────────────────────────────────────────────────────────┐
               │ 历史会话收割完成 (500+ Episodes 存入底层 SQLite)       │
               └───────────────────────────┬────────────────────────────┘
                                           │
                    ┌──────────────────────┴──────────────────────┐
                    ▼                                             ▼
┌───────────────────────────────────────┐   ┌───────────────────────────────────────┐
│ 轨 A：事实底座 (Factual Reserve)      │   │ 轨 B：真实相处节奏 (Relational Pace)  │
│ - 解决“算法有据可查、不瞎猜”的问题    │   │ - 解决“彼此从陌生到信任的破冰过程”    │
│ - 作为后台静默样本池                  │   │ - 严格由 data/first_seen.json 驱动    │
│ - 在前 14 天保持 100% 静默潜伏        │   │ - 坚决不因历史数据提前开闸说教        │
└───────────────────────────────────────┘   └───────────────────────────────────────┘
```

伴生体的前台相处节奏严格执行 14 天渐进破冰（DESIGN & CONCEPT §7 硬约束）：
- **Day 1 ~ 3（Stage 1 初见与调频）**：
  - 哪怕底层有 500 个历史 session，桌宠表现依然是“刚来桌面的初见小动物”；
  - **物理克制**：每天主动发声上限严格为 **0 ~ 1 次**（仅限平实初见打招呼）；
  - **绝对静默**：`allows_psychological_analysis = False`，绝不主动抛出任何历史分析或假说询问。
- **Day 4 ~ 7（Stage 2 事实镜子与切片回响）**：
  - 仅反映当下即时的状态关怀（如深夜加班）与用户主动投喂的切片；
  - 每天发声上限为 **2 次**，保持桌面极度安静。
- **Day 8 ~ 14（Stage 3 渐进校准试水）**：
  - 经过一周多的物理陪伴，用户对桌宠的存在已形成心理安全感与熟悉感；
  - 允许桌宠在最放松的闲暇时刻，试探性地抛出一条客观习惯询问（例如结合既往事实温和求证）；
  - 每天发声上限为 **3 次**。
- **Day 15+（Mature 成熟期）**：
  - 双方跨越冷启动期，正式解锁长期发展假说与共同校准机制；
  - 此时历史数据池才正式与用户开启双向对齐，此时抛出的共识，既有长达数月的事实支撑，又建立在 14 天真实的信任基础之上。
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
- **AC-6 真实陪伴天数锁定（硬约束）**：无论导入多少历史日志，`data/first_seen.json` 所锚定的真实物理陪伴天数、阶段与每日发言配额绝对不被快进，确保用户主观体验上的初见破冰节奏完全自然。

---

## 8. 缺陷排查与工程修复复盘（Bug Post-mortems）

### 8.1 缺陷 1：12 万级历史事件扫描与导入致 GUI 假死未响应（GUI Main-Thread Blocking & Row-by-Row Commit Disaster）
- **现象**：在点击「扫描预览」或「一键安全收割导入」时，窗口标题栏频繁出现 `(未响应)` 假死，且当事件量达到 12 万条时，导入过程异常缓慢、甚至卡顿长达数分钟。
- **根因**：
  1. **主线程同步阻塞**：原实现在 Qt GUI 主事件循环线程直接执行几百个文件的跨网 UNC I/O 和数据库写入，阻断了 Windows 系统的消息泵（`WM_PAINT`）；
  2. **逐行物理刷盘灾难（Row-by-Row fsync Disaster）**：原 `ChronicleStore.record_event` 在单行插入后紧跟 `self._conn.commit()`。当面对 124,454 条历史事件时，触发了 12.4 万次独立的物理磁盘刷盘，导致 I/O 阻塞长达数分钟。
- **修复方案**：
  1. **极速批量事务入库**：新增 `ChronicleStore.record_events_batch`，采用 `executemany` 配合单次显式事务提交，将 12.4 万条事件的落盘时间从数分钟暴降至 **0.5 秒以内（300x+ 提升）**；
  2. **QThread 后台工作线程化**：重构 `HarvestHistoryDialog`，扫描与批量导入彻底委托给后台 `HarvestWorkerThread` 异步执行，主界面保持 60fps 丝滑响应，配备动态脉冲进度条与实时文本流；
  3. **行级快速前置过滤**：在读取 JSONL 文件时先进行轻量字符串匹配过滤，直接跳过无关内部状态日志，避免无谓的 `json.loads` 反序列化。
