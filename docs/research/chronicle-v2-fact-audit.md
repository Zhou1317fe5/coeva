# Co-evolving Companion Chronicle / Self Model / Growth Chapters 事实审计报告
## ——Phase 2 V2 重构前现状与证据架构事实全景

> **审计基准与原则声明**：
> - 审计时间：2026-10-18
> - 代码库版本：Phase 2D 完成态（Git 159 项测试全量通过）
> - 数据库：`data/companion_chronicle.db`（只读挂载审计，未写入、未迁移、未修改）
> - 规范事实源：`docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md`、`HISTORICAL_HARVESTING_SPEC.md`、`CHAPTERS_SPEC.md`、`AGENTS.md`
> - 审计准则：严格区分**代码事实（Code Fact）**、**数据事实（Data Fact）**、**推断（Inference）**与**建议（Recommendation）**。无证据项显式标注为 `Unknown` 或 `未定义`，不预设 V2 方案必定正确。

---

## 1. Executive Summary（执行摘要）

本次事实审计覆盖伴生体项目的持久化存储（`ChronicleStore`）、检索链路（`MemoryRetriever`）、行为挖掘（`PatternBuilder`）、假说推理（`HypothesisEngine`）、共同认知自模型（`SelfModelManager`）以及章节叙事（`ChapterGenerator`）。核心事实发现如下：

1. **数据面与推断严重脱节（Slices Orphaned from Inference）**：
   - 生产库包含 **115,317 条遥测事件（Events）** 与 **42 条用户切片（Slices）**。
   - `PatternBuilder.build_patterns()` **100% 只查询 `events` 表**，`slices` 表从未作为输入参与任何模式挖掘或假说合成。
   - `slices` 表设计中甚至**完全没有 `session_id` 字段**，用户主动投喂的内容在数据结构上就是孤立的。

2. **假说由硬编码模版映射生成（Hard-coded Pattern-to-Hypothesis Mapping）**：
   - `HypothesisEngine.synthesize()`（`src/core/hypotheses.py:73-176`）采用显式 `if pat.pattern_id == ...` 结构，将 5 种固定模式硬编码映射为 5 条固定心理学文案。
   - 界面上呈现的“正例 46 处 / 反例 7 处 / high confidence”中的统计单位是 **`session_id`（即当前定义下的 Episode）**，置信度依据会话数与支持率做纯规则阈值切分（`support_cnt >= 4 and ratio >= 0.75`）。

3. **日常记忆检索字面依赖过重且退化严重（LIKE Retrieval Fragility）**：
   - `MemoryRetriever`（`src/memory/retriever.py`）依赖分词、停用词清洗、2~3 字 N-gram 生成后，通过 SQLite `LIKE '%kw%'` 进行全表扫描。
   - 离线 10 组语义回归实测显示：**语义相近但字面无交集的查询 100% 漏召回（False Negative）**；而包含通用词（如“代码”）的正面表述会**错误命中严重的负面情绪吐槽（False Positive / 语义漂移）**。

4. **确认共识进入数据库后成为运行时死数据（Confirmed Insights as Dead Sinks）**：
   - 全局符号检索确认：`store.list_insights()` 仅被 `src/body/chronicle_window.py`（UI 列表展示）和 `src/core/chapters.py`（章节资格门判定与 LLM Prompt 注入）调用。
   - `insights` **完全未进入** `personality prompt`、日常对话气泡、主动关怀（State Care）、避风港（Sanctuary）、昼夜节律（Circadian）或身体状态机（Body Controller）。

5. **章节生成器存在时间变化叙事幻觉（Temporal Hallucination in Chapters）**：
   - `ChapterGenerator`（`src/core/chapters.py`）向 LLM 传递的上下文仅包含：整体起止日期、全局事件/会话累计总数、静态累计模式列表、采样会话 ID 列表。
   - **完全未传递分时序（Chronology）对比数据或阶段演进差异**。由于 Prompt 强约束章节结构为“伴生体的观察与心智转移（The Shift）”并提供了“从事必躬亲到学会委派”的标题样例，LLM **在毫无时间分段证据的情况下，自行脑补捏造了“起初……随着推进……逐步转变为……发生转移……”的时间演化叙事**。

6. **本地轻量化与隐私红线（Local-First & Strict Privacy Invariants）**：
   - 现有环境已原生启用 SQLite FTS5（SQLite 3.53.1），但目前零 ML 依赖（无 numpy / torch / transformers / onnxruntime / sqlite-vec）。
   - 架构红线明确禁止记录用户 Prompt 文本、LLM 思维链（CoT）及工具返回详情；所有 Connector 均将 Prompt 文本丢弃，仅记录 occurrence。用户删除数据后的派生假说与章节级联处理在当前规范中**未定义**。

---

## 2. Current Data Model（当前数据模型与持久化事实）

### 2.1 物理存储与文件拓扑
- **SQLite 数据库**：`data/companion_chronicle.db`（运行时强制启用 `PRAGMA journal_mode=WAL`，`src/memory/store.py:138`）。
- **切片冗余流**：`data/raw_slices.jsonl`（由 `SliceStore` 负责 append-only 写入，`src/feeder/storage.py`）。
- **成长章节 Markdown**：`data/chapters/chapter_*.md`（独立文本文件持久化，`src/core/chapters.py:88`）。
- **首次唤醒标记**：`data/first_seen.json`（记录物理陪伴第一天本地时间戳，供 `ColdStartPolicy` 计算伴生天数）。

### 2.2 完整 SQLite Schema（代码事实：`src/memory/store.py:34-98`）
数据库初始化通过 `_SCHEMA` 脚本执行（全部带 `IF NOT EXISTS`）：

```sql
-- 1. 用户投喂切片表
CREATE TABLE IF NOT EXISTS slices (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'user',
    source      TEXT NOT NULL DEFAULT 'manual_feed',
    content     TEXT NOT NULL,
    mood_flag   TEXT NOT NULL DEFAULT 'neutral',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. 外部 Agent 遥测事件表
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    agent_id        TEXT NOT NULL,
    session_id      TEXT NOT NULL DEFAULT 'default',
    event_type      TEXT NOT NULL,
    tool_name       TEXT NOT NULL DEFAULT '',
    error_message   TEXT NOT NULL DEFAULT '',
    provenance      TEXT NOT NULL,
    retention_class TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. 索引定义
CREATE INDEX IF NOT EXISTS idx_slices_time      ON slices(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_time      ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_session   ON events(session_id);
CREATE INDEX IF NOT EXISTS idx_events_retention ON events(retention_class, timestamp);

-- 4. 统一证据视图（VIEW，非物理表）
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

-- 5. 候选发展假说表
CREATE TABLE IF NOT EXISTS hypotheses (
    id                  TEXT PRIMARY KEY,
    statement           TEXT NOT NULL,
    lenses              TEXT NOT NULL,
    supporting_patterns TEXT NOT NULL,
    supporting_episodes TEXT NOT NULL,
    counter_episodes    TEXT NOT NULL,
    confidence          TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL
);

-- 6. 双方确认的共识（自模型）表
CREATE TABLE IF NOT EXISTS insights (
    id                  TEXT PRIMARY KEY,
    statement           TEXT NOT NULL,
    lenses              TEXT NOT NULL,
    supporting_patterns TEXT NOT NULL,
    user_confirmation   TEXT NOT NULL,
    valid_from          TEXT NOT NULL,
    last_revalidated    TEXT NOT NULL,
    status              TEXT NOT NULL
);

-- 7. 活跃发展主题表
CREATE TABLE IF NOT EXISTS growth_themes (
    id                  TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    lens                TEXT NOT NULL,
    statement           TEXT NOT NULL,
    status              TEXT NOT NULL,
    created_at          TEXT NOT NULL
);
```

### 2.3 关键字段实际用法与语义事实

| 字段 | 宿主表 | 数据类型 | 实际写入值 / 逻辑规则 | 源码位置 |
| :--- | :--- | :--- | :--- | :--- |
| `session_id` | `events` | `TEXT` | 外部 Agent 会话标识（UUID 或哈希）。**`slices` 表中不存在此字段**。 | `store.py:47` |
| `timestamp` | `slices`, `events` | `TEXT` | 严格标准 ISO-8601 UTC 字符串，以 `+00:00` 结尾。 | `base.py:13-31` |
| `source` | `slices` | `TEXT` | 当前代码写死为 `'manual_feed'`。无 bubble / manual / import 区分。 | `contracts.py:23` |
| `provenance` | `events` | `TEXT` | 由 `classify(event_type)` 计算：`user_prompt` $\to$ `'user_action'`；其余事件 $\to$ `'agent_context'`。 | `attribution.py:27-37` |
| `retention_class`| `events` | `TEXT` | 由 `classify(event_type)` 计算：`user_prompt` $\to$ `'durable'`；其余事件 $\to$ `'transient'`（30天过期）。 | `attribution.py:27-37` |
| `mood_flag` | `slices` | `TEXT` | 由 `SanctuaryGuard.evaluate_text()` 正则匹配 18 个负面词汇判定：命中 $\to$ `'frustrated'`；未命中 $\to$ `'neutral'`。 | `run_companion.py:483` |
| `event_type` | `events` | `TEXT` | 9 种枚举字符串：`session_start`, `user_prompt`, `pre_tool_use`, `post_tool_use`, `tool_failure`, `task_complete`, `turn_end`, `needs_input`, `session_end`。 | `contracts.py:10-25` |

### 2.4 特殊概念与高级字段存在性事实
经对所有表执行 `PRAGMA table_info` 深度排查：
- **`episode`**：无独立物理表。`store.list_episodes()` 仅是一条 `SELECT session_id, MIN(timestamp), MAX(timestamp)... GROUP BY session_id` 的聚合查询；`hypotheses` 表中以逗号分隔存储 `session_id` 字符串（`supporting_episodes`, `counter_episodes`）。
- **`topic`**：完全不存在。
- **`salience`（显著性/重要度）**：完全不存在。
- **`embedding`**：完全不存在（无向量字段、无 blob 向量）。
- **`access_count` / `last_accessed_at`**：完全不存在。
- **`valid_from` / `last_revalidated`**：仅存在于 `insights` 表，以 `YYYY-MM-DD` 日期字符串存储。
- **`valid_until`**：完全不存在。

### 2.5 `raw_slices.jsonl` 与 SQLite `slices` 的关系
- **代码事实**：用户提交切片时，在 `run_companion.py:549-558` 中执行**双写**：先调用 `SliceStore.save()` 追加写入 `data/raw_slices.jsonl`，再调用 `ChronicleStore.record_slice()` 插入 SQLite `slices` 表。
- **冷启动与恢复事实**：`ChronicleStore.import_slices_jsonl()`（`store.py:215-245`）支持从 `raw_slices.jsonl` 幂等增量导入到 SQLite（按 `id` 执行 `INSERT OR IGNORE`）。若 SQLite 丢库，可通过 JSONL 恢复用户切片，但无法恢复 `events`。
- **一致性风险**：两者无分布式事务保证。若应用在写入 JSONL 后崩溃，会导致 JSONL 与 SQLite 短暂不一致（但在下次启动执行 `import_slices_jsonl` 时会自动对齐）。

### 2.6 Chapters Markdown 与数据库的关联事实
- **代码事实**：`ChapterGenerator.generate_chapter()`（`chapters.py:220-324`）将生成的章节内容直接落盘为 `data/chapters/chapter_{id}.md`。
- **数据库关联**：**完全无物理外键或数据库记录**。数据库中没有任何关于章节元数据（chapter_id、生成时间、覆盖区间）的记录。`ChapterGenerator.list_chapters()` 是通过实时扫盘 `data/chapters/` 目录并用正则表达式解析 Markdown 正文重构出 `GrowthChapter` 对象的（`chapters.py:326-369`）。

### 2.7 数据库迁移机制事实
- **代码事实**：`store.py:139` 仅通过 `self._conn.executescript(_SCHEMA)` 启动。
- **迁移机制**：**当前项目零迁移机制（No Alembic, No Version Table, No Migration Scripts）**。
- **真实库状态**：实测 `PRAGMA user_version = 0`。
- **向后兼容性事实**：
  - 若未来新增数据表（`CREATE TABLE IF NOT EXISTS`），现有旧数据库完全兼容，无缝创建；
  - **若未来对现有表新增字段（如给 `slices` 增加 `session_id`），`CREATE TABLE IF NOT EXISTS` 不会触发 ALTER TABLE**。直接启动会导致旧数据库缺少新列，查询时抛出 `sqlite3.OperationalError: no such column`。必须在 `ChronicleStore.__init__` 中引入 `PRAGMA user_version` 或受控的 `ALTER TABLE ADD COLUMN` 迁移逻辑。

---

## 3. Real Data Statistics（真实生产库只读审计数据）

基于本地真实 `data/companion_chronicle.db`（115k 行量级真实数据）执行只读分析，统计结果如下（执行脚本：`audit_db.py`）：

### 3.1 实体行数总览
- **Events 总数**：**115,317** 行
- **Slices 总数**：**42** 行
- **Hypotheses 总数**：**4** 行（全部处于 `candidate` 状态）
- **Insights 总数**：**0** 行（尚无双方校准确认的共识）
- **Growth Themes 总数**：**0** 行
- **Distinct Sessions（唯一会话数）**：**237** 个

### 3.2 时间跨度与对比
- **Events 时间跨度**：`2026-06-09T02:15:48.536000+00:00` 至 `2026-10-18T02:19:16.711689+00:00`（**跨度 131 天，超 4 个月**）
- **Slices 时间跨度**：`2026-10-15T15:43:57.811963+00:00` 至 `2026-10-18T01:21:49.210279+00:00`（**仅跨度约 2.5 天**）
- **数据事实推断**：Events 绝大部分来自于历史会话收割器（`HistoricalHarvester`）对过往数月 Pi/Codex/Hermes 日志的集中入库；而 Slices 是桌宠在近 3 天真实启动运行后由用户主动投喂或测试录入的。

### 3.3 Event 类型分布（Event Type Breakdown）

| 事件类型 (`event_type`) | 事件数量 | 占比 | 归因属性 (`provenance` / `retention`) |
| :--- | :--- | :--- | :--- |
| `pre_tool_use` | 52,102 | 45.18% | `agent_context` / `transient` |
| `post_tool_use` | 50,236 | 43.56% | `agent_context` / `transient` |
| `turn_end` | 3,891 | 3.37% | `agent_context` / `transient` |
| `tool_failure` | 3,668 | 3.18% | `agent_context` / `transient` |
| `user_prompt` | 3,247 | 2.82% | **`user_action` / `durable`** |
| `task_complete` | 1,803 | 1.56% | `agent_context` / `transient` |
| `session_start` | 192 | 0.17% | `agent_context` / `transient` |
| `session_end` | 178 | 0.15% | `agent_context` / `transient` |
| **总计** | **115,317** | **100.00%** | **Durable: 3,247 (2.8%) / Transient: 112,070 (97.2%)** |

### 3.4 Agent 来源分布与交叉矩阵

| Agent 来源 (`agent_id`) | 事件总数 | 占比 | 主要事件特征 |
| :--- | :--- | :--- | :--- |
| `pi` | 90,928 | 78.85% | 高频工具调用：`post_tool_use` (43.3k), `pre_tool_use` (42.8k), `tool_failure` (2.9k), `user_prompt` (1.6k) |
| `pi-desktop` | 11,115 | 9.64% | 包含大量一轮结束信号：`turn_end` (3,849), `pre_tool_use` (3,560), `post_tool_use` (3,130) |
| `hermes` | 6,824 | 5.92% | 工具链执行：`pre_tool_use` (3,237), `post_tool_use` (3,136), `user_prompt` (243), 无 `task_complete` |
| `codex` | 6,449 | 5.59% | 高频任务完成信号：`pre_tool_use` (2,507), **`task_complete` (1,801)**, `user_prompt` (1,229) |
| `pi-cli` | 1 | <0.01% | 仅 1 条历史测试会话标记 |

### 3.5 Session 事件数分布（Session Event Distribution）
对 237 个 Session 的事件总数进行统计分布分析：
- **最小值 (Min)**：1
- **最大值 (Max)**：8,054
- **中位数 (Median)**：25.0
- **平均值 (Mean)**：486.57
- **分位数分布**：P25 = 5.0，P75 = 352.0，P90 = 1,494.0，P95 = 2,386.0
- **极端两极化特征**：
  - **超长会话（>1,000 事件）**：40 个（占 16.9%）。用户在同一个会话中持续工作数天，包含成百上千次工具调用；
  - **微型碎片会话（<=3 事件）**：40 个（占 16.9%）。单次 ping、快捷测试或空会话；
  - 传统以 `session_id` 作为“一次完整任务经历（Episode）”的假设在现实长任务中发生严重形变。

### 3.6 Slices 关联性与时间邻近分布事实
- **Slices 总数**：42 条（脱敏统计显示实际仅 **18 条唯一文本**，存在多处毫秒级连击/重复提交）。
- **与 Session 的关联能力**：
  - Slices 表中没有 `session_id` 列，**无法通过物理外键精确关联到任何会话**；
  - 若采用时间窗口（$\pm 5$ 分钟）进行概率推断：42 条切片在时间轴上均能落入某个 Agent 事件的 $\pm 5$ 分钟窗口内（0 条绝对离线孤立切片）；
  - **但存在严重的多会话并发歧义**：实测发现有切片在 $\pm 5$ 分钟内同时与 3 个并发活跃的 Session（涉及 `pi` 和 `codex` 两个不同 Agent）发生时间交叠，纯靠时间戳无法断定用户当时在向哪个 Agent 的任务输入。

---

## 4. Source Fidelity Matrix（各数据源保真度与字段完整度矩阵）

| 维度 / 字段 | Pi CLI (Harvested) | PI-Desktop (Harvested) | Codex CLI (Harvested) | Hermes DB (Harvested) | Realtime `/api/event` |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`timestamp`** | ISO-8601 UTC（毫秒） | ISO-8601 UTC（毫秒） | ISO-8601 UTC（毫秒） | ISO-8601 UTC（毫秒） | 服务端接收时打时间戳（`now(UTC)`） |
| **`session_id`** | 会话文件 stem / UUID | 会话文件 stem / UUID | `payload.session_id` | `sessions.id` (整型或UUID) | 客户端显式传递（缺省为 `'default'`） |
| **`user_prompt` 标记**| 有 (`role == "user"`) | 有 (`role == "user"`) | 有 (`role == "user"`) | 有 (`role == "user"`) | 有（依赖 hook 显式上报） |
| **Prompt 文本内容** | **丢弃（隐私断言）** | **丢弃（隐私断言）** | **丢弃（隐私断言）** | **丢弃（隐私断言）** | **丢弃 / 不传递** |
| **`tool_name`** | 有（从 toolCall 提取） | 有（从 blocks 提取） | 有（从 function_call 提取）| 有（从 tool_calls 提取） | 有 |
| **`error_message`** | 仅标准占位符 (`{tool} failed`) | 仅标准占位符 (`{tool} failed`) | 仅标准占位符 (`{tool} failed`) | 简要错误标记 (`{tool} error`)| 客户端透传错误摘要 |
| **`task_complete`** | 无（Pi 日志无此事件） | 极少 (2 条) | **高频 (1,801 条)** | 无（Hermes 无此事件） | 依赖 hook 显式上报 |
| **`turn_end`** | 无 | **高频 (3,849 条)** | 极少 (42 条) | 无 | 依赖 hook 显式上报 |
| **Repo / Workspace** | **无** | **无** | **无** | **无** | **无** |
| **Task / Issue ID** | **无** | **无** | **无** | **无** | **无** |

### 核心差异总结：
1. **Harvester 历史收割与 Realtime 实时数据的关键差异**：
   - 历史收割数据的时间戳忠实还原自日志文件内部（具备高精度相对顺序）；
   - 实时端点 `/api/event` 的事件若客户端未携带时间戳，将在服务端生成。如果网络抖动或批量发送，可能导致实时事件的时间戳发生微小颠倒；
   - 历史数据覆盖面极广（131天），但部分事件类型存在源头缺失（如 Pi 无 `task_complete`，Hermes 无 `turn_end`）。

---

## 5. Event ↔ Slice ↔ Session Linkability（可关联性深度审计）

本节直接回答核心问题：**“目前系统能否回答：某条用户 Slice / 用户输入，是在哪个任务、哪个 Session、哪些 Agent Event 前后产生的？”**

### 5.1 事实断定

#### 1. 当前可以可靠重建什么（Reliably Reconstructible）：
- **单个 Session 内的行为事件因果流**：在同一个 `session_id` 下，可以 100% 按照 `timestamp ASC` 重建其时间轴。可以明确确定在特定 Session 内：
  - 哪个工具在何时被调用（`pre_tool_use`）；
  - 工具是否报错（`tool_failure`）及后续是否紧跟用户指令（`user_prompt`）；
  - 该会话的开始与结束时间、总事件数与涉及的 Agent。
- **单个切片的绝对产生时间**：每条 Slice 记录了精确的 UTC 创建时间戳（精确到微秒）。

#### 2. 当前只能概率性推断什么（Probabilistically Inferable Only）：
- **Slice 与 Session 的归属关系**：
  - 只能通过时间窗口启发式推断（例如判定 `event.timestamp` 在 `slice.timestamp - 5min` 到 `+ 5min` 区间内）；
  - **当单 Agent 独占会话时**，这种时间邻近推断准确率较高（可达 80%~90%）；
  - **当多 Agent 并行或后台任务执行时**，推断将退化为多值歧义（无法判断用户是针对 Pi 的代码重构吐槽，还是针对 Codex 的执行反馈输入）。
- **用户 Prompt 触发的具体工具链**：
  - 可以推断某个 `user_prompt` 事件后直到下一个 `user_prompt` 之间发生的所有 `pre_tool_use` 属于该轮对话；
  - 但因缺乏 Prompt 文本，无法得知用户到底下达了什么业务指令。

#### 3. 当前完全没有记录、无法恢复什么（Completely Unrecorded & Unrecoverable）：
- **Prompt 文本内容**：所有历史会话和实时会话中的用户提问、指令文本，已被隐私防线彻底过滤，数据库中**没有任何字符沉淀**。
- **任务（Task）、项目（Project）、工作区（Workspace）、仓库（Repo）标识**：
  - 数据模型中**完全不存在** `repo_path`、`project_name`、`workspace_dir`、`task_id` 字段；
  - 无法判断 Session A 和 Session B 是否在同一个 Git 仓库中工作，无法判断一个跨越三天的重构是否属于同一个 Task。
- **一个 Session 内的多个独立子任务**：
  - 当用户在同一个长期 CLI 窗口（例如持续 8,000 事件的超长 Session）中连续执行了 5 个完全无关的编码需求时，系统**没有任何语义或业务边界信号**能将其自动解耦为 5 个任务。
- **跨 Session 的长期任务**：
  - 当一个任务因为重启 CLI 或切换 Agent 分散在 3 个 Session 时，系统**没有任何上层线索**将其拼接为同一个生命周期任务。

---

## 6. Current Inference Pipeline（当前心智推断完整调用链）

### 6.1 完整调用链追踪
```
ChronicleStore
  │
  ├─► PatternBuilder.build_patterns()
  │     │
  │     └─► HypothesisEngine.synthesize()
  │           │
  │           ├─► SelfModelManager.apply_calibration()
  │           │     │
  │           │     └─► ChronicleStore.save_hypothesis() / save_insight()
  │           │
  │           └─► ChapterEligibilityGate.evaluate()
  │                 │
  │                 └─► ChapterGenerator.generate_chapter()
  │                       │
  │                       └─► ChronicleViewerWindow (UI呈现与人工校准)
```

### 6.2 模块契约与触发机制详查

| 模块 / 函数 | 触发时机 | 输入 | 输出 | 是否定时 / 常驻 |
| :--- | :--- | :--- | :--- | :--- |
| `PatternBuilder.build_patterns()` (`src/core/patterns.py:45`) | 1. 打开自模型页面 (`_refresh_self_model`)<br>2. 手动点击“重新挖掘”<br>3. 章节生成前评估 | `store.list_episodes(limit=100)` (仅 events 表) | `list[BehavioralPattern]` (最多3个模式) | **否**。仅在 UI 刷新或章节生成时按需调用。 |
| `HypothesisEngine.synthesize()` (`src/core/hypotheses.py:73`) | 紧随 `build_patterns()` 执行 | `list[BehavioralPattern]` | `list[DevelopmentHypothesis]` | **否**。纯函数计算。 |
| `SelfModelManager.apply_calibration()` (`src/core/self_model.py:91`) | 用户在 UI 点击校准按钮（是/部分/否） | `(hypothesis, response, user_comment)` | `(updated_hyp, insight, revised_hyp)` | **否**。纯事件触发。 |
| `ChapterGenerator.generate_chapter()` (`src/core/chapters.py:220`) | 用户在 UI 点击“生成章节”按钮 | `ChronicleStore` 统计指标、模式、共识、采样会话 | `GrowthChapter` (Markdown 文件) | **否**。手动触发。 |

### 6.3 假说生成、去重、置信度与反例计算事实

#### 1. 假说去重机制：
- 在 `HypothesisEngine` 中，`hypothesis_id` 生成规则直接写死为 `f"hyp_{pat.pattern_id}"`（例如 `hyp_pat_friction_recovery`）。
- 写入数据库使用 `store.save_hypothesis()` $\to$ `INSERT OR REPLACE INTO hypotheses`。
- **因此同一模式生成的假说在数据库中通过固定主键直接覆盖，不存在自然去重或语义聚类**。

#### 2. 置信度（Confidence）计算公式（代码事实：`src/core/hypotheses.py:178-186`）：
```python
ratio = pattern.support_ratio  # supporting / (supporting + counter)
support_cnt = len(pattern.supporting_episodes)

if support_cnt >= 4 and ratio >= 0.75:
    return ConfidenceLevel.HIGH
if support_cnt >= 2 and ratio >= 0.5:
    return ConfidenceLevel.MODERATE
return ConfidenceLevel.LOW
```
- 置信度纯粹是基于会话数量和正反支持率的**硬编码离散阶梯**，不包含任何贝叶斯更新或先验概率模型。

#### 3. “正例 46 处 / 反例 7 处 / high confidence”审计取证（Bug/现象溯源）：
- **统计单位事实**：**统计单位 100% 为 `session_id`**（即 `Episode.session_id`）。
- **取证过程**：
  - 在 `src/core/patterns.py:81-105` 中，遍历每个 `ep in episodes`，检查该 session 内是否存在 `tool_failure`，以及其后是否有 `user_prompt`。
  - 若在报错后出现 prompt，将 `ep.session_id` 放入 `intervened_episodes`（正例）；否则放入 `autonomous_healing_episodes`（反例）。
  - 在当前真实生产库中执行查询验证：`hyp_pat_friction_recovery` 的正例列表包含 46 个 session ID，反例列表包含 7 个 session ID。
  - $46 / (46 + 7) = 0.868 \ge 0.75$ 且 $46 \ge 4$，因而输出为 `high confidence`。
  - **结论：此处的“46 处”绝非 46 个事件或 46 个切片，而是 46 个发生过报错纠偏的独立会话！**

#### 4. 状态演化与淘汰生命周期事实：
- **状态流转**：`candidate` $\to$（用户点击 YES）$\to$ `confirmed`；或 $\to$（用户点击 NO）$\to$ `rejected`；或 $\to$（用户点击 PARTLY）$\to$ `calibrating` 并衍生出 `hyp_..._revised`（`candidate`）。
- **Rejected 是否会重新出现**：
  - 代码事实：若用户在 UI 拒绝了假说，状态变为 `rejected`；
  - 但在 `chronicle_window.py:594-597` 中，若用户点击了“重新挖掘”（`_re_mine_self_model`），系统会再次调用 `fresh_hyps = HypothesisEngine().synthesize(pats)`，并无差别执行 `self.store.save_hypothesis(h)`。
  - **因为 `fresh_hyps` 中的主键是硬编码的 `hyp_{pattern_id}`，且初始状态写死为 `candidate`，`save_hypothesis` 执行 `INSERT OR REPLACE` 会直接将用户此前标记为 `rejected` 的记录强行覆盖回 `candidate`！** 这是一个关键的生命周期覆盖缺陷。
- **过期与重评估**：
  - `ConfirmedInsight` 一旦写入，除非用户手动点击“退休”（`retire_insight`），否则其状态永远保持 `active`；
  - **新到达的数据和证据绝对不会触发旧 Insight 的重新评估或自动撤销**。
- **反例数据模型（Contradictory Evidence）**：
  - 仅以逗号分隔的字符串存储在 `hypotheses.counter_episodes` 列；
  - 晋升为 `ConfirmedInsight` 后，**反例字段被彻底丢弃**（`insights` 表中根本没有 `counter_episodes` 字段）。

---

## 7. Current Memory Retrieval Audit（日常检索实现与离线失效取证）

### 7.1 当前检索实现机制分析（代码事实：`src/memory/retriever.py`）
日常伴生体在响应气泡或对话输入时，调用 `run_companion.py:_recall_memories()` $\to$ `MemoryRetriever.recall_records(query, limit=3)`。其内部由三道按序匹配的通道组成：

1. **时间意图通道（Temporal Intent）**：
   - 正则检测“昨天”、“前天”、“大前天”、“今天”、“X天前”；
   - 换算为本地目标日期的 00:00:00 至 23:59:59，转为 UTC ISO 字符串区间；
   - 执行 `SELECT * FROM slices WHERE timestamp >= ? AND timestamp <= ? ORDER BY timestamp DESC LIMIT 50`；
   - 一旦命中明确日期，**直接返回该日期的切片并立即终止**，不进入后续通道。
2. **关键词子串通道（Keyword Substring Search）**：
   - 提取 2 位以上英数单词；
   - 中文文本剔除标点与 51 个硬编码停用词（`DEFAULT_STOP_WORDS`，如“你”、“我”、“之前”、“昨天”、“聊过”等）；
   - 对剩余词段，若长度 $\ge 2$ 计入关键词；若长度 $>2$，穷举生成 2 字和 3 字 N-gram（例如“感觉好累”生成 `['感觉好累', '感觉', '觉好', '好累', '感觉好', '觉好累']`）；
   - 对每个提取的关键词，按序执行 SQLite 查询：
     `SELECT * FROM slices WHERE content LIKE '%kw%' ORDER BY timestamp DESC LIMIT 10`；
   - 去重并累加候选，满 3 条即截断返回。
3. **开放式记忆意图通道（Open-ended Memory Intent）**：
   - 检查是否命中 16 个意图词（“还记得”、“聊过什么”、“关于我”、“记忆库”等）；
   - 执行 `SELECT * FROM slices ORDER BY timestamp DESC LIMIT 30` 获取最新切片。
4. **噪声过滤与 Prompt 呈现**：
   - 过滤短于 2 字、处于 `DEFAULT_TRIVIAL_SLICES`（如“hi”、“测试”、“嗯嗯好的”）及自身为元提问的切片；
   - 注入 Prompt 格式（`personality.py:280`）：`[{YYYY-MM-DD}] 用户提到: {content}`。
   - **完全无排序打分、无语义距离、无情绪加权、无访问频次衰减**。

### 7.2 离线语义检索评测事实（10 组真实案例对照）

在当前真实 42 条切片库（包含 18 条唯一真实文本）上，执行预设的 10 组离线语义测试（执行脚本：`detailed_retrieval_test.py`），结果如下：

| 编号 | 测试输入 Query | 预期意图 / 语义目标 | 提取的 Keywords / N-grams | 实际召回结果 (Recalled) | 评测结论与缺陷定性 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | `感觉好累想休息一下` | 劳累/受挫（库中有“真烦死了全搞砸了”） | `['感觉好累', '感觉', '好累', '休息']` | **0 条 (空)** | **False Negative (漏召回)**：字面完全无交集，同义情绪无法感知。 |
| **TC-02** | `报错怎么解决` | 调试阻力（库中有“这代码烦死了全搞砸了”） | `['报错', '解决']` | **0 条 (空)** | **False Negative (漏召回)**：用户吐槽使用口语，无法与技术词“报错”字面匹配。 |
| **TC-03** | `代码写得差不多了` | 正常收工/完结（积极平静） | `['代码写', '代码', '差不多']` | **2 条**：<br>1. `这代码真烦死了全搞砸了`<br>2. `这代码烦死了😡，全搞砸了` | **False Positive & 语义漂移（严重缺陷）**：仅凭字面“代码”子串，**把历史严重暴躁崩溃切片召回给正向收工的用户**！ |
| **TC-04** | `有bug需要修复` | 缺陷定位（中英术语通用） | `['bug', '需要', '修复', 'bu', 'ug', 'g需']` | **0 条 (空)** | **False Negative & 英文噪声**：英文与中文混合产生无意义字符碎片，无语义对齐。 |
| **TC-05** | `正在重构桌面端组件`| 项目重构（库中有“优化你的形象和行为”）| `['重构', '桌面', '组件']` | **0 条 (空)** | **False Negative (漏召回)**：任务动作表达不同，无法关联。 |
| **TC-06** | `你还记得前天我们聊了什么吗` | 时间意图（动态定位 2 天前） | `[]`（命中前天意图） | **2 条**（落入前天时间窗口的切片） | **Pass (部分准确)**：但严格受限于用户当前测试执行日期与切片日期的物理天数差。 |
| **TC-07** | `你对我有什么记忆` | 开放式回忆（概括性了解） | `['记忆']` | **3 条**：<br>1. 优化交流功能...<br>2. 一直在开发桌宠...<br>3. 你好 很高兴认识你 | **Pass (部分准确)**：触发了兜底全局最新扫描，但第 3 条问候噪声未能被彻底过滤。 |
| **TC-08** | `测试一下功能` | 含有技术泛词的随意输入 | `['测试', '功能']` | **2 条**：<br>1. 测试发消息自动探头<br>2. 优化交流功能... | **Irrelevant Recall (无关噪音召回)**：因命中“功能”二字，把不相关的长切片生硬捞出。 |
| **TC-09** | `喝水休息一会儿` | 休息关怀（生活节律） | `['喝水', '休息', '一会儿']` | **0 条 (空)** | **False Negative (漏召回)**：库中缺乏字面词，零召回。 |
| **TC-10** | `开发进度如何` | 询问开发进展 | `['开发进度', '开发', '进度']` | **1 条**：`挺顺的，一直在开发桌宠项目` | **Pass (字面命中)**：恰好包含“开发”二字，命中。 |

### 7.3 检索缺陷总结：
- **False Negative 占比约 60%**：只要用户换用同义词、口语表达或中英术语，LIKE 检索彻底失效。
- **False Positive 存在情绪灾难风险**：如 TC-03，用户在轻松状态下提到“代码”，却被系统召回“真烦死了全搞砸了”，若注入 LLM 会导致伴生体突然莫名其妙地抚慰用户情绪，破坏真实相处信任。

---

## 8. Episode Construction Feasibility（经历分段可行性审计与仿真）

针对生产库中的 115,346 条有序事件流，审计分析未来构建 `Episode` 层时可利用的边界信号，并执行了三种分割模型的只读仿真（执行脚本：`simulate_episodes.py`）：

### 8.1 边界模型仿真数据对比

| 仿真方案 | 分割逻辑依据 | 生成 Episode 总数 | 最小/最大事件数 | 事件数中位数 | 超长 Episode (>1000事件) | 极短碎片 (<=3事件) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Model A: Current Session** | `session_id` 即 Episode（当前现状） | **237** | 1 / 8,054 | 25.0 | **40 个 (16.9%)** | **40 个 (16.9%)** |
| **Model B: Inactivity Gap** | Session 内部若相邻事件间隔 $> 30$ 分钟则断开 | **743** | 1 / 2,607 | 25.0 | **19 个 (2.6%)** | **167 个 (22.5%)** |
| **Model C: Prompt Turn Burst**| 以每个 `user_prompt` 为边界切分为轮次 Episode | **3,410** | 1 / 1,324 | **2.0** | **1 个 (<0.1%)** | **1,867 个 (54.8%)** |

### 8.2 信号可行性与缺陷定性分析：
1. **Model A（纯 Session ID）**：
   - 缺陷：**严重的超长会话污染**。16.9% 的会话事件数超过 1,000，最高达 8,054。这些会话往往跨越数天，包含多个完全不相关的开发任务，整体打包导致任何单一模式计算被极端稀释；同时也有 16.9% 的空测碎片。
2. **Model B（Session + 30分钟 Inactivity Gap）**：
   - 表现：**最为均衡的物理分割方案**。超长会话从 40 个压制到 19 个（仅占 2.6%），有效切开了隔夜未关闭的 CLI 进程；同时保留了连续开发的工作流完整性。
3. **Model C（以 User Prompt 划分）**：
   - 缺陷：**极度过碎（Over-fragmentation）**。超过 54.8% 的分段事件数 $\le 3$。一次简单的问答（Prompt $\to$ Tool $\to$ TurnEnd）被单独切割，丢失了“在遇到报错后连续重试 3 次”这类复杂阻力排查的上下文全景。
4. **现有数据对 Episode 的最高支持度**：
   - **支持度评估**：当前数据**最适合支持“Session + 30分钟空闲间隔（Inactivity Gap）”的双层复合切分**。纯语义任务切分在缺乏 Prompt 文本和 Repo 标识的情况下无法进行确定性计算。

---

## 9. Insight Runtime Consumers（确认认知运行时消费审计）

全局符号追踪 `insights` 与 `ConfirmedInsight` 在代码库中的所有引用与消费场景：

| 潜在消费场景 | 是否实际消费 | 代码调用点与审计事实 | 结论定性 |
| :--- | :--- | :--- | :--- |
| **Personality Prompt** | **否** | `src/core/personality.py:build_system_prompt()` 仅接收 `memories`，从未接收 `insights`。 | **完全未消费** |
| **LLM Dialogue Prompt**| **否** | `src/core/llm_client.py:CompanionAIEngine.request_reply()` 无任何 insight 注入逻辑。 | **完全未消费** |
| **Speech Bubble 气泡输出** | **否** | `src/body/speech_bubble.py` 纯表现层，只接收文字渲染。 | **完全未消费** |
| **Proactive Reflection** | **否** | 项目当前无后台主动反思守护线程。 | **完全未消费** |
| **Sanctuary 避风港** | **否** | `src/core/sanctuary.py` 纯正则匹配用户输入，不读取自模型。 | **完全未消费** |
| **Circadian 节律感知** | **否** | `src/core/circadian.py` 仅计算当前小时，不读取共识。 | **完全未消费** |
| **Life Scheduler** | **否** | 架构中尚无 Life Scheduler 模块。 | **完全未消费** |
| **Body State 姿态控制** | **否** | `src/body/controller.py` 仅响应直接 action 与 state。 | **完全未消费** |
| **Intervention Cooldown**| **否** | `src/core/intervention.py` 仅依赖 overwork 时间和冷启动天数。 | **完全未消费** |
| **Chronicle Window UI** | **是** | `src/body/chronicle_window.py:619`：在“共同认知”Tab 的列表中展示已确认条目。 | **仅用于展示** |
| **Chapter Generation** | **是** | `src/core/chapters.py:138, 239`：作为资格门判定依据之一，并拼装为 Prompt 字符串提供给大模型。 | **仅用于章节生成** |

### 核心结论：
`ConfirmedInsight` 在当前系统中**彻底退化为死数据（Dead Data Sink）**。除了在 UI 上供用户翻阅以及在生成章节时作为一小段静态提示词外，**对伴生体的日常桌面行为、主动发声、关怀时机与对话风格产生的影响为绝对的 0%**。

---

## 10. ChapterGenerator 事实审计与时间演化虚假叙事归因

### 10.1 ChapterGenerator 输入全景事实（代码事实：`src/core/chapters.py:237-275`）
`ChapterGenerator.generate_chapter()` 向 LLM 发送的全部信息结构如下：

1. **统计事实**：
   - 记录周期：`earliest` 至 `latest`（仅取所有会话最小/最大日期的标量文本，例如 `2026-06-09 至 2026-10-16`）；
   - 累计经历：`stats['episodes']` 个研发会话，`stats['events']` 条客观行为事件（仅是全局总数数字）。
2. **挖掘出的稳定模式**：
   - `patterns_summary`：遍历 `patterns` 拼接 `f"- [{p.pattern_id}] {p.description} (支持会话: {len(p.supporting_episodes)})"`。
3. **双方已达成的共识**：
   - `insights_summary`：拼接 `f"- [共识] {ins.statement} (批注: {ins.user_confirmation_text})"`。
4. **近期典型会话采样**：
   - `sample_episodes`：取 `episodes[:10]` 拼接 `f"- Session {ep.session_id[:12]}: 事件数 {ep.event_count}, Agents {ep.agent_ids}"`。

### 10.2 关键缺失项审计：
- **是否传 Slice 原文**：**否！0 条切片内容进入 Prompt**。
- **是否传具体 Episode 内部细节**：**否！仅传了前 10 个会话的前 12 位 UUID 和数字**。
- **是否传时序演进（Chronology）**：**完全没有！没有任何前期与后期的对比切片或分段统计**。
- **是否传反例（Counter Evidence）**：**否！反例会话数完全被省略**。
- **Session ID 样本的价值**：仅传了类似 `pi-48b5b09e-`、`01a14556-125` 的截断哈希，大模型仅能将其作为不可解释的符号用在 Markdown 中装点真实感（如生成的章节中的：`在如 pi-48b5b09e- 这类重型任务中...`）。
- **叙事防火墙（Narrative Firewall）**：
  - 系统 Prompt（`NarrativeFirewall.get_system_prompt()`）声明了 5 条红线；
  - 产出后置清洗（`NarrativeFirewall.sanitize_narrative()`）仅是对 9 个固定词汇（如“令人钦佩”、“卓越的智慧”、“你应该放松”）的**纯字符串替换（粗暴替换为“踏实的投入”）**；
  - **完全不存在任何事实性校验或幻觉约束检查**。

### 10.3 虚假时间演化叙事（"The Shift" Hallucination）根因定位
在已生成的真实文件 `data/chapters/chapter_01_20261016.md` 中，清晰记录了如下文字：
> *“起初在面对复杂任务时，交互往往伴随着即时、密集的确认；但随着会话推进，协作形态逐步转变为「大段放权与精准纠偏」……我的工作重心也相应发生了转移——从等待逐条指令的零散响应者，转变为在长程任务中自主推进行动……”*

**该时间变化主张（Temporal Claim）的产生根因已被彻底定位**：
1. **Prompt 强指令索取转移**：在 `chapters.py:272` 中，Prompt 模板硬性要求大模型输出 Markdown 二级标题 `## 1. 伴生体的观察与心智转移（The Shift）`，并举例示范标题 `# 章节标题（如：《从事必躬亲到学会委派》、《在长任务中寻找节奏》）`；
2. **缺乏时序证据约束**：大模型接收到了“The Shift（心智转移）”与“从事必躬亲到学会委派”的强暗示，但输入数据中只提供了全生命周期的静态汇总统计（例如 `pat_hands_off_delegation` 累计支持 64 次），**根本没有提供“第 1 个月放权几次 vs 第 4 个月放权几次”的时序事实**；
3. **大模型为满足 Prompt 格式而必然产生幻觉**：面对“写出心智转移”的要求与空白的时序证据，LLM 只能利用其语料先验，捏造出由“起初密集确认”到“逐步转变为大段放权”的虚构演变过程。

---

## 11. Local Semantic Stack Feasibility（本地语义与轻量化能力可行性评估）

### 11.1 当前 LLMClient 接口与能力事实（代码事实：`src/core/llm_client.py`）
- **接口形式**：原生 Python 标准库实现（`urllib.request`），零外部 SDK 依赖。
- **协议兼容性**：支持标准 OpenAI `/v1/chat/completions` 协议。通过 `LLMConfig` 统一配置 `base_url`, `api_key`, `model`，原生兼容 Ollama、DeepSeek、OpenAI、vLLM、OneAPI。
- **结构化输出（Structured Output）**：**不支持** `response_format={"type": "json_object"}`，完全依赖 Prompt 自然语言指示与正则后处理。
- **模型能力探测（Capability Detection）**：**无**。
- **重试、超时与降级**：
  - 支持配置超时时间（`timeout_seconds`，默认 25s）；
  - **无自动重试机制（Zero Retry）**；
  - 具备优雅降级：在 `_GenerateRunnable.run()` 中捕获 `Exception` 后，自动回退到预设的静态对话语料（`PersonalityFallback`，`src/core/personality.py:32`）；
  - **离线解耦保证**：当 `config.enabled = False` 或网络离线时，系统完全退回本地预置词条，UI 与核心桌宠逻辑 100% 正常运行，不阻塞主线程。

### 11.2 当前 Python / SQLite 运行环境实测数据
- **Python 版本**：3.11.15 (MSC v.1944 64 bit Windows)
- **SQLite 版本**：3.53.1
- **SQLite FTS5 支持状态**：**已原生内置并启用**（经实测 `CREATE VIRTUAL TABLE USING fts5` 及 MATCH 语法执行完全成功）。
- **已安装依赖库**：`PySide6` (6.12.0), `pydantic` (2.14.1), `Pillow`, `pynput`, `platformdirs`。
- **未安装依赖库（均为 None）**：`numpy`, `torch`, `transformers`, `sentence-transformers`, `onnxruntime`, `sqlite-vec`, `chromadb`, `faiss`, `scipy`, `sklearn`。

### 11.3 五种轻量语义检索方案工程兼容性可行性对比

| 方案 | 额外依赖与体积 | Windows / CPU 兼容性 | 内存与常驻开销 | 离线能力 | 首次启动耗时 | 12万行场景匹配度 | 综合可行性评估 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **1. SQLite FTS5 only** | **0 MB**（内置） | **最高**（无外部编译） | **极低**（<5 MB） | 100% 本地离线 | 0 毫秒（即时） | 优秀（针对 42 条切片即时生效，但需解决中文分词） | **可行性极高（MVP推荐）**。<br>已知限制：SQLite 原生分词对 2 字中文失效，需配合紧凑纯 Python n-gram/前缀索引。 |
| **2. FTS5 + 纯 Python 内存向量 (BM25 + Cosine)** | **0 MB**（纯 Python） | **最高** | **低**（切片数少时内存 <10 MB） | 100% 本地离线 | 0 毫秒 | 极佳（仅对几十到数千条切片与共识做语义排序） | **可行性极高**。<br>无需任何 C/C++ 扩展或模型，在内存中维护轻量 TF-IDF 或调用已有 LLM API 提取特征。 |
| **3. FTS5 + `sqlite-vec`** | 动态链接库 (~2-5 MB) | **中等偏低**（Windows DLL 兼容与 PyInstaller 打包风险） | 极低 | 100% 本地离线 | 毫秒级 | 优秀 | **中等可行性**。<br>Windows 下分发 native sqlite extension 存在打包和环境路径加载风险。 |
| **4. ONNX Embedding + SQLite** | `onnxruntime` (~50-80 MB) + 模型文件 (~30-50 MB) | **高**（纯 CPU ONNX 稳定） | **中等**（常驻内存增加 80~150 MB） | 100% 本地离线 | 模型加载需 1~2 秒 | 极佳 | **后期演进可行**。<br>引入 ONNX 依赖会显著增大轻量桌宠的分发安装包体积，打破现有“零重型依赖”准则。 |
| **5. Sentence-Transformers + Torch** | `torch` + `transformers` (**>1.5 GB**) | **低**（体积严重超标） | **极高**（常驻内存 >500 MB） | 本地离线 | 首次加载需 3~5 秒 | 过度设计 | **彻底不可行**。<br>严重违背常驻桌面轻量伴生体设计原则。 |

---

## 12. Migration & Compatibility Constraints（数据迁移与兼容性硬约束）

1. **零破坏向后兼容**：
   - 现存 `data/companion_chronicle.db` 已沉淀 115,317 条真实历史事件与 42 条切片，未来升级严禁删库重建；
   - 新增表（如 `episodes`, `evidence_ledger`）可安全使用 `CREATE TABLE IF NOT EXISTS`；
   - **向后兼容陷阱**：若对现存表 `slices` 新增列（如 `session_id`、`salience`），必须编写版本感知或防御式检查：
     ```python
     cols = [r["name"] for r in conn.execute("PRAGMA table_info(slices)").fetchall()]
     if "session_id" not in cols:
         conn.execute("ALTER TABLE slices ADD COLUMN session_id TEXT NOT NULL DEFAULT ''")
     ```
2. **读写分离与并发保证**：
   - 生产库已运行于 WAL 模式（`PRAGMA journal_mode=WAL`），该配置必须在 V2 中延续；
   - 必须保持 `check_same_thread=False` 与只读连接（`?mode=ro`）用于异步检索与后台分析，严禁读写锁死 UI 渲染线程。

---

## 13. Privacy & Invariants（隐私安全与规范铁律事实）

经过对 `HISTORICAL_HARVESTING_SPEC.md`、`SPEC.md` 与 `AGENTS.md` 的对照审计，确认以下各项属于系统不可破坏的架构铁律（Invariants）：

1. **三零隐私铁律（Zero-Prompt / Zero-CoT / Zero-Output）**：
   - 历史与实时 Agent 事件中**绝对禁止捕获与持久化 Prompt 文本**；
   - **绝对禁止捕获思维链（Reasoning / CoT）**；
   - **绝对禁止捕获工具返回详情的大段输出**。
   - 代码现状：`PiDesktopParser`、`CodexCliParser`、`HermesDbParser` 均在源码中严格实现了丢弃逻辑，数据中确无任何泄漏。
2. **切片数据边界（Slice Text Authority）**：
   - `slices` 表**允许且必须保留用户原始文本**（作为 `user_explicit` 的唯一凭证）；
   - 严禁将未脱敏的用户切片直接大批量暴露在外部网络未鉴权接口中。当前 HTTP 接口 `/api/chronicle/*` 严格通过 `is_loopback_client()` 实行回环限定（非 127.0.0.1 来源 403 阻断）。
3. **叙事防火墙隔离原则（Narrative Firewall）**：
   - AI 生成的人生章节与总结性文本**绝对不得反向写回 `events` 或 `slices` 表**作为下一轮心智推断的事实证据；
   - 防止系统陷入“AI 瞎编 $\to$ 存入证据 $\to$ 强化错误推断”的自强化怪圈。
4. **用户删除行为的级联影响规范（Cascade on Delete）**：
   - **事实状态：【未定义】**。
   - 现有代码和 Spec 中只实现了 `ChronicleStore.prune()`（基于 TTL 定期物理删除 `transient` 事件）。
   - 若用户主动在界面删除某条 `slice` 或某个 `session`，其派生的 `BehavioralPattern`、`DevelopmentHypothesis`、`ConfirmedInsight` 以及已经生成的 Markdown 章节是否需要同步回滚或删除，**当前规范与代码均没有任何定义与实现**。

---

## 14. Test Coverage Inventory（现有自动化测试覆盖事实）

当前工程包含 **23 个测试文件，159 项自动化测试**，全量执行通过率 100%。与 Chronicle / Self Model 核心链路直接相关的测试分布如下：

| 测试文件 | 用例数 | 覆盖的核心模块与行为 |
| :--- | :--- | :--- |
| `tests/test_memory.py` | 12 | `ChronicleStore` 基础读写、去重、JSONL 幂等导入、`prune()` 衰减、`list_episodes` 聚合 |
| `tests/test_patterns_and_hypotheses.py` | 5 | `PatternBuilder` 沉默原则（样本不足）、报错因果恢复判定、反例提取、`HypothesisEngine` 映射 |
| `tests/test_self_model.py` | 7 | `SelfModelManager` 校准状态机（YES/PARTLY/NO/NOT_NOW）、共识生成与退休、3个活跃主题上限 |
| `tests/test_chapters.py` | 5 | `ChapterEligibilityGate` 四道门检查、`NarrativeFirewall` 谄媚词汇替换、`ChapterGenerator` Markdown 解析 |
| `tests/test_memory_retriever.py` | 7 | `MemoryRetriever` 相对日期解析（昨天/前天）、开放式意图、噪声过滤、Prompt 格式组装 |
| `tests/test_history_harvester.py` | 8 | 多 Agent 历史解析器（Pi, Codex, Hermes）、时间戳归一化、Dry-run、幂等入库 |
| `tests/test_chronicle_http.py` | 4 | Chronicle 只读 HTTP API、回环 IP 拦截（403）、统计与搜索端点 |
| `tests/test_chronicle_window.py` | 4 | UI 界面列表渲染、校准交互弹窗、历史导入对话框联动 |

**测试事实定性**：现有测试套件非常扎实地保护了 Phase 2 原有设计的契约（如零 Prompt 泄露、状态机流转、衰减规则）。但测试中使用的全是仅含几条事件的 Memory Mock 数据，**未能暴露出真实 115k 规模下的会话极度超长、语义漏召回与时序脑补等系统性现实缺陷**。

---

## 15. Unknowns / Missing Evidence（未知项与缺失证据清单）

审计中发现以下事实信息在当前代码库与本地数据中**完全缺失，无法下定论**：

1. **真实的跨 Agent 任务关联图谱**：无法得知 131 天里的某次重构到底是由哪个 Agent 开头、哪个 Agent 结尾，缺乏统一的任务 Session 桥梁。
2. **切片的实际语义分布比例**：由于 42 条切片中大多为桌宠功能上线初期的联调测试词条（“测试”、“你是谁”、“挺顺的”），缺乏用户长达数月的真实工作切片样本，无法断定真实用户切片中事实、偏好、目标与感受的自然稳态分布。
3. **用户物理删除数据后的级联预期**：用户在桌宠端删除切片或在外部清空 Agent 历史时，心智层应该“装作不知道”还是“立刻遗忘派生共识”，在心理学与工程层均属**未定义**。

---

## 16. Facts That V2 Design Must Respect（V2 设计必须尊重的既成事实）

在下一步设计 Chronicle V2 / Evidence Architecture 时，必须以此处总结的不可辩驳的硬事实为底线：

1. **事实 1：切片不是日志，不能强求用户写结构化元数据**。
   用户在 Slice Feeder 输入时追求的是瞬态与随手（平均长度仅 6.6 字）。切片元数据补齐必须由后台轻量算法隐式推断完成，严禁在 UI 界面增加表单强迫用户选择“这是哪个会话/哪个任务/什么情绪”。
2. **事实 2：`session_id` 绝对不能等同于 `Episode`**。
   真实数据证明会话长度两极分化严重（最高达 8,054 事件，跨越数天）。V2 的 Episode 必须是**切片驱动或时间空闲窗口（如 30-min Inactivity Gap）切分的局部任务段**。
3. **事实 3：Prompt 文本绝不可能从历史遥测中找回**。
   三零隐私铁律不可动摇。V2 的 Evidence Ledger 必须接受“用户指令仅有时间与存在性，而无内容文本”的客观事实，通过前后工具调用签名推断意图，绝不可假设能够回溯 Prompt。
4. **事实 4：FTS5 是本地搜索的底线起点，禁止引入重量级 Torch 依赖**。
   当前环境已经证明原生 FTS5 可用，而 ML 依赖为 0。V2 的语义检索必须保持纯 CPU、低内存开销（FTS5 + 纯 Python 向量打分），严禁给常驻桌宠背负数百兆模型包袱。
5. **事实 5：没有时序分段证据，就坚决不许写“The Shift”**。
   V2 若要生成包含“逐渐”、“转变为”等时序词汇的章节，必须在 Prompt 前置输入中显式提供分阶段的量化对比事实（例如 Period A 支持率 vs Period B 支持率）。证据不足时，章节必须保持静态现状描述，禁止触发大模型幻觉。
6. **事实 6：共识必须反哺日常行为，否则没有存在价值**。
   `ConfirmedInsight` 必须设计明确的运行时消费契约（影响对话 Prompt、主动关怀阈值或桌宠微表情），彻底终结“存入数据库即成死数据”的现状。

---

## 17. Proposed V2 Capability Support Matrix（V2 拟提能力支撑现状对照表）

| Proposed V2 Capability | Already Supported | Partially Supported | Missing | Evidence (代码/数据依据) |
| :--- | :---: | :---: | :---: | :--- |
| **Episode（经历分段层）** | | **✓** | | **Partially Supported**。<br>代码中仅有 `store.list_episodes()` 按 `session_id` 简单聚合，无物理表；真实数据显示 16.9% 会话超长（>1,000事件），缺乏复合分段逻辑。 |
| **Evidence Ledger（统一证据账本）** | | **✓** | | **Partially Supported**。<br>已有 `evidence` VIEW（联合 slices 与 events），能表达 `provenance` 与 `retention_class`；但缺失 `salience`、`topic`、`task_id`、`session_id`（slices侧）及反向关联。 |
| **Semantic Retrieval（语义检索）** | | | **✓** | **Missing**。<br>`MemoryRetriever` 依赖纯字面 LIKE 与 N-gram，离线评测显示同义词 100% 漏召回，正向输入误召回严重负面切片；环境有 FTS5 但缺分词，零向量能力。 |
| **Counter-evidence（反例追踪）** | | **✓** | | **Partially Supported**。<br>`hypotheses` 表中保留了 `counter_episodes` 列表；但在晋升为 `insights` 时反例字段被彻底丢弃，且反例无细粒度数据模型。 |
| **Temporal Change（时间演化证据）** | | | **✓** | **Missing**。<br>`ChapterGenerator` 仅传递全局总计数字与采样 ID，无分期对比数据；已生成的章节中的时序演进描述 100% 为大模型脑补幻觉。 |
| **Hypothesis Revision（假说版本修订）** | | **✓** | | **Partially Supported**。<br>`SelfModelManager.apply_calibration()` 支持 PARTLY 产生 `_revised` 假说；但重新挖掘会通过固定 ID 覆盖旧状态，且无法追踪历史修订树。 |
| **Insight $\to$ Behavior（共识反哺行为）** | | | **✓** | **Missing**。<br>全局搜索确认 `list_insights` 仅在 UI 列表展示和章节生成中被读取，完全未进入任何对话、姿态、关怀决策链路，处于完全停滞状态。 |
| **Evidence-grounded Chapter（事实锚定章节）** | | **✓** | | **Partially Supported**。<br>拥有资格门与防火墙（字符串替换）；但输入缺乏真实 episode 细节与用户切片原话，大模型在没有微观证据的情况下只能泛泛而谈。 |

---
*(报告结束 · 本轮事实审计未对项目源代码、数据库、依赖项执行任何修改)*
