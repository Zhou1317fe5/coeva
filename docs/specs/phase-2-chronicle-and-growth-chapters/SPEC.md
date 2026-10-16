---
id: companion-phase-2-growth-core-and-chronicle
type: module-design
status: active
version: 0.3
title: 第二阶段规范：长盛心智与人生章节（Phase 2A MVP：证据档案库与归因门）
parent: co-evolving-companion-root
depends-on: [companion-architecture-design, companion-phase-1-runtime-and-bridge]
tags: [phase-2, growth-core, chronicle, attribution, evidence-ledger, sqlite, local-first, mvp]
---

# 第二阶段规范：长盛心智与人生章节

> 本文描述 Phase 2 的整体目标，但**当前生效的范围只有 2A MVP**（证据档案库 + 归因门）。
> 2B/2C/2D 的推理与叙事层已设计但**明确延后**，清单见 §8，以免被误读为已承诺。

---

## 1. 阶段目标

Phase 1 交付了独立桌面身体、Slice Feeder、Sanctuary Guard 与多 Agent Connector Hub。
Phase 2 建立伴生体的长期心智，回答四个问题：

1. 发生过什么？ → **2A（本次交付）**
2. 哪些事情反复出现？ → 2B
3. 我们目前如何理解这些变化？ → 2C
4. 哪些变化重要到值得成为人生章节？ → 2D

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

---

## 5. 归因门规则

纯函数 `classify(event_type) -> (provenance, retention_class)`，无状态、无 LLM、无 I/O：

| `event_type` | `provenance` | `retention_class` |
| :--- | :--- | :--- |
| `user_prompt` | `user_action` | `durable` |
| 其余全部 | `agent_context` | `transient` |

**硬约束**：`agent_context` 永远不得升级为高权重发展证据。
这是 §2.2 在代码中的唯一落点，也是 2A 唯一可在单测中断言的归因规则（见 AC-2）。

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

## 8. 待做（Deferred Backlog）

以下各项均已设计、确认有价值，但**本次不实现**。每项注明启动条件，避免被误认为已承诺。

| 项 | 所属 | 启动条件 |
| :--- | :--- | :--- |
| Pattern Builder | 2B | 持久化 Episode 累计 ≥ 100 且跨度 ≥ 4 周；否则阈值只能靠猜 |
| Hypothesis Engine | 2B | 依赖 Pattern；须先实现 counter-evidence 存储（AC-3 类要求） |
| Development Lens | 2B | 依赖 Hypothesis；每个判定须可追溯到 evidence id |
| User Calibration | 2C | 依赖 Hypothesis；须先定义"认领"的精确语义（点 Confirm 算不算？） |
| Confirmed Insight 与退休 | 2C | 依赖 Calibration |
| Growth Themes | 2C | 依赖 Insight；须先解决"1–3 个硬上限"与用户自主目标的冲突 |
| Evidence-based Cold Start | 2C | **日计数缺陷已修**（`ColdStartPolicy.from_persisted_first_seen()` 按真实天数推进，`data/first_seen.json`）。**但本项仍待做**：改为证据驱动（而非纯时间驱动）尚未开始 |
| Chapter Eligibility Gate | 2D | 依赖 Insight；须定义 Sustained / Structural / Diversity / Meaning 四项的可判定阈值 |
| Chapter 生成 | 2D | 需 LLM 客户端（当前依赖树无任何 LLM SDK）、API key 存放约定、超时与离线降级 |
| Narrative Firewall | 2D | 随 Chapter 生成一并实现（§2.5 目前无执行对象） |
| Co-authoring / Co-Naming | 2D | 依赖 Chapter；须先解决与 Sanctuary、每日发言配额的冲突 |
| Chronicle Viewer | 2D | 依赖 Chapter。**可提前**：只读证据列表（v0.2 §27 去掉假设层）零 LLM 可做，且正好验证 AC-4 |
| FTS5 + 中文分词 | 检索 | 切片 > 10k；须引入 jieba 类分词器 |
| Interaction 层证据 | 归因 | 需 connector 侧新增用户侧事件（用户中止 / 继续 / pivot），当前 `AgentEventType` 无法表达 |
| 事件契约扩展 `platform` / `distro` | 归因 | hook JS 已发送这两个字段，但 `dispatch_json` 未透传、`AgentEvent` 无对应字段。需要按环境区分证据时再扩契约（会改动 Phase 1 契约） |
| token 鉴权 | 安全 | 仅当端口需要暴露到非回环 |
| 精细衰减分层 | 存储 | 两档 TTL 不够用时 |
| 端到端事件去重 | 存储 | hook 载荷携带稳定 id/时间戳之后（当前见 §4.3 限制） |
| `prune()` 的定时触发 | 存储 | **已完成**：`CompanionApp._setup_decay()` 在启动时与每 24 小时调用 |
| 切片写入 Chronicle 的接线 | 归因 | `run_companion._on_slice_submitted` 已写 `RawSlice` 并存档案库；`SliceStore`（jsonl）仍为 Phase 1 遗留双写，待确认是否保留为导出通道 |

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
