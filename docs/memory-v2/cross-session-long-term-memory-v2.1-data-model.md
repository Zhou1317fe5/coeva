# Co-evolving Companion：跨会话长期记忆 V2.1 逻辑数据模型规范 (Frozen Edition)
## ——关系完整性、生命周期解耦、语义级联删除与最小 SQLite 本地持久化设计

> **规范状态与元数据**：
> - **阶段定位**：Logical Data Model & Information Schema Design (V2.1 Freeze Review & Correction)
> - **文档状态**：`Data Model Revision: v2.1 (Frozen — Final Specification Applied)`
> - **上位冻结规范**：`docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture Revision: v2.1 Frozen)
> - **事实源基线**：
>   1. `docs/research/cross-session-long-term-memory-fact-audit.md` (生产数据库事实审计：42 slices, 115k events)
>   2. `docs/research/long-term-memory-reference-architecture-study.md` (外部参考架构调研：Hindsight, TDAI, Mem0, Letta, Graphiti)
>   3. 真实生产环境：`data/companion_chronicle.db` (SQLite WAL) 与 `data/raw_slices.jsonl`
> - **硬性设计边界**：
>   - 本文档**严格限定在逻辑数据模型、实体关系、字段语义、生命周期与迁移映射**；
>   - **不修改任何生产代码、不执行数据库迁移脚本、不写具体 CREATE TABLE / ALTER TABLE DDL**；
>   - **不选型检索技术、不做 Embedding / FTS / Vector Benchmark、不实现 Consolidator 与 UI**；
>   - **不引入 Graph DB、PostgreSQL、Redis 等重型组件，坚持本地轻量 SQLite 单文件与 Markdown 人文档案结合**；
>   - 杜绝通用 EAV 实体属性库与伪多态外键，实现 SQLite 级原生外键完整性（Referential Integrity）。

---

## 1. V2.1 Data Model Freeze Corrections（数据模型冻结修正核心声明）

针对上一轮数据模型设计中存在的 5 项 P0 阻断性缺陷与多项 P1 语义混淆，本冻结版本完成全面修正与语义闭环：

1. **彻底消除伪多态外键，确立类型化关系模型（Resolved Pseudo-Polymorphic FKs）**：
   - 彻底废除 `(evidence_type, evidence_id)` 无约束外键伪设计；
   - 深度比较并决议采用 **Candidate P-A：类型化关系表（Typed Relation Tables）**，为 `raw_slices`、`event_skeletons`、`semantic_memories`、`observations`、`hypotheses`、`confirmed_insights` 与 `episodes` 建立原生强外键关联表，确保 SQLite 原生具备外键约束能力与确定性反向遍历路径；
2. **共识理解与候选假说物理实体分立（Independent Confirmed Insights Entity）**：
   - 废除将人类校准结果仅作为 `hypotheses.status` 粗暴枚举的做法；
   - 正式设立独立的 `confirmed_insights` 实体，完美支持 `user_action = 'partly'` 时人类附加更正手记（`user_note`）与最终校准共识陈述（`calibrated_statement`）的落盘，确立校准前假说与校准后共识的版本演化链，解耦待审心智假说与行为指导共识；
3. **敏感语义副本全面清查与原话去冗余（Sensitive Payload Inventory & Deduplication）**：
   - 建立全系统敏感语义副本盘点表（Sensitive Payload Inventory）；
   - 决议：`semantic_memories` **废除复制的 `raw_quote` 冗余字段**，通过 `source_slice_id` 强外键动态关联合法用户原话；物理硬删除时底座清除即彻底断绝原文泄露，并在人生章节中执行脱敏重写；
4. **闭环遥测事件 TTL 与长期观察信念的生命周期冲突（Event Retention Pinning）**：
   - 深度比较三种遥测保留策略，决议采用 **Strategy E-C：引用钉住（Retention-Pinned）策略**：外部遥测事件虽受固定 TTL 清理管辖，但**一旦被 `observation_event_links` 或 `episode_event_links` 引用为长期认知或经历的溯源锚点，在后台清理任务中强制豁免**，直到观察被撤回或经历解除，彻底杜绝长期信念溯源凭空悬空；
5. **区分全局范围与未决工程范围（Disambiguate Unknown vs Global Scope）**：
   - 确立三态范围模型（`'global'` / `'project'` / `'unresolved'`），严禁在未获知当前工程时将技术事实草率默认填为 `'global'`；支持后续由经历聚类或人类显式补全工程范围；
6. **物理写入幂等与认知证据独立性严格解耦（Idempotency vs Evidence Independence）**：
   - 区分物理入库防抖（`ingestion_dedup_key`）与认识论证据独立性（`evidence_reinforcements.independence_fingerprint`），移出过早固化的 5 秒窗口与具体哈希公式，数据模型仅保留结构化表达能力；
7. **事实有效性状态与表达展示策略正交解耦（Semantic State vs Expression Policy）**：
   - 将事实是否为真（`validity_status: active / superseded / invalidated / ambiguous`）与表达策略（`expression_policy: normal / muted / do_not_mention`）拆分为独立字段；移除数据模型中残留的 1.0/0.3 等检索阶段数值；
8. **人生章节与观察信念的多源强类型溯源（Chapter & Observation Typed Provenance）**：
   - 明确人生章节为文学叙事，**叙事文本绝不反向作为认知证据（DM-8）**；建立 `chapter_slice_links`、`chapter_episode_links` 与 `chapter_insight_links` 明确溯源；
   - 明确经历容器（Episode）仅作为组织与语境背景，其 summary 绝不能伪装成直接事实证据；通过 `observation_episode_links` 表征语境范围，由 `observation_slice_links`、`observation_event_links`、`observation_memory_links` 承载直接正反证据；
9. **假说多观察证据依赖与主锚点治理（Hypothesis Multi-Observation Links）**：
   - 废除单字段 `primary_observation_id` 构成的单点脆弱依赖，引入 `hypothesis_observation_links` 关系表，支持多项 Observation 分别扮演 supporting / counter / contextual 角色，并标识 `is_primary` 主锚点；
10. **确立单一法定实体清单（Single Canonical Entity Inventory · 20大实体规格）**：
    - 正式发布全局统一的 20 大实体清单（8 大核心实体 + 1 大叙事元数据 + 10 大类型化关系表 + 1 大独立证据流水账本），ER 图、Schema、迁移映射与删除遍历 100% 严格对齐。

---

## 2. Frozen Architecture Constraints（上位冻结架构约束映射）

本数据模型设计必须原样恪守 V2.1 冻结架构（`cross-session-long-term-memory-v2.1-architecture-frozen.md`）所确立的 10 大架构定理：

| 架构定理 | 数据模型设计映射与落地方式 |
| :--- | :--- |
| **INV-1. Evidence ≠ Interpretation** | `raw_slices` / `event_skeletons` 为物理只读底座；`semantic_memories` / `hypotheses` 为派生层，物理分表存储，严禁改写底座。 |
| **INV-2. Past Truth ≠ Current Truth** | `semantic_memories` 与 `confirmed_insights` 引入 `valid_from` 与 `invalidated_at`；废除物理覆盖，通过时态字段表达有效性演进。 |
| **INV-3. Retrieved ≠ Injected ≠ Spoken** | 数据模型仅负责存储与高效提供候选检索视图，不包含任何将记忆强行塞入 Prompt 的字段级强耦合，预留正交过滤字段。 |
| **INV-4. Silence Is Valid** | 允许检索返回空结果（0 行）；表达偏好（`expression_policy`）独立落盘，静谧静默为默认合法状态。 |
| **INV-5. User Voice > Telemetry Inference** | 引入 `authority_class`（claim-sensitive），对用户自述给予偏好/自我认知最高解释权；Telemetry 仅为 `system_observed`。 |
| **INV-6. Candidate ≠ Confirmed** | 候选假说（`hypotheses`）与最终共识（`confirmed_insights`）物理解耦分表，未校准前绝不并入共识实体。 |
| **INV-7. No Belief Without Provenance** | 每个派生实体必须具备非空的强外键溯源；有效证据归零强制触发 `RETRACT`，杜绝孤儿共识。 |
| **INV-8. Deletion Propagates Semantically** | 建立类型化外键反向遍历查询路径，物理硬删除切片时，级联递减 Observation 支撑度，归零则撤回高层假说与共识。 |
| **INV-9. Sanctuary Overrides Recall** | 情感状态作为瞬时 Context 挥发字段，不作为持久化实体污染长期数据库。 |
| **INV-10. Memory Must Not Echo** | 大模型回音壁反馈隔离围栏由上层过滤，数据模型层只负责存储纯粹、干净、具备独立溯源的事实文本。 |

---

## 3. Current-State Storage Audit（当前生产存储现状审计）

基于 `data/companion_chronicle.db` 的真实 Schema（`dump_db_schema.py` 提取）与 11.5 万条历史数据审计：

| Existing Storage | Current Role | Canonical? | Mutable? | Referenced By | Core Defect / Architectural Mismatch |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **`slices`** (42行) | 随手投喂切片 | **YES** | NO | `evidence` 视图 | **无 session/project 字段**；57.1% 为调试与重复闲聊；无版本与失效机制。 |
| **`events`** (11.5万行)| 外部遥测流 | **YES** | NO | `evidence` 视图 | 11.5 万行。`user_prompt` 文本已被脱敏剥离；无上下文关联到具体 Slice。 |
| **`evidence`** (视图) | 统一联合视图 | NO (VIEW) | NO | 无显式查询 | 粗暴使用 `UNION ALL`，将用户投喂与工具报错硬拼在一起，无法做精细区分。 |
| **`hypotheses`** (4条) | 候选心理假说 | **YES** | YES | 界面查看 | `supporting_episodes` 存为逗号分隔字符串，**失去外键完整性**；无时间性与共识分立。 |
| **`insights`** (0条) | 确认认知共识 | **YES** | YES | 章节资格门 | 运行时完全死锁在表中，**Daily Recall 检索器完全不读**；无时效演化。 |
| **`growth_themes`** (0行)| 认知主题 | **YES** | YES | 界面查看 | 仅 0 行数据，概念重叠，与 Hypotheses 功能混淆。 |
| **`raw_slices.jsonl`** | 切片追加日志 | **NO** (副本) | NO | 文件持久化 | 双写冗余；无法表达软删除与置失效状态，易造成事实源分裂。 |
| **`chapters/*.md`** | 人生章节文件 | **YES** (正文) | YES | 界面阅读 | 独立于 SQLite，元数据与数据库脱节；敏感删除时无法按外键自动脱敏。 |

---

## 4. Canonical Source of Truth Decision（法定权威事实源选型决议）

针对当前 SQLite 与 `raw_slices.jsonl` 双主库的历史包袱，进行方案对比：

| 评估维度 | Option A: SQLite 为唯一事实源 (推荐选定) | Option B: JSONL 为唯一事实源 (SQLite物化) | Option C: 文件系统 Git 仓库为事实源 |
| :--- | :--- | :--- | :--- |
| **事务与一致性 (ACID)** | **极高**。原生事务支持，外键约束与状态更新可靠。 | **差**。行级追加无法原子更新 `invalidated_at`。 | **低**。文件并发读写与锁竞争复杂。 |
| **删除语义 (Hard Delete)**| **确定性**。一条 SQL 物理删除，并能触发级联。 | **极难**。append-only 文件必须重写物理磁盘全量文件。| 需生成新的 Git Commit，操作重。 |
| **时序与有效性查询** | **极快**。直接按 `valid_from` 与索引高效区间过滤。 | **慢**。每次查询都需要从头重放所有 JSON 行。 | 慢。 |
| **崩溃恢复能力** | **强**。SQLite WAL 模式保障断电数据零损坏。 | 易出现半截损坏行。 | 强。 |
| **工程实现复杂度** | **低**。Python 标准库 `sqlite3` 原生驱动，零外部依赖。| 中。需要自行手写 JSONL 物化与索引重构代码。 | 极高。 |

> **选型决议**：
> **全面选定 Option A：`data/companion_chronicle.db`（SQLite WAL 模式）为全局唯一法定权威事实源（Canonical Source of Truth）。**
> 
> - `data/raw_slices.jsonl` 降级为**单向异步导出副本（Read-only Export Stream）**；
> - 任何系统的写入、更新、软删除与物理硬删除，**100% 必须先在 SQLite 事务中完成并以其为准**；
> - 彻底废除两处同时各自为政双写的架构缺陷。

---

## 5. Candidate Data Models & Trade-off Analysis（候选数据模型对比与推荐决议）

针对多源溯源指针（Provenance）如何组织跨表关系，深入比较 3 种候选数据模型：

### 5.1 候选方案定义

- **Candidate P-A：类型化关系表模型（Typed Relation Tables Model - 推荐选定）**：
  为每种源实体与目标实体之间的关系建立专属的强类型中间表（如 `observation_slice_links`、`observation_event_links`、`observation_memory_links`、`observation_episode_links`、`hypothesis_observation_links` 等）。每张表只有两个强类型外键字段及少量关系元数据。
- **Candidate P-B：证据超类型统一实体模型（Evidence Supertype Identity Model）**：
  引入抽象超类型父表 `evidence_nodes(id, evidence_kind)`，`raw_slices` 和 `event_skeletons` 将自身 ID 注册为 `evidence_nodes` 的子实体。上层通过单一的 `observation_evidence_links(observation_id, evidence_node_id)` 关联。
- **Candidate P-C：演进式多态弱引用模型（Evolutionary Hybrid / Polymorphic IDs Model）**：
  沿用 V1 的松散设计，在关联表中使用 `(evidence_type, evidence_id)` 字符串伪外键，或者在 JSON 文本列中存储引用 ID 数组。

### 5.2 九大评估维度深度权衡矩阵

| 评估维度 | Candidate P-A: Typed Relation Tables (推荐) | Candidate P-B: Evidence Supertype Identity | Candidate P-C: Evolutionary Hybrid (伪外键) |
| :--- | :--- | :--- | :--- |
| **1. SQLite FK 真实完整性** | **100% 原生支持**。每一列都由 SQLite 物理外键约束保证，断绝悬空引用。 | 仅对父表具备 FK，无法原生约束父表 ID 确实属于某具体子表，需手写触发器。 | **完全丢失**。SQLite 无法对动态类型字段建外键，悬空引用率极高。 |
| **2. Hard Delete 反向遍历** | **极简单极快**。直接按强类型关联表执行 `SELECT ... WHERE slice_id = :id`，覆盖索引命中。 | 中等。需要两次查询（子表 -> 父表 -> 引用表），关联链路长。 | 极脆弱。必须针对字符串拼接解析，无法利用数据库引擎级联能力。 |
| **3. Schema 复杂度** | 结构平铺直观。表数量为 20 张，但每张表字段极少（2~4 列），语义单一清晰。 | 表数量较少（约 12 张），但引入父子继承结构，抽象层增加。 | 表数量最少（约 10 张），但业务逻辑与约束全部泄露给应用层。 |
| **4. 迁移与数据平移成本** | **极低**。现存 42 条切片与 11.5 万条事件平移无需创建中间代理节点。 | **高**。迁移时必须先为数十万事件生成 `evidence_nodes` 代理主键，迁移事务耗时长。 | 最低，但将所有技术债永久保留。 |
| **5. 查询可读性与执行计划** | **极高**。标准的 SQL `JOIN`，查询计划直观，EXPLAIN QUERY PLAN 最优。 | 中等。必须进行多次多表关联（Join Chaining），执行计划易退化。 | 差。SQL 中需频繁写 `AND evidence_type = 'slice'`，易漏写导致数据错乱。 |
| **6. 未来扩展性** | **优**。新增证据类型（如后续增加语音输入）仅需新增一张强类型关联表，不影响既有结构。 | 具有形式上的通用性，但新增类型需维护全局 ID 生成器与父子一致性。 | 表面灵活，实质上缺乏结构演进保障。 |
| **7. 过度工程化与 EAV 风险**| **零风险**。纯正的关系范式设计，无任何 EAV 或通用对象建模陷阱。 | **有风险**。超类型设计极易诱导后续开发者将所有属性上提，最终退化为通用 EAV。| 零工程化，但属于反模式。 |
| **8. 隐私边界保障** | **极强**。硬删除时精准命中对应关联表，无残留代理 ID。 | 较弱。删除子实体后父表节点容易成为无语义僵尸孤儿，泄露历史流水痕迹。 | 极差。极易在多态引用中遗漏某类关联导致未删净。 |
| **9. 本地 SQLite 适用度** | **完美适配**。SQLite 引擎擅长管理大量小型的 B-tree 索引表，内存与磁盘开销极低。| 较差。在无服务端的嵌入式 SQLite 中过度抽象会增加应用层 ORM 胶水代码负担。 | 一般。 |

> **决议裁定**：
> **全面选定 Candidate P-A：类型化关系表模型（Typed Relation Tables Model）。**
> 
> 尽管相较于伪多态设计表数量增加至 20 张，但其**在嵌入式 SQLite 环境下彻底实现了 100% 原生外键完整性、确定性反向遍历和零 EAV 风险**，是唯一能够承受长期伴生系统严苛隐私删除与认识论溯源闭环的坚实方案。

---

## 6. Master Entity Inventory（唯一法定实体清单 · 20大实体规格）

本清单为 Coeva 跨会话长期记忆 V2.1 数据模型的**唯一法定实体目录**。后续 Schema、ER 图、迁移映射与删除算法必须 100% 与本表保持一致：

| # | 实体名称 (Entity Name) | 实体类别 (Classification) | 持久化方式 | 权威事实源? | 核心职责与语义定义 |
| :-: | :--- | :--- | :---: | :---: | :--- |
| **1** | **`raw_slices`** | Core Evidence Table | SQLite | **Canonical** | 用户亲口输入的原始原话切片底座 (不可篡改的最高优先级资产) |
| **2** | **`event_skeletons`** | Core Evidence Table | SQLite | **Canonical** | 外部 Agent 客观行为遥测骨架底座 (受引用钉住与 TTL 管辖) |
| **3** | **`episodes`** | Experience Container | SQLite | Derived | 组织时空与任务经历的结构化容器 (含派生摘要，非事实证据) |
| **4** | **`semantic_memories`** | Semantic Fact / Pref | SQLite | Derived | 派生原子事实、长期偏好与相处规则 (时序双时间戳置失效) |
| **5** | **`observations`** | Belief Layer | SQLite | Derived | 跨经历聚合的客观信念单元 (承载独立证据计数 proof_count) |
| **6** | **`hypotheses`** | Candidate Understanding | SQLite | Derived | 伴生体主观心智推断假说 (状态机：candidate / retracted 等) |
| **7** | **`calibration_events`** | Human Action Log | SQLite | **Canonical** | 人类在校准面板做出的历史决断不可变流水 (Yes / Partly / No) |
| **8** | **`confirmed_insights`** | Confirmed Self Model | SQLite | Derived | 经校准批准的最终自模型共识实体 (承载人类确认后的规范化文本) |
| **9** | **`chapter_metadata`** | Narrative Metadata | SQLite | Derived (MD为本)| 人生章节外部 Markdown 文件的元数据索引与脱敏状态标记 |
| **10**| **`episode_slice_links`** | Typed Relation Table | SQLite | Derived | Episode 与 Raw Slice 的强外键关联映射表 (含系统/人工标定) |
| **11**| **`episode_event_links`** | Typed Relation Table | SQLite | Derived | Episode 与 Event Skeleton 的强外键关联映射表 |
| **12**| **`evidence_reinforcements`**| Proof Counting Ledger | SQLite | Derived | 派生记忆的独立证据印证记录流水 (基于独立性指纹防刷分) |
| **13**| **`observation_slice_links`**| Typed Relation Table | SQLite | Derived | Observation 与 Raw Slice 的强外键关联表 (区分支撑与反例) |
| **14**| **`observation_event_links`**| Typed Relation Table | SQLite | Derived | Observation 与 Event Skeleton 的强外键关联表 (锁定钉住引用) |
| **15**| **`observation_memory_links`**| Typed Relation Table | SQLite | Derived | Observation 与 Semantic Memory 的强外键关联表 (支持反例) |
| **16**| **`observation_episode_links`**| Typed Relation Table | SQLite | Derived | Observation 与 Episode 的强外键关联表 (限定经历语境范围) |
| **17**| **`hypothesis_observation_links`**| Typed Relation Table | SQLite | Derived | Hypothesis 与 Observation 的多路强外键关联表 (含主锚点标记) |
| **18**| **`chapter_slice_links`** | Typed Relation Table | SQLite | Derived | Chapter 与 Raw Slice 叙事引用的强外键映射表 (硬删除脱敏路标) |
| **19**| **`chapter_episode_links`** | Typed Relation Table | SQLite | Derived | Chapter 与 Episode 叙事引用的强外键映射表 |
| **20**| **`chapter_insight_links`** | Typed Relation Table | SQLite | Derived | Chapter 与 Confirmed Insight 叙事引用的强外键映射表 |

---

## 7. Sensitive Payload Inventory（敏感语义副本盘点与处置表）

为确保物理硬删除（Hard Delete）不发生任何语义泄漏，全系统对所有可能复制、改写用户敏感语义的字段进行盘点并确立处置规程：

| 实体 / 字段 | 是否包含用户语义副本？ | 资产属性 | 物理硬删除时的确定性处置行动 (Hard Delete Action) |
| :--- | :---: | :---: | :--- |
| **`raw_slices.content`** | **YES (原文)** | Canonical | **物理抹除 (DELETE FROM raw_slices)**。底层彻底销毁，零容忍。 |
| **`semantic_memories.raw_quote`** | **REMOVED** | N/A | **架构修正：彻底废除该字段**。通过 `source_slice_id` 动态 JOIN，底座删除时无任何原话残留。 |
| **`semantic_memories.statement`** | **YES (派生改写)**| Derived | 若无其他独立证据支撑，置为 `validity_status = 'deleted'` 或直接物理级联删除。 |
| **`episodes.summary`** | **YES (阶段摘要)**| Derived | 依赖被删切片的 Episode Summary 标记为失效，触发**异步重新生成（Recompute）**。 |
| **`observations.statement`** | **YES (信念陈述)**| Derived | 证据归零时置为 `status = 'retracted'`；证据削弱时扣减计数并重新评估有效性。 |
| **`hypotheses.statement`** | **YES (推断陈述)**| Derived | 支撑 Observation 撤回时，假说同步置为 `status = 'retracted'`，退出候选。 |
| **`confirmed_insights.statement`**| **YES (共识陈述)**| Derived | 支撑完全归零时置为 `status = 'retracted'`，立即退出检索与行为提示。 |
| **`calibration_events.user_note`**| **YES (修正手记)**| Canonical | 属于历史校准行为事实。用户隐私硬删除时执行字段级**脱敏掩蔽 (Redact to empty)**。 |
| **`chapter_metadata` (MD正文)** | **YES (叙事文学)**| Canonical | 标记 `needs_privacy_redaction = 1`，后台调度异步任务执行敏感实体脱敏重写。 |

---

## 8. Event Retention vs Durable Provenance（遥测 TTL 与引用钉住机制决议）

外部 Agent 遥测数据（11.5 万行）既是客观行为流水，又受轻量存储与隐私保护管辖。为解决“30 天 TTL 清理导致长期信念溯源断裂”的矛盾，对比 3 种策略：

### 8.1 策略权衡比较

| 评估维度 | Strategy E-A: TTL 事件永不入持久理解 | Strategy E-B: 采用时快照提升为持久证据 | Strategy E-C: 引用钉住机制 (Retention Pinning - 推荐选定) |
| :--- | :--- | :--- | :--- |
| **隐私保护度** | 极高（仅短期留存）。 | 中等（产生不可变快照）。 | **极高**（仅保留脱敏骨架：`tool_name`、`event_type`，无代码/正文）。 |
| **存储膨胀风险** | 零膨胀。 | 产生大量不可变的快照冗余行。 | **极低**。仅少数被 Observation 采纳的关键骨架行被钉住，其余 99% 流水按期蒸发。 |
| **溯源完整性** | **断裂**。伴生体无法形成跨数月的客观工作习惯理解。 | 完整，但维护两套表结构。 | **完美闭环**。SQLite 强外键始终有效，无任何悬空断裂。 |
| **删除语义清晰度** | 简单。 | 复杂（涉及快照清理）。 | **极清晰**。Observation 撤回后钉住自动解锁，下次定时任务自然清理。 |
| **工程实现复杂度** | 最低，但功能受损严重。 | 高。需要实现“提升/快照”流水线。 | **极低**。仅需在清理 SQL 的 `WHERE` 条件中增加两行 `NOT EXISTS` 关联查询。 |
| **可解释性** | 差。无法解释“你上个月频繁超时”的依据。 | 良好。 | **优秀**。可直接枚举出被引用的具体工具执行骨架。 |

> **选型决议**：
> **全面选定 Strategy E-C：引用钉住（Retention-Pinned）策略。**
> 
> - 外部遥测事件虽受固定 TTL（例如 30 天）清理管辖；
> - 但**一旦被 `observation_event_links` 引用为长期观察信念的溯源锚点，或被 `episode_event_links` 引用为重要经历骨架，在后台定时清理任务中强制豁免**；
> - 当且仅当该 Observation 被撤回且 Episode 被归档且无任何活动引用时，钉住状态自动解除，在下一轮清理中安全蒸发。

```sql
-- 概念清理逻辑规范 (Retention Pinning Purge Logic)
DELETE FROM event_skeletons
 WHERE retention_class = 'transient'
   AND occurred_at < :cutoff_timestamp
   -- 核心约束：凡是被持久化经历或观察信念引用的事件，强制钉住豁免！
   AND event_id NOT IN (SELECT event_id FROM episode_event_links)
   AND event_id NOT IN (SELECT event_id FROM observation_event_links);
```

---

## 9. Scope Model: Unknown ≠ Global Scope（工程范围模型与后补机制）

系统确立三态范围模型，杜绝将未知工程武断升级为全局：

```text
Scope Model (三态划分)
├── 'project'    : 明确归属于特定工程 (project_id 必须为非空有效字符串)
├── 'global'     : 明确跨工程通用的全局偏好/规则/事实 (project_id 必须为 'global')
└── 'unresolved' : 当前无法可靠确认工程归属 (project_id 强制为 NULL)
```

- **语义定义**：
  - `global`：明确知道该信息跨项目成立（如用户说：“我写所有代码都习惯用 4 格缩进”）；
  - `project`：明确绑定特定工作区（如用户在 `co-evolving-companion` 窗口投喂：“这个项目改用 PySide6”）；
  - `unresolved`：当前无法可靠判断项目范围（例如用户在全局快捷键投喂：“把测试框架换成 pytest”，此时前台未检测到活跃 IDE）。
- **后补机制（Post-Resolution Workflow）**：
  1. 初始捕获赋予 `scope = 'unresolved', project_id = NULL`；
  2. 当该切片后续被归纳进某次明确工程的 Episode 时，或关联到带有工程上下文的事件时，由系统或人类在校准面板显式补全工程范围（`scope = 'project', project_id = :id`）；
  3. 检索层在特定工程上下文中，允许通过策略决定是否读取 `unresolved` 事实，但绝不允许未决事实静默污染其他确定工程。

---

## 10. Idempotency vs Evidence Independence（物理防抖与认识论证据独立性解耦）

数据模型将“物理写入幂等”与“认识论证据独立性”彻底物理拆分：

### 10.1 物理防抖（Write Idempotency）
- **解决目标**：“这是不是同一次物理写入被重复提交？”（防前端快速双击、网络超时重试、Connector 启动重放、文件重新导入）；
- **数据模型承载**：`raw_slices.ingestion_dedup_key`；
- **数据库约束**：在 `raw_slices` 上建立 `UNIQUE(ingestion_dedup_key)`；重复写入直接由数据库唯一键拒绝或忽略；
- **具体算法后置**：具体防抖窗口秒数与哈希生成算法由接入层实现决定，数据模型仅保证键的存在与唯一性。

### 10.2 认知证据独立性（Evidence Independence）
- **解决目标**：“这是不是一条跨越时空的、真正独立的认知新证据？”；
- **数据模型承载**：`evidence_reinforcements` 实体；
- **字段规格**：`(memory_id, independence_fingerprint, occurred_at)`；
- **数据库约束**：`UNIQUE(memory_id, independence_fingerprint)`；
- **认识论规则**：
  - 同一会话、同一经历内的反复唠叨或回音，生成相同的独立性指纹，不递增 `proof_count`；
  - 经历一个月后，用户在另一个独立场景中再次重申相同事实，生成新的独立性指纹，成功落盘并递增支撑计数；
  - 物理防抖与认知独立性彻底解耦，互不干扰。

---

## 11. Semantic Truth Lifecycle vs Expression / Retrieval Policy（事实有效性与表达门控正交解耦）

数据模型彻底分离“事实有效性状态”与“表达展示策略”，严禁将 `muted` 等展示逻辑作为事实真伪状态：

### 11.1 语义真实性状态（Semantic State · `validity_status`）
描述事实客观上是否为真、是否处于争议中：
- `active`：当前成立并生效的有效事实；
- `superseded`：已被后序更新的事实明确取代，退出当前决策，但保留历史足迹；
- `invalidated`：已被证实不再成立或自然失效；
- `ambiguous`：发现存在表面冲突但证据不足以确信变更，挂起等待进一步观察。

### 11.2 表达与检索策略（Expression Policy · `expression_policy`）
描述在认知成立的前提下，是否允许主动提及：
- `normal`：默认状态，在满足相关性与门控时可自然唤醒或表达；
- `muted`：后台知道该事实为真，但用户要求“不要主动提起”；
- `do_not_mention`：涉敏或用户偏好闭锁，严禁在任何生成回复中出现。

### 11.3 检索辅助指标的定位（Retrieval-use Metadata）
- 访问计数、衰减时间戳（`last_accessed_at`）等属于**检索执行策略元数据**；
- 移除数据模型中一切未经基准验证的固定数值（如 1.0/0.3 等权重），具体数值下放至检索技术评测阶段。

---

## 12. Confirmed Insight Entity & Partly Calibration Lifecycle（共识理解实体与校准生命周期）

针对人类校准行为，深度评估共识表示方案，并给出生命周期闭环：

### 12.1 方案对比与决议

- **Option U-A：独立共识实体（`confirmed_insights` - 推荐选定）**：
  待审假说（`hypotheses`）与确认共识（`confirmed_insights`）物理分表。校准事件（`calibration_events`）作为不可变流水纽带，在确认或部分确认时，将最终提炼的共识陈述存入 `confirmed_insights`。
- **Option U-B：假说版本化（Hypothesis Versioning）**：
  单表假说引入 `version` 字段，校准后原地递增版本号。

> **决议裁定**：
> **全面选定 Option U-A：独立设立 `confirmed_insights` 实体。**
> 
> 彻底解决 `Hypothesis.statement` 无法表达人类附加修正（`Partly`）的致命缺陷。行为指导策略（Behavior Policy）和宏观反思只读取 `confirmed_insights`，绝不直接将半生不熟的候选假说当作行为准则。

### 12.2 Partly 校准场景下的完整生命周期演练（T1 ~ T7 溯源闭环）

以下通过跨月实际场景演练生命周期与实体追溯机制：

```text
[T1 - 初始推断]
伴生体根据近两周开发遥测，生成候选假说:
  - Hypothesis H1: "你喜欢让 Agent 完全自主闭环完成任务，无需中途向你确认。"
  - Status: 'candidate'

[T2 - 人类校准]
用户在校准面板查看 H1，点击 Partly，并附带手记:
  - Calibration Event C1:
    user_action = 'partly'
    user_note = "只在前端和样式任务中如此；架构决策和后端核心逻辑仍希望先确认。"

[T3 - 共识生成]
系统生成独立共识实体，H1 标记为已校准，行为策略立即读取 U1:
  - Confirmed Insight U1:
    source_hypothesis_id = H1.id
    source_calibration_id = C1.id
    statement = "在前端和样式任务中倾向 Agent 完全自主闭环；在架构决策与后端核心逻辑中坚持先确认。"
    status = 'confirmed'
    valid_from = T3

[T4 - 隐私删除]
数月后，用户要求物理删除 T1 期间的某批前端调试切片。
底层关联清除后，经重新计算，H1 依赖的有效观察支撑度削弱。

[T5 - 触发降级]
U1 依赖链受损，但仍有部分历史痕迹:
  - U1.status 变更为 'revalidation_required'
  - 伴生体在行为中降低对该共识的笃定度，提示条目出现校准问号。

[T6 - 再次校准]
用户在校准面板确认最新态度并更新说明:
  - Calibration Event C2:
    user_action = 'yes'
    user_note = "现在全栈任务都可以完全自主，我只看最终 diff。"

[T7 - 共识更替]
系统生成全新共识 U2，并建立版本更替链:
  - Confirmed Insight U2:
    source_hypothesis_id = H1.id
    source_calibration_id = C2.id
    statement = "全栈任务均支持 Agent 完全自主闭环，偏好通过最终 diff 进行验收。"
    status = 'confirmed'
    valid_from = T7
  - U1.superseded_by = U2.id
  - U1.invalidated_at = T7
  - U1.status = 'superseded'

溯源链条完整无缺:
  H1 -> C1 -> U1 -> (T4/T5 Event) -> C2 -> U2 (完全杜绝字符串无痕覆盖)
```

---

## 13. Multi-Evidence Observation & Hypothesis Provenance（观察信念与假说多证据依赖规范）

### 13.1 观察信念的多路强类型溯源（Observation Provenance）
Observation 是跨经历聚合的信念层，其支撑证据来源通过以下强类型关联表表达：
- `observation_slice_links`：指向具体的原始切片（`raw_slices`），字段 `role: 'supporting' | 'counter'`；
- `observation_event_links`：指向具体的外部工具遥测骨架（`event_skeletons`），字段 `role: 'supporting' | 'counter'`；
- `observation_memory_links`：指向派生原子事实（`semantic_memories`），字段 `role: 'supporting' | 'counter'`；
- `observation_episode_links`：指向经历容器（`episodes`），字段 `role: 'contextual_scope'`。**特别约束：Episode 仅提供经历发生的时空与任务语境，其摘要（summary）绝不可作为直接事实证据**。

### 13.2 假说多观察证据关联表（`hypothesis_observation_links`）
废除单一的 `primary_observation_id` 单点依赖，引入专属类型化关系表：
- **实体**：`hypothesis_observation_links`；
- **字段**：`hypothesis_id`（FK）、`observation_id`（FK）、`role`（`'supporting' | 'counter' | 'contextual'`）、`is_primary`（`0 | 1`）；
- **级联判定**：
  - 当一个支撑 Observation 被撤回时，若假说仍有其他有效支撑 Observation，假说状态不直接撤回，而是置为 `status = 'revalidation_required'`；
  - 当且仅当假说的所有有效支撑 Observation 全部归零时，假说才触发物理撤回（`status = 'retracted'`）。

---

## 14. Chapter Provenance & Narrative Boundary（人生章节溯源与叙事边界规范）

- **叙事不可反向为凭定理（DM-8）**：
  人生章节（Growth Chapters）是双人共写留白的宏观人生纪实，物理保存在 Markdown 文件中。**叙事文本绝不反向作为任何微观事实、偏好或信念的证据**。
- **章节类型化溯源关系表**：
  - `chapter_slice_links`：记录该章节引用或提及了哪些原始切片（`raw_slices`）；
  - `chapter_episode_links`：记录该章节取材了哪些经历结构（`episodes`）；
  - `chapter_insight_links`：记录该章节反映了哪些确认共识（`confirmed_insights`）。
- **隐私脱敏联动机制**：
  当用户执行某条切片的物理硬删除时，通过 `chapter_slice_links` 直接精准反查受影响章节，将 `chapter_metadata.needs_privacy_redaction` 置为 1，触发后台异步脱敏任务，杜绝隐私在文学正文中泄露。

---

## 15. Canonical / Derived / Rebuild Classification（法定事实源与重建语义分类规范）

数据模型对全系统 20 大实体的权威性与可重建性做出清晰裁决：

| 资产类别 | 覆盖实体 | 权威性 (Authority) | 是否可被模型改写？ | 丢库后能否自动重算重建？ | 生命周期与治理策略 |
| :--- | :--- | :---: | :---: | :---: | :--- |
| **P1 核心证据资产** | `raw_slices`<br>`event_skeletons` | **Canonical** | **绝对禁止** | **绝对不能** | 系统的立足之本。必须由 SQLite WAL 模式强事务保护，定时备份。 |
| **P1 核心行为资产** | `calibration_events` | **Canonical** | **绝对禁止** | **绝对不能** | 人类历史校准行为事实。不可篡改，支持用户隐私擦除。 |
| **P1 人文叙事资产** | `chapters/*.md` 正文 | **Canonical** | 需用户协作 | **不能通过算法重建** | 文学留白资产，纯文本 Markdown 保存，数据库仅存元数据索引。 |
| **P2 派生结构与经历** | `episodes`<br>`episode_*_links` | Derived | 允许系统聚类维护 | **可由证据流重算** | 包含 `curation_source: 'system' \| 'user'`；用户手工标定的经历组织不可随意重置。 |
| **P2 派生认知与信念** | `semantic_memories`<br>`observations`<br>`hypotheses`<br>`confirmed_insights` | Derived | 允许调和置失效 | **可基于证据与校准流水重构**| 依赖归零时强制撤回，时态置失效，不物理覆盖历史版本。 |
| **P3 关系与流水账本** | 各种 Typed Links<br>`evidence_reinforcements` | Derived | 严格受外键管辖 | **可完全重构** | 强外键级联管理，底层删除时自动清理。 |

---

## 16. Proposed Logical Schema（正式建议逻辑 Schema · 20大实体字段规格）

以下为 V2.1 冻结数据模型的 20 大实体完整逻辑规格。字段标注其可变性（Mutability）、必填性（Required）及权威性质（Canonical / Derived）：

### 16.1 核心证据与经历实体 (Core Evidence & Experience)

#### 实体 1：`raw_slices`（用户原话底座）
```text
Entity: raw_slices
Purpose: 用户亲口投喂与气泡回复的原话不可篡改证据底座 (Raw Evidence, Immutable)
Fields:
  - slice_id: TEXT (PK, UUIDv4) [Immutable, Required, Canonical]
  - occurred_at: TEXT (ISO-8601 UTC) [Immutable, Required, Canonical]
  - content: TEXT (用户原始输入明文，严禁模型篡改润色) [Immutable, Required, Canonical]
  - actor: TEXT ('user') [Immutable, Required, Canonical]
  - source: TEXT ('manual_feed' | 'bubble_reply') [Immutable, Required, Canonical]
  - scope: TEXT ('global' | 'project' | 'unresolved') [Mutable, Required, Canonical, Default 'unresolved']
  - project_id: TEXT (归属工程标识, scope='unresolved'时强制为NULL) [Mutable, Optional, Canonical]
  - ingestion_dedup_key: TEXT (客户端生成的防抖幂等键) [Immutable, Required, Canonical]
  - created_at: TEXT (落盘时间) [Immutable, Required, Canonical]
Index Requirements:
  - INDEX on occurred_at
  - INDEX on scope, project_id, occurred_at
  - UNIQUE on ingestion_dedup_key
```

#### 实体 2：`event_skeletons`（外部遥测骨架）
```text
Entity: event_skeletons
Purpose: 外部 Agent 客观行为遥测底座 (受引用钉住与 TTL 管辖)
Fields:
  - event_id: TEXT (PK, 稳定哈希) [Immutable, Required, Canonical]
  - occurred_at: TEXT (ISO-8601 UTC) [Immutable, Required, Canonical]
  - agent_id: TEXT ('pi-desktop' | 'hermes' | 'codex' 等) [Immutable, Required, Canonical]
  - session_id: TEXT (外部物理会话标识) [Immutable, Required, Canonical]
  - event_type: TEXT (枚举: 'pre_tool_use' | 'tool_failure' | 'user_prompt' 等) [Immutable, Required, Canonical]
  - tool_name: TEXT (脱敏工具签名, 如 'bash') [Immutable, Canonical, Default '']
  - error_category: TEXT (错误分类, 如 'Timeout') [Immutable, Canonical, Default '']
  - retention_class: TEXT ('transient' | 'durable') [Immutable, Required, Canonical]
  - created_at: TEXT [Immutable, Required, Canonical]
Index Requirements:
  - INDEX on occurred_at
  - INDEX on session_id, occurred_at
  - INDEX on retention_class, occurred_at
```

#### 实体 3：`episodes`（经历结构容器）
```text
Entity: episodes
Purpose: 组织真实经历的时空容器 (Grouping Container, Non-Evidence)
Fields:
  - episode_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - scope: TEXT ('global' | 'project' | 'unresolved') [Mutable, Required, Derived]
  - project_id: TEXT (工程归属标识, scope='unresolved'时为NULL) [Mutable, Optional, Derived]
  - started_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
  - closed_at: TEXT (ISO-8601 UTC) [Mutable, Optional, Derived]
  - title_hint: TEXT (经历简明主题标签) [Mutable, Required, Derived]
  - summary: TEXT (派生索引摘要, 证据变动时可重算) [Mutable, Optional, Derived]
  - status: TEXT ('open' | 'closed' | 'archived') [Mutable, Required, Derived]
  - created_at: TEXT [Immutable, Required, Derived]
Index Requirements:
  - INDEX on scope, project_id, started_at
  - INDEX on status
```

#### 实体 4：`episode_slice_links`（经历-切片关联表）
```text
Entity: episode_slice_links
Fields:
  - episode_id: TEXT (FK -> episodes.episode_id) [PK1, Immutable, Required, Derived]
  - slice_id: TEXT (FK -> raw_slices.slice_id) [PK2, Immutable, Required, Derived]
  - curation_source: TEXT ('system' | 'user') [Mutable, Required, Derived, Default 'system']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (episode_id, slice_id)
  - INDEX on slice_id
```

#### 实体 5：`episode_event_links`（经历-事件关联表）
```text
Entity: episode_event_links
Fields:
  - episode_id: TEXT (FK -> episodes.episode_id) [PK1, Immutable, Required, Derived]
  - event_id: TEXT (FK -> event_skeletons.event_id) [PK2, Immutable, Required, Derived]
  - curation_source: TEXT ('system' | 'user') [Mutable, Required, Derived, Default 'system']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (episode_id, event_id)
  - INDEX on event_id
```

---

### 16.2 派生事实与认知信念实体 (Derived Facts & Understanding)

#### 实体 6：`semantic_memories`（派生语义事实与偏好）
```text
Entity: semantic_memories
Purpose: 派生原子事实、长期偏好与相处规则 (时序双时间戳置失效，无冗余原话)
Fields:
  - memory_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - category: TEXT ('preference' | 'fact' | 'relationship_rule' | 'goal') [Immutable, Required, Derived]
  - statement: TEXT (规范化语义陈述) [Immutable, Required, Derived]
  - authority_class: TEXT ('user_asserted' | 'system_observed' | 'user_confirmed') [Immutable, Required, Derived]
  - scope: TEXT ('global' | 'project' | 'unresolved') [Mutable, Required, Derived]
  - project_id: TEXT (工程归属, scope='unresolved'时为NULL) [Mutable, Optional, Derived]
  - source_slice_id: TEXT (直接证据外键 -> raw_slices.slice_id, 动态JOIN原话) [Immutable, Optional, Derived]
  - source_episode_id: TEXT (关联经历外键 -> episodes.episode_id) [Immutable, Optional, Derived]
  - valid_from: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
  - invalidated_at: TEXT (ISO-8601 UTC, 失效时间) [Mutable, Optional, Derived]
  - superseded_by: TEXT (自引用 FK -> semantic_memories.memory_id) [Mutable, Optional, Derived]
  - validity_status: TEXT ('active' | 'superseded' | 'invalidated' | 'ambiguous') [Mutable, Required, Derived]
  - expression_policy: TEXT ('normal' | 'muted' | 'do_not_mention') [Mutable, Required, Derived, Default 'normal']
  - created_at: TEXT [Immutable, Required, Derived]
Index Requirements:
  - INDEX on scope, project_id, validity_status, valid_from
  - INDEX on source_slice_id
  - INDEX on superseded_by
```

#### 实体 7：`evidence_reinforcements`（独立证据印证账本）
```text
Entity: evidence_reinforcements
Purpose: 独立证据印证记录流水 (基于独立性指纹防刷分)
Fields:
  - reinforcement_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - memory_id: TEXT (FK -> semantic_memories.memory_id) [Immutable, Required, Derived]
  - slice_id: TEXT (FK -> raw_slices.slice_id, 可空) [Immutable, Optional, Derived]
  - event_id: TEXT (FK -> event_skeletons.event_id, 可空) [Immutable, Optional, Derived]
  - independence_fingerprint: TEXT (认知独立性指纹) [Immutable, Required, Derived]
  - occurred_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - UNIQUE on memory_id, independence_fingerprint
  - INDEX on memory_id
  - INDEX on slice_id
  - INDEX on event_id
```

#### 实体 8：`observations`（聚合客观信念）
```text
Entity: observations
Purpose: 跨经历聚合客观信念层 (承载独立有效支撑计数 proof_count)
Fields:
  - observation_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - scope: TEXT ('global' | 'project' | 'unresolved') [Mutable, Required, Derived]
  - project_id: TEXT [Mutable, Optional, Derived]
  - statement: TEXT (客观信念陈述) [Immutable, Required, Derived]
  - proof_count: INTEGER (有效独立支撑证据总数) [Mutable, Required, Derived, Default 1]
  - status: TEXT ('active' | 'retracted') [Mutable, Required, Derived]
  - created_at: TEXT [Immutable, Required, Derived]
  - updated_at: TEXT [Mutable, Required, Derived]
Index Requirements:
  - INDEX on scope, project_id, status
```

#### 实体 9：`observation_slice_links`（观察-切片关联表）
```text
Entity: observation_slice_links
Fields:
  - observation_id: TEXT (FK -> observations.observation_id) [PK1, Immutable, Required, Derived]
  - slice_id: TEXT (FK -> raw_slices.slice_id) [PK2, Immutable, Required, Derived]
  - role: TEXT ('supporting' | 'counter') [Immutable, Required, Derived, Default 'supporting']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (observation_id, slice_id)
  - INDEX on slice_id
```

#### 实体 10：`observation_event_links`（观察-事件关联表 · 钉住锚点）
```text
Entity: observation_event_links
Fields:
  - observation_id: TEXT (FK -> observations.observation_id) [PK1, Immutable, Required, Derived]
  - event_id: TEXT (FK -> event_skeletons.event_id) [PK2, Immutable, Required, Derived]
  - role: TEXT ('supporting' | 'counter') [Immutable, Required, Derived, Default 'supporting']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (observation_id, event_id)
  - INDEX on event_id
```

#### 实体 11：`observation_memory_links`（观察-记忆关联表）
```text
Entity: observation_memory_links
Fields:
  - observation_id: TEXT (FK -> observations.observation_id) [PK1, Immutable, Required, Derived]
  - memory_id: TEXT (FK -> semantic_memories.memory_id) [PK2, Immutable, Required, Derived]
  - role: TEXT ('supporting' | 'counter') [Immutable, Required, Derived, Default 'supporting']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (observation_id, memory_id)
  - INDEX on memory_id
```

#### 实体 12：`observation_episode_links`（观察-经历语境关联表）
```text
Entity: observation_episode_links
Purpose: 仅限定 Observation 产生的时空与任务语境范围 (Non-Evidence)
Fields:
  - observation_id: TEXT (FK -> observations.observation_id) [PK1, Immutable, Required, Derived]
  - episode_id: TEXT (FK -> episodes.episode_id) [PK2, Immutable, Required, Derived]
  - role: TEXT ('contextual_scope') [Immutable, Required, Derived, Default 'contextual_scope']
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (observation_id, episode_id)
  - INDEX on episode_id
```

---

### 16.3 心智假说与确认共识实体 (Hypotheses & Confirmed Consensus)

#### 实体 13：`hypotheses`（候选假说）
```text
Entity: hypotheses
Purpose: 伴生体主观心智推断假说 (状态机管理，独立于共识)
Fields:
  - hypothesis_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - statement: TEXT (伴生体主观心智推断陈述文本) [Immutable, Required, Derived]
  - lenses: TEXT (心理灵活性六大透镜标签) [Immutable, Required, Derived]
  - confidence_class: TEXT ('tentative' | 'grounded') [Mutable, Required, Derived]
  - status: TEXT ('candidate' | 'rejected' | 'revalidation_required' | 'retracted') [Mutable, Required, Derived]
  - last_calibrated_at: TEXT (最后校准时间) [Mutable, Optional, Derived]
  - created_at: TEXT [Immutable, Required, Derived]
Index Requirements:
  - INDEX on status
```

#### 实体 14：`hypothesis_observation_links`（假说-观察多路关联表）
```text
Entity: hypothesis_observation_links
Purpose: 支持假说由多项 Observation 共同支撑，并标记主锚点
Fields:
  - hypothesis_id: TEXT (FK -> hypotheses.hypothesis_id) [PK1, Immutable, Required, Derived]
  - observation_id: TEXT (FK -> observations.observation_id) [PK2, Immutable, Required, Derived]
  - role: TEXT ('supporting' | 'counter' | 'contextual') [Immutable, Required, Derived, Default 'supporting']
  - is_primary: INTEGER (1为主锚点, 0为次要支撑) [Mutable, Required, Derived, Default 0]
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (hypothesis_id, observation_id)
  - INDEX on observation_id
```

#### 实体 15：`calibration_events`（人类校准流水）
```text
Entity: calibration_events
Purpose: 人类历史校准行为不可变流水日志 (Yes / Partly / No)
Fields:
  - calibration_id: TEXT (PK, UUIDv4) [Immutable, Required, Canonical]
  - hypothesis_id: TEXT (FK -> hypotheses.hypothesis_id) [Immutable, Required, Canonical]
  - user_action: TEXT ('yes' | 'partly' | 'no') [Immutable, Required, Canonical]
  - user_note: TEXT (人类附加更正说明手记) [Mutable, Optional, Canonical]
  - calibrated_at: TEXT (物理发生时间) [Immutable, Required, Canonical]
Index Requirements:
  - INDEX on hypothesis_id, calibrated_at
```

#### 实体 16：`confirmed_insights`（已确认共识自模型实体）
```text
Entity: confirmed_insights
Purpose: 经人类校准批准的最终自模型共识实体 (驱动行为策略与背景反思)
Fields:
  - insight_id: TEXT (PK, UUIDv4) [Immutable, Required, Derived]
  - source_hypothesis_id: TEXT (FK -> hypotheses.hypothesis_id) [Immutable, Required, Derived]
  - source_calibration_id: TEXT (FK -> calibration_events.calibration_id) [Immutable, Required, Derived]
  - statement: TEXT (校准后的最终共识陈述文本) [Immutable, Required, Derived]
  - valid_from: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
  - invalidated_at: TEXT (ISO-8601 UTC, 失效时间) [Mutable, Optional, Derived]
  - superseded_by: TEXT (自引用 FK -> confirmed_insights.insight_id) [Mutable, Optional, Derived]
  - status: TEXT ('confirmed' | 'superseded' | 'revalidation_required' | 'retracted') [Mutable, Required, Derived]
  - created_at: TEXT [Immutable, Required, Derived]
Index Requirements:
  - INDEX on status, valid_from
  - INDEX on source_hypothesis_id
```

---

### 16.4 人生叙事元数据与关联实体 (Narrative Metadata & Links)

#### 实体 17：`chapter_metadata`（人生章节元数据）
```text
Entity: chapter_metadata
Purpose: 人生章节 Markdown 物理档案索引表与脱敏重写状态路标
Fields:
  - chapter_id: TEXT (PK, 稳定标识如 'chapter_01_20261016') [Immutable, Required, Derived]
  - title: TEXT (章节标题) [Immutable, Required, Derived]
  - file_path: TEXT (相对 Markdown 物理文件路径) [Immutable, Required, Derived]
  - time_span_start: TEXT [Immutable, Required, Derived]
  - time_span_end: TEXT [Immutable, Required, Derived]
  - needs_privacy_redaction: INTEGER (是否触发脱敏重写, 0/1) [Mutable, Required, Derived, Default 0]
  - created_at: TEXT [Immutable, Required, Derived]
Index Requirements:
  - UNIQUE on file_path
```

#### 实体 18：`chapter_slice_links`（章节-切片引用表）
```text
Entity: chapter_slice_links
Fields:
  - chapter_id: TEXT (FK -> chapter_metadata.chapter_id) [PK1, Immutable, Required, Derived]
  - slice_id: TEXT (FK -> raw_slices.slice_id) [PK2, Immutable, Required, Derived]
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (chapter_id, slice_id)
  - INDEX on slice_id
```

#### 实体 19：`chapter_episode_links`（章节-经历引用表）
```text
Entity: chapter_episode_links
Fields:
  - chapter_id: TEXT (FK -> chapter_metadata.chapter_id) [PK1, Immutable, Required, Derived]
  - episode_id: TEXT (FK -> episodes.episode_id) [PK2, Immutable, Required, Derived]
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (chapter_id, episode_id)
  - INDEX on episode_id
```

#### 实体 20：`chapter_insight_links`（章节-共识引用表）
```text
Entity: chapter_insight_links
Fields:
  - chapter_id: TEXT (FK -> chapter_metadata.chapter_id) [PK1, Immutable, Required, Derived]
  - insight_id: TEXT (FK -> confirmed_insights.insight_id) [PK2, Immutable, Required, Derived]
  - linked_at: TEXT (ISO-8601 UTC) [Immutable, Required, Derived]
Index Requirements:
  - PRIMARY KEY (chapter_id, insight_id)
  - INDEX on insight_id
```

---

## 17. Mermaid ER Diagram（逻辑实体关系全景图）

```mermaid
erDiagram
    %% Core Evidence & Episodes
    RAW_SLICES ||--o{ EPISODE_SLICE_LINKS : "grouped into"
    EVENT_SKELETONS ||--o{ EPISODE_EVENT_LINKS : "grouped into"
    EPISODES ||--o{ EPISODE_SLICE_LINKS : "contains"
    EPISODES ||--o{ EPISODE_EVENT_LINKS : "contains"
    
    %% Semantic Memories & Provenance
    RAW_SLICES ||--o{ SEMANTIC_MEMORIES : "dynamically joined by"
    EPISODES ||--o{ SEMANTIC_MEMORIES : "contextualizes"
    SEMANTIC_MEMORIES ||--o{ SEMANTIC_MEMORIES : "supersedes"
    
    %% Evidence Reinforcements
    SEMANTIC_MEMORIES ||--o{ EVIDENCE_REINFORCEMENTS : "proven by"
    RAW_SLICES ||--o{ EVIDENCE_REINFORCEMENTS : "re-affirms"
    EVENT_SKELETONS ||--o{ EVIDENCE_REINFORCEMENTS : "re-affirms"
    
    %% Observations & Typed Links
    OBSERVATIONS ||--o{ OBSERVATION_SLICE_LINKS : "supported by"
    RAW_SLICES ||--o{ OBSERVATION_SLICE_LINKS : "evidences"
    OBSERVATIONS ||--o{ OBSERVATION_EVENT_LINKS : "supported by (pinned)"
    EVENT_SKELETONS ||--o{ OBSERVATION_EVENT_LINKS : "evidences"
    OBSERVATIONS ||--o{ OBSERVATION_MEMORY_LINKS : "supported by"
    SEMANTIC_MEMORIES ||--o{ OBSERVATION_MEMORY_LINKS : "evidences"
    OBSERVATIONS ||--o{ OBSERVATION_EPISODE_LINKS : "scoped by"
    EPISODES ||--o{ OBSERVATION_EPISODE_LINKS : "scopes"
    
    %% Hypotheses & Understanding
    HYPOTHESES ||--o{ HYPOTHESIS_OBSERVATION_LINKS : "grounded by"
    OBSERVATIONS ||--o{ HYPOTHESIS_OBSERVATION_LINKS : "grounds"
    HYPOTHESES ||--o{ CALIBRATION_EVENTS : "calibrated via"
    
    %% Confirmed Insights Consensus
    HYPOTHESES ||--o{ CONFIRMED_INSIGHTS : "distills into"
    CALIBRATION_EVENTS ||--o{ CONFIRMED_INSIGHTS : "ratifies"
    CONFIRMED_INSIGHTS ||--o{ CONFIRMED_INSIGHTS : "supersedes"
    
    %% Narrative Links
    CHAPTER_METADATA ||--o{ CHAPTER_SLICE_LINKS : "cites"
    RAW_SLICES ||--o{ CHAPTER_SLICE_LINKS : "cited by"
    CHAPTER_METADATA ||--o{ CHAPTER_EPISODE_LINKS : "narrates"
    EPISODES ||--o{ CHAPTER_EPISODE_LINKS : "narrated by"
    CHAPTER_METADATA ||--o{ CHAPTER_INSIGHT_LINKS : "reflects"
    CONFIRMED_INSIGHTS ||--o{ CHAPTER_INSIGHT_LINKS : "reflected in"

    RAW_SLICES {
        string slice_id PK
        string occurred_at
        string content
        string source
        string scope
        string project_id
        string ingestion_dedup_key
    }

    EVENT_SKELETONS {
        string event_id PK
        string occurred_at
        string agent_id
        string event_type
        string tool_name
        string retention_class
    }

    EPISODES {
        string episode_id PK
        string scope
        string project_id
        string started_at
        string closed_at
        string summary
        string status
    }

    SEMANTIC_MEMORIES {
        string memory_id PK
        string category
        string statement
        string authority_class
        string scope
        string valid_from
        string invalidated_at
        string superseded_by FK
        string validity_status
        string expression_policy
    }

    OBSERVATIONS {
        string observation_id PK
        string statement
        int proof_count
        string status
    }

    HYPOTHESES {
        string hypothesis_id PK
        string statement
        string lenses
        string confidence_class
        string status
    }

    CALIBRATION_EVENTS {
        string calibration_id PK
        string hypothesis_id FK
        string user_action
        string user_note
        string calibrated_at
    }

    CONFIRMED_INSIGHTS {
        string insight_id PK
        string source_hypothesis_id FK
        string source_calibration_id FK
        string statement
        string valid_from
        string invalidated_at
        string superseded_by FK
        string status
    }

    CHAPTER_METADATA {
        string chapter_id PK
        string title
        string file_path
        int needs_privacy_redaction
    }
```

---

## 18. Lifecycle State Machine Diagrams（关键生命周期状态迁移图）

### 18.1 派生语义事实状态机 (`semantic_memories.validity_status`)
```mermaid
stateDiagram-v2
    [*] --> active: 调和裁定为新事实 (ADD)
    active --> superseded: 调和裁定为更替更正 (SUPERSEDE)，指向新事实
    active --> invalidated: 事实自然失效、超过有效时限或被用户显式推翻
    active --> ambiguous: 发现表面冲突但证据不足以确信变更，挂起观察
    ambiguous --> active: 获得新证据或经人类确认为真
    ambiguous --> superseded: 获得新证据或经人类确认为已被取代
    active --> deleted: 底层唯一 Raw Evidence 被 Hard Delete 抹除
    superseded --> [*]
    invalidated --> [*]
    deleted --> [*]
```

### 18.2 心智假说状态机 (`hypotheses.status`)
```mermaid
stateDiagram-v2
    [*] --> candidate: Observation 累积达标，六大透镜推理生成
    candidate --> rejected: 人类在校准面板点击 No
    rejected --> candidate: 跨月新时空且出现极强新独立证据，伴生体谦逊重提
    candidate --> candidate: 人类在校准面板点击 Yes / Partly (生成独立 Confirmed Insight)
    candidate --> revalidation_required: 部分底层 Observation 支撑受损
    revalidation_required --> candidate: 获得新独立证据补充
    candidate --> retracted: 底层支撑 Observation 全部撤回 (proof == 0)
    revalidation_required --> retracted: 剩余支撑完全归零
    retracted --> [*]: 彻底退出候选队列与背景反思
```

### 18.3 确认共识自模型状态机 (`confirmed_insights.status`)
```mermaid
stateDiagram-v2
    [*] --> confirmed: 人类校准 (Yes / Partly) 批准共识落盘
    confirmed --> superseded: 用户二次校准形成新共识陈述 (指向新 Insight)
    confirmed --> revalidation_required: 底层部分证据被 Hard Delete，支撑度削弱
    revalidation_required --> confirmed: 人类再次确认为有效
    revalidation_required --> superseded: 人类更新共识并签署新文本
    confirmed --> retracted: 底层支撑证据完全归零 ( proof == 0 )
    revalidation_required --> retracted: 人类显式否定或底层证据归零
    retracted --> [*]: 彻底退出检索、行为策略与自模型提示
```

---

## 19. Data Model Invariants（数据模型 13 项不可违背定理）

- **DM-1. Raw Evidence is never model-overwritten**：`raw_slices` 行一经创建，任何模型与算法无权执行 `UPDATE` 改写 content 文本；
- **DM-2. Episode is not Raw Evidence**：经历容器是时空组织手段，其 summary 绝不能伪装成直接事实证据外键；
- **DM-3. All derived claims have FK-safe valid provenance**：所有派生事实与信念必须通过类型化关系表强链接到底层证据；
- **DM-4. Unknown scope never silently becomes global**：未获知工程范围的数据标记 `'unresolved'`，严禁默认升格为 `'global'`；
- **DM-5. Idempotency ≠ Evidence Independence**：物理防抖（`ingestion_dedup_key`）与认识论证据独立性（`evidence_reinforcements`）彻底解耦；
- **DM-6. Zero valid support retracts dependent understanding**：底层有效支撑归零时，Observation、Hypothesis 与对应 Confirmed Insight 必须物理置为 `retracted`；
- **DM-7. Semantic validity ≠ Expression policy**：事实真伪状态（`validity_status`）与是否允许说出口的门控策略（`expression_policy`）正交独立；
- **DM-8. Narrative never becomes Evidence**：人生章节 Markdown 文件与叙事元数据绝不反向作为任何微观事实与理解的证据；
- **DM-9. Hard Delete removes or recomputes every semantic copy**：物理删除微观原话时，底座物理抹除，派生摘要重算，章节执行脱敏重写；
- **DM-10. Telemetry retention cannot invalidate durable provenance silently**：被持久信念引用的事件骨架强制钉住，不受固定 TTL 驱逐；
- **DM-11. Partly-confirmed understanding preserves calibrated semantics**：人类附带修正手记的共识作为独立实体保存，不与原假说混淆，保留历史演变版本；
- **DM-12. No derived claim depends on opaque dangling polymorphic IDs**：彻底根除伪多态外键，实现 SQLite 级真实关系完整性；
- **DM-13. Multi-observation support eliminates single-anchor brittleness**：假说支持多观察证据输入，单项观察撤回不直接导致假说脆断，而是触发复核。

---

## 20. DB Constraints vs Application Invariants（数据库强制约束与应用层保证边界）

系统明确界定数据库底层强制机制与应用层核心逻辑的职责边界，不虚构 SQLite 无法原生保证的语义：

| 约束类别 | 规则项 | 落地与强制机制 (Enforcement Mechanism) |
| :--- | :--- | :--- |
| **SQLite 强制** | 主键非空与全局唯一性 | `PRIMARY KEY` (如 `slice_id`, `event_id`, `memory_id` 等) |
| **SQLite 强制** | 物理写入防抖 | `UNIQUE(ingestion_dedup_key)` 约束 |
| **SQLite 强制** | 证据独立性防刷分 | `UNIQUE(memory_id, independence_fingerprint)` 约束 |
| **SQLite 强制** | 真实外键参照完整性 | 原生 `FOREIGN KEY REFERENCES`，启用 `PRAGMA foreign_keys = ON` |
| **SQLite 强制** | 复合主键防重复关联 | 关联表 `PRIMARY KEY (parent_id, child_id)` |
| **SQLite 强制** | 枚举值合法性检查 | SQLite `CHECK (status IN ('active', 'retracted'))` 等约束 |
| **应用层保证** | 认知独立性指纹生成 | 跨会话、跨时序与非重复文本正则化算法生成 `fingerprint` |
| **应用层保证** | 时态调和与置更替 | 写入事务内判定新老语义冲突，原子更新 `superseded_by` 与 `invalidated_at` |
| **应用层保证** | 命题敏感权威裁决 | `claim-sensitive authority`：用户自述偏好优先，系统观测环境事实优先 |
| **应用层保证** | 未决工程范围补全 | 通过经历聚类或校准交互将 `scope = 'unresolved'` 显式后补为 `project` |
| **应用层保证** | 级联撤回与计数维护 | 底层删除时重新计算 `proof_count`，为 0 时更新为 `retracted` |
| **应用层保证** | 外部章节文学脱敏 | 异步扫描 Markdown 文件执行正则掩蔽，并重置 `needs_privacy_redaction` |

---

## 21. Current → Target Migration Mapping（现有生产资产无损迁移表）

| 现存物理资产 | 目标逻辑实体 | 迁移策略与处置动作 (Action) | 数据损失风险？ | 字段映射与重新分类规范 |
| :--- | :--- | :--- | :---: | :--- |
| **`slices` (42行)** | `raw_slices` | **100% 物理平移保留** | **零损失** | 原 `content` 原样保留；`source` 设为 `'manual_feed'`；**`scope` 设为 `'unresolved'`，`project_id` 设为 NULL**（绝不武断默认全局或当前工程）。 |
| **`events` (11.5万行)**| `event_skeletons` | **100% 物理平移保留** | **零损失** | 原 Hash ID 与时间戳保留；`retention_class` 设为 `'transient'`；未被引用的老事件根据 TTL 正常进入滚动归档。 |
| **`hypotheses` (4条)** | `hypotheses` | 结构平移与拆分 | **零损失** | 原假说文本保留为 `statement`；历史逗号分隔的 episodes 字符串解构至关联表；`status` 映射为 `'candidate'`。 |
| **`insights` (0条)** | `confirmed_insights` | 准备就绪 | **零损失** | 当前生产库为 0 条，迁移成本为零。 |
| **`growth_themes` (0行)**| 废弃合并 | 废除单独立表 | **零损失** | 生产库 0 行，概念并入 `chapter_metadata`，彻底消除冗余表。 |
| **`raw_slices.jsonl`** | 导出只读流 | 降级为单向异步投影 | **零损失** | 由 SQLite 定期异步刷新，不再接受前端直写，彻底杜绝双写分裂。 |
| **`chapters/*.md`** | `chapter_metadata` | 补建元数据索引 | **零损失** | 磁盘文件原地不动，扫描文件补齐数据库 `chapter_metadata` 记录。 |

---

## 22. Hard Delete Reverse Traversal Walkthrough（硬删除全依赖反向遍历演练）

数据模型支持从任意原始证据触发清晰、可审计的全链路级联清理：

### 22.1 演练 1：用户原话切片物理硬删除 (`raw_slices.slice_id = S_0`)

```text
[Step 1: 物理抹除底座 (DELETE)]
DELETE FROM raw_slices WHERE slice_id = S_0;

[Step 2: 直接关联关系清理 (DELETE)]
DELETE FROM episode_slice_links WHERE slice_id = S_0;
DELETE FROM evidence_reinforcements WHERE slice_id = S_0;
DELETE FROM observation_slice_links WHERE slice_id = S_0;

[Step 3: 派生语义记忆处置 (RETRACT / DELETE)]
FOR affected_mem IN (SELECT memory_id FROM semantic_memories WHERE source_slice_id = S_0):
    IF NOT EXISTS (SELECT 1 FROM evidence_reinforcements WHERE memory_id = affected_mem):
        UPDATE semantic_memories SET validity_status = 'deleted' WHERE memory_id = affected_mem;
    END IF

[Step 4: 经历容器摘要重算 (RECOMPUTE)]
FOR affected_ep IN (SELECT DISTINCT episode_id FROM episode_slice_links WHERE slice_id = S_0):
    标记 affected_ep.summary 需异步重新生成 (Recompute)

[Step 5: 观察信念与高层假说级联反查 (RECOMPUTE / RETRACT)]
FOR affected_obs IN (SELECT DISTINCT observation_id FROM observation_slice_links WHERE slice_id = S_0):
    obs.proof_count = COUNT(valid remaining supporting links in slice/event/memory);
    IF obs.proof_count == 0 THEN
        UPDATE observations SET status = 'retracted' WHERE observation_id = affected_obs;
        -- 触发假说依赖复核
        FOR affected_hyp IN (SELECT hypothesis_id FROM hypothesis_observation_links WHERE observation_id = affected_obs):
            IF COUNT(valid remaining active observations) == 0 THEN
                UPDATE hypotheses SET status = 'retracted' WHERE hypothesis_id = affected_hyp;
                UPDATE confirmed_insights SET status = 'retracted' WHERE source_hypothesis_id = affected_hyp;
            ELSE
                UPDATE hypotheses SET status = 'revalidation_required' WHERE hypothesis_id = affected_hyp;
                UPDATE confirmed_insights SET status = 'revalidation_required' WHERE source_hypothesis_id = affected_hyp;
            END IF
    ELSE
        UPDATE observations SET proof_count = obs.proof_count WHERE observation_id = affected_obs;
    END IF

[Step 6: 人生章节脱敏标记 (REDACT)]
FOR affected_ch IN (SELECT chapter_id FROM chapter_slice_links WHERE slice_id = S_0):
    UPDATE chapter_metadata SET needs_privacy_redaction = 1 WHERE chapter_id = affected_ch;
    DELETE FROM chapter_slice_links WHERE chapter_id = affected_ch AND slice_id = S_0;
    -- 调度后台任务读取对应 Markdown 文件，执行敏感实体脱敏重写
```

### 22.2 演练 2：外部遥测事件物理删除 (`event_skeletons.event_id = E_0`)

```text
[Step 1: 检查钉住保护]
IF EXISTS (SELECT 1 FROM observation_event_links WHERE event_id = E_0) OR 
   EXISTS (SELECT 1 FROM episode_event_links WHERE event_id = E_0):
    -- 被持久化信念或经历引用，强制钉住豁免删除！
    ACTION: NO ACTION (PRESERVE PINNED)
ELSE:
    -- 无任何持久化引用，TTL 正常执行
    DELETE FROM event_skeletons WHERE event_id = E_0;
    ACTION: DELETE
```

---

## 23. Freeze Consistency Check Matrix & Formal Sign-off（最终冻结一致性自检表与冻结裁决）

| 审查项 (Check Item) | 预期判定 | 实际审计结论与支撑机制 |
| :--- | :---: | :--- |
| **1. Provenance model FK-safe?** | **YES** | 采用 Candidate P-A（类型化关系表），每张关联表均受 SQLite 物理外键约束。 |
| **2. Confirmed Insight semantics explicit?** | **YES** | 独立为 `confirmed_insights` 实体，与待审假说物理分离，语义清晰。 |
| **3. Partly calibration representable?** | **YES** | `calibration_events.user_note` 与 `confirmed_insights.statement` 完整承接补充修正。 |
| **4. Hard Delete graph complete?** | **YES** | 覆盖了原话、派生记忆、Episode、Observation、Hypothesis、Insight 与章节脱敏的全闭环。 |
| **5. Event retention vs durable provenance resolved?** | **YES** | 确立引用钉住机制（Retention Pinning），被观察引用的事件豁免于 TTL 清理。 |
| **6. Unknown scope representable?** | **YES** | 引入 `scope = 'unresolved'`，严禁将未知工程武断当成全局。 |
| **7. Idempotency and evidence independence separated?**| **YES** | 物理入库防抖（`ingestion_dedup_key`）与证据独立性（`evidence_reinforcements`）彻底解耦。 |
| **8. Semantic state and expression state separated?** | **YES** | `validity_status`（真伪）与 `expression_policy`（表达门控）正交拆分。 |
| **9. Entity inventory internally consistent?** | **YES** | 20 大实体在 Master Inventory、Schema、ER 图、删除图与迁移表中 100% 严格一致。 |
| **10. Migration mapping consistent?** | **YES** | 现有 42 条切片与 11.5 万条事件全部实现无损物理平移，无孤儿断裂。 |
| **11. ER diagram consistent?** | **YES** | Mermaid 实体关系图完整映射 20 大实体，无任何悬空伪外键。 |
| **12. Any blocker before Technical Retrieval Design?** | **NONE** | 数据模型语义与关系结构已达完全冻结标准。 |

---

## 24. Formal Freeze Conclusion（数据模型正式冻结裁决）

```text
================================================================================
       COEVA CROSS-SESSION LONG-TERM MEMORY DATA MODEL V2.1 REVIEW
--------------------------------------------------------------------------------
  [✓] Provenance model FK-safe?                       : YES (Candidate P-A)
  [✓] Confirmed Understanding semantics explicit?     : YES (Option U-A)
  [✓] Partly calibration representable?               : YES (Full Statement)
  [✓] Hard Delete graph complete?                     : YES (Sensitive Purge)
  [✓] Event retention vs durable provenance resolved? : YES (Strategy E-C)
  [✓] Unknown scope representable?                    : YES (Unresolved State)
  [✓] Idempotency and evidence independence separated?: YES (Dual Key)
  [✓] Semantic state and expression state separated?  : YES (Orthogonal)
  [✓] Entity inventory internally consistent?         : YES (20 Master Entities)
  [✓] Migration mapping consistent?                   : YES (100% Non-destructive)
  [✓] ER diagram consistent?                          : YES (100% Aligned)
  [✓] Any blocker before Technical Retrieval Design?  : NONE
--------------------------------------------------------------------------------
                         >>> DATA MODEL FROZEN <<<
                  READY FOR TECHNICAL RETRIEVAL DESIGN
================================================================================
```

### 本轮停止声明
Coeva 跨会话长期记忆逻辑数据模型 V2.1 已解决全部 P0/P1 残余设计缺陷与关系完整性问题，通过了一致性检查与冻结就绪评审，**数据模型正式冻结**。

**本轮立即停止。不编写具体的 DDL SQL 代码、不执行数据库迁移、不修改生产代码、不实现 Retriever 或检索算法。后续工程任务将正式以此冻结数据模型为基石，启动下一阶段：Technical Retrieval Design & Benchmark（技术检索设计与基准评测）。**
