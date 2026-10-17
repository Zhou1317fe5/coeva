---
id: companion-phase-2-growth-core-and-chronicle
type: module-design
status: active
version: 1.0
title: 第二阶段规范：长盛心智与人生章节（Phase 2 全阶段完成）
parent: co-evolving-companion-root
depends-on: [companion-architecture-design, companion-phase-1-runtime-and-bridge]
tags: [phase-2, growth-core, chronicle, attribution, evidence-ledger, sqlite, local-first, mvp]
---

# 第二阶段规范：长盛心智与人生章节
> 本文规定 Phase 2 的长盛心智架构与四个子阶段的落地事实。
> **Phase 2A、2B、2C、2D 已全部实现并通过全量自动化测试与真实数据验证。**
> 子模块规范参见：
> - `HISTORICAL_HARVESTING_SPEC.md`（多 Agent 历史会话归因挖掘与证据驱动冷启动）
> - `CHAPTERS_SPEC.md`（大模型接入、叙事防火墙与人生章节共创）

---

## 1. 阶段目标与落地状态

Phase 1 交付了独立桌面身体、Slice Feeder、Sanctuary Guard 与多 Agent Connector Hub。
Phase 2 建立了伴生体的长期心智体系，完整闭环回答了四个关键问题：

1. **发生过什么？** → **Phase 2A（客观证据档案库，已完成）**
2. **哪些事情反复出现？** → **Phase 2B（行为模式挖掘与心理灵活性假说，已完成）**
3. **哪些理解经双方确认？** → **Phase 2C（共同认知自模型与双向校准，已完成）**
4. **这段时期在用户生命里意味着什么？** → **Phase 2D（大模型接入、叙事防火墙与人生章节，已完成）**
> 让离散经历逐渐形成有证据、可修正、会遗忘、会演化的长期理解，
> 并在真实结构性变化发生后，形成用户共同书写的人生章节。

---

## 2. 核心原则（不可协商）

### 2.1 Evidence ≠ Interpretation

`Evidence ≠ Pattern ≠ Hypothesis ≠ Insight ≠ Narrative`。
任何高层结论必须能够向下追溯到 Evidence。

### 2.2 Agent Behavior ≠ User Behavior

Agent 的搜索、重试、工具调用、reasoning、subagent **不能独立成为用户心理或人格证据**，只能作为 Context。
具有归因价值的只有：用户明确表达、用户主动决策、用户对 Agent 状态的响应、跨情境重复出现的交互模式。

### 2.3 不把成长压缩成分数

六大发展透镜（时间整合 / 未知开放 / 调节灵活性 / 自主行动 / 情绪开放 / 叙事整合）只是**理解变化的透镜**。
任何界面不得呈现 `心理灵活性 = 72`、成长等级、好感度等数值。

### 2.4 Hypothesis ≠ Truth

未经用户校准的深层理解一律标记 `candidate`，可被 confirm / revise / reject / retire。不存在永久真理。

### 2.5 Narrative Firewall

AI 生成的总结、反思、章节、角色对白**不得反向成为下一轮推断的证据**，否则会形成
「AI 推断 → 写进故事 → 故事被当作历史事实 → 强化原推断」的自我强化循环。
（2A 不产生任何生成物，故该规则暂无可执行对象；引入 LLM 生成物时必须先实现它。）

### 2.6 Silence Is a Valid Result

理解得多，表达得少。Sanctuary 激活、高认知负荷、证据不足时默认沉默。
**不生成任何输出是完全正确的成功状态。**

---

## 3. 当前范围：Phase 2A MVP

### In Scope

1. **Agent 事件持久化** —— Phase 1 的事件流仅存在于内存（`LocalEventBus._history`），进程重启即清零。
   2A 首先补上这条输入流，否则后续一切推理都无米下锅。
2. **Chronicle Store（`src/memory/store.py`）** —— 本地 SQLite（WAL），两张表 + 一个视图。
3. **归因门（`src/core/attribution.py`）** —— 纯函数，判定每条证据的 `provenance` 与 `retention_class`。
4. **Episode 查询** —— 以 `session_id` 为天然边界，不建表、不写切分算法。
5. **检索** —— 时间 / 来源 / 关键词过滤。
6. **衰减** —— `prune()` 按 `retention_class` 删除旧的高频事件。
7. **只读 HTTP 端点** —— `/api/chronicle/*`，回环限定。

### Out of Scope

Pattern、Hypothesis、Development Lens、User Calibration、Confirmed Insight、Growth Theme、
Chapter Eligibility、Chapter 生成、Co-authoring / Co-Naming、Chronicle Viewer、任何 LLM 调用。
逐项启动条件见 §8。

---

## 4. 数据契约

### 4.1 表与视图

`data/companion_chronicle.db`，连接时 `PRAGMA journal_mode=WAL`。

```sql
CREATE TABLE IF NOT EXISTS slices (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'user',
    source      TEXT NOT NULL DEFAULT 'manual_feed',
    content     TEXT NOT NULL,
    mood_flag   TEXT NOT NULL DEFAULT 'neutral',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,          -- sha1 幂等键，见 §4.3
    timestamp       TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    session_id      TEXT NOT NULL DEFAULT 'default',
    event_type      TEXT NOT NULL,
    tool_name       TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    provenance      TEXT NOT NULL,             -- 见 §4.2
    retention_class TEXT NOT NULL,             -- 见 §4.2
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_slices_time      ON slices(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_time      ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_retention ON events(retention_class, timestamp);

-- evidence 是视图，不是表：单一事实源，不复制内容，无需同步触发器
CREATE VIEW IF NOT EXISTS evidence AS
    SELECT id, timestamp, 'slice' AS source_type, actor,
           'user_explicit' AS provenance, 'durable' AS retention_class,
           content
      FROM slices
    UNION ALL
    SELECT id, timestamp, 'event' AS source_type, agent_id,
           provenance, retention_class,
           CASE WHEN tool_name <> '' THEN event_type || ':' || tool_name ELSE event_type END
      FROM events;
```

**为什么只有两张表**：推理层（Pattern / Hypothesis）落地前不需要更多实体；
`evidence` 用 VIEW 表达即可，避免"证据表"与原始表双写导致的事实源分裂。

### 4.2 provenance 与 retention_class

`provenance` 是 v0.2 §5.3 的子集，MVP 只用到 3 个值：

| 值 | 含义 | 来源 |
| :--- | :--- | :--- |
| `user_explicit` | 用户明确表达（含原话） | `slices` |
| `user_action` | 用户主动决策，但内容未被捕获 | `events.user_prompt` |
| `agent_context` | Agent 自主行为 | 其余全部 `event_type` |

`retention_class` 只有两档：

| 值 | 成员 | 生命周期 |
| :--- | :--- | :--- |
| `durable` | `slices`、`user_prompt` | 不删除 |
| `transient` | 其余 events | 默认 30 天后由 `prune()` 删除 |

> 只分两档是**有意的**：v0.2 §25 要的语义是"降低旧信息对当前模型的影响"，两档已满足。
> 更细的 TTL 分层在确有需要时再引入（§8）。

### 4.3 事件幂等键

`AgentEvent` 无 id 字段，且 hook 可能重投。事件 id 取

```
sha1(agent_id | session_id | timestamp | event_type | tool_name | error_message)
```

写入使用 `INSERT OR IGNORE`，保证**同一事件对象**重复写入不产生重复行。

> **已知限制（实现时实测确认）**：hook 载荷不带时间戳，`AgentEvent.create` 在服务端
> 打时间戳（`src/connectors/contracts.py`）。因此**同一条 hook 被重投两次会得到两个不同 id**，
> 该幂等键只覆盖"同对象重复写入"，不覆盖"同事实重投"。
> 端到端去重需要 connector 侧在载荷中携带稳定 id 或时间戳（§8）。

### 4.4 检索策略

MVP 使用 `LIKE '%kw%'`，不做 FTS5。

**已知约束（本项目 `.venv` 实测，SQLite 3.53.1，FTS5 已编译）**：
`unicode61` 与 `trigram` 两种分词器对 **2 字中文词均为 0 命中**（`trigram` 需 ≥3 字）。
即 FTS5 在中文场景下默认是坏的，做对需要引入分词器依赖。故 MVP 不采用。

```
shortcut: LIKE 全表扫描，切片 > 10k 时换 FTS5 + 中文分词器（见 §8）
```

### 4.5 切片双写契约（Chronicle + JSONL）

用户主动投喂的一条切片被**有意写入两处**，职责不同、不构成事实源分裂：

| 目标 | 角色 | 事实源？ | 可重建？ |
| :--- | :--- | :--- | :--- |
| `data/companion_chronicle.db` (`slices` 表) | 结构化查询、归因、Episode、衰减 | **是（唯一）** | 否 |
| `data/raw_slices.jsonl` | 人类可读的 append-only 导出流 | 否 | 是（可由 Chronicle 重建） |

判定依据：
1. `raw_slices.jsonl` 是 Phase 1 遗留的平铺格式（SPEC.md §3.2），SUPER.md §5 的
   "轻量移动端同步"目标需要一个**不依赖 SQLite**、可直接被手机端只读翻阅的载体；
2. 二者写入的都是同一条 `RawSlice`（同一 id / timestamp），`import_slices_jsonl()` 按 id
   `INSERT OR IGNORE`，因此 JSONL 丢失或损坏时可由 Chronicle 反向导出恢复；
3. 反向不成立（JSONL 无法表达 `provenance` / `retention_class` / events），
   故 Chronicle 是唯一事实源，JSONL 只是投影。

> 硬约束：任何**新的**读取路径（推理、Pattern、Chapter）必须只读 Chronicle；
> JSONL 仅允许被导出类功能读取。若将来引入手机端写回，写回目标也必须是 Chronicle。

---

## 5. 归因门规则

纯函数 `classify(event_type) -> (provenance, retention_class)`，无状态、无 LLM、无 I/O：

| `event_type` | `provenance` | `retention_class` |
| :--- | :--- | :--- |
| `user_prompt` | `user_action` | `durable` |
| 其余全部 | `agent_context` | `transient` |

**硬约束**：`agent_context` 永远不得升级为高权重发展证据。
这是 §2.2 在代码中的唯一落点，也是 2A 唯一可在单测中断言的归因规则（见 AC-2）。

### 5.1 事件类型与 Episode 边界

`AgentEventType` 共 9 种。**`session_id` 必须由 connector 为每次会话生成**，
否则所有会话塌缩成同一个 Episode，跨会话的 Pattern 永远无法成立。

| 事件 | 语义 | 备注 |
| :--- | :--- | :--- |
| `session_start` | 会话开始 | **必须携带新的 session_id** |
| `user_prompt` | 用户发起一轮 | 唯一 `user_action` |
| `pre_tool_use` | 即将调用工具 | |
| `post_tool_use` | 工具**成功**返回 | 缺失时只有失败可见 |
| `tool_failure` | 工具失败 | |
| `turn_end` | 一轮对话结束 | **不是** `task_complete` |
| `task_complete` | 任务真正完成 | 低频 |
| `needs_input` | 等待用户输入 | |
| `session_end` | 会话结束 | |

> **为何区分 `turn_end` 与 `task_complete`**：实测一个工作日产生约 450 条 `turn_end`。
> 若都记为 `task_complete`，未来的 Episode/Pattern 统计会得出"用户完成了数百个任务"的失真结论。
> 已知 connector 实测（pi-desktop）：`turn_end` 报为 `task_complete` 时的分布为
> `task_complete 449 / pre_tool_use 412 / tool_failure 25 / user_prompt 16`。

> v0.1 的 `tool_loop_abort` / `late_night_push` 归因**已移除**：
> 前者需要"用户中止"事件类型（`AgentEventType` 中不存在），
> 后者把 Agent 自主行为等同于用户作息，违反 §2.2。二者均需 connector 侧先提供用户侧信号（§8）。

---

## 6. Episode

Episode = 同一 `session_id` 的事件集合，边界由 `session_start` / `session_end` 界定。

MVP 以 `GROUP BY session_id` 查询实现，**不建表、不写切分算法**：

```
list_episodes(limit) -> [session_id, started_at, ended_at, event_count, agent_ids, has_user_action]
```

---

## 7. 接口与安全边界

### 7.1 端点（全部只读）

- `GET  /api/chronicle/stats`
- `GET  /api/chronicle/slices?limit=&offset=&mood=`
- `POST /api/chronicle/slices/search` —— `{query, limit}`
- `GET  /api/chronicle/evidence?limit=&offset=&provenance=`
- `GET  /api/chronicle/episodes?limit=`

### 7.2 回环限定（硬约束）

`src/connectors/http_server.py` 当前为 `DEFAULT_HOST = "0.0.0.0"` 且全链路零鉴权。
Phase 1 暴露的只是 Agent 开关；2A 的端点会暴露**用户原始切片原话与完整证据链**。

但**不能直接把 host 改成 `127.0.0.1`** —— WSL 中的 Agent（Hermes / Pi CLI）依赖跨网访问 Windows 宿主
（见 `hook_manager.py` 的 WSL interop fallback）。

因此：单服务不变，`/api/chronicle/*` 按 `client_address` 判定，**非回环来源一律 403**。

---

## 8. 实施状态与未来规划（Implementation Status & Future Backlog）

### 8.1 Phase 2 交付矩阵（已 100% 落地）

| 项 | 所属 | 落地说明 |
| :--- | :--- | :--- |
| **Chronicle Store 底座** | 2A | SQLite 单一事实源 + `raw_slices.jsonl` 双写，回环只读 API |
| **归因安全门** | 2A | 严格零 Prompt 隐私，区分 `user_action` 与 `agent_autonomous` |
| **定期修剪衰减** | 2A | `prune()` 24 小时巡检，30 天 transient 事件衰减，切片永留 |
| **Pattern Builder** | 2B | 挖掘节律、摩擦与委派；实现严格时间序因果一致性约束 |
| **Hypothesis Engine** | 2B | 映射至 ACT 六大透镜，包含正例与反例 Episode 追溯 |
| **User Calibration** | 2C | 支持 YES（转共识）、PARTLY（细化）、NO（封存）、NOT_NOW（保持）状态机 |
| **Confirmed Insights & 退休** | 2C | 长期共识管理与生命周期自然成长退休（Outgrowth） |
| **Growth Themes** | 2C | 1~3 个活跃发展主题硬上限防护 |
| **多 Agent 历史会话收割** | 2C | 自动扫描 WSL/Win 下 Pi, Codex, Hermes 历史日志（实测入库 12 万条） |
| **物理陪伴冷启动锁** | 2C | 事实与信任分离，真实陪伴天数雷打不动，守住破冰分寸 |
| **OpenAI-Compatible LLM Client** | 2D | 原生标准库实现，零第三方臃肿 SDK，配置本地安全落盘 |
| **Chapter Eligibility Gate** | 2D | 持续性、结构性、多样性、自愿性四大资格门校验 |
| **Narrative Firewall** | 2D | 过滤谄媚与说教，通篇锁定工坊战友并肩作战口吻，锚定真实事实 |
| **Growth Chapters 生成与共创** | 2D | 本地 Markdown 生成（`data/chapters/`），用户手记在线留白共写与导出 |
| **Chronicle Viewer 全功能界面** | 2D | 5 大页面完整联动（切片、会话、检索、认知自模型、人生章节） |

### 8.2 Phase 3 待做演进（Future Ecosystem Backlog）

| 项 | 类别 | 说明 |
| :--- | :--- | :--- |
| Vasu 原生精灵帧动画全量制作 | 身体 | 按 `docs/specs/vasu/SPEC.md` 完成 9 行核心动画与专属扩展动作 |
| 多端只读同步通道 | 同步 | 支持通过 WebDAV / S3 将 `data/chapters/*.md` 同步至手机端查看 |
| FTS5 中文全文分词 | 检索 | 当切片积累超过 10,000 条时引入 jieba 中文全文索引 |
| HTTP 只读路由补齐 | 接口 | 补充 `GET /api/chronicle/insights` 与 `GET /api/chronicle/themes` |
---

## 9. 验收标准

- **AC-1 事件持久化**：每个经 `/api/event` 的 `AgentEvent` 落盘；进程重启后 `events` 行数不减少。
- **AC-2 归因安全（硬）**：给定只含 `pre_tool_use` / `post_tool_use` / `tool_failure` 任意数量、
  **无 `user_prompt`** 的事件流，`evidence` 中 `provenance ∈ {user_explicit, user_action}` 的行数为 0。
- **AC-3 幂等导入**：对同一 `raw_slices.jsonl` 重复导入 N 次，`slices` 行数不变。
- **AC-4 证据可追溯**：任一 `evidence` 行可由 `(source_type, id)` 定位到 `slices` / `events` 的原始行。
- **AC-5 中文检索**：查询 `明天` 能命中包含该词的切片（验证 §4.4 的 LIKE 路径）。
- **AC-6 衰减**：`prune()` 后 `transient` 事件按 TTL 删除，`slices` 与 `user_prompt` 行数不变。
- **AC-7 回环限定**：非回环来源请求 `/api/chronicle/*` 返回 403；回环返回 200。
- **AC-8 无叙事产物**：依赖树中不含任何 LLM SDK，且无 chapters 表（`pyproject.toml` 可断言）。
- **AC-9 检索性能**：10,000 条切片下，时间范围 + mood 过滤查询 P95 ≤ 50ms（本地热缓存），
  防止实现中出现意外的 O(n) 退化。

---

## 10. 风险

1. **2A 没有任何用户可见的新功能** —— 桌宠行为与 Phase 1 完全一致，只是开始默默攒证据。
   若需要可见成果，做 §8 中标注"可提前"的只读证据列表。
2. **当前数据量不足以支撑 2B** —— `data/raw_slices.jsonl` 仅 10 条，且 Agent 事件从未落盘。
   §8 的 2B 启动门不是保守，而是防止把阈值写成猜测。
3. **WSL 跨网访问与回环限定的张力** —— §7.2 以按路由判定解决；
   若将来拆分为独立端口，需重新评估。

---

## 11. 缺陷排查与工程修复复盘（Bug Post-mortems）

为便于团队开发、后续交接与架构审查，记录在 Phase 2 记忆归因与行为模式挖掘中排查的关键缺陷及根治方案：

### 11.1 缺陷 1：摩擦归因缺乏时间序因果导致 Agent 自主修复被误判为用户干预（Temporal Causality Attribution Bug）
- **现象**：在 Agent 执行长链路复杂任务中，工具执行产生报错（`tool_failure`）后，Agent 自主分析上下文并尝试修复，用户并未进行任何干预；但在行为模式挖掘时，该 Episode 却被错误归因为 `pat_friction_recovery`（用户主动下发纠偏指令），导致认知画像与用户真实行为完全相反。
- **根因**：原 `_detect_friction_response` 仅使用集合包含判定（`fails > 0 and user_prompts > 0`）。然而，几乎所有会话的最开始都包含一条用户发起的初始任务 Prompt（`user_prompt` at t=0）。由于缺乏时间序前后因果判定，前置的初始 Prompt 被误作为“报错后的干预证据”。
- **修复方案**：
  1. **严格时间序因果约束（Strict Temporal Causality Rule）**：重构 `PatternBuilder._detect_friction_response`，按 `timestamp ASC` 严格遍历事件流。只有当 `user_prompt` 的时间戳严格发生在 `tool_failure` 之后，才记为用户介入；
  2. **双向模式与认知透镜健全**：若 Agent 遭遇报错但用户未在报错后打断，如实归因为 `pat_agent_autonomous_recovery`（给予自主修复空间），并在心智层映射到“接纳不确定性（Openness to Uncertainty）”与“调节灵活性（Regulatory Flexibility）”透镜；
  3. **任务委派比率因果化**：重构 `_detect_delegation_ratio`，计算用户 Prompt 占总事件比率，支持 `pat_hands_off_delegation`（深度信任委派）与 `pat_interactive_steering`（紧密阶段引导）双向判定。

### 11.2 缺陷 2：冷启动天数计算与每日发言配额跨天未自然滚动（Cold Start Day Progression & Speech Quota Rollover）
- **现象**：伴生体连续运行数天后，系统内部仍被锁定在 Day 1 且每日气泡配额耗尽后无法在次日自然重置。
- **根因**：`ColdStartPolicy` 原实现仅在内存中维护会话内天数；且 `InterventionPolicy.can_speak()` 的配额重置只基于静态字典，缺乏跨日期的本地持久化锚点。
- **修复方案**：引入 `data/first_seen.json` 作为首次唤醒持久化记录，通过 `ColdStartPolicy.from_persisted_first_seen()` 根据本地日历天数自然递增计算伴生天数；在 `can_speak()` 中增加基于当前日期的 `roll_over_if_new_day()` 检查，次日自动刷新 3 次发言配额。

### 11.3 缺陷 3：数据面 Agent 执行与控制面桌宠姿态强耦合导致毫秒级震荡（Planes Separation & Telemetry Decoupling）
- **现象**：当外部 Agent 高频调用 CLI/工具时，桌宠在 2 分钟内震荡切换 700+ 次动画状态，甚至导致多 Agent 并发时的状态踩踏。
- **根因**：控制面（桌面表现层）与数据面（只读事件流）未物理解耦，HTTP 接收器与 EventBus 直接回调了 `BodyController.set_state`。
- **修复方案**：彻底切断 EventBus 对身体姿态的直连。所有 Agent 遥测数据 100% 作为只读证据流进入 Chronicle 与 StateWatcher，身体姿态主权回归人类与自然节律（静默 Idle、投喂 Jump、离开打瞌睡 Sleep）。
