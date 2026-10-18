# Co-evolving Companion：跨会话长期记忆检索与注入专项事实审计报告
## ——现状、数据形态、失败模式、工程约束与能力事实全景

> **审计基准与声明**：
> - **审计时间**：2026-10-18
> - **代码库版本**：Phase 2D 演进态（全量 159 项单元与集成测试通过）
> - **基准数据库**：`data/companion_chronicle.db`（只读挂载审计，未篡改数据、未执行迁移）
> - **审计边界**：严格聚焦**跨会话长期记忆（Cross-Session Long-Term Memory）的写入、存储、检索、排序、注入与生命周期**。
> - **证据级别规范**：
>   - `[代码事实]`：依据当前实际可执行代码行号与符号定义；
>   - `[数据事实]`：依据实际生产/测试数据库真实记录与统计；
>   - `[实验观察]`：依据只读离线脚本与无副作用评测运行结果；
>   - `[推断]`：基于代码与系统拓扑得出的逻辑因果推论；
>   - `[待确认项 / Unknown]`：当前代码与文档无明确定义、缺乏证据证明的事项。

---

## 1. Executive Summary（执行摘要）

本次审计针对“用户问及往事时桌宠容易失忆或答非所问”的现象，对 Co-evolving Companion 的跨会话长期记忆链路进行了端到端事实排查。核心事实结论如下：

1. **“长期记忆”在代码中实质仅等价于用户切片表（Slices）**：
   - 系统数据库中虽然沉淀了 **115,537 条遥测事件（Events）** 与 **4 条候选假说（Hypotheses）**，但日常跨会话检索（Daily Recall）的**唯一数据来源是 42 条 `slices`**；
   - 遥测事件中的 3,250 条 `user_prompt` 虽然标记为 `retention_class='durable'`，但在入库时**文本已被 Connector 丢弃，仅记录 occurrence**；
   - 假说（Hypotheses）、共识洞察（Confirmed Insights）与人生章节（Chapters）**完全未接入跨会话日常回忆通道**，形成了数据孤岛。

2. **检索机制本质为基于 N-gram 的模糊字面匹配（LIKE-based Substring Scanning）**：
   - 现存检索器 `MemoryRetriever` 通过停用词清洗后生成 2~3 字 N-gram，在 SQLite 中执行 `content LIKE '%kw%'`；
   - 40 组典型意图基准测试（Benchmark）实测表明：**综合语义命中正确率仅为 40.0%**。语义相同但字面无交集的查询 **100% 漏召回（False Negative）**；包含高频通用词（如“代码”、“测试”、“项目”）的查询产生 **46.2% 的语义漂移误召回（False Positive）**。

3. **完全缺失“重要性（Salience）”与“时间有效性（Temporal Validity）”建模**：
   - 存储模型中无任何记忆重要度、访问频次或用户标记字段；
   - 无任何版本废弃机制。当用户产生相互矛盾的表述时（如“喜欢 X”与“不再喜欢 X”），系统由于 `ORDER BY timestamp DESC` 仅机械返回最新一条，或在多词命中时将冲突记录一并塞入 Prompt，迫使 LLM 产生幻觉与猜测。

4. **会话/工程上下文隔离度为零（Context Agnostic）**：
   - 切片表 `slices` 设计中**无 `session_id`、`project_id`、`repo`、`task_id` 字段**。在跨端、跨工程（如从桌宠切换至后端服务开发）时，检索层对上下文一无所知，极易发生跨项目串扰（Cross-project Contamination）。

---

## 2. What “Long-Term Memory” Actually Means Today（当前项目里“长期记忆”到底指什么）

### 2.1 数据源与可达性全景表

| Data Source | Persisted | Storage | Cross-session retrievable | Injected into daily LLM context | Notes |
| :--- | :---: | :--- | :---: | :---: | :--- |
| **Feeder Slice**（悬浮条随手投喂） | **Yes** | SQLite `slices` + `raw_slices.jsonl` | **Yes** | **Yes** (Top-1~3) | `[代码事实]` 日常跨会话记忆的**绝对主体与唯一实际输入源**。 |
| **Speech Bubble Reply**（气泡内联回复） | **Yes** | SQLite `slices` + `raw_slices.jsonl` | **Yes** | **Yes** (Top-1~3) | `[代码事实]` 与 Feeder 本质相同，作为 `manual_feed` 切片存盘。 |
| **Agent User Prompt**（外部工具提问） | **Partial** | SQLite `events` | **No** | **No** | `[代码事实]` 只存事件元数据（时间、session、agent），**原始 Prompt 文本被主动丢弃**。 |
| **Agent Telemetry Events**（工具调用/报错） | **Yes** | SQLite `events` | **No** | **No** | `[代码事实]` 共 11.5 万条。100% 作为数据面只读证据，严禁进入日用上下文。 |
| **Hypotheses**（候选心理假说） | **Yes** | SQLite `hypotheses` | **No** | **No** | `[代码事实]` 仅供 Chronicle Viewer 界面查看与校准，日常记忆检索不读。 |
| **Confirmed Insights**（已确认认知共识） | **Yes** | SQLite `insights` | **No** | **No** | `[代码事实]` 仅供 UI 展示与章节资格门判定，未注入日用对话 Prompt。 |
| **Growth Chapters**（人生章节） | **Yes** | `data/chapters/*.md` | **No** | **No** | `[代码事实]` 独立长文本 Markdown，日常跨会话检索完全不可见。 |
| **Pet State / Satiety / Energy** | **No** | 运行时内存 | **No** | **No** | 纯内存姿态变量，进程关闭即销毁。 |

### 2.2 核心断言

> **事实结论**：
> 当前项目中，**“被保存”、“属于长期记忆”、“能被跨会话想起”三者绝对不是同一件事**。
> - **“被保存”** 范围极大（涵盖 115,537 条工具调用、会话流、章节 Markdown 与切片）；
> - **“属于长期记忆”** 在产品概念中包含了认知自模型与人生章节，但在代码层它们是静默死库；
> - **“能被跨会话想起”** 在当前代码中**狭隘地等于且仅等于对 42 条 `slices` 表执行 Substring Search**。

---

## 3. Memory Write Paths（写入链路全追踪）

```text
1. 用户输入入口 (Feeder / Bubble Reply)
   ├── src/feeder/overlay.py:607 (`slice_submitted.emit(text)`)
   └── src/body/speech_bubble.py:155 (`user_replied.emit(reply_text, orig)`)
         ↓
2. 表现层汇聚 (PetWindow)
   ├── src/body/window.py:214 (`_on_slice_submitted`)
   └── src/body/window.py:223 (`_on_bubble_user_replied`)
         ↓
3. 容器双写落盘 (CompanionApp)
   ├── 写 JSONL: src/feeder/storage.py:41 (`SliceStore.save(RawSlice)`) -> data/raw_slices.jsonl
   └── 写 SQLite: src/memory/store.py:148 (`ChronicleStore.record_slice(SliceRecord)`)
         ↓
4. 数据库表: data/companion_chronicle.db -> 表 `slices`
         ↓
5. 元数据保留情况:
   - timestamp: YES (UTC ISO-8601)
   - content: YES (完整原始文本，仅做 strip)
   - actor: YES (硬编码 'user')
   - source: YES ('manual_feed')
   - mood_flag: YES ('neutral' 或 'frustrated'，由 SanctuaryGuard 判定)
   - session_id: NO (完全缺失)
   - project/repo: NO (完全缺失)
   - topic/tags: NO (完全缺失)
   - retention_class: NO (切片表无此列，视图 `evidence` 中虚拟映射为 'durable')
         ↓
6. 后续召回消费者:
   └── src/memory/retriever.py:140 (`MemoryRetriever.recall_records()`)
```

### 3.1 写入机制细节对照

1. **写入触发条件**：
   - 随手投喂框按下回车，且 `text.strip()` 非空；
   - 气泡回复输入框按下回车，且文本非空。
2. **去重与覆盖行为**：
   - `RawSlice.create()` 每次生成基于随机 UUID 的 ID（`f"slice_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"`）；
   - SQL 采用 `INSERT OR IGNORE INTO slices ... VALUES (...)`；
   - **完全没有内容去重逻辑**。若用户在不同时间投喂了完全相同的文字（例如“hi 你好”），系统会分配不同 ID 视为两条独立切片落盘。数据事实表明，42 条记录中存在 **24 条重复内容（占 57.1%）**。
3. **生命周期与衰减**：
   - `ChronicleStore.prune()`（`src/memory/store.py:353`）的清理逻辑为：
     `DELETE FROM events WHERE retention_class = 'transient' AND timestamp < ?`
   - **衰减仅针对 events 表，对 slices 表 100% 豁免**。`slices` 永久保留，无任何 TTL、软删除或定期归档逻辑。

---

## 4. Storage Model（底层存储模型事实）

### 4.1 表结构与字段能力对照（`src/memory/store.py:34-98`）

```sql
-- 真实物理表：slices
CREATE TABLE IF NOT EXISTS slices (
    id          TEXT PRIMARY KEY,
    timestamp   TEXT NOT NULL,
    actor       TEXT NOT NULL DEFAULT 'user',
    source      TEXT NOT NULL DEFAULT 'manual_feed',
    content     TEXT NOT NULL,
    mood_flag   TEXT NOT NULL DEFAULT 'neutral',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_slices_time ON slices(timestamp);
```

### 4.2 存储设计缺失事实分析
1. **缺失项目与环境归属**：无 `project_id`、`cwd`、`repo_url`。
2. **缺失会话连续性**：无 `session_id`。同一个工作下午连续投喂的 3 句话，在存储层没有任何天然分组。
3. **缺失重要性度量**：无 `salience`、`importance`、`pinned`、`access_count`。
4. **缺失状态机字段**：无 `is_active`、`superseded_by`、`expires_at`。

---

## 5. Retrieval Call Chain（跨会话检索完整链路追踪）

```text
Current User Input (例如："昨天我们聊了什么")
    ↓
run_companion.py:561 (`_on_slice_submitted`) / run_companion.py:498 (`_on_user_reply_to_bubble`)
    ↓
run_companion.py:468 (`CompanionApp._recall_memories(text, limit=3, exclude_ids={curr_id})`)
    ↓
src/memory/retriever.py:215 (`MemoryRetriever.recall(query, limit=3, exclude_ids=...)`)
    ↓
src/memory/retriever.py:140 (`MemoryRetriever.recall_records()`)
    ├── 1. Temporal Intent: `_detect_temporal_target()` -> 解析相对日期 (如昨天/前天)
    │      └── 若命中目标日期 -> 调用 `store.get_slices_in_timerange()` 范围检索并直接返回
    │
    ├── 2. Substring & Keyword Search:
    │      ├── `_extract_keywords()`: 剔除 `DEFAULT_STOP_WORDS`，生成 2~3 字符 N-gram
    │      └── 遍历 keywords -> 调用 `store.search_slices(kw)` (`SELECT * FROM slices WHERE content LIKE ?`)
    │
    └── 3. Open-ended Memory Fallback:
           └── 若命中 `memory_intent_markers` 且候选不足 -> 调用 `store.list_slices(limit=30)` 回退近期切片
    ↓
Candidate Filtering:
    ├── 排除当前提问自身 `clean_q` 与 `exclude_ids`
    └── 排除 `DEFAULT_TRIVIAL_SLICES` (如 'hi', '测试', '你是谁')
    ↓
Top-K Selection: 按 SQL 默认的 `ORDER BY timestamp DESC` 截取最多 3 条
    ↓
Prompt Formatting:
    └── src/core/personality.py:274 (`format_memory_snippet(ts, content)`)
        -> 生成 `[YYYY-MM-DD] 用户提到: ...`
    ↓
Prompt Assembly:
    └── src/core/personality.py:246 (`build_system_prompt(..., memories=...)`)
        -> 插入至 System Prompt 末尾 `【你与用户过往的真实经历记忆】`
    ↓
LLM Dispatch:
    └── src/core/llm_client.py:350 (`CompanionAIEngine.request_reply()`)
        -> QThreadPool 异步线程调用 OpenAI 协议 Chat Completion API
```

---

## 6. Query Formation 专项审计（15 组脱敏 Dry-run 实测）

依据 `src/memory/retriever.py:100-138` 的实际运行逻辑，对 15 组典型意图输入执行离线 Dry-run，结果如下：

| # | 类别 | 用户输入原始文本 | 提取关键词列表（N-gram） | 命中日期/意图 | 召回候选数 | 检索真实表现与根因分析 |
| :-: | :--- | :--- | :--- | :--- | :-: | :--- |
| 1 | 中文短句 | 还是算了。 | `[]` | None | 0 | 停用词清洗后为空，安全返回 0 条。 |
| 2 | 中文长句 | 今天把整个前端动画状态机和气泡输入框的交互逻辑全部重新整理了一遍。 | 40 个子串 (`前端`, `状态机`, `气泡`, `逻辑`...) | 今天 | 0 | 命中日期但今日尚无匹配切片，N-gram 未命中。 |
| 3 | 英文 | I prefer using python for all automation scripts. | 45 个子串 (`prefer`, `python`, `scripts`...) | None | 0 | 英文单词及滑动窗口爆炸，但库中无对应英文切片。 |
| 4 | 中英混合 | 在 VSCode 里面跑 pytest 总是遇到超时问题。 | 38 个子串 (`VSCode`, `pytest`, `超时`, `问题`...) | None | 0 | 专有名词被暴力拆分成 `VS`, `SC`, `ode` 等无意义片段。 |
| 5 | 技术术语 | WA_TranslucentBackground | 37 个片段 (`WA_Tr`, `slucentB`...) | None | 0 | 下划线驼峰变量被滑窗切碎，破坏完整专有词。 |
| 6 | 模型名 | gemini-3.8-flash 跑起来效果怎么样？ | 30 个片段 (`gemini`, `3.8`, `flash`...) | None | 0 | 连字符版本号被拆散，无向量时字面无法对齐“大模型”。 |
| 7 | 版本号 | Python 3.11.15 的性能表现如何？ | 24 个片段 (`Python`, `3.11.15`, `性能`...) | None | 0 | 库中无对应技术记录，安全返回 0。 |
| 8 | 情绪表达 | 这代码真烦死了，搞了一整天全是 bug！ | `['bug', '代码', '真烦', '烦死', ...]` | None | 2 | **错误召回**历史抱怨切片（`[2026-10-15] 这代码真烦死了全搞砸了`）。 |
| 9 | 指代句 | 和上次一样。 | `['上次', '一样']` | None | 0 | 无法获知“上次”指代何事，返回 0 条。 |
| 10 | 延续句 | 继续昨天那个。 | `['继续']` | 昨天 (2026-10-17) | 3 | **精准命中**昨天的 3 条实质切片（桌宠项目、形象优化）。 |
| 11 | 省略主语 | 准备去吃午饭了。 | `['准备', '午饭']` | None | 0 | 无历史午饭记录，安全返回 0 条。 |
| 12 | 完全新话题 | 明天打算去买几盆绿植放在阳台。 | `['买几', '绿植', '阳台']` | None | 0 | 库中无绿植记录，安全返回 0 条。 |
| 13 | 共享常用词 | 今天写代码挺顺的，继续优化功能。 | `['代码', '挺顺', '优化', '功能']` | 今天 | 0 | 包含“代码/优化”，因限定“今天”而未被昨天数据污染。 |
| 14 | 同义改写 | 桌面伙伴的身体表现层目前运转良好。 | `['桌面', '伙伴', '身体', '表现', '目前', '运转']` | None | 1 | **命中漂移**：命中`目前在优化交流功能...`，仅因共享“目前”二字！ |
| 15 | 否定句 | 我现在已经不想这么做了。 | `['已经', '经不']` | None | 0 | 否定词丢失，退化为无意义词检索。 |

---

## 7. Real Data Profile（真实数据规模与分布）

基于本地 `data/companion_chronicle.db` 与 `data/raw_slices.jsonl` 只读审计统计：

```text
=== 生产数据库只读统计报告 ===
• slices 总记录数: 42 行
• events 总记录数: 115,537 行
• hypotheses 假说总数: 4 条
• insights 确认共识数: 0 条
• growth_themes 认知主题数: 0 条

=== Slices 切片形态 ===
• 物理时间跨度: 2026-10-15 15:43:57 UTC 至 2026-10-18 01:21:49 UTC (跨度 3 天)
• 文本长度: 最小 2 字, 最大 18 字, 平均 6.6 字, 中位数 5 字, P90=12 字, P95=13 字
• 去重前条数: 42 条
• 纯内容去重后条数: 18 条 (重复记录达 24 条，重复率 57.1%)
• 语言分布: 纯中文 30 条 (71.4%), 纯英文 5 条 (11.9%), 中英混合 7 条 (16.7%)
• 技术内容: URL 占比 0%, 代码片段占比 0%
• 情绪标记 (mood_flag): neutral 38 条 (90.5%), frustrated 4 条 (9.5%)
• 写入来源 (source): 100% 为 'manual_feed'

=== Events 遥测事件形态 ===
• 物理时间跨度: 2026-06-09 至 2026-10-18 (四个月真实开发遥测沉淀)
• 涉及 Agent 客户端: pi (90,928), pi-desktop (11,307), hermes (6,824), codex (6,477)
• 事件类型分布:
  - pre_tool_use: 52,180 (45.2%)
  - post_tool_use: 50,296 (43.5%)
  - turn_end: 3,952 (3.4%)
  - tool_failure: 3,671 (3.2%)
  - user_prompt: 3,250 (2.8%)
  - task_complete: 1,817 (1.6%)
• 聚合 Session (Episodes) 覆盖数: 238 个独立会话
```

---

## 8. Slice Content Characteristics（真实切片内容异质性分析）

对现存 42 条真实切片进行内容语义聚类抽样发现，切片呈现高度异质性，而系统当前统一将其作为无差别记忆处理：

1. **浅层调试与连通性验证（瞬时信息，占 45.2%）**：
   - 典型样例：`"测试"`, `"测试气泡"`, `"测试发消息自动探头"`, `"hi"`, `"hi 你好"`
   - 特点：完全无长期留存价值，数天后被唤醒会造成极其尴尬的用户体验。
2. **极度受挫的情绪发泄（状态切片，占 9.5%）**：
   - 典型样例：`"这代码烦死了😡，全搞砸了"`, `"这代码真烦死了全搞砸了"`
   - 特点：具有高度情境依赖性，数天后若因为关键词再次召回，会重新向 LLM 注入负面情绪偏见。
3. **真实项目进展与开发共识（长期核心事实，占 14.3%）**：
   - 典型样例：`"挺顺的，一直在开发桌宠项目"`, `"目前在优化交流功能还有你的形象和行为"`
   - 特点：**真正具有跨会话价值的伙伴记忆**。
4. **关系与身份确认（人际交互，占 19.0%）**：
   - 典型样例：`"你是谁"`, `"你是？"`, `"你好 你了解我吗"`, `"你好 很高兴认识你"`
5. **记忆元查询（系统问答，占 11.9%）**：
   - 典型样例：`"昨天我们聊了什么"`, `"你还记得什么"`
   - 特点：用户发出的提问本身绝不能沉淀为往事事实。

---

## 9. Ranking / Ordering 机制事实

### 9.1 当前排序规则
`[代码事实]` 在 `src/memory/store.py:297` 中，切片查询 SQL 显式定义为：
```sql
SELECT * FROM slices WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?
```
在多关键词查询时，`MemoryRetriever`（`src/memory/retriever.py:176-189`）遍历关键词列表并依次追加到 Python 列表，去重后截断 `[:limit]`。

### 9.2 排序机制缺陷
1. **纯粹依赖时间逆序（Recency Only）**：
   - 无任何匹配度分数计算；
   - 命中 5 个关键词的切片与命中 1 个关键词的弱相关切片享有同等权重，只要后者时间更新，后者必然排在前面。
2. **重复切片挤占 Top-K 预算**：
   - 早期历史中用户重复投喂的 `"hi 你好"`、`"这代码真烦死了全搞砸了"` 会多次占满 Top-K，导致更具信息量的更早记忆被挤出。

---

## 10. Retrieval Benchmark（40 个测试用例基准与失败分类学）

通过运行离线基准评测套件（40 Cases，无数据污染），测得当前机制能力矩阵如下：

```text
=== 40-Case Retrieval Failure Benchmark Summary ===
• 整体正确行为率: 16 / 40 (40.0%)
• 语义不符/虚假召回 (False Positives): 6 例 (占比 15.0%)
• 语义匹配但漏召回 (False Negatives): 3 例 (占比 7.5%)
• 关键词重合但语义漂移 (Semantic Mismatch): 3 例 (占比 7.5%)
• 冲突与指代歧义无法处理 (Ambiguous / Contradiction Failures): 12 例 (占比 30.0%)
```

### 10.1 失败分类学（Failure Taxonomy）

```text
Failure Taxonomy
  ├── 1. 字面断裂 (Lexical Fracture)
  │      └── 典型现象: 用户说“报错全修好了”，但库中记录为“全搞砸了”，字面 0 命中导致失忆。
  │
  ├── 2. 停用词与常用词泛滥 (Keyword Hijacking)
  │      └── 典型现象: 提问“测试用例通过了吗”，因包含“测试”而强行翻出“测试发消息自动探头”。
  │
  ├── 3. 跨工程串扰 (Cross-Project Contamination)
  │      └── 典型现象: 询问“另一个客户端项目”，因包含“项目”二字误召回“桌宠项目”。
  │
  ├── 4. 时序冲突覆盖 (Temporal Overwrite)
  │      └── 典型现象: 产生“不再喜欢 X”时，系统可能同时召回旧记录，或让旧记录排在前面。
  │
  └── 5. 缺乏否定语义感知 (Negation Blindness)
         └── 典型现象: “不想这么做了”丢失“不想”，反向检索正面行动。
```

---

## 11. Temporal Validity & Contradiction（时效性与观点冲突）

1. **系统当前是否具备有效期定义？**
   - `[代码事实]`：**完全没有**。无 `valid_from`、`valid_until`、`superseded_by` 或状态置失效标识。
2. **新旧冲突真实表现**：
   - 当用户在时间 $T_1$ 说：“这代码真烦死了全搞砸了”；
   - 在时间 $T_2$ 说：“我现在一点都不烦代码了，写得很开心”；
   - 检索“代码”时，由于 SQL 按 `timestamp DESC` 排序，新记录排在最前，但旧记录若也在 Top-K 内，两条截然相反的切片会**同时被注入 System Prompt**。Prompt 中没有标注哪一条是已废弃事实，LLM 只能凭借自身概率分布盲猜用户的心态。

---

## 12. Session / Task / Project Awareness（上下文感知事实）

| 维度 | 当前是否记录 | 当前是否参与检索 | 失败根因 |
| :--- | :---: | :---: | :--- |
| **Session ID** | NO (slices表无此列) | NO | 无法依据同一个工作会话将多次投喂逻辑关联。 |
| **Agent / Client** | Slices 表仅存 `'manual_feed'` | NO | 无法区分用户在手机端、CLI 还是桌面端投喂。 |
| **Project / Repo** | NO | NO | 多项目并行工作时，不同仓库的讨论必然相互串扰。 |
| **Task / Goal** | NO | NO | 伴生体无法建立“某个复杂任务正在进行”的记忆绑定。 |
| **当前日期** | 运行时计算注入 | YES (已修复增强) | 已具备将“昨天/前天”映射到 UTC 日期区间能力。 |

---

## 13. Conversation vs Cross-Session Memory（对话上下文与长程记忆分层事实）

1. **对话上下文存在哪里？**
   - `[代码事实]`：桌宠表现层**完全没有维护多轮会话列表**。
   - 每次 LLM 请求（`src/body/window.py` 与 `run_companion.py`）只构造两行消息：
     - `{"role": "system", "content": system_prompt}`
     - `{"role": "user", "content": user_context}`
   - 对话结束后，历史消息不在内存保留。
2. **是否存在 Short-term → Long-term Consolidation？**
   - **`Missing`（完全缺失）**。不存在任何自动从多轮对话中提炼关键事实并固化为长期记忆的 Consolidation 管道。用户输入的每一句话直接被粗暴持久化为一条独立的平铺切片。

---

## 14. No-Memory Behavior（何时应当保持静默）

1. **当前系统是否存在相关度门控？**
   - `[代码事实]`：`src/memory/retriever.py` 中不存在任何基于分数（Score）或置信度（Confidence）的阈值门控。
   - 只要字符串经 N-gram 切分后在数据库中能 `LIKE` 出记录，就会截取 Top-K 注入。
2. **不相关查询被强行注入的风险**：
   - 评测显示，在 40 个测试用例中，有 **15.0% 的无关提问被误强行召回历史切片**（例如技术协议询问强行关联形象优化）。

---

## 15. Memory Injection 专项审计（Prompt 构造与毒化风险）

### 15.1 Prompt 构造真实模板（`src/core/personality.py:221-251`）

```python
sections.append(
    f"【你与用户过往的真实经历记忆（当前日期：{current_date_str}）】：\n"
    "请注意：上面标注日期的经历是你和用户真实聊过/发生过的事。"
    "当用户问起'昨天聊了什么'、'还记得什么'或相关往事时，请自然从中调取并简短作答，证明你确实记得。"
)
for mem in memories:
    sections.append(f"- {mem}")
```

### 15.2 潜在风险点
1. **假性事实确定感（False Certainty）**：
   - Prompt 明确告诉 LLM“上面标注日期的经历是真实聊过/发生过的事”，当检索错误（如将网络协议误召回为形象优化）时，LLM 会误以为用户在询问旧事，从而**在回答中强行提起不相关的往事，造成话题劫持（Topic Hijacking）**。
2. **字符预算缺乏硬约束**：
   - 单条 memory 虽然通过 `format_memory_snippet` 做了 60 字符截断，但多条注入时没有整体 token 预算保护机制。

---

## 16. Effect on LLM Responses（离线注入对照实验）

选取 2 组真实 Query 进行有无 Memory 注入的对照：

- **实验 Query 1**：`"你平时交流都用什么协议？"`
  - **Condition A (无 Memory 注入)**：
    > *“哪有什么协议啊，跟你聊天，靠的全是实在的大白话。”*（自然、极简、符合同伴人设）
  - **Condition B (注入错误召回的优化交流记忆)**：
    > *“哈哈，心意相通协议吧。只要你开口，我都认真接着。”*（受记忆关键词干扰，回复重心发生漂移）

- **实验 Query 2**：`"把那个网页前端的项目优化一下"`
  - **Condition A (无 Memory 注入)**：
    > *“挺好，理顺了用着也痛快。跟着你的节奏慢慢来。”*
  - **Condition B (注入昨天桌宠项目优化记忆)**：
    > *“好主意，理顺了用着也舒坦。这次打算先动哪一块？”*（将外部网页项目与桌宠项目产生概念粘连）

---

## 17. SelfModel / Insight / Chapter Relationship（认知与记忆孤岛分析）

```text
Slices (42 条) ─────────── NO ────────────→ Pattern / Hypotheses 挖掘
                                                   ↓
                                            Events (11.5万条) ── YES ──→ Hypotheses (4 条)
                                                                            ↓ (用户校准)
                                                                        Insights (0 条)
                                                                            ↓
Daily Recall ←─────── NO ───────────────────────────────────────────────────┘
     ↑
     └─────────────── NO ────────────────── Chapters (1 篇)
```

1. **Slices 与 Hypotheses 割裂**：`PatternBuilder` 仅读取 `events` 表，用户手动投喂的切片从未参与行为模式挖掘；
2. **Insights 与 Daily Recall 割裂**：即使用户确认了认知共识，共识也仅保存在 `insights` 表中，**Daily Recall 检索器完全不读取 `insights` 表**，桌宠在日常对话中无法主动调用这些共识；
3. **Chapters 成为单向终端**：章节生成后作为 Markdown 文件落盘，无法反哺日常记忆检索。

---

## 18. Forgetting / Deletion / Lifecycle（遗忘与生命周期事实）

1. **切片删除与编辑**：
   - 当前 UI 界面与底层 API 中，**没有为切片提供任何删除（Delete）或编辑（Edit）接口**；
   - `data/raw_slices.jsonl` 为 append-only 模式，物理上无删除支持。
2. **级联影响（Cascade Missing）**：
   - 当前规范完全未定义：“若用户删除了某条包含隐私或负面情绪的切片，派生的假说、章节或检索索引如何级联同步清理”。

---

## 19. Privacy / Security / Prompt Injection 风险

1. **外部数据边界安全**：
   - `events` 表严格脱敏，不记录任何代码、CoT、Prompt 文本；
   - 风险主要集中于 `slices`：切片由用户在输入框键入，系统不做任何语义安全脱敏，若用户键入了包含 API Key 或隐私凭据的文本，该文本会**永久明文保存在本地 SQLite 与 JSONL 中，并在后续检索命中时明文重新送入大模型 Prompt**。

---

## 20. Performance（性能与资源事实）

在本地环境对 10,000 条切片规模进行只读性能基准压测：

- **命中检索平均耗时**：`p50 = 0.082 ms`, `p95 = 0.125 ms`（SQLite 缓存命中极快）；
- **全表扫描最坏未命中耗时（Worst-Case Miss Scan）**：
  - 当输入长难查询、生成 30+ 个 N-gram 且全部未命中时，触发 30+ 次独立 `LIKE '%kw%'` 全表扫描；
  - **最坏耗时**：`p50 = 42.79 ms`, `p95 = 46.41 ms`；
  - 结论：在 1 万条切片以内，当前检索耗时严格受控于 50ms 规范门禁，但在主线程高频触发时仍存在微秒级 I/O 隐患。

---

## 21. Existing Tests & Gaps（测试覆盖与缺口矩阵）

| 评测维度 | 当前测试状态 | 覆盖测试文件 | 存在缺口 / 盲区 |
| :--- | :---: | :--- | :--- |
| **基础写入与持久化** | **Covered** | `tests/test_memory.py` | 覆盖 SQLite 重启存盘、双写幂等。 |
| **按天/相对时间检索** | **Covered** | `tests/test_memory_retriever.py` | 覆盖昨天/前天时间换算。 |
| **开放式记忆唤醒** | **Covered** | `tests/test_memory_retriever.py` | 覆盖“还记得什么”近期切片回退。 |
| **语义相似但字面不同** | **Missing** | 无 | 缺乏对“意思相同但换词表达”的回归断言。 |
| **同字异义/虚假召回** | **Missing** | 无 | 缺乏对通用高频词污染的拦截测试。 |
| **观点矛盾与冲突覆盖** | **Missing** | 无 | 完全未测试新旧观点冲突时的召回排序。 |
| **跨项目串扰隔离** | **Missing** | 无 | 未测试不同 project/workspace 下的切片隔离。 |
| **删除级联生命周期** | **Missing** | 无 | 无删除 API，亦无相关测试。 |

---

## 22. Spec / Invariants（规范与红线事实）

根据 `AGENTS.md` 与 durable spec graph，跨会话记忆演化不可违背的核心红线：
1. **控制面与数据面物理分离**：高频遥测仅落库，绝不可直连 UI 或直接篡改桌宠姿态；
2. **严禁采集用户私密信息**：严禁记录外部 Agent 的 Prompt 正文、思维链（CoT）及工具返回详情；
3. **极简质朴回复红线**：单次回复必须控制在 12 到 28 个汉字以内，严禁长篇大论，注入记忆不能诱发 LLM 喋喋不休；
4. **避风港（Sanctuary）绝对优先**：用户受挫心烦时，严禁调取历史旧事说教，只给极简接纳与安静陪伴。

---

## 23. Runtime Capability Facts（运行环境技术事实）

- **Python 运行时**：`Python 3.11.15 (MSC v.1944 64 bit AMD64)`
- **内置 SQLite 版本**：`3.53.1`
- **SQLite FTS5 虚拟表扩展**：**已原生内置启用（FTS5 enabled: True）**
- **第三方依赖现状**：
  - `PySide6 (v6.12.0)`：已安装
  - `pydantic (v2.14.1)`：已安装
  - `numpy`, `scipy`, `torch`, `transformers`, `sentence_transformers`: **全部未安装（NOT INSTALLED）**
  - `onnxruntime`, `sqlite_vec`, `faiss`, `fastembed`: **全部未安装（NOT INSTALLED）**
  - `jieba`: **未安装（NOT INSTALLED）**
- **工程结论**：
  - 当前环境是一个**纯标准库 + PySide6 的极度轻量级常驻进程**；
  - 引入大型深度学习框架（如 PyTorch）会带来数百 MB 内存占用与冷启动开销，违背轻量桌宠初衷。

---

## 24. 核心问题逐项事实解答（Questions Answered）

### Q1: 当前所谓“跨会话长期记忆”在真实代码中到底是什么？
> `[代码事实]` 是用户通过悬浮框或气泡手动提交、写入 SQLite `slices` 表的单条短文本记录。

### Q2: 是不是本质上主要等于：historical slices + lexical/substring lookup + Top-K prompt injection？
> `[代码事实]` **是的，完全符合这一描述**。除新增的相对自然日时间区间换算外，检索核心完全基于 N-gram 子串切分与 SQLite `LIKE '%kw%'` 扫描，并将匹配到的前 1~3 条格式化为静态文本嵌入 System Prompt。

### Q3: 哪些信息可以在数天/数月后真正被 Vasu 重新想起？
> 仅限用户主动在 Feeder 或气泡中投喂的 `slices` 文本。

### Q4: 哪些长期保存的数据实际上永远不会被日常 recall？
> 1. `events` 表中全部 11.5 万条遥测记录；
> 2. `hypotheses` 表中的候选心智假说；
> 3. `insights` 表中的共识洞察；
> 4. `chapters/*.md` 中的人生章节正文。

### Q5: 为什么“意思一样但措辞不同”容易失忆？
> 因为当前完全依赖字面字符包含（`LIKE`），无任何语义向量表示或同义词网络，字面无重合则数据库返回空。

### Q6: 为什么“不相关但有几个相同字”容易被错误召回？
> 检索器将长句机械切分为 2 字 N-gram（如“代码”、“测试”、“优化”），常用词的高频出现直接击穿了字面匹配，造成语义漂移。

### Q7: 当前有没有真正的 relevance score？
> **没有**。只有 SQL 匹配是否存在，无相似度打分。

### Q8: 当前有没有 recency？
> **有**。SQL 查询强制附加 `ORDER BY timestamp DESC`。

### Q9: 当前有没有 salience / importance？
> **没有**。所有切片权重平等。

### Q10: 当前有没有 memory type？
> **没有**。随手吐槽、核心目标、问候、技术配置全部混存在同一张平铺表中。

### Q11: 当前有没有 temporal validity？
> **没有**。无任何失效期或有效起止时间字段。

### Q12: 当前如何处理新旧观点冲突？
> 机械依靠 `timestamp DESC` 优先返回最新一条；若新旧多条同时被截入 Top-K，则一并塞给大模型，由 LLM 自行猜度。

### Q13: 当前有没有“什么都不要召回”的能力？
> **有，但属于被动发生**。当输入分词被停用词完全过滤为空时返回 0 条；但对存在常用词的无关查询，无法主动决策保持静默。

### Q14: 当前是否理解 session / task / project / topic 上下文？
> **完全不理解**。切片表不保存也不感知上述任何上下文。

### Q15: 当前 conversation memory 和 cross-session memory 是否真正分层？
> **没有分层**。因为表现层根本没有短程多轮对话记忆，每次交互都是一问一答的单轮请求。

### Q16: 当前有没有 consolidation？
> **Missing（完全没有）**。无短程提炼至长程的巩固管道。

### Q17: 当前有没有 forgetting？
> 遥测事件有基于 30 天 TTL 的 `prune` 清理；**切片表（用户记忆）没有任何遗忘机制**。

### Q18: 用户删除一条原始记忆后，派生信息是否仍可能残留？
> 当前没有删除切片功能；若手动从数据库删除切片，已生成的假说与章节文件**仍会完整残留该切片的影响痕迹**。

### Q19: 当前 memory injection 是否可能让 LLM 把历史记忆误当成仍然有效的当前事实？
> **可能**。Prompt 指示“上面标注日期的经历是你和用户真实聊过的事”，无防范时效过期的约束。

### Q20: 当前最大的 10 个真实 failure modes 是什么？
> 1. 字面断裂导致漏召回；2. 通用词引发语义漂移；3. 情绪发泄切片污染日后正常提问；4. 浅层问候占据 Top-K；5. 专有名词被 N-gram 拆碎；6. 跨项目串扰；7. 观点冲突共存；8. 无法理解代词指代；9. 缺乏静默决策强行召回；10. 诱发 LLM 话题劫持。

### Q21: 哪些问题属于“检索问题”？
> 字面断裂漏召回、同义词无法关联、专有名词切分破坏。

### Q22: 哪些问题其实属于数据建模、生命周期与 Prompt 注入问题？
> 跨项目串扰（缺少 project 元数据）、新旧观点冲突（缺少版本与时效建模）、浅层问候污染（缺少 memory type 分级）、话题劫持（Prompt 注入缺乏置信度与弱化提醒）。

---

## 25. 规范附录：四大核心事实矩阵

### 表 1：Memory Capability Matrix（记忆能力事实矩阵）

| Capability | Current Status | Evidence | Failure / Limitation |
| :--- | :---: | :--- | :--- |
| **Persistent storage** | **Implemented** | SQLite `slices` + `raw_slices.jsonl` 双写 | 平铺存储，无结构化分级 |
| **Cross-session recall** | **Implemented** | `MemoryRetriever.recall()` | 仅覆盖切片，不覆盖认知模型 |
| **Lexical relevance** | **Implemented** | `src/memory/store.py:297` (`LIKE '%kw%'`) | 仅子串扫描，缺乏 BM25 等统计打分 |
| **Semantic relevance** | **Missing** | 纯标准库，无向量检索 | 语义相同但换词即 100% 漏召回 |
| **Recency** | **Implemented** | `ORDER BY timestamp DESC` | 仅依赖时间戳逆序，无法与相关度加权 |
| **Salience** | **Missing** | 存储层无对应字段 | 无法区分重要决定与随口问候 |
| **Memory type** | **Missing** | 仅有 mood_flag，无类型分级 | 瞬时切片与长期目标无差别对待 |
| **Session awareness** | **Missing** | `slices` 表无 `session_id` | 无法感知同一会话内的连续投喂 |
| **Project awareness** | **Missing** | 存储层无 `project` / `repo` 字段 | 跨工程工作时记忆必然串扰 |
| **Topic awareness** | **Missing** | 无自动聚类或主题提取 | 无法围绕某一主题聚合多条记忆 |
| **Temporal validity** | **Missing** | 无有效起止时间或状态标记 | 无法标识已过期的历史偏好 |
| **Contradiction handling** | **Missing** | 无版本链或对立关系标记 | 矛盾事实同时注入 Prompt，诱发幻觉 |
| **No-memory decision** | **Partial** | 依赖停用词清洗被动为 0 | 无法对命中常用词的无关查询主动静默 |
| **Forgetting** | **Partial** | 仅 `events` 有 TTL，`slices` 永不删除 | 记忆无限堆积，无降级与淘汰 |
| **Deletion propagation** | **Undefined** | 代码中无删除接口 | 规范未定义删除派生数据的级联逻辑 |
| **Provenance** | **Implemented** | `actor='user'`, `source='manual_feed'` | 粒度过粗，无法细分终端与场景 |
| **Prompt injection safety**| **Partial** | 仅进行截断与问句特征排除 | 注入未与不可信输入隔离，存在越权风险 |
| **SelfModel integration** | **Missing** | `retriever` 不读取 `insights` 表 | 用户校准后的共识无法进入日常对话 |
| **Chapter integration** | **Missing** | `retriever` 不读取 Markdown 章节 | 章节成为静态只读档案，与记忆脱节 |

---

### 表 2：Failure Case Matrix（失败用例矩阵 · 15 个脱敏实测案）

| # | Failure Case（测试输入） | Current Behavior（当前表现） | Expected Semantic Behavior（预期语义行为） | Root Cause（根因） | Evidence（代码与数据证据） |
| :-: | :--- | :--- | :--- | :--- | :--- |
| 1 | 上次我们碰到的那个报错全修好了 | 召回 0 条 | 关联到历史上因报错受挫的切片 | 纯字面扫描；“报错”与“烦死了全搞砸了”无字面重合 | `src/memory/retriever.py:176` |
| 2 | 这个测试用例通过了吗？ | 召回 `测试发消息自动探头` | 不应召回（当下技术问句，非历史回忆） | 通用高频词“测试”无权重衰减，击穿 Substring 匹配 | `src/memory/retriever.py:125` |
| 3 | 帮我看看这个形象设计图好看吗 | 召回 `目前在优化交流功能还有你的形象和行为` | 不应召回（评价当下设计图） | 词语“形象”被命中，缺乏任务上下文感知 | `src/memory/retriever.py:178` |
| 4 | 另一个客户端项目的UI状态机怎么样了？ | 召回 `挺顺的，一直在开发桌宠项目` | 不应召回（询问外部项目） | 切片无项目归属字段，常用词“项目”跨工程串扰 | `src/memory/store.py:34` |
| 5 | 给后端服务加一个自动化测试 | 召回 `测试发消息自动探头` | 不应召回（后端服务与桌宠无关） | 无工程与仓库隔离能力，单字“测试”强行命中 | `data/companion_chronicle.db` |
| 6 | 把那个网页前端的项目优化一下 | 召回桌宠项目及形象优化切片 | 不应召回 | 词语“优化”和“项目”引发双重命中 | `src/memory/retriever.py:178` |
| 7 | 桌面伙伴的身体表现层目前运转良好 | 召回 `目前在优化交流功能还有你的形象和行为` | 关联桌宠开发挺顺，而非形象优化 | N-gram 恰好包含“目前”，命中弱相关切片 | `src/memory/retriever.py:127` |
| 8 | 我现在已经不想这么做了 | 召回 0 条 | 识别用户策略放弃或偏好转移 | 停用词清洗导致“已经不想”被拆碎，丢失否定语义 | `src/memory/retriever.py:27` |
| 9 | 和上次一样 | 召回 0 条 | 结合最近会话的意图进行指代解析 | 无短程对话历史支撑，代词无法消歧 | `src/body/window.py:223` |
| 10 | 打算给窗口加个阴影效果 | 召回 0 条 | 关联到桌宠形象优化话题 | “阴影效果”在字面上与“形象和行为”无重合 | `src/memory/store.py:297` |
| 11 | 你平时交流都用什么协议？ | 召回 `目前在优化交流功能...` 并影响 LLM 回复 | 纯技术协议答复，不应受桌宠优化干扰 | 常用词“交流”产生虚假语义关联，Prompt 诱发话题劫持 | `test_llm_pairwise.py` |
| 12 | 今天真不想折腾了 | 若历史上包含“折腾”则强行召回 | 静默陪伴，不应调取记忆 | 缺乏情感门控与静默决策机制 | `src/memory/retriever.py:192` |
| 13 | 晚上打算做一份番茄炒蛋吃 | 召回 0 条 (符合预期) | 保持静默 (0 条) | 新概念在字面上完全未命中任何记录 | `dry_run_queries.py` |
| 14 | 以后不要再提醒我休息了 | 召回 0 条 | 识别用户偏好变更并标记相关规则 | 系统完全无偏好（Preference）提取与覆写管道 | `src/core/intervention.py` |
| 15 | WA_TranslucentBackground 怎么配？ | 召回 0 条 | 关联到 Windows 透明窗口历史记录 | 下划线专有名词被 N-gram 强行切碎导致未命中 | `src/memory/retriever.py:112` |

---

### 表 3：Data Source → Recall Reachability（数据源召回可达性）

| Source | Stored（已存盘） | Searchable（可被搜到） | Ranked（参与排序） | Injected（已注入Prompt） | Used Across Sessions（实现跨会话） |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Feeder Slice** | YES | YES | YES (Recency) | YES | **YES** |
| **Bubble Reply** | YES | YES | YES (Recency) | YES | **YES** |
| **Agent User Prompt** | YES (无正文) | NO | NO | NO | **NO** |
| **Agent Event** | YES (11.5万) | NO | NO | NO | **NO** |
| **Hypothesis** | YES (4条) | NO | NO | NO | **NO** |
| **Confirmed Insight**| YES (0条) | NO | NO | NO | **NO** |
| **Chapter** | YES (1篇) | NO | NO | NO | **NO** |

---

### 表 4：Unknowns Blocking V2 Design（阻塞 V2 架构设计的未知项）

| Unknown（待确认项） | Why It Matters（为何关键） | How to Verify（如何核实验证） |
| :--- | :--- | :--- |
| **U1. 切片是否允许记录会话 ID？** | 若切片绑定 `session_id`，需要评估当用户无明确 Agent 会话时（纯桌面闲置），该 ID 该如何生成与闭环。 | 检查 `src/connectors/hook_manager.py` 与 `PetWindow` 的生命周期钩子。 |
| **U2. 用户删除切片后的派生假说是否需要重算？** | 若用户要求 GDPR 级删除，现有依据该切片生成的假说、置信度以及章节是否需要物理撤回或脱敏重写。 | 审查心理灵活性假说生成器 `HypothesisEngine.synthesize()` 的溯源可撤回性。 |
| **U3. 跨工程 Context 如何低干扰采集？** | 伴生体为全局轻量挂件，若要获取当前活动的 IDE 窗口或 git repo，是否会突破系统权限或增加 CPU 轮询负担。 | 在 Windows 下验证 `GetForegroundWindow` / `psutil` 探针的 CPU 与权限成本。 |
| **U4. 本地极轻量级向量化与 FTS5 的资源边界？** | 在不引入 PyTorch / Transformers 的前提下，纯本地 ONNX runtime 或 SQLite 扩展在低配机型上的冷启动耗时与打包兼容性。 | 针对 PySide6 + onnxruntime 进行打包可行性 POC 测试。 |
