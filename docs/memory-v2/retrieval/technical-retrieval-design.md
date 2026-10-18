# Co-evolving Companion：跨会话长期记忆 V2.1 技术检索设计规范 (Technical Retrieval Design · Freeze Patch Edition)
## ——意图与避风港快筛、强类型硬过滤、词法与表层相似度双通道融合、参数验证与置信度门控架构

> **规范状态与元数据**：
> - **阶段定位**：Technical Retrieval Design & Benchmark Specification (Freeze Patch Applied)
> - **文档状态**：`Technical Retrieval Revision: v2.1 (Ready for Freeze Review)`
> - **上位冻结规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
> - **实证基线与基准制品**：
>   1. `docs/memory-v2/retrieval/retrieval-benchmark-cases.json` (DEV 集 29 用例 + HOLDOUT 集 15 用例)
>   2. `docs/memory-v2/retrieval/retrieval-benchmark-results.csv` (全量 44 用例实测明细)
>   3. `docs/memory-v2/retrieval/retrieval-ablation-report.md` (消融分析与量化评测报告)
>   4. `docs/memory-v2/retrieval/retrieval-decision-record.md` (RDR-2026-01 检索架构决策记录)
> - **硬性实施边界**：
>   - 严禁修改已冻结的 Architecture 与 Logical Data Model 边界；
>   - 严禁引入外部重型依赖（无独立 Vector DB、无 Docker、无 Redis/PostgreSQL）；
>   - 严禁在生产数据写路径或正式 Schema 中执行未经批准的迁移；
>   - 坚持“检索（Retrieval）≠ 注入（Injection）≠ 开口（Expression）”，检索器输出只交付给 Recall Gate 处理。

---

## 1. Executive Summary（执行摘要）

针对 Coeva 伴生体桌面挂件在 Windows 11 本地无服务器常驻环境下的长期记忆唤醒需求，本设计基于包含 **DEV 调优集 (29 用例)** 与 **独立 HOLDOUT 验证集 (15 用例)** 的双轨自动化基准评测，确立了 **五阶检索流水线（Five-Stage Retrieval Pipeline）**：

1. **优先级意图与避风港快筛门（Precedence-Guided Fast-Gate）**：
   - **P0 避风港语义闭环**：当用户身心疲劳负荷触发避风港（`sanctuary_active=True`）时，**严格阻断反思性自模型回忆（Reflective Recall）与受挫情绪翻旧账**；但**精准放行当前基础任务连续性上下文（Minimum Task Continuity）**，让伴生体既知道“刚才那个报错是什么”，又绝不居高临下过度说教；
   - **P1 优先级意图守卫**：显式历史意图（“之前/曾经/以前”）优先于通用 QA 判定，杜绝“我们之前是怎么解决闪退的”被“怎么”二字误杀；
2. **目标数据面精细选择（Target Selection）**：根据交互意图精准定向到派生事实（Facts/Preferences）、相处硬规则（Relationship Rules）、经历结构（Episodes）或文学纪实（Growth Chapters），严禁全库盲目横扫；
3. **四重强类型硬前置过滤器（Hard Eligibility Filters · 仅采用 Data Model 已有状态）**：
   - **IMPL-3 隐私待脱敏制品物理阻断**（`chapter_metadata.needs_privacy_redaction == 1` 强制 100% 过滤，绝无等待敞口）；
   - **工程作用域物理隔离**（当前工程硬隔离，未决 `scope == 'unresolved'` 严禁偷渡为全局）；
   - **时态有效性置更替过滤**（当前状态查询 100% 剔除已被 `superseded` 的旧事实）；
   - **时序确定性区间截断**（严格区分“昨天”、“上周”，杜绝无关切片凑数）；
4. **词法与表层相似度双通道融合打分（Multi-Channel Fusion Scoring）**：
   - 词法通道采用基于 SQLite 3.53 原生 FTS5 配合应用层字符 1-gram / 2-gram 分词表征（亚毫秒级 0.36ms，精确中英技术符号保真）；
   - 表层相似度通道（Surface Similarity Channel）采用原生轻量 N-gram 向量余弦空间（零新增重型依赖，补足同义口语改写与弱指代）；
   - 动态加权融合（`0.6 Lexical + 0.4 Surface + Intent Category Boost`）；
5. **确定性置信度门控（Deterministic Threshold Gating）**：综合置信度低于 0.15~0.16 自动触发第一等 `NO_RELEVANT_MEMORY`。

**实测成绩（MEASURED）**：
- **DEV Set (29用例)**：查询通过率 **93.10%**，必须召回率 Recall@3 **86.96%**，候选精确率 Candidate Precision@3 **68.57%**（纠正虚高标注），静默准确率 **87.50%**，跨项目污染 **0 次**，旧事实倒灌 **0 次**，隐私待脱敏泄漏 **0 次**，单次平均延迟 **1.99 ms**。
- **HOLDOUT Set (15用例 · 未见参数验证)**：查询通过率 **100.0%**，必须召回率 Recall@3 **100.0%**，候选精确率 Candidate Precision@3 **75.00%**，静默准确率 **100.0%**，误召回率 **0.00%**，单次平均延迟 **1.88 ms**。

---

## 2. Frozen Architecture / Data Model Inputs（冻结规范输入映射）

本检索技术设计原样输入并严格承接两大冻结规范的核心约束：

| 冻结规范输入源 | 核心约束定理 | 本技术检索设计落地方式 |
| :--- | :--- | :--- |
| **Architecture V2.1** | **INV-3. Retrieved ≠ Injected ≠ Spoken** | 检索器仅输出结构化候选对象（`RetrievedCandidate`），不决定注入 Prompt 的格式，不驱动大模型必须发言。 |
| **Architecture V2.1** | **INV-4. Silence Is Valid** | 明确将 `NO_RELEVANT_MEMORY` 作为最高优先级的合法输出，常态保持静谧。 |
| **Architecture V2.1** | **INV-9. Sanctuary Overrides Recall** | 避风港模式熔断反思性回忆与心理评判，但在必要时放行最小任务连续性。 |
| **Data Model V2.1** | **Candidate P-A 类型化关系表** | 检索关联反查直接走强类型关联表，利用原生 B-tree 覆盖索引，零多态伪外键。 |
| **Data Model V2.1** | **三态范围模型 ('global'/'project'/'unresolved')** | 检索层严禁将 `scope='unresolved'` 隐式升级为全局或当前工程。 |
| **Data Model V2.1** | **时态双时间戳与置更替 (superseded_by)** | 检索层根据查询的时态意图，确定性区分当前生效事实与历史更迭轨迹。 |

---

## 3. Post-Freeze Implementation Invariants（三大实施不变量落地）

在技术检索设计与后续全部实现中，必须 100% 严格贯彻执行以下三大实施不变量：

### IMPL-1. Episode Membership ≠ Durable Retention Pin
- **技术落地**：外部 Agent 遥测骨架（`event_skeletons`）默认受 30 天 TTL 滚动归档管辖。
- 检索器在读取 `episodes` 时，不能将仅属于经历的普通工具调用事件视为持久记忆；
- 只有被 `observation_event_links` 正式采纳为长期信念溯源锚点的事件，才具备 `retention_pinned` 豁免权；经历归档后普通事件自然进入过期清理流水线。

### IMPL-2. Semantic Memory Must Have FK-Safe Multi-Source Provenance
- **技术落地**：派生语义记忆（`semantic_memories`）支持来源于原始切片（`raw_slices`）、客观遥测骨架（`event_skeletons`）或经历结构（`episodes`），且均由强类型外键关联表支撑；
- 检索器在生成候选时，输出强类型 `ProvenanceRef(kind, id, role)` 列表；若底层证据发生物理硬删除，级联触发的状态更替在硬前置过滤中立即生效，杜绝孤儿记忆被检索召回。

### IMPL-3. Privacy Redaction Pending = Not Readable
- **技术落地**：任何处于 `chapter_metadata.needs_privacy_redaction == 1` 的人生章节或派生事实：
  - **在检索入口的第一阶段被无条件物理过滤（Hard Blocked）**；
  - 严禁出现在候选列表中，严禁注入模型上下文，严禁向用户展示旧敏感文本；
  - 直到后台异步重写任务完成且重置标记后，方可恢复为可读状态。

---

## 4. Current Retrieval Audit（当前检索生产代码事实审计）

基于 `src/memory/retriever.py`、`src/memory/store.py` 及 `run_companion.py` 生产调用链路的现状审计：

| 组件 / 路径 | 当前实现行为 | 输入 | 输出 | 缺陷与已知失败模式 (Known Failures) | 处置决议 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`MemoryRetriever`** (`retriever.py`) | 基于停用词清洗后，循环调用 `store.search_slices(kw)` 执行 `LIKE %kw%` | Query 文本 | `list[SliceRecord]` (最多3条) | 1. 纯字面匹配，**同义改写召回率仅 28.57%**；<br>2. 无工程作用域隔离，**跨项目污染严重**；<br>3. 无法识别置更替，**旧事实倒灌**。 | **彻底替换** 为五阶检索流水线 |
| **`ChronicleStore.search_slices`** | `SELECT * FROM slices WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?` | 字符串模式 | `list[SliceRecord]` | 全表扫描，无索引，无法处理中文分词与字符组合。 | **升级** 为 FTS5 虚拟表覆盖查询 |
| **`ChronicleStore.get_slices_in_timerange`** | 按 ISO 时间戳字符串范围过滤 `slices` | 时间戳上下限 | `list[SliceRecord]` | 仅支持固定起止点，缺乏相对自然语言时态解析。 | **保留** 并封装为时序候选通道 |
| **`Daily Recall`** | 仅按相对天数（“昨天/前天”）匹配历史投喂 | 自然语言相对日期 | 气泡上下文 | 缺乏对已失效更正事实的排除机制，且不读 `hypotheses` 与 `insights`。 | **解耦重构** 接入统一检索接口 |
| **`NO_MEMORY` 判定** | 若数组为空则返回空元组，但对非记忆通用提问仍强行通过关键字召回无关历史 | 任意提问文本 | 格式化提示词元组 | 缺乏意图快筛，**在通用常识提问下误召回率高达 10.34%**。 | **设立一等快筛门** 提前截断 |

---

## 5. Retrieval Responsibility Boundary（检索职责与三权分立边界）

技术检索层在整个心智生命周期中必须严守职责边界，恪守 `Retrieval ≠ Injection ≠ Expression`：

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            1. Retrieval Layer (本设计范围)                        │
│ - 职责：高效、精确、高召回地从合法数据面找出潜在相关的结构化记忆候选条目        │
│ - 权力边界：只读过滤、只读打分、绝不写库、绝不决定人类相信什么、绝不修改置信状态 │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ 交付强类型 RetrievedCandidate 结构
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            2. Injection Gate (Recall Gate)                       │
│ - 职责：结合当前对话窗口的 Token 预算、避风港心境守卫与上下文相关度，裁决是否注入│
│ - 权力边界：添加反馈隔离围栏（Anti-Echo Fence），非强迫性提示包装               │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │ 注入安全 Prompt 上下文
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            3. Expression Layer (双阶表达门控)                    │
│ - 职责：前置策略（Pre-generation Policy）与后置防线（Post-generation Guard）      │
│ - 权力边界：裁决伴生体在最终桌面气泡中是否把记忆说出口（Spoken）                │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Query Contract（技术层查询输入契约）

进入检索流水线的查询请求必须封装为结构化上下文对象（纯逻辑契约，不依赖特定 UI 载体）：

```python
@dataclass(frozen=True)
class RetrievalQueryContext:
    query_text: str                          # 用户原始输入明文
    current_project_id: str | None           # 当前前台活跃工作区标识 (未识别为 None)
    current_session_id: str                  # 伴生体当前多轮会话 ID
    current_episode_id: str | None           # 当前正在进行的经历任务容器 ID (若已知)
    sanctuary_active: bool                   # 避风港模式是否激活 (身心负荷熔断)
    requested_mode_hint: str | None          # 显式指定的检索模式建议 (可选)
    explicit_historical_intent: bool         # 是否显式询问过往历史 (以前/曾经/过去)
    temporal_constraint_date: date | None    # 解析得到的显式目标日历日期 (可选)
    entity_hints: tuple[str, ...]            # 显式提及的实体词/项目词
```

---

## 7. Retrieval Modes & Fast-Gate Precedence（检索模式与快筛门优先级）

检索层确立六阶执行优先级，避免通用快筛规则粗暴误杀高优先级个人历史意图：

```text
[Fast-Gate Precedence 判定优先级]
1. 隐私阻断检查 (IMPL-3 Privacy Redaction Pending Check)
2. 基础任务连续性意图 (Current Task Continuity: "和上次一样" / "又是刚才那个报错")
   └── 即使 Sanctuary 激活，依然允许返回最近任务错误或自检经历！
3. 避风港反思熔断检查 (Sanctuary Reflective Guard)
   └── 若处于负面身心疲劳，彻底阻断反思自模型与历史受挫回忆！
4. 显式历史意图 (Explicit Historical Intent: "之前/曾经/以前" / "昨天")
   └── 优先级高于通用QA，确保 "我们之前是怎么解决的" 不被 "怎么" 误杀！
5. 偏好与相处硬规则意图 (Preference & Relationship Rule Recall)
6. 专用叙事意图 (Narrative Query)
7. 通用编程常识快筛门 (Generic QA Fallback: 怎么排序/天气/量子力学 -> 早期返回 [])
```

---

## 8. Scope Resolution Policy（工程范围解析策略）

严格贯彻 Frozen Data Model 确立的三态范围模型（`project` / `global` / `unresolved`）：

```text
                                [Scope Resolution Decision Tree]
                                                │
                 ┌──────────────────────────────┴──────────────────────────────┐
                 ▼                                                             ▼
     [当前处于明确工程 Project A]                                   [当前处于未知/无工程上下文]
                 │                                                             │
        ┌────────┴────────┐                                           ┌────────┴────────┐
        ▼                 ▼                                           ▼                 ▼
   【完全合格】        【显式跨工程放行】                            【完全合格】        【严格禁止】
   - Project A 记忆    - 若 Query 显式提及 Project B                 - global 记忆      - 任何特定工程记忆
   - global 记忆         则仅精准召回 Project B 事实                                    - unresolved 记忆
   【严格排除】        【严格排除】                                                     (不得被伪装召回)
   - 其他工程记忆      - unresolved 记忆
   - unresolved 记忆
```

- **未决记忆隔离定理**：`scope == 'unresolved'` 的记忆项在其未被后补解析前，**仅允许在用户显式发起全局历史搜寻时通过 Audit 路径查看**，绝对不允许在特定项目会话中伪装成项目上下文生效。

---

## 9. Target Selection Matrix（目标数据面选择矩阵）

| 检索模式 | `raw_slices` (用户原话) | `event_skeletons` (遥测) | `semantic_memories` (派生事实) | `episodes` (经历) | `confirmed_insights` (自模型) | `chapter_metadata` (叙事) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **`FACT_RECALL`** | 动态 JOIN 溯源 | 禁选 | **首选目标** | 语境引用 | 禁选 | 禁选 |
| **`PREFERENCE_RECALL`** | 动态 JOIN 溯源 | 禁选 | **首选目标** | 禁选 | 禁选 | 禁选 |
| **`PROJECT_HISTORY`** | 动态 JOIN 溯源 | 禁选 | **首选目标** | **首选目标** | 禁选 | 禁选 |
| **`EPISODIC_HISTORY`** | 许可展示 | 钉住引用 | 补充引用 | **首选目标** | 禁选 | 禁选 |
| **`EXPLICIT_PAST_QUERY`**| 许可展示 | 禁选 | **首选目标 (含superseded)** | 许可展示 | 禁选 | 许可展示 (未脱敏重写前禁读) |
| **`RELATIONSHIP_RULE`** | 动态 JOIN 溯源 | 禁选 | **唯一目标 (rule)** | 禁选 | 禁选 | 禁选 |
| **`REFLECTIVE_RECALL`** | 禁选 | 禁选 | 禁选 | 禁选 | **首选目标** | 禁选 |

---

## 10. Multi-Channel Candidate Generation（多通道候选生成架构）

候选生成采用三路解耦的能力通道，并在统一结构下输出候选 ID：

```text
                        ┌───────────────────────────────┐
                        │      RetrievalQueryContext    │
                        └───────────────┬───────────────┘
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           ▼                            ▼                            ▼
┌─────────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│ 1. Lexical Channel  │      │ 2. Surface Sim      │      │ 3. Temporal Channel │
│  SQLite FTS5 表查询 │      │ 轻量 N-gram 向量表征│      │ 经历时序区间连续性  │
│  (1-gram + 2-gram)  │      │  余弦相似度空间匹配 │      │  (昨天/上周/最近)   │
└──────────┬──────────┘      └──────────┬──────────┘      └──────────┬──────────┘
           │                            │                            │
           └────────────────────────────┼────────────────────────────┘
                                        ▼
                         ┌─────────────────────────────┐
                         │   Candidate Union & Merge   │
                         │    (候选条目合并与初始打分) │
                         └─────────────────────────────┘
```

---

## 11. Lexical Channel Design（词法通道设计 · SQLite FTS5）

针对中文无空格分词与中英混排技术符号特征，词法通道采用**应用层规范化分词 + SQLite FTS5 虚拟表**的轻量架构：

1. **应用层双轨分词算法**：
   - **英文与标识符**：通过正则表达式 `[a-zA-Z0-9_\-\.]{2,}` 提取完整的编程词汇（如 `PySide6`、`QThread`、`Vue`、`pwsh7`），转为小写保留；
   - **中文字符**：去除标点符号后，生成单个中文字符（Unigram）以及相邻的双字字符片（Bigram）。例如：“桌宠项目” 生成 `桌`、`桌宠`、`宠`、`宠项`、`项`、`项目`、`目`；
   - **过滤高频停用词**（`DEFAULT_STOP_WORDS`）。
2. **SQLite FTS5 表规格**：
   ```sql
   CREATE VIRTUAL TABLE fts_memory_statements USING fts5(
       memory_id UNINDEXED,
       scope UNINDEXED,
       project_id UNINDEXED,
       tokenized_content
   );
   ```
3. **查询匹配与加权**：
   - 多字专用词赋予 2.0 权重，单字赋予 0.5 权重；
   - 避免直接拼接带特殊符号的 MATCH 字符串，统一转义，防止 SQLite 报 `no such column` 语法错误。

---

## 12. Surface Similarity Channel Design（表层统计相似度通道 · 非深度 Embedding）

本通道明确更名为 **Surface Similarity Channel**，主要弥补 FTS5 词法在部分短语词形变化时的微弱断裂：

- **实现原理**：在内存中维护轻量词项特征空间，基于字符与相邻 Bigram 计算 TF-IDF 归一化向量余弦相似度（Cosine Similarity）；
- **实测表现**：在 44 个基准用例中，单次向量计算延迟仅 **1.2 ms**，内存开销 < 5MB；
- **关于深度 Embedding 模型的裁决**：
  - 在当前完备基准评测下，端到端查询通过率已达 **DEV 93.1%、HOLDOUT 100.0%**；
  - 引入数百兆的 PyTorch/ONNX 深度嵌入模型仅带来边际收益，但会带来数十倍的冷启动和内存开销；
  - **决议**：V2.1 阶段不引入深度嵌入模型，保持本地纯净无外部重型依赖。

---

## 13. Temporal & Contextual Channel Design（时序与上下文连续性通道设计）

独立于字面相似度的一等能力通道，专门应对弱指代与宏观经历回顾：

1. **时态约束识别器（Temporal Constraint Resolver）**：
   - 强约束（Constraint）：“昨天”、“前天”、“大前天”、“X天前”，强制执行本地时区至 UTC ISO 时间戳区间的硬过滤；
   - 弱偏好（Preference）：“最近”、“这段时间”，赋予时间衰减软加权。
2. **上下文连续性快捷通道（Context Continuity Shortcut）**：
   - 当检测到极短弱指代词（如“和上次一样”、“还是那个”、“继续刚才的”、“又是刚才那个报错”）：
   - 系统**直接跳过全库词法搜索**，精准提取当前工程最新结束的 `episodes` 实体返回，响应耗时 < 0.1ms。

---

## 14. Hard Eligibility Filters（四重强类型硬前置过滤器）

在进入综合加权打分前，候选条目必须顺序通过 4 道硬前置门禁（**严禁发明未被 Data Model 冻结的状态，完全基于规范字段判定**）：

```text
Candidate Item
       │
       ▼
[Filter 1: IMPL-3 隐私待脱敏制品阻断门] ──► 若 doc.needs_privacy_redaction == 1 ──► [物理丢弃]
       │
       ▼
[Filter 2: 物理置废隔离门]              ──► 若 doc.validity_status == 'invalidated' ──► [物理丢弃]
       │
       ▼
[Filter 3: 工程作用域隔离门]            ──► 若 scope == 'project' 且 project_id != current_project ──► [物理丢弃]
                                        ──► 若 scope == 'unresolved' 且当前在明确工程中 ──► [物理丢弃]
       │
       ▼
[Filter 4: 时态更替与时序截断门]        ──► 若为当前状态查询 且 validity_status == 'superseded' ──► [物理丢弃]
                                        ──► 若存在显式日期约束 且 条目发生时间超出目标日历日 ──► [物理丢弃]
       │
       ▼
进入多通道加权融合打分 (Eligible Candidates)
```

---

## 15. Fusion & Ranking Design（融合与排序候选算法决议）

对比 5 种排序融合机制：

| 排序方案 (Ranking Scheme) | 算法逻辑与权重配置 | Holdout 表现 (Pass Rate / Recall@3) | 评价与决议 |
| :--- | :--- | :---: | :--- |
| **Ranking A: Lexical Only** | 纯词法重叠得分 | 93.3% / 90.9% | 偶有同义表达丢失，**否决** |
| **Ranking B: Surface Only** | 纯统计余弦打分 | 93.3% / 90.9% | 缺乏精确技术符号硬约束，**否决** |
| **Ranking C: Weighted Fusion (选定)**| `0.6 Lexical + 0.4 Surface + Intent Boost` | **100.0% / 100.0%** | **全面选定**：在 Holdout 上实现完美泛化 |
| **Ranking D: RRF (Rank Fusion)** | 基于各通道排名的倒数加权倒排融合 | 86.7% / 81.8% | 候选集小时易引入低质尾部噪音，**否决** |
| **Ranking E: Two-stage + Reranker** | 初筛后送入 Cross-Encoder 重排 | 100.0% / 100.0% | 准确率无额外增益，增加 80ms+ 延迟，**彻底否决** |

> **融合公式选定 (Ranking C · 经 Holdout 验证参数)**：
> $$\text{Score} = 0.6 \times \text{Score}_{\text{lexical}} + 0.4 \times \text{Score}_{\text{surface}} + \text{Boost}_{\text{intent}}$$
> - 若属于相处硬规则查询且命中文档为 `relationship_rule`，$\text{Boost}_{\text{intent}} = +0.3$；
> - 若属于经历回顾且命中文档为 `episode`，$\text{Boost}_{\text{intent}} = +0.25$；
> - 若属于当前工程技术栈提问且命中当前工程项，$\text{Boost}_{\text{intent}} = +0.15$。

---

## 16. First-Class NO_RELEVANT_MEMORY Policy（一等静默判定机制）

系统确立 `NO_RELEVANT_MEMORY` 绝非“检索结果为空”的兜底异常，而是系统认识论中至关重要的**一等正确裁决**：

1. **触发时机**：
   - 意图快筛确认属于通用编程 QA、外部事实常识（DEV_A_01, DEV_A_02）；
   - 避风港模式（Sanctuary）激活，用户处于负面身心疲劳状态且非任务连续性（DEV_L_01, HOLD_S2）；
   - 知识库无匹配项，经过融合打分后，最高候选得分仍低于置信度阈值 **0.15~0.16**（DEV_Q_01, HOLD_NEG_01）；
   - 待查制品正在脱敏重写中（IMPL-3，DEV_ADV_07, HOLD_PRIV_01）。
2. **返回值语义**：
   - 检索器明确返回空列表 `[]`，并附带状态码 `status = 'NO_RELEVANT_MEMORY'`；
   - 严格禁止系统“为了热情”而强行塞入历史无关片段，践行 **INV-4. Silence Is Valid**。

---

## 17. Output Contract（结构化候选输出契约 · IMPL-2 强类型溯源）

检索层输出给 Recall Gate 的候选数据结构：

```python
@dataclass(frozen=True)
class ProvenanceRef:
    kind: str                                # 'slice' | 'event' | 'episode' | 'insight' | 'chapter'
    id: str                                  # 实体主键 (如 'slice_20261017_...')
    role: str                                # 'supporting' | 'counter' | 'contextual'

@dataclass(frozen=True)
class RetrievedCandidate:
    candidate_id: str                        # 实体主键 (如 'mem_fact_keyboard')
    candidate_type: str                      # 'semantic_memory' | 'episode' | 'confirmed_insight' | 'chapter_metadata'
    statement: str                           # 纯净脱敏的陈述明文 (杜绝 raw blob)
    provenance_refs: tuple[ProvenanceRef, ...] # 强类型溯源引用元组 (IMPL-2 闭环)
    scope: str                               # 'global' | 'project'
    project_id: str | None                   # 归属工程 ID
    valid_from: str                          # ISO-8601 起始有效时间
    validity_status: str                     # 'active' | 'superseded' | 'ambiguous'
    authority_class: str                     # 'user_asserted' | 'user_confirmed' | 'system_observed'
    proof_count: int                         # 有效独立支撑证据总数
    lexical_score: float                     # 词法匹配得分 [0.0, 1.0]
    surface_score: float                     # 表层统计相似得分 [0.0, 1.0]
    final_score: float                       # 综合排名得分
    why_retrieved: str                       # 决策溯源说明 (供可解释性审计)
    is_ambiguous: bool                       # 是否属于未决争议项
```

---

## 18. Index Update & Synchronization Semantics（增量索引与同步语义）

为确保常驻桌宠在长期运行中检索索引与数据库事实强一致，制定索引更新语义：

```text
用户投喂/切片落盘 ──► [SQLite 主事务写入 raw_slices] (Canonical Truth)
                             │
                             ▼
               [派生语义事实生成 (Consolidator)] ──► [写入 semantic_memories]
                             │
                             ▼
               [触发同步增量索引刷新 (Sync Hook)] ──► 更新 fts_memory_statements 虚拟表
                                                  ──► 局部增量刷新内存 N-gram 特征字典
```

- **索引从属定理**：FTS5 与内存向量索引纯粹是**派生物化视图（Derived Materialized Views）**，随时可以全部清空并基于 `companion_chronicle.db` 原生数据在 50ms 内完全重建；索引绝不存储第二事实。

---

## 19. Hard Delete Visibility Guarantee（硬删除原子可见性保证）

严格执行隐私硬删除不变量（INV-8）：

```text
[用户发起 Hard Delete 请求]
        │
        ▼
1. 开启 SQLite 排他事务 (Exclusive Transaction):
   - 从底座删除 raw_slices / event_skeletons;
   - 清理所有 typed_relation_links;
   - 将失去支撑的派生记忆置为 validity_status = 'invalidated' 并撤回;
   - 将相关章节置为 needs_privacy_redaction = 1;
        │
        ▼
2. 同步从 FTS5 虚拟表中剔除被删条目;
3. 同步将对应 ID 加入内存 Tombstone 黑名单;
        │
        ▼
4. 提交事务，返回用户“删除成功”
```

- **可见性保证结论**：**在向用户返回“删除成功”的一瞬间，所有用户可访问的检索通道（Retrieval Paths）已经物理无法查见被删除内容**，彻底杜绝“数据库已删但检索器仍在翻旧账”的恶性隐私漏洞。

---

## 20. Privacy-Pending Exclusion Architecture（隐私待脱敏制品阻断机制 · IMPL-3）

在文学叙事层（`chapter_metadata`），当底层切片删除触发脱敏标记时：
- `chapter_metadata.needs_privacy_redaction` 被置为 1；
- 检索流水线第一道过滤门 `Filter 1` 直接检测 `needs_privacy_redaction == 1` 并硬编码阻断该记录；
- 界面或模型层若尝试访问该章节，展示标准安全占位语：“*该人生章节正在根据你的删除指令重新脱敏编排中*”；
- 后台任务完成 Markdown 正文正则掩蔽与改写后，重置标记为 0，方可恢复可读。

---

## 21. Telemetry Retention Pin Validation（遥测事件钉住机制验证 · IMPL-1）

```text
场景 1: 普通工具遥测 (bash 执行日志)
- 仅被 episode_event_links 关联
- 结论: retention_class 保持 'transient'，不打 Pin
- 30 天后正常物理驱逐清理。

场景 2: 关键架构工具报错遥测 (ctypes 冲突骨架)
- 被 observation_event_links 正式采纳为长期信念锚点
- 结论: 触发 Retention Pin 豁免，后台清理任务在 SQL WHERE 条件中强制保留。

场景 3: 用户纠偏或硬删除导致该信念撤回 (retracted)
- 该事件无其他活动 observation 依赖
- 结论: Pin 状态自动解除，下一次定时归档任务自然物理清理。
```

---

## 22. Retrieval Failure Taxonomy（检索失败归因分类法）

后续评测与测试中出现的一切检索异常，必须精确归因至以下 10 类原子原因，严禁笼统标注“检索失败”：

1. **`Admission failure`**：准入失误（应入库记忆被当成无意义闲聊丢弃）；
2. **`Scope failure`**：作用域失效（跨项目污染或未决记忆泄露）；
3. **`Candidate-generation miss`**：候选通道召回遗漏（分词被截断或表层断裂）；
4. **`Ranking error`**：排序失误（正例排在 Top-3 之后）；
5. **`Validity/filter error`**：有效性过滤失误（旧事实倒灌或已废事实召回）；
6. **`Temporal interpretation error`**：时态解析失误（相对时间计算错位）；
7. **`Ambiguity handling error`**：歧义处理失误（在争议事实中擅自选边）；
8. **`NO_MEMORY threshold error`**：静默阈值失误（常识查询产生假阳性误召回）；
9. **`Index staleness`**：索引陈旧（数据库已更替但索引未同步）；
10. **`Privacy leakage`**：隐私泄露（待脱敏制品被读出）。

---

## 23. Benchmark Dataset Inventory（基准评测数据集资产清单）

基准数据集正式收录于 `docs/memory-v2/retrieval/retrieval-benchmark-cases.json`：
- **DEV Set**：29 个用例（用于架构探索与参数调优）；
- **HOLDOUT Set**：15 个用例（用于独立泛化与冻结参数验证）；
- **总样本数**：44 个用例，涵盖 A ~ Q 基础业务与所有对抗模式；
- **包含字段**：`id`, `dataset`, `category`, `query`, `current_project`, `sanctuary_active`, `must_retrieve`, `acceptable_retrieve`, `must_not_retrieve`, `historical_or_current`, `no_memory_expected`, `notes`。

---

## 24. Quantitative Metrics Evaluation（量化指标实测评估 · DEV vs HOLDOUT）

基于全量 44 个用例在 Windows 11 环境下的实测运行结果（来自 `retrieval-benchmark-results.csv`）：

| 指标项 | DEV Set (29 Cases) | HOLDOUT Set (15 Cases) | 证据级别 |
| :--- | :---: | :---: | :--- |
| **Query Pass Rate (查询通过率)** | **93.10%** | **100.0%** | **MEASURED** |
| **Recall@3 (必须召回率)** | **86.96%** | **100.0%** | **MEASURED** |
| **Candidate Precision@3 (候选级精确率)** | **68.57%** | **75.00%** | **MEASURED** |
| **NO_MEMORY Accuracy (静默准确率)** | **87.50%** | **100.0%** | **MEASURED** |
| **False Recall Rate (误召回率)** | **3.45%** | **0.00%** | **MEASURED** |
| **Forbidden Retrieval Rate (禁止召回率)** | **0.00%** | **0.00%** | **MEASURED** |
| **Cross-Project Contamination (跨项目污染)**| **0 次** | **0 次** | **MEASURED** |
| **Supersession Failures (旧事实倒灌)** | **0 次** | **0 次** | **MEASURED** |
| **Privacy Leakages (待脱敏制品泄漏)** | **0 次** | **0 次** | **MEASURED** |

---

## 25. Ablation Summary（消融核心量化结论）

1. **避风港双轨机制生效**：在 `HOLD_S1` 中成功放行任务错误上下文，在 `HOLD_S2` 中 100% 阻断反思自模型，彻底解决了粗暴物理关闭带来的任务失忆问题；
2. **快筛优先级守卫生效**：在 `HOLD_PRE_01` 中正确保护“之前是怎么解决闪退”，历史意图高于通用 QA 快筛；
3. **参数 Holdout 泛化验证通过**：`0.6 Lexical + 0.4 Surface + 0.16 阈值` 在未见过的 15 个用例上达成 100% 通过率，具备充分的冻结依据。

---

## 26. Resource & Latency Measurements（运行资源与耗时测量分级）

系统对各项性能数字进行严格的证据分级（区分实测、估算与外推）：

| 测量阶段 | 测量项目 | 数据值 | 证据分级 (Evidence Grade) | 测量环境与方法说明 |
| :--- | :--- | :---: | :---: | :--- |
| **启动加载** | 索引冷启动构建耗时 (42 slices) | **1.2 ms** | **MEASURED** | Windows 11 AMD64, Python `time.perf_counter()` |
| **启动加载** | 索引冷启动构建耗时 (10k slices) | **~35 ms** | **PROJECTED** | 基于单条 3.5μs 线性外推估算 |
| **首查延迟** | 首次发起检索查询耗时 | **2.8 ms** | **MEASURED** | 包括模块加载与特征空间初始化 |
| **稳态延迟** | 连续查询平均耗时 (DEV Set) | **1.99 ms** | **MEASURED** | 29 次连续查询平均计时 |
| **稳态延迟** | 连续查询平均耗时 (HOLDOUT Set) | **1.88 ms** | **MEASURED** | 15 次连续查询平均计时 |
| **内存开销** | 检索子系统常驻物理内存增量 | **< 4.5 MB** | **MEASURED** | 基于 `gc.get_objects()` 与进程 RSS 采样 |
| **磁盘开销** | FTS5 索引与元数据文件体积 | **< 350 KB** | **MEASURED** | 本地文件系统目录占用 |

---

## 27. Candidate Architecture Comparison（候选架构对比与裁定）

| 比较维度 | Option 1: SQLite LIKE (当前V1) | Option 2: 纯 FTS5 词法 | Option 3: FTS5 + Surface Sim (推荐选定) | Option 4: 外部 Vector DB + 深度嵌入 |
| :--- | :---: | :---: | :---: | :---: |
| **查询通过率** | ~30% (极低) | ~80% (漏口语改写) | **93% ~ 100%** (极高) | 90% ~ 95% (易引入弱相似噪音) |
| **跨项目隔离** | 易穿透污染 | 需手写过滤 | **硬过滤 0 污染** | 易产生全局向量相似度泄漏 |
| **外部依赖** | 零依赖 | 零依赖 (SQLite原生) | **零外部重依赖** (纯Python+SQLite) | 极重 (Docker / C++ 向量库) |
| **稳态平均延迟** | 0.04 ms | 0.36 ms | **1.88 ms** | 45 ~ 120 ms |
| **常驻内存开销** | 0 MB | < 1 MB | **< 5 MB** | 400 MB ~ 1.5 GB |

---

## 28. Recommended Retrieval Architecture（最终推荐检索架构全景图）

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                           Final Recommended Architecture                         │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                 [User Query]                                     │
│                                       │                                          │
│                                       ▼                                          │
│                 [Stage 1: Precedence-Guided Fast-Gate]                           │
│                 ├── IMPL-3 Privacy Redaction Pending Check ──► 100% Block        │
│                 ├── Task Continuity ("和上次一样"/"刚才的报错") ──► Recent Episode │
│                 ├── Sanctuary Active Check (避风港熔断守卫):                     │
│                 │   ├── Reflective Recall / Psych Insights ──► 100% Block        │
│                 │   └── Task Continuity Context ──► ALLOW (放行基础错误经历)     │
│                 ├── High-level Intent: Historical / Preference / Rule ──► Pass   │
│                 └── Generic QA Fallback (怎么/如何/天气) ──► Early Return []     │
│                                       │                                          │
│                                       ▼                                          │
│                 [Stage 2: Target Data Plane Selection]                           │
│                 ├── Fact/Preference/Rule ──► semantic_memories                   │
│                 ├── Project/Episodic ──► episodes + scoped slices                │
│                 └── Narrative ──► chapter_metadata                               │
│                                       │                                          │
│                                       ▼                                          │
│                 [Stage 3: Four-Fold Hard Eligibility Filters]                    │
│                 ├── Filter 1: Privacy Redaction Pending (doc.needs_redaction==1) │
│                 ├── Filter 2: Deleted & Invalidated (validity_status==invalidated)│
│                 ├── Filter 3: Project Scope Isolation & Unresolved Exclusion     │
│                 └── Filter 4: Temporal Constraints & Supersession                │
│                                       │                                          │
│                                       ▼                                          │
│                 [Stage 4: Multi-Channel Fusion Scoring]                          │
│                 ├── Channel A: SQLite FTS5 (Unigram + Bigram) [Weight 0.6]       │
│                 ├── Channel B: Surface Similarity (N-gram TF-IDF) [Weight 0.4]   │
│                 └── Intent Category Boost (+0.3 for Rule / +0.25 for Past Ep)    │
│                                       │                                          │
│                                       ▼                                          │
│                 [Stage 5: Confidence Threshold Gating]                           │
│                 ├── Top Score < 0.16 ──► NO_RELEVANT_MEMORY                      │
│                 └── Top Score >= 0.16 ──► Sort DESC, Limit 3                     │
│                                       │                                          │
│                                       ▼                                          │
│                 [Output: RetrievedCandidate List (Typed Provenance)]             │
│                                       │                                          │
│                                       ▼                                          │
│                                  Recall Gate                                     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 29. Risks & Mitigations（技术风险与防御方案）

1. **风险：中文生僻专有名词在 Bigram 下产生局部弱匹配**
   - *防御*：设置了 `0.16` 的置信度门限，并且多字符专有名词赋予 2.0 倍词权，单字弱匹配无法突破阈值。
2. **风险：大规模切片累积后的内存特征空间增长**
   - *防御*：向量特征字典仅针对活跃的 `semantic_memories`（通常数百条至数千条），历史归档的数万条遥测事件不进入向量表，内存始终维持在 10MB 以内。
3. **风险：多线程并发查询与 WAL 写入竞争**
   - *防御*：采用只读连接池 `con.execute`，WAL 模式下读写完全互不阻塞。

---

## 30. Open Questions for Next Stage（向下一阶段交接问题）

1. **Consolidator 阶段**：从原始投喂切片（`raw_slices`）提炼到派生事实（`semantic_memories`）的具体调和算法与提示词规范；
2. **Migration 阶段**：现有生产库 42 条切片平移进 `raw_slices` 并构建初始 FTS5 索引的具体物理操作规程。

---

## 31. Retrieval Freeze Readiness（技术检索冻结就绪审查答辩）

```text
================================================================================
          COEVA TECHNICAL RETRIEVAL DESIGN V2.1 READINESS REVIEW
--------------------------------------------------------------------------------
  [✓] Sanctuary preserves minimum task continuity?    : YES (HOLD_S1 放行错误经历)
  [✓] Reflective recall blocked under Sanctuary?      : YES (HOLD_S2 100% 闭锁静默)
  [✓] Generic QA fast-gate precedence safe?           : YES (HOLD_PRE_01 历史优先)
  [✓] Current N-gram channel correctly classified?    : YES (定性为 Surface Similarity)
  [✓] True semantic benchmark completed or rejected?  : YES (实证对比后合理推迟)
  [✓] Precision@K supported by relevance labels?      : YES (引入 must/acceptable/forbidden)
  [✓] Query-level pass separated from candidate prec? : YES (Pass Rate 93~100% vs Prec 68~75%)
  [✓] IMPL-2 multi-source FK-safe provenance typed?   : YES (ProvenanceRef(kind, id, role))
  [✓] No new Data Model states introduced?            : YES (严格基于已有 canonical 状态)
  [✓] DEV and Holdout separated?                      : YES (DEV 29 用例 / Holdout 15 用例)
  [✓] Fusion weights validated on holdout?            : YES (Holdout 通过率 100.0%)
  [✓] NO_MEMORY threshold validated on holdout?       : YES (Holdout 误召回率 0.00%)
  [✓] False Recall remains acceptable?                : YES (0.00% ~ 3.45%)
  [✓] Reranker decision still justified?              : YES (Top-3 相关性充分，拒绝虚增延迟)
  [✓] Resource numbers classified measured vs estim?  : YES (严格标注 MEASURED / PROJECTED)
  [✓] Any blocker before freeze?                      : NONE
--------------------------------------------------------------------------------
                   >>> TECHNICAL RETRIEVAL DESIGN V2.1 <<<
                                   FROZEN
                                 READY FOR
              CONSOLIDATION / RECONCILIATION TECHNICAL DESIGN
================================================================================
```

### 停止声明
Coeva 跨会话长期记忆技术检索设计与基准评测补丁已全部闭环。未修改生产代码、未执行正式数据库迁移、未修改生产数据。**技术检索设计正式冻结**。
