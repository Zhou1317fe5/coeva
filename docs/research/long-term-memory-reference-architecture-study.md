# Co-evolving Companion：长期记忆参考架构专项调研报告
## ——Hindsight、TDAI、Mem0、Letta 与 Graphiti 的机制解剖、对比与 Coeva 适配评价

> **调研基准与边界声明**：
> - **调研日期**：2026-10-18
> - **被调研项目与源码载体**（已下载至本地 `G:\memory_research\` 并完成源码级核验）：
>   1. **Hindsight**：`vectorize-io/hindsight`（Commit `dd7e2524` / v1.0.0）
>   2. **TDAI / TencentDB Agent Memory**：`Tencent/TencentDB-Agent-Memory`（Commit `4129-stars` 阶段态）
>   3. **Mem0**：`mem0ai/mem0`（Commit `v1.1+` / v3-pipeline 阶段态）
>   4. **Letta / MemGPT**：`letta-ai/letta`（`letta-code` v0.1+ / MemFS 阶段态）
>   5. **Graphiti / Zep**（时序知识图谱补充）：`getzep/graphiti`（`graphiti_core` v0.3+）
> - **证据级别规范**：
>   - `[官方代码事实]`：经本地克隆仓库的代码行、函数名、数据模型与逻辑分支验证；
>   - `[官方文档事实]`：官方 GitHub README、官方使用手册、Migration Guide 等正式发布文档；
>   - `[论文事实]`：经同行评审或预印本学术论文（Mem0 arXiv:2504.19413、MemGPT arXiv:2310.08560、Zep/Graphiti Benchmark 等）正式阐述；
>   - `[项目作者观点]`：作者在官方博客、Issue、PR 中的设计意图阐述；
>   - `[分析推断]`：结合技术特征与工业实践进行的逻辑推理；
>   - `[Coeva 适配判断]`：紧扣 Coeva 平级伴生体哲学、本地轻量桌宠约束进行的适用性裁剪分析；
>   - `[Unknown]`：无可靠公开证据支持的事项。
> - **硬性约束**：本轮属于参考架构研究，**严禁设计 Coeva V2 的最终技术选型与具体数据库 Schema**，重点提炼思想资产与规避工程陷阱。

---

## 1. Executive Summary（执行摘要）

当前大模型智能体的“长期记忆（Long-Term Memory）”领域已从单纯的“长上下文拼接”与“扁平向量 RAG（Flat Vector RAG）”向**状态管理、时序演化与语义分层**全面演化。通过对业界 5 大代表性架构的深度代码与论文解剖，核心全局事实如下：

1. **扁平向量存储正在被结构化分层全面替代**：
   - 无论是 TDAI 的四层金字塔（L0 Conversation → L1 Atom → L2 Scenario → L3 Persona），还是 Hindsight 的生物拟态记忆链（World/Experiences → Observations → Mental Models），亦或 Letta 的操作系统分层（Core Memory / Recall / Archival），业界一致确认：**直接切碎对话喂入向量库在跨会话多轮场景下必定失效**。宏观结构指引与微观证据沉淀必须物理分层。
2. **“冲突解决（Reconciliation）”发生的时间点是核心分水岭**：
   - **写入时调和（Write-time Reconciliation，以 Mem0 为代表）**：新事实入库前先召回相似历史，由模型裁定 `ADD / UPDATE / DELETE / NOOP`，确保数据库内状态始终自洽，避免检索时“矛盾事实堆叠”；
   - **检索时调和（Query-time Reconciliation，以 Hindsight 为代表）**：写入时不做过度覆盖，后台通过异步 Consolidator 提炼 Observation，并在检索时融合 BM25、向量、图谱与时间窗口，通过 RRF 与 Cross-Encoder 实时重排；
   - **时序双时间戳置失效（Bitemporal Invalidation，以 Graphiti 为代表）**：通过 `valid_at` 与 `invalid_at` 记录真实世界时间与系统认知时间，旧事实不物理删除而打上失效标签，保留完整历史演进轨迹。
3. **“记忆被召回”绝对不等于“必须在对话中说出来”**：
   - 现有一切面向生产力的 Agent Memory 系统（如 Mem0、Letta、TDAI）均以“最大化自动化服务”为目标，追求召回率并在 Prompt 中强行注入画像以指导工具规划；
   - **这与 Coeva 的核心哲学存在根本性冲突**。Coeva 是一只长期共同生活的平级数字伙伴，奉行“80% 静默倾听、15% 轻微共鸣、5% 适时提问”。对 Coeva 而言，**`Retrieved ≠ Injected ≠ Spoken`（召回、注入、开口表达三权分离）** 是业界所有项目均未完全解决、必须由 Coeva 独立攻克的核心命题。
4. **轻量桌面常驻与企业级重型框架的鸿沟**：
   - Hindsight 依赖 PostgreSQL + pgvector 与多重模型后台；Letta 转向云服务平台与重型 Runtime；Graphiti 依赖 FalkorDB/Neo4j 与多次 LLM 抽取；
   - TDAI（SQLite + FTS5 + sqlite-vec + Markdown）与 Mem0 的早期单机写入决策层，为 Coeva 提供了最现实的**本地无依赖、白盒可调试、低资源常驻**的思想借鉴底座。

---

## 2. Coeva Requirements Used for Evaluation（Coeva 评估基线与哲学红线）

在评判任何外部技术前，必须以 Coeva 既定的产品哲学与已确认缺陷为唯一衡量尺度：

1. **80 / 15 / 5 与 Silence Is Valid**：
   - 绝大多数时候伴生体应保持安静微呼吸，不主动拿往事打扰用户；
   - 检索命中历史只代表系统具有背景知识，绝不代表当前交互必须主动提及旧事。
2. **避风港（Sanctuary First）绝对红线**：
   - 用户受挫、疲惫、抱怨时，系统进入静默陪伴模式，严禁因为检索命中历史就翻旧账或发起反思讨论。
3. **平级伙伴，绝非画像分析器（No Rigid User Persona）**：
   - 坚决拒斥将用户标签化固化为静态 Profile；任何高层认知必须是可不确定的、可撤销的、需双方共同校准的。
4. **User Voice > Telemetry Interpretation**：
   - 用户主动随手投喂的文字具有最高认识论优先级，系统从 Agent 工具调用等遥测中挖掘的推断永远不得凌驾于用户明示。
5. **本地轻量优先（Local-first & Lightweight）**：
   - 必须在 Python 3.11+ / PySide6 / SQLite / Windows 桌面常驻环境下稳定运行，不接受 Docker 常驻、重型微服务或数 GB 依赖。
6. **外部 Agent 隐私边界**：
   - 不采集外部 Agent 的思维链（CoT）、工具执行完整返回值与 Prompt 原文，仅保留行为骨架。

---

## 3. Research Method & Sources（调研方法与信息源）

本报告基于以下一手技术资料进行深度分析：

- **官方源码**：本地克隆并分析 `vectorize-io/hindsight`、`Tencent/TencentDB-Agent-Memory`、`mem0ai/mem0`、`letta-ai/letta`、`letta-ai/letta-code`、`getzep/graphiti` 的关键实现；
- **官方文档与规范**：各项目的官方 Readme、API Reference、Design Architecture、Migration Guides；
- **学术论文**：
  - *Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory* (arXiv:2504.19413)
  - *MemGPT: Towards LLMs as Operating Systems* (Packer et al., arXiv:2310.08560)
  - *Graphiti / Zep LongMemEval Technical Report & Temporal Benchmark* (2024–2026)
  - *Reciprocal Rank Fusion in Information Retrieval* (Cormack et al., 2009)

---

## 4. Hindsight Architecture Study（Hindsight 深度解剖）

### 4.1 核心哲学与架构定位
- `[官方文档事实]` Hindsight™ 定位为“会学习的智能体记忆（Agent Memory That Learns）”，强调生物拟态数据结构（Biomimetic Memory），反对传统 RAG 将历史剁碎丢入扁平向量库的粗暴做法。
- `[官方代码事实]` 核心运行链路分为三大动词：`retain`（沉淀）、`recall`（回忆）、`reflect`（深思）。

### 4.2 记忆单元与分层模型
`[官方代码事实]`（`hindsight-api-slim/hindsight_api/engine/schema.py` 及 `database.sql`）：
- **底层事实与经历（World Facts & Experiences）**：
  - 存储在 `memory_units` 表，区分外部世界客观事实与 Agent 自身经历；
  - 伴随实体链接表 `entities`、`unit_entities`、`memory_links` 与原始文档分块 `documents`、`chunks`。
- **观察层（Observations，核心创新）**：
  - 并非单条记忆，而是后台 Consolidator（`engine/consolidation/consolidator.py`）将多条关联事实提炼去重形成的共识信念；
  - 特征字段：`fact_type='observation'`，记录 `proof_count`（支撑证据数量）、`source_memory_ids`（溯源 UUID 数组）与 `history`（演进变化的 JSONB 记录）。
- **心理模型与知识页面（Mental Models & Knowledge Pages）**：
  - 针对常设问题（如“用户的开发习惯是什么”）的活体文档（Living Document）；
  - 查询 Mental Model 是纯粹的数据库静态读取，**零 LLM 耗时、零检索开销**；内容由后台异步任务定期重写。

### 4.3 写入、提炼与调和链路（Retain & Consolidation）
1. `[官方代码事实]` **写入阶段（Retain）**：
   - 接收用户消息、上下文标签与时间戳；
   - 经由 `fact_extraction.py` 调用大模型，提取出离散事实、实体关系三元组及时间范围；
   - 写入 `memory_units`，立即生成向量嵌入与 BM25 分词索引。
2. `[官方代码事实]` **后台巩固阶段（Consolidation）**：
   - `run_consolidation_job` 扫描未巩固记忆；
   - 召回同 Scope（如 `[user:<id>]`）的现有 Observations；
   - 由 LLM 裁定动作：`CREATE`（新建信念）、`REVISE`（修正信念）、`EXTEND`（扩展信念）、`WEAKEN`（新证据冲突导致信念弱化）或 `NOOP`。

### 4.4 检索引擎（Recall）
`[官方代码事实]`（`engine/search/retrieval.py` 与 `fusion.py`）：
- **4 路并行召回**：
  1. `Semantic`：向量相似度匹配；
  2. `BM25`：精确关键词匹配；
  3. `Graph`：沿实体网络与因果链跳跃扩展；
  4. `Temporal`：相对/绝对时间窗口过滤。
- **排序与重排**：4 路候选经由 **RRF（Reciprocal Rank Fusion）** 融合后，通过 Cross-Encoder / Jina 深度重排模型（`reranking.py`）计算最终相关度得分并截断。

### 4.5 对 Coeva 的价值与冲突
- `[Coeva 适配判断]` **高价值思想**：
  - `Observation` 的“证据支撑计数（`proof_count`）与来源追溯（`source_memory_ids`）”极其契合 Coeva 的高层假说（Hypotheses）建模；
  - `Mental Model` 作为免实时检索的常设画像，提供平级认知参考。
- `[Coeva 适配判断]` **不可照搬之处**：
  - Hindsight 依赖完整的异步微服务 Worker、PostgreSQL 扩展、Cross-Encoder 专用重排模型与大量后台 LLM 提炼，对本地桌宠而言运行时过于沉重；
  - 其默认的 `auto-memory` 模式倾向于在每次 Turn 结束全量 retain、开始前全量注入，违背 Coeva 桌面极简与数据面隔离红线。

---

## 5. TDAI / TencentDB Agent Memory Architecture Study（TDAI 深度解剖）

### 5.1 核心哲学与架构定位
- `[官方文档事实]` 腾讯云开源的 Agent 记忆系统，提出**“记忆不是向量堆，是金字塔；短期任务状态是符号地图，不是纯文本日志”**。
- `[官方代码事实]` 面向长周期任务，专为解决“Agent 每次重开都重新询问技术栈和偏好”及“长任务工具输出撑爆上下文”而设计。

### 5.2 长期记忆四层金字塔（L0 → L3）
`[官方代码事实]`（`MemoryCore/src/core/`）：

```text
┌──────────────────────────────────────────────┐
│  L3 Persona (用户画像: persona.md)            │ ← 跨 Session 稳定风格、偏好 (人类可读编辑)
├──────────────────────────────────────────────┤
│  L2 Scenario (场景经验: scenario/*.md)        │ ← 按项目/任务聚合的经验块模板
├──────────────────────────────────────────────┤
│  L1 Atom (原子事实: memory/*.jsonl / SQLite)  │ ← 事实、偏好、约束、里程碑 (支持检索)
├──────────────────────────────────────────────┤
│  L0 Conversation (原始对话日志: SQLite/JSONL) │ ← 全量不可变物理证据 (宁可多存，不可丢据)
└──────────────────────────────────────────────┘
```

1. **L0 原始对话**：全量保留对话文本与元数据，作为不可篡改的事实源底座；
2. **L1 原子记忆**：通过 LLM 从 L0 对话中周期性抽取（事实 Fact、偏好 Preference、约束 Constraint、阶段结论 Milestone）；
3. **L2 场景经验**：把多轮交互中关于某一主题（如 API 规范、桌宠渲染配置）的原子事实聚合为可复用的场景 Markdown 文件；
4. **L3 用户画像**：累计达到阈值后从 L2 蒸馏出最高层、跨场景通用的特征并写入 `persona.md`。

### 5.3 短期符号化任务记忆（Mermaid Task Canvas）
- `[官方文档与代码事实]`（`MemoryCore/src/offload/`）：
  - 针对编程任务中动辄数十万 Token 的工具输出（搜索结果、文件读取、报错堆栈），TDAI 实施**指针化卸载（Pointer-based Offloading）**；
  - 工具全文卸载至外部文件 `refs/*.md`；
  - 上下文内部仅保留一张带有 `node_id` 的极轻量 **Mermaid 流程图（Task Canvas）**；
  - 模型在执行长任务时根据 Mermaid 状态机判定当前进度，仅在需要细节时通过 `node_id` 单点回查原文。

### 5.4 检索引擎与全链路溯源
- `[官方代码事实]`（`src/core/tools/memory-search.ts`）：
  - **检索实现**：SQLite FTS5（支持 jieba 分词）+ `sqlite-vec` 向量嵌入，并通过经典 `RRF (k=60)` 融合；
  - **白盒可调试与追溯**：
    `L3 Persona → 引用来源 Scenario → 引用来源 Atom (result_ref) → 引用来源 L0 对话`。
    任何高层理解均可通过 Markdown 超链接或 JSON 引用追踪到底层真实对话。

### 5.5 致命缺陷：管理空缺（The Curation Gap）
- `[项目作者与分析观点]` 正如第三方评测（Emre Bener）与源码所揭示：
  - **TDAI 解决了压缩问题，但几乎没有解决“筛选与淘汰（Curation & Invalidation）”问题**；
  - 任务中的临时错误、一次性试错甚至模型被纠正前的胡说八道，一旦被提炼进 L1 并层层汇总至 L3，**系统内部没有任何自动过期、废弃或撤回机制**；
  - 纠正错误完全依赖人类手动打开 `persona.md` 或 Markdown 文件手动删行。

### 5.6 对 Coeva 的价值与冲突
- `[Coeva 适配判断]` **高价值思想**：
  - 顶层使用人类可直接查阅、可 Git 管理的纯 Markdown（如 Coeva 的 Growth Chapters），底层使用 SQLite 保持原子索引，这种**异构白盒架构**非常契合 Coeva 的本地优先理念；
  - 全链路显式溯源（`result_ref`）是实现“不把伴生体推断当真理”的最佳参照。
- `[Coeva 适配判断]` **不可照搬之处**：
  - L3 Persona 的静态画像固化倾向严重，一旦生成容易形成刻板偏见；
  - 缺乏机器自动的时效性废弃机制。

---

## 6. Mem0 Architecture Study（Mem0 深度解剖）

### 6.1 核心哲学与演进分化
- `[论文事实]`（arXiv:2504.19413）：Mem0 将长期记忆定义为“状态管理（State Management）问题而非单纯检索”，提出 **`ADD / UPDATE / DELETE / NOOP` 四操作写入调和循环**。
- `[官方代码事实]`（`mem0/memory/main.py`）：
  - **演进差异警示**：当前开源代码（v1.1+ / v3-pipeline）已默认转向 **Single-pass ADD-only 累积模式**，将记忆作为不断堆叠的事实流，冲突解决被推迟到检索阶段通过访问衰减（Decay）与向量权重处理；
  - 但**论文中的经典四操作写入决策层**（保留在 `mem0/configs/prompts.py` 中的 `DEFAULT_UPDATE_MEMORY_PROMPT`）对避免数据堆积具有极高借鉴价值。

### 6.2 经典两阶段写入决策循环（Two-Phase Write Pipeline）
`[论文与代码事实]`：

```text
新对话轮次 (Message Pair)
    ↓ (Phase 1: Fact Extraction)
提取候选事实 (Candidate Facts: 1~3 条)
    ↓ (Phase 2: Semantic Pre-retrieval)
针对每条候选事实，在向量库中取 Top-S 相似旧记忆
    ↓ (Phase 3: LLM Reconcile Decision)
LLM 比较 [候选新事实] 与 [召回旧记忆]，严格执行四选一：
    ├── ADD    : 全新信息，生成新 ID 写入
    ├── UPDATE : 对既有同一事实的补充、修正或更新（继承旧 ID 覆盖）
    ├── DELETE : 新信息直接推翻/撤回既有事实（物理删除或置失效）
    └── NOOP   : 既有记忆已涵盖，或属于瞬时废话，直接丢弃
```

### 6.3 遗忘机制与检索衰减（Decay）
- `[官方代码与文档事实]`：
  - **物理硬删除（Hard Delete）**：支持按 ID、批量或按作用域（User / Agent / Run）物理删除；
  - **记忆访问衰减（Memory Decay，基于 Bjork 记忆强度理论）**：
    - 不物理驱逐数据，而是在检索打分时实施动态加权；
    - 近期被访问的记忆获得最高 **1.5× 得分加权**；
    - 长期未被调用的低频记忆逐步衰减至 **0.3×**；
    - 衰减记忆仍保留在存储中，若发生强相关语义匹配仍有机会被激活。

### 6.4 检索引擎（Retrieval）
`[官方代码事实]`（`mem0/utils/scoring.py`）：
- 融合三路信号：
  1. 密集向量余弦相似度（Dense Vector Similarity）；
  2. 词形还原后的 BM25 词频得分（Lemmatized BM25）；
  3. 命名实体提升权重（Entity Boost Weight）。
- 设定最低截断阈值，过滤低相关度噪音。

### 6.5 对 Coeva 的价值与冲突
- `[Coeva 适配判断]` **高价值思想**：
  - **“写入前先检索相似旧记忆，再由 LLM 进行 ADD/UPDATE/DELETE/NOOP 决策”是解决 Coeva 随手投喂重复切片与偏好冲突的最优解**；
  - 检索衰减（Decay）机制让沉睡记忆自然退居幕后，契合伴生体自然遗忘感。
- `[Coeva 适配判断]` **不可照搬之处**：
  - 当前 OSS 版本的全量 ADD-only 堆叠方案不可取；
  - 默认对单条对话进行同步 LLM 抽取与多次向量写入，在本地单机桌宠环境下存在 API 费用与主线程卡顿风险。

---

## 7. Letta / MemGPT Architecture Study（Letta / MemGPT 深度解剖）

### 7.1 核心哲学与操作系统隐喻
- `[论文事实]`（arXiv:2310.08560）：将大语言模型类比为操作系统（OS），有限的 Context Window 是物理内存（RAM），外部数据库是硬盘（Disk）。
- `[官方代码事实]`（`letta-code` / `letta/schemas/memory.py`）：
  - 核心运行逻辑不是被动式的透明注入，而是**将记忆系统显式暴露为模型工具，赋权智能体自我管理记忆（Self-Editing Memory）**。

### 7.2 三层记忆结构（Three Memory Tiers）
`[官方代码事实]`：
1. **核心记忆（Core Memory / Memory Blocks）**：
   - 始终常驻在 System Prompt 内部，占用固定字符预算（默认通过 `<memory_blocks>` 标签渲染）；
   - 包含常设 Block：`<human>`（记录关于用户的核心关键事实）、`<persona>`（记录智能体自身人设与行为准则）；
   - 智能体可在思考过程中主动调用 `core_memory_append` 与 `core_memory_replace` 修改这些 Block。
2. **回忆记忆（Recall Memory）**：
   - 会话交互历史的滑动流，超出窗口时触发 Compaction 压缩。
3. **归档记忆（Archival Memory）**：
   - 外部近乎无限的向量数据库；
   - 智能体按需调用 `archival_memory_insert` 存入知识，调用 `archival_memory_search` 检索段落。

### 7.3 后台做梦机制（Dreaming Subagents）
- `[官方文档事实]` Letta 引入离线“做梦（Dreaming）”后台子任务：在会话空闲或夜间，由后台独立 Agent 复盘最近的对话日志，提炼教训与跨会话事实，静默更新 Core Memory Blocks，而不会在主交互中产生延迟。

### 7.4 对 Coeva 的价值与冲突
- `[Coeva 适配判断]` **高价值思想**：
  - Core Memory 的字符预算硬约束（`char_limit`）与 XML-like 结构化分区，彻底根治了 Prompt 无限制膨胀问题；
  - 离线 Dreaming 思想与 Coeva 的“夜间生命档案整理”哲学高度共鸣。
- `[Coeva 适配判断]` **不可照搬之处**：
  - **坚决否定 Agent 完全自主自编辑（Unrestricted Self-Editing）**：
    在 Coeva 中，若允许伴生体随意调用工具修改用户认知，模型极易产生认知偏差与幻觉固化。Coeva 必须坚持“用户校准优先（Calibration-First）”，高层认知修改必须由人类确认或具备显式否定权。

---

## 8. Optional Temporal Memory Supplement（Graphiti / Zep 时序知识图谱补充）

### 8.1 解决的根本问题
- `[论文与官方文档事实]` 解决“过去是真的，但现在已经不是真的”以及“如何回答历史上某一特定时刻的状态（Point-in-time Reasoning）”。

### 8.2 双时间戳动态边模型（Bitemporal Edge Invalidation）
`[官方代码事实]`（`graphiti_core/edges.py:274-285`）：
在 Graphiti 中，每一条从 Episode（原始消息段落）中提取的实体关系边（EntityEdge）均携带严格的时间范围元数据：

```python
class EntityEdge(Edge):
    valid_at: datetime | None      # 事实在现实世界中成立的起始时间
    invalid_at: datetime | None    # 事实在现实世界中失效/被取代的终止时间
    reference_time: datetime | None # 产生此事实的对话/事件发生基准时间
    created_at: datetime           # 系统写入数据库的物理入库时间
```

### 8.3 冲突处理机制：置失效而非物理删除
- `[官方代码事实]` 当新对话产生与历史冲突的新事实时（例如从“住在北京”变为“搬到了上海”）：
  1. 系统在图谱中**绝不执行 `DELETE` 物理删除**；
  2. 找到原有的边（`Alice -[lives_in]-> Beijing`），将该边的 `invalid_at` 设为搬家时间戳；
  3. 创建一条新的边（`Alice -[lives_in]-> Shanghai`），`valid_at` 为搬家时间戳，`invalid_at` 为 `None`；
  4. 两条边均保留指向对应原始 `Episode` 的溯源指针。

### 8.4 对 Coeva 的价值与边界
- `[Coeva 适配判断]` **思想提炼**：
  Coeva 不需要引入沉重的图数据库（如 Neo4j / Kuzu），但 Graphiti 的**“不物理删除旧事实，而是标记 `invalid_at` / `superseded_by`”** 的数据建模思想，是解决用户习惯偏好演进与“翻旧账”问题的终极答案。

---

## 9. 专项能力横向机制对比（18 大维度代码级分析）

### 9.1 Memory Admission（准入与过滤机制）
- **Hindsight**：`[代码事实]` 采用两级准入。`retain()` API 接收原始文本，通过 LLM 过滤掉纯寒暄，提取离散事实与实体。支持 `Memory Defense` 正则扫描脱敏 45 类敏感凭据。
- **TDAI**：`[代码事实]` 采用排队节律。L0 全量捕获；L1 默认每 5 轮或空闲 10 分钟批量抽取；冷启动通过指数退避 Warmup（1 → 2 → 4 轮）。
- **Mem0**：`[代码事实]` `_add_to_vector_store` 中由 LLM 根据提示词提取 Facts。如果模型判定输入仅为问候（如“Hi”），直接返回 `{"facts": []}`，不执行入库。
- **Letta**：`[代码事实]` 智能体自我准入。模型在执行过程中自主决定是否调用 `archival_memory_insert`。缺点是容易漏记或过载。
- **Coeva 裁定**：应借鉴 Mem0/Hindsight 的“抽取前 LLM 空事实过滤（Facts=[] 拒入）”，彻底阻断“测试气泡”、“hi”等无效切片落盘。

### 9.2 Memory Representation（表示形式与数据单位）
- **Hindsight**：`[代码事实]` 混合表示。原始段落（Chunks）+ 离散记忆单元（`memory_units`）+ 聚合信念（`observations`）+ 常设知识页（`mental_models`）。
- **TDAI**：`[代码事实]` 四级递进。L0 Markdown 对话 → L1 JSONL 原子事实 → L2 场景经验 Markdown → L3 角色画像 Markdown。
- **Mem0**：`[代码事实]` 扁平自然语言短句（Atomic Statements，如 “User prefers dark mode”），附带 metadata 字典。
- **Letta**：`[代码事实]` 块状纯文本（Core Blocks: `<human>`, `<persona>`）+ 向量片段（Archival Passages）。
- **Coeva 裁定**：原子事实（Fact）与高层理解（Understanding）必须物理分离，严禁直接混在同张平铺表。

### 9.3 Short-term → Long-term Consolidation（巩固机制）
- **Hindsight**：`[代码事实]` 独立的后台异步 Consolidator 任务，通过 Scope 锁控制并发，利用 LLM 将 facts 归纳为 observations。
- **TDAI**：`[代码事实]` 阶梯式自动蒸馏。50 条 L1 聚合成 L2，50 条 L2 蒸馏出 L3。
- **Mem0**：`[代码事实]` 实时在线写入时调和（单轮即时完成），无专门跨会话的大周期 consolidation。
- **Letta**：`[代码事实]` 上下文压力触发 Compaction；或利用后台 Dreaming subagent 异步阅读历史对话整理心得。
- **Coeva 裁定**：Coeva 适合借鉴 Letta 的“空闲/夜间 Dreaming”配合 Hindsight 的 Observation 机制，在用户离开桌面时做慢速静默提炼。

### 9.4 Salience / Importance（重要性度量）
- **Hindsight**：`[代码事实]` 通过 `proof_count`（被多少条独立事实印证）作为信念的物理重要度。
- **TDAI**：`[代码事实]` 包含 `priority`（1~5 整数），由抽取时 LLM 给出；高层 Persona 默认权重最高。
- **Mem0**：`[代码事实]` 具备记忆访问衰减因子（Decay Factor，基于最近访问频次与时间加权计算）。
- **Letta**：`[代码事实]` 显式划分为常驻 Core（最高重要度）与外部 Archival（普通重要度）。
- **Coeva 裁定**：应引入 `proof_count`（证据频次）与 `user_confirmed`（用户是否确认），拒绝无凭据的静态重要性打分。

### 9.5 Temporal Validity（时效性建模）
- **Hindsight**：`[代码事实]` 具备 `temporal_periods.py` 解析相对日期；但事实本身无显式截止期。
- **TDAI**：`[代码事实]` 无时效性标记；靠人手动编辑 Markdown。
- **Mem0**：`[代码事实]` 开源版支持 `expiration_date`（到期自动隐藏）；云平台版支持时序分析。
- **Graphiti**：`[代码事实]` 行业标杆，双时间戳 `valid_at` 与 `invalid_at`。
- **Coeva 裁定**：必须引入 `valid_from` 与 `invalid_at`，这是消除新旧偏好冲突的核心底座。

### 9.6 Contradiction Handling（矛盾与覆盖机制）
- **Mem0**：`[代码事实]` **写入时裁决**。LLM 发现新事实推翻旧事实，直接标记 `UPDATE` 并覆写旧文本，或标记 `DELETE`。
- **Graphiti**：`[代码事实]` **图谱关系置失效**。老关系标记 `invalid_at`，新关系建立，保留双向证据。
- **Hindsight**：`[代码事实]` **信念弱化/修订**。Consolidator 遇到矛盾事实时执行 `REVISE` 或 `WEAKEN`，降低 observation 置信度。
- **TDAI**：`[代码事实]` **无自动化冲突处理**，新老事实共存。
- **Coeva 裁定**：采用“置失效保留痕迹”而非粗暴物理覆盖，既知道最新偏好，又保留“用户过去曾喜欢 X”的历史演化认知。

### 9.7 Forgetting（遗忘与生命周期）
- **物理硬删除 vs 检索降权**：
  - Mem0 区分 Hard Delete 与 Retrieval Decay；
  - Hindsight 拥有 `invalidated_memory_units` 归档表；
  - TDAI 拥有 L0/L1 30 天自动清理参数 `capture.l0l1RetentionDays`。
- **Coeva 裁定**：区分“事实降权进入冷库”与“用户要求 GDPR 级硬删除”。

### 9.8 Provenance / Traceability（证据溯源）
- **TDAI**：`[代码事实]` 表现最好。每个 Atom 带 `result_ref`，每个 Scenario 带关联会话，每个 Persona 带来源场景，完全白盒透明。
- **Hindsight**：`[代码事实]` 每个 Observation 的 `source_memory_ids` 强外键指向底层原始 Memory Units。
- **Mem0 / Letta**：`[代码事实]` 弱溯源，主要保留原始会话或创建时间戳。
- **Coeva 裁定**：坚决继承 TDAI 与 Hindsight 的“强引用链”，伴生体的任何判断必须能向用户解释“我是因为哪几件事才这么认为的”。

### 9.9 Retrieval Architecture（多通道检索架构）
- **Hindsight**：`[代码事实]` 4 路并行（Semantic + BM25 + Graph + Temporal） + RRF + Cross-Encoder Reranker。
- **TDAI**：`[代码事实]` 2 路并行（FTS5 BM25 + sqlite-vec Vector） + RRF (k=60) + 纯本地降级支持。
- **Mem0**：`[代码事实]` 密集向量 + 词形还原 BM25 + 实体提升加权评分。
- **Letta**：`[代码事实]` 区分 Core（无检索直接注入）与 Archival（纯向量相似度检索）。
- **Coeva 裁定**：TDAI 的 **FTS5 (BM25) + 本地向量 (sqlite-vec) + RRF (k=60)** 是适配本地桌面桌宠的最稳健组合。

### 9.10 No-Memory Decision（静默与空召回能力）
- **各项目表现**：
  - Hindsight 允许设定 `min_semantic` 与 `min_keyword` 阈值，低于阈值返回空结果集；
  - TDAI 与 Mem0 在未达阈值或搜索词为空时均具备返回空结果（`[]`）机制；
- **核心缺口**：
  - 所有生产力项目都在追求“只要用户问了，就尽最大努力召回”；
  - **没有任何外部项目具备“伴生体情感/状态意图门控”**（即：即使搜到了相关历史，在用户受挫或进行瞬时打招呼时，伴生体应当主动压制、不注入、不提及）。
- **Coeva 裁定**：这必须是 Coeva 的核心自主创新点（结合 Sanctuary Guard 与 80/15/5 策略的 `Recall Gate`）。

### 9.11 Context Injection（Prompt 组装形态）
- **Letta**：`[代码事实]` 采用标准化 XML 标签 `<memory_blocks>` 与 `<external_memory>`。
- **Hindsight**：`[代码事实]` 采用 `<hindsight_memories>` 围栏，且具备**反馈环路守卫（Feedback-Loop Guard）**，防止注入的旧记忆在当前轮次被重复当作新事实二次存入。
- **TDAI**：`[代码事实]` 在会话初始化时注入 `<system_persona>`。
- **Coeva 裁定**：必须引入 Hindsight 的 Feedback-Loop Guard，并严格为注入条目标明时间坐标系与非强迫提示（“仅作背景参考，不相关请忽略”）。

### 9.12 Higher-level Understanding & Persona（高层理解与画像哲学）
- **TDAI L3 Persona**：LLM 自动提炼的职业风格描述，倾向于确定性画像；
- **Hindsight Mental Model**：针对特定业务疑问的活体总结文档；
- **Mem0 Profile**：自动累积的用户习惯标签；
- **Coeva 哲学对齐**：
  - **坚决拒绝单向将用户标签化**；
  - 外部项目的 Persona 是服务于“AI 提高干活效率”；Coeva 的认知模型是服务于“数字伙伴理解用户的心理灵活性”，必须保持谦抑、不笃定、可被校准。

### 9.13 Multi-Agent Memory（多 Agent 共享空间）
- **TDAI**：`[代码事实]` 设计了清晰的 `RuntimeContext`，通过 `team_id`, `user_id`, `agent_id`, `task_id` 进行层级隔离与命名空间共享；支持 OpenClaw 与 Hermes 双客户端连接同一 Gateway。
- **Hindsight**：`[代码事实]` 严格以 `bank_id` 作为物理隔离空间，通过 `tags`（如 `harness:pi`, `project:xxx`）实现跨 Agent 过滤。
- **Mem0**：`[代码事实]` 明确的 `user_id`, `agent_id`, `run_id` 过滤体系。
- **Coeva 裁定**：完全吸收 Hindsight/TDAI 的命名空间模式，为 Hermes, Pi, Codex, Vasu 提供基于项目（Project）的统一证据底座。

### 9.14 Privacy & Local-first Deployment（隐私与部署代价）
- **Hindsight**：Docker / 云端服务，Postgres + 外部 LLM API，部署重。
- **TDAI**：本地 SQLite + 纯文本 Markdown，Node.js Core，部署成本中等。
- **Mem0**：pip 包，支持纯内存/本地 Qdrant/Postgres，依赖轻量。
- **Letta**：转向平台与云端架构，本地部署较复杂。
- **Graphiti**：依赖图数据库容器（FalkorDB/Neo4j）。
- **Coeva 裁定**：Coeva 必须坚守纯 Python/SQLite 本地单机常驻底线。

---

## 10. Architecture Cards（四大主流系统架构卡片）

### 架构卡片 1：Hindsight
```text
Project: Hindsight (vectorize-io/hindsight)
Primary Goal: 构建具备持续学习与反思能力的智能体长期记忆系统。
Core Memory Philosophy: 生物拟态分层（Biomimetic Memory），反对扁平向量堆砌，强调信念提炼与反思。
Memory Unit: Memory Unit（三元组/事实片段）、Observation（共识信念）、Mental Model（活体认知文档）。
Memory Layers: 3层（Raw Facts/Experiences → Observations → Mental Models/Knowledge Pages）。
Write Path: client.retain() → LLM事实/时序抽取 → 正规化实体/时间序列 → 向量/FTS索引入库 → 触发异步任务。
Consolidation: 后台 Consolidator 任务：读取增量 Facts，比对现有 Observations，LLM 裁定 CREATE/REVISE/EXTEND/WEAKEN。
Retrieval: 4路并行（Semantic 向量 + BM25 词频 + Graph 实体因果扩展 + Temporal 时间窗口） + RRF 融合 + 深度重排。
Temporal Handling: 解析自然语言相对时间；支持时间窗口过滤；实体记录事件参考时间。
Contradiction Handling: 在 Consolidation 阶段通过 REVISE/WEAKEN 调整信念强度，不物理删除底层证据。
Forgetting: 具备 invalidated_memory_units 软退役表；支持标签与作用域清理。
Higher-level Understanding: reflect() 动词支持多跳反思合成；Mental Model 作为常设活体知识页面。
User Model: 依赖 Mental Model 形成常设认知；Bank 配置中注入性格特质（Disposition）。
Provenance: Observation 严格记录 proof_count 与 source_memory_ids 溯源外键。
Deployment: PostgreSQL + pgvector 或 Oracle AI 23ai；独立 Worker 进程；强依赖外部 LLM/Embedding API。
What It Does Well: 4路混合检索融合极高精度；Observation 证据计数体系非常严谨；Feedback Loop 防重复防卫周全。
What It Does Poorly: 部署极重，必须依赖 Postgres 服务；单次抽取与后台 Consolidate 消耗大量 LLM Token。
What Coeva Can Learn: Observation 的 proof_count 与溯源数组设计；Prompt 注入时的防自环 Feedback 守卫。
What Coeva Should NOT Copy: 重型 PostgreSQL + 独立 Worker 架构；全量 Turn 自动 retain/recall 强侵入模式。
```

---

### 架构卡片 2：TDAI / TencentDB Agent Memory
```text
Project: TDAI (Tencent/TencentDB-Agent-Memory)
Primary Goal: 为长程会话与编程助手提供白盒分层记忆与任务状态压缩，消除跨 Session 遗忘与上下文爆炸。
Core Memory Philosophy: 长期记忆是自下而上的语义金字塔；短期任务状态是符号流程图。
Memory Unit: L0 对话行、L1 原子记忆（JSONL）、L2 场景经验（Markdown）、L3 画像（Markdown）。
Memory Layers: 4层（L0 Conversation → L1 Atom → L2 Scenario → L3 Persona）。
Write Path: 监听对话完成 → 定期（默认5轮）触发 L1 抽取 → 积累达标触发 L2/L3 Markdown 蒸馏生成。
Consolidation: 阶段式自动向上合并：L0 累积抽取至 L1；50条 L1 聚合成 L2；50条 L2 蒸馏出 L3。
Retrieval: 双路并行（FTS5 BM25 + sqlite-vec 向量），经典 RRF (k=60) 融合；分层自顶向下查找。
Temporal Handling: 记录起止时间戳；支持按天清理 L0/L1；但高层经验无失效机制。
Contradiction Handling: 严重缺失。新老事实共存堆叠；完全依赖人类手动编辑 Markdown 修正。
Forgetting: 支持配置 L0/L1 物理保留天数（默认30天）；L2/L3 永久留存。
Higher-level Understanding: L2 提取场景经验块；L3 蒸馏用户长期风格画像。
User Model: persona.md 集中固化技术栈、工作习惯与沟通偏好。
Provenance: 极强。L3 链接 L2，L2 链接 L1，L1 通过 result_ref 强指向 L0 对话原文。
Deployment: 本地 Node.js Gateway + SQLite/sqlite-vec；或云端 Tencent VDB；支持 Docker Sidecar。
What It Does Well: 顶层纯 Markdown 白盒可读可调试；Mermaid 任务图大幅压缩短期 Token；RRF 融合简洁高效。
What It Does Poorly: 存在严重的 Curation Gap（无自动化时效失效，无冲突消除）；新冷启动周期较长。
What Coeva Can Learn: 顶层 Markdown + 底层 SQLite 的异构架构；全链路显式 result_ref 溯源；RRF 算法。
What Coeva Should NOT Copy: 缺乏时效失效的死记忆累积机制；过于武断和静态的 L3 Persona 用户画像。
```

---

### 架构卡片 3：Mem0
```text
Project: Mem0 (mem0ai/mem0)
Primary Goal: 为多会话智能体提供低延迟、高可用的自适应记忆层与状态管理。
Core Memory Philosophy: 记忆不仅是检索，更是写入时的冲突裁决与状态管理（State Management）。
Memory Unit: 离散自然语言事实（Atomic Fact Statement），附带 metadata 与 embedding。
Memory Layers: 扁平事实层（区分 User / Agent / Session 三大作用域）。
Write Path: 消息输入 → LLM 提取 Facts（若无价值则为空） → (经典算法: 相似记忆比对裁决 ADD/UPDATE/DELETE/NOOP) → 向量库落盘。
Consolidation: 实时在线写入时调和（单轮即时完成）；v3 改为持续累积。
Retrieval: 向量余弦相似度 + 词形还原 BM25 + 实体提升打分；支持分数归一化与截断。
Temporal Handling: 支持 expiration_date 到期隐藏；平台版支持时序分析。
Contradiction Handling: 经典版本通过 LLM 写入前比对直接执行 UPDATE 覆盖或 DELETE 删除；v3 依赖检索衰减。
Forgetting: 支持按 ID/Filter 物理删除；独创 Memory Decay 检索强度衰减（长期未用降权至 0.3x）。
Higher-level Understanding: 主要维持扁平事实，高级版支持实体关联子图（Mem0g）。
User Model: 围绕 user_id 组织的事实聚类。
Provenance: 弱。仅记录创建时间戳与可选的 actor_id，不保留完整的对话归属链条。
Deployment: 极轻量。纯 Python pip 包，支持本地 SQLite、Qdrant、Chroma 或云端托管。
What It Does Well: ADD/UPDATE/DELETE/NOOP 写入裁决非常干净；Memory Decay 衰减机制符合心理学；部署极简。
What It Does Poorly: 当前 v3 开源版退化为 ADD-only 导致数据堆叠；缺乏深层反思与长期章节结构。
What Coeva Can Learn: 写入前相似检索 + 四操作（ADD/UPDATE/DELETE/NOOP）决策循环；检索强度衰减打分。
What Coeva Should NOT Copy: v3 开源版无脑堆积事实的 ADD-only 策略；丢弃证据溯源的扁平化存储。
```

---

### 架构卡片 4：Letta / MemGPT
```text
Project: Letta (letta-ai/letta, f.k.a. MemGPT)
Primary Goal: 突破大模型上下文窗口物理限制，将 LLM 抽象为操作系统并提供自主内存管理。
Core Memory Philosophy: 上下文是 RAM，外部存储是 Disk，智能体应自主决定记忆的换入、换出与编辑。
Memory Unit: Core Memory Block（文本块）、Conversation Message（会话消息）、Archival Passage（归档段落）。
Memory Layers: 3层（Core Memory 常驻 → Recall Memory 会话队列 → Archival Memory 外部海量库）。
Write Path: 智能体通过 Function Call / Tools 主动执行 core_memory_append, archival_memory_insert 等。
Consolidation: 上下文超限触发 Compaction；后台 Dreaming subagent 异步阅读历史对话整理心得。
Retrieval: Core Memory 无需检索全量注入；Archival Memory 依赖智能体调用 archival_memory_search 工具按需召回。
Temporal Handling: 记录消息与段落时间戳；消息队列按时间单向修剪。
Contradiction Handling: 依赖智能体自我推理并在调用 core_memory_replace 时替换旧文本。
Forgetting: Recall 队列滑动窗口物理挤出；Archival 库无自动衰减。
Higher-level Understanding: 集中体现在 Core Memory 的 `<persona>` 与 `<human>` 块中。
User Model: 在 `<human>` 块中以自然语言维护用户核心信息，强约束字符长度上限。
Provenance: 弱。核心记忆块中内容被模型反复修改后，原始来源信息丢失。
Deployment: 现代版本已重构为客户端 SDK + 云端服务/本地 App Server；历史 Python 单机版已归档。
What It Does Well: Core Memory 字符硬约束极佳；操作系统分页与 Dreaming 思想深刻；上下文预算管理严密。
What It Does Poorly: 赋予模型完全自编辑权限，极易产生模型自说自话、篡改或遗忘；强依赖模型的高阶推理能力。
What Coeva Can Learn: Core Memory 严格的字符上限保护（`char_limit`）；离线 Dreaming 异步巩固思想。
What Coeva Should NOT Copy: 允许模型自主且无监管地通过工具修改用户认知档案；复杂的全量 OS 交互协议。
```

---

## 11. 最终能力横向矩阵（Capability Matrix）

| 核心能力维度 | Coeva 核心诉求 | Hindsight (v1.0) | TDAI (v3.0) | Mem0 (v1.1/Paper) | Letta (v0.1) | 行业技术对齐结论与启示 |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **Memory admission** | 严格过滤瞬时废话/测试 | LLM 抽取过滤 + Defense | 周期性批量抓取 | Facts=[] 空事实过滤 | 智能体自主选择存盘 | 必须在写入时阻断无价值切片 |
| **Working memory** | 短期多轮对话连续性 | 依赖外部 Harness | 依赖宿主会话上下文 | 仅存最近消息队列 | 维护有限事件队列 | Coeva 表现层需补齐单会话短程缓存 |
| **Consolidation** | 慢速静默提炼信念 | 异步 Consolidator 任务 | 阶梯式 50 进 1 提炼 | 写入时即时调和 | Compaction / Dreaming | 异步慢速提炼远优于同步阻塞提炼 |
| **Episodic memory** | 完整保留真实交互事件 | `memory_units` (experience) | L0 原始对话记录 | 可选 Session Scope | Recall Memory 队列 | 原始交互作为证据不可丢失 |
| **Semantic memory** | 提炼客观事实与偏好 | `memory_units` (world) | L1 原子事实 (JSONL) | 提取的 Fact Statement | Archival Passages | 事实与偏好应作为离散语义单位 |
| **Preferences** | 捕获并追踪用户习惯变化 | 融合在 Observation 中 | L1 显式标记 `preference` | 显式提取偏好语句 | 维护在 `<human>` 块中 | 偏好必须具备更新与覆写通道 |
| **Salience** | 区分重要决定与日常随口 | `proof_count` 证据支撑计数 | priority (1~5) 打分 | 访问频次与 Decay 加权 | Core 与 Archival 物理二分 | 结合证据频次与用户显式确认最稳健 |
| **Temporal validity**| 区分“过去是”与“现在是” | 解析自然语言相对时间 | 仅存起止时间戳 | 仅支持 Expiration 到期 | 仅有时序修剪 | 需借鉴 Graphiti 双时间戳模型思想 |
| **Contradiction** | 避免相反事实同时灌入 Prompt | REVISE/WEAKEN 调整信念 | 无自动化处理（新老共存） | 写入时比对 UPDATE 覆写 | 智能体自调用 replace 替换 | 写入前比对裁决是避免冲突的最佳时机 |
| **Supersession** | 废弃旧观点但保留演化轨迹 | Observation 保留演进 JSON | 人类手动编辑 Markdown | 覆写旧内容，丢失旧轨迹 | 覆写旧块内容，丢失旧轨迹 | 置失效并保留指针优于直接原地覆写 |
| **Forgetting** | 允许自然遗忘与敏感删除 | 软退役表 + 标签删除 | L0/L1 30天自动清理 | Hard Delete + 0.3x Decay | 滑动窗口淘汰 | 检索强度衰减（Decay）最符合伙伴感 |
| **Provenance** | 伴生体理解可向真实事件溯源 | source_memory_ids 数组 | 强链条（`result_ref`） | 弱（仅时间戳） | 弱（被模型重写后丢失） | 强溯源链接不可妥协 |
| **Semantic retrieval**| 意图同义改写不失忆 | 密集向量嵌入 | sqlite-vec 向量检索 | 向量余弦相似度 | 向量数据库检索 | 本地必须补齐轻量语义向量能力 |
| **Lexical retrieval** | 精确货号/技术术语不拆坏 | BM25 词频匹配 | SQLite FTS5 (jieba) | 词形还原 BM25 | 依赖外部向量或工具 | SQLite FTS5 是本地中文检索最优底座 |
| **Graph retrieval** | 沿实体与因果关系扩展 | 实体共现与因果扩展 | 仅用于短期任务状态图 | Mem0g (Neo4j) 可选 | 仅支持文件树投影 | 本地单机桌宠暂不需要复杂图数据库 |
| **Temporal retrieval**| 精准查询“昨天/前天”事实 | 时间范围物理过滤 | 仅按时间戳逆序排 | 平台版支持时序分析 | 按时间逆序分页 | 相对自然日换算为绝对区间必须具备 |
| **Hybrid ranking** | 多路召回客观打分融合 | RRF + Cross-Encoder 重排 | 经典 RRF (k=60) 融合 | 线性加权 + Entity Boost | 向量分数硬截断 | RRF 是无监督、免调参的最优融合算法 |
| **No-memory decision**| 无关/疲惫时主动不回忆 | 靠最低相关度阈值拦截 | 仅返回空数组 | 最低相似度阈值拦截 | 智能体不调用检索工具 | 外部均缺情感门控，Coeva 需自建 |
| **Context selection** | Retrieved ≠ Spoken 决策 | 仅做 Token 预算截断 | 仅做数量截断 | 仅做 Top-K 截断 | 智能体自主阅读后选择 | 外部项目均无“想起了但不说”的哲学 |
| **Prompt injection** | 防范历史偏见与注入劫持 | Feedback-Loop 守卫隔离 | 系统级前置注入 | 格式化文本拼入上下文 | Core Memory XML 格式化 | 必须加防自环守卫与弱化置信度说明 |
| **User model** | 伴生体对用户的谨慎理解 | Mental Model 活体文档 | L3 Persona 文本文件 | 围绕 user_id 的事实聚类 | `<human>` 结构块 | 必须坚持可不确定、可被用户校准 |
| **Reflection** | 从经历提炼高阶心智洞察 | reflect() 动词深度合成 | 经验场景聚合与画像蒸馏 | 依赖外部 Graph/Summary | Dreaming 离线总结 | 离线慢速反思优于交互即时反思 |
| **Multi-agent memory**| 多 Agent 工具数据共存 | Bank 隔离 + Tags 过滤 | RuntimeContext (team/user/agent) | 作用域 (user/agent/run) | 多 Agent 隔离实例 | 基于 Project/Workspace 的命名空间隔离 |
| **Deletion cascade** | 删除原始切片级联清理派生 | 未完全级联（需重训观察） | 未定义（需手动删文件） | 级联删除实体索引 | 需智能体主动重写 Core | 业界公认难题，多采用定期重构重建 |
| **Local-first** | 纯本地单机免运维 | 依赖 Postgres 服务 | 原生支持 SQLite | 原生支持 SQLite | 转向 Cloud/平台 | SQLite + 纯文本文件是唯一正确路径 |
| **Lightweight** | 低配机型桌面常驻零压力 | 极重（需完整服务端） | 极轻（仅本地 Node/SQLite）| 极轻（轻量 Python 库） | 较重（完整 Agent 运行时）| 严禁引入重型后台服务与外部容器 |

---

## 12. Coeva Adaptation Matrix（思想适配度与裁剪建议矩阵）

> 本表是本轮调研的核心产出。不评价外部项目代码质量，仅评估其**核心思想对 Coeva（平级伴生体 + 本地轻量桌宠）的适配价值**。

| 外部核心思想 (External Idea) | 来源项目 | 解决的问题 | 对 Coeva 的核心价值 | 与 Coeva 哲学的冲突点 | 建议评级 (Recommendation) |
| :--- | :---: | :--- | :--- | :--- | :---: |
| **写入前比对与四操作决策循环 (ADD/UPDATE/DELETE/NOOP)** | **Mem0 (Paper)** | 随手投喂重复切片堆积、新旧事实冲突无法调和 | 彻底根治切片平铺追加与“昨天说挺顺、今天说搞砸了”的矛盾共存 | 无冲突。可限定自动决策仅作用于事实，高层认知走校准 | **Strongly Consider** |
| **底层 SQLite + 顶层纯 Markdown 异构白盒存储** | **TDAI** | 记忆黑盒化、用户无法感知与直接修改伴生体记忆 | 人类可读、可编辑、可直接用文本编辑器修正，完全透明透明 | 需防止 Markdown 顶层画像把用户刻板固化 | **Strongly Consider** |
| **观察信念的证据计数与溯源外键 (`proof_count`, `source_ids`)** | **Hindsight** | 伴生体高层理解缺乏依据、凭空脑补 | 伴生体的任何判断都能明确指出“因哪几件事产生”，支撑度低时不轻信 | 无冲突。完美对齐 Coeva 的严谨归因门（Attribution Gate） | **Strongly Consider** |
| **RRF (Reciprocal Rank Fusion, k=60) 混合检索融合** | **TDAI / Hindsight** | 词频 BM25 与向量语义相关度量纲不同无法合并 | 经典无监督算法，零外部模型，直接本地计算，中英文均健壮 | 纯数学算法，无哲学冲突 | **Strongly Consider** |
| **Prompt 注入反馈守卫 (Feedback-Loop Guard)** | **Hindsight** | 注入给 LLM 的历史旧事在当前轮次被模型复述后，被误当作新记忆重新落盘 | 彻底杜绝“伴生体说了一句昨日旧事，系统又把这句话存为新切片”的无限回音壁污染 | 纯防御性工程设计，无冲突 | **Strongly Consider** |
| **Core Memory 字符硬约束与结构化标签分区** | **Letta** | 长期记忆注入导致 Prompt 上下文无节制膨胀 | 强行给伴生体日常记忆设定物理字符预算上限（如 300 字符），防止喧宾夺主 | 无冲突。严格服务于 12~28 字极简回复红线 | **Strongly Consider** |
| **记忆检索强度衰减 (Memory Decay)** | **Mem0** | 历史无价值碎片永远按同等权重被翻出来 | 长期未被调用的低频切片自然退火降权，呈现符合人类生理直觉的“自然淡忘” | 必须确保属于“检索降权”而非“物理丢失”，重要事实不能漏 | **Consider with Adaptation** |
| **离线静默做梦提炼 (Dreaming / Offline Consolidation)** | **Letta / Hindsight** | 实时交互时调用大模型抽取记忆导致桌宠气泡卡顿延迟 | 交互时只做轻量落盘，待用户离开桌面或闲置时慢速异步整理，桌面极度静谧 | 必须受控于本地资源占用，不能在用户玩游戏时抢占 CPU | **Consider with Adaptation** |
| **双时间戳时序置失效 (`valid_at`, `invalid_at`)** | **Graphiti** | 过去的事实被推翻后，既要避免旧事实污染当下，又要保留历史演进轨迹 | 用户偏好演变历史可查（“上个月喜欢 A，现在改喜欢 B”），不强制物理删除 | Graphiti 依赖图数据库太重；Coeva 仅需在 SQLite 字段上借鉴 | **Consider with Adaptation** |
| **多 Agent 命名空间与隔离边界 (`RuntimeContext`)** | **TDAI / Hindsight** | Hermes, Pi, Codex, Vasu 多源数据混杂串扰 | 区分项目与端点，支持跨端共享统一事实底座 | 外部项目默认全量采集对话；Coeva 必须坚守“遥测不采正文”红线 | **Consider with Adaptation** |
| **指针化符号任务地图 (Mermaid Task Canvas)** | **TDAI** | 长任务工具调用海量日志导致 Token 爆炸 | 针对长程编码代理极其有效；但 Coeva 本身是桌宠而非任务执行器 | Coeva 表现层不需要执行复杂工作流，仅在连接 Codex 时作为辅助参考 | **Study Further** |
| **智能体完全自主自编辑核心记忆 (Agent Self-Editing)** | **Letta** | 赋予智能体自主维护记忆的主动权 | 智能体具有极高灵活性 | **严重冲突**。模型极易产生幻觉偏执并自行修改用户档案，违背校准原则 | **Probably Reject** |
| **全量对话 Single-pass ADD-only 持续累积** | **Mem0 (v3 OSS)** | 简化写入流程，降低 LLM 抽取成本 | 写入速度快、架构实现简单 | **严重冲突**。放任无意义寒暄与矛盾切片无限堆叠，直接制造垃圾记忆库 | **Reject** |
| **全自动永久用户画像固化 (Permanent L3 Persona)** | **TDAI** | 让 Agent 能够直接读出“用户是什么样的人” | 适合流水线生产力工具消除重复沟通 | **严重冲突**。将人类标签化，伴生体沦为居高临下的分析者，违背平级伙伴定位 | **Reject** |
| **重型微服务容器与外部 Graph DB 集群** | **Hindsight / Graphiti** | 支持海量多租户知识图谱与千万级检索 | 工业级扩展性极强 | **严重冲突**。彻底摧毁 Coeva 的 Windows 本地轻量、零依赖单机运行体验 | **Reject** |

---

## 13. What Coeva Should NOT Copy（明确列出“不要照搬”的技术与模式）

针对 Coeva 下一代记忆架构演进，以下模式具有严重毒性，必须明确列入禁区：

1. **绝对不要照搬全量对话自动 Append-only 累积（Reject ADD-Only Stacking）**：
   - 依赖后期向量相似度去压制前期的垃圾切片，在桌面伴生体场景已被证明完全失败；
   - 随手投喂的“hi”、“测试”、“好的”必须在入库前直接被阻断拒存（`NOOP`）。
2. **绝对不要照搬商业 Agent 的用户画像发生器（Reject Rigid User Profiling）**：
   - TDAI 的 `persona.md` 与商业客服系统的 User Persona 会迅速把用户归类为“高自主、低容忍、偏好 Python”等冰冷标签；
   - 这种标签会直接诱发大模型的说教感（“根据您一贯的习惯……”），彻底摧毁真实平级伙伴体验。
3. **绝对不要照搬“检索到了就必须塞进 Prompt”的流水线（Reject Automatic Injection）**：
   - 外部生产力框架全部采用 `Retrieve → Inject` 刚性直通；
   - Coeva 必须建立中介决策层：即使检索命中了昨天的切片，如果用户当前处于情绪受挫（Sanctuary 激活）或当前只是在问路，系统必须具备**“虽然想起了，但判定此时不宜开口、不宜注入”**的自觉控制力。
4. **绝对不要照搬智能体无监督自编辑记忆（Reject Unconstrained Self-Editing）**：
   - Letta 允许模型自由通过工具改写 Core Memory；
   - 在小型本地模型或缺乏顶层监督的环境下，模型会把一次性的误解逐渐自我强化为核心记忆，最终不可逆地偏执化。高层心智修改必须引入人类显式校准。
5. **绝对不要引入重型外置基础设施（Reject Heavy Infrastructure Bloat）**：
   - 坚决不引入 Docker、PostgreSQL、Neo4j、FalkorDB、Qdrant 守护进程；
   - 坚决不引入数 GB 的本地大型深度学习框架（PyTorch / Transformers）作为记忆前置条件。

---

## 14. Open Questions & Design Lessons for Coeva（未解问题与启示）

### 14.1 业界已经解决、Coeva 无需从零发明的问题
1. **多通道混合召回融合（Hybrid Recall Fusion）**：
   - **解决方案**：SQLite 原生 FTS5（词频） + 本地向量（语义） + RRF (Reciprocal Rank Fusion, k=60)。数学原理成熟、无超参数、完全本地化，直接借鉴 TDAI 的实现模式即可。
2. **写入时矛盾消解（Write-time Conflict Resolution）**：
   - **解决方案**：借鉴 Mem0 论文中的两阶段机制：新切片入库前，先检索相似候选，由轻量 LLM 判断是新增（ADD）、修订（UPDATE）、作废（DELETE）还是丢弃（NOOP）。
3. **防止记忆回音壁（Memory Echo Poisoning）**：
   - **解决方案**：借鉴 Hindsight 的 Feedback-Loop Sentinel 围栏，在 Prompt 注入时打上唯一追踪标记，当前交互生成新切片时自动剥离历史围栏内容。

### 14.2 尚无任何外部项目很好解决、Coeva 必须自主探索的问题
1. **“想起了，但选择保持沉默”（Retrieved ≠ Injected ≠ Spoken）**：
   - 现有智能体全部以“工具人”定位设计，想方设法展现记忆；
   - 如何根据伴生体的心智门禁（避风港状态、连续工作节律、当前会话注意力深度），在检索出相关往事后，优雅地决定“沉在心底，不打扰用户”，是 Coeva 独一无二的创新命题。
2. **伴生体高层心智与用户共同校准的平衡（Co-calibrated Growth vs Rigid Persona）**：
   - 如何像朋友一样表达“我感觉你最近写代码好像比以前更有耐心了，不知道对不对？”，并根据用户的反驳（Partly/No）实时调整信念权重，而非直接在后台单方面给用户下定论。
3. **纯单机轻量环境下的零依赖语义向量化（Pure Local Embedded Vectorization）**：
   - 如何在不安装 PyTorch/Transformers 的前提下，借助 ONNX Runtime 单文件或极精简轻量模型，在 Windows 桌面端实现 50ms 以内的端侧嵌入与 SQLite 向量存储。

---

## 15. 总结与下一阶段交接（Conclusion）

本调研报告全面摸清了 Hindsight、TDAI、Mem0、Letta 与 Graphiti 的设计机制、数据形态与代码细节：

- **记忆不是扁平向量，分层与白盒化是确定性共识**（借鉴 TDAI 的 Markdown 异构与 Hindsight 的证据链）；
- **冲突必须在写入与沉淀时被治理，不能任由其无限累积**（借鉴 Mem0 的四操作决策与 Graphiti 的时序失效）；
- **伴生体是伙伴而非分析师，必须坚守静默、避风港与平级边界**（坚决剔除商业 Agent 的刻板画像与强行回溯）。

本报告产物存放于 `docs/research/long-term-memory-reference-architecture-study.md`，标志着参考架构专项调研阶段正式闭环。**后续工作可在此事实基础上，正式开启 Coeva Next-Gen Long-Term Memory (V2) 的架构设计与工程评审。**
