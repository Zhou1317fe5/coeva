# Co-evolving Companion：跨会话长期记忆 V2.1 记忆巩固与调和技术设计规范 (Consolidation & Reconciliation Technical Design · Final Freeze Edition)
## ——两阶段提议校验、增量感知回音壁防护、Fail-Closed 调和边界与双轨基准评测架构

> **规范状态与元数据**：
> - **阶段定位**：Consolidation & Reconciliation Technical Specification (Final Freeze Patch Edition)
> - **文档状态**：`Consolidation Technical Design Revision: v2.1 (Frozen — Final Specification Sign-off)`
> - **上位冻结规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
>   - `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
> - **三大实施不变量约束**：
>   - **IMPL-1**：Episode Membership ≠ Durable Retention Pin（经历成员不等于持久保留钉住）；
>   - **IMPL-2**：Semantic Memory Must Have FK-Safe Multi-Source Provenance（派生记忆必须具备多源强外键溯源）；
>   - **IMPL-3**：Privacy Redaction Pending = Not Readable（待脱敏制品立即可读阻断）。
> - **技术检索技术口径约束**：
>   - **RET-EVIDENCE-1**：当前 V2.1 正式检索架构为 FTS5 词法 + 表层相似度（Surface Similarity），不强制引入深度 Dense Embedding；
>   - **RET-EVIDENCE-2**：检索层严格保持读写分离，本巩固设计不修改检索逻辑，专注于将客观证据安全转化为派生记忆。

---

## 1. Executive Summary（执行摘要）

在 Coeva 伴生体系中，记忆巩固（Consolidation）与调和（Reconciliation）回答的是：
> **“发生过的原始证据（Raw Evidence）如何被安全、准确、可逆地转化为值得长期留存的派生记忆（Derived Semantic Memory / Observation），并在冲突、重复、演化、否定、删除与不确定情况下保持坚实闭环。”**

本技术规范基于 **DEV 调优集 (20用例)** 与 **独立 HOLDOUT 验证集 (15用例)** 的双轨自动化基准评测，确立了 **两阶段混合巩固架构（Design C: Two-Phase Hybrid Architecture）**：
1. **Phase 1 (只读提议阶段 · LLM-assisted)**：大模型仅扮演只读分析器角色，遵循严格的结构化 JSON Schema 提炼语义候选主张（Candidate Claims）并建议调和动作意向；
2. **Phase 2 (确定性校验阶段 · Deterministic Validator)**：本地代码在写入数据库前，强制执行包含物理幂等防抖键、增量感知型回音壁剥离、作用域安全守卫（未知工程强制 `unresolved`）、强类型外键存在性、时态双时间戳约束以及独立性指纹计算的 **6 重确定性物理校验**；
3. **Fail-Closed 核心安全定理**：
   > **When uncertain between SUPERSEDE and AMBIGUOUS: prefer AMBIGUOUS.**
   > **Destructive semantic mutation must fail closed.**
   > （当在更替与歧义之间存在不确定性时，强制裁决为 AMBIGUOUS；破坏性语义更替必须安全闭锁，宁可挂起冲突，绝不草率覆盖。）
4. **单事务原子提交（Atomic ACID Commit Boundary）**：校验完全通过后，在单一原子 SQLite 事务边界内执行数据落盘，绝无半更替或孤儿状态。

**评测成绩与证据分级（Evidence Grading）**：
- **DEV Set (20用例 · MEASURED)**：准入准确率 100.0%，调和动作准确率 100.0%，支撑计数准确率 100.0%，综合通过率 **100.0%**；**False ADD = 0**，**False SUPERSEDE = 0**，**False REINFORCE = 0**。
- **HOLDOUT Set (15用例 · MEASURED)**：准入准确率 100.0%，调和动作准确率 100.0%，支撑计数准确率 100.0%，综合通过率 **100.0%**；**False ADD = 0**，**False SUPERSEDE = 0**，**False REINFORCE = 0**。
- **安全不变量断言矩阵 (S-01 ~ S-14 · MEASURED)**：**14 / 14 达成 100.0% PASS**。
- **性能测量口径分级**：确定性校验器耗时为 **0.02 ~ 0.03 ms (MEASURED)**；LLM 提议层为后台异步非关键路径，具体模型/Token/时延基准归属于实施期模型选型（**NOT MEASURED**）。

---

## 2. Frozen Inputs（冻结规范输入与承接约束）

本设计原样输入并严格承接三大冻结规范的最高意志：

| 上位冻结输入源 | 核心约束定理 | 本巩固与调和设计落地方式 |
| :--- | :--- | :--- |
| **Architecture V2.1** | **INV-1. Evidence ≠ Interpretation** | `raw_slices` 与 `event_skeletons` 保持物理只读，Consolidator 绝不修改原始证据明文。 |
| **Architecture V2.1** | **INV-2. Past Truth ≠ Current Truth** | 更替事实通过 `superseded` 与 `invalidated_at` 表达，禁止物理覆盖历史版本。 |
| **Architecture V2.1** | **INV-5. User Voice > Telemetry Inference** | 实行 Claim-sensitive Authority，用户主观自我陈述优先级绝对压倒遥测推断。 |
| **Architecture V2.1** | **INV-6. Candidate ≠ Confirmed** | 待审假说（`hypotheses`）绝不允许因证据多而自动升级，必须经人类校准后生成 `confirmed_insights`。 |
| **Architecture V2.1** | **INV-10. Memory Must Not Echo** | 伴生体复述历史的提问必须携带 Feedback 隔离围栏，存盘时剥离，阻断自强化死循环。 |
| **Data Model V2.1** | **Candidate P-A 类型化关系表** | 派生记忆通过专属强类型中间表与底层证据绑定，实现 SQLite 级原生外键保护。 |
| **Data Model V2.1** | **三态范围模型 ('global'/'project'/'unresolved')** | 范围无法可靠判断时强制赋予 `unresolved`，严禁未经证实默认升级为 `global`。 |

---

## 3. Current Write-Path Audit（当前生产写入链路事实审计）

基于真实代码审计（`src/body/window.py`、`src/memory/store.py`、`src/feeder/storage.py`、`src/core/patterns.py`、`src/core/hypotheses.py`、`src/core/self_model.py`、`src/core/chapters.py`）：

| 组件 / 写入链路 | 输入 | 当前输出 | 写入位置 | 语义角色 | 存在的核心缺陷 (Problems) | 处置决议 |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: |
| **Feeder 随手投喂** (`storage.py`) | 用户悬浮框输入 | `RawSlice` 记录 | `raw_slices.jsonl` + SQLite `slices` | 原始用户输入 | **无任何准入门禁**；双写冗余；无作用域与防抖机制。 | **重构** 接入统一准入与防抖管道 |
| **气泡用户回复** (`window.py`) | 用户回复气泡 | `RawSlice` 记录 | `raw_slices.jsonl` + SQLite `slices` | 交互用户原话 | 包含问候、附和（“嗯嗯”），100% 直通存盘导致垃圾数据膨胀。 | **重构** 增设上下文关联与准入过滤 |
| **遥测事件入库** (`LocalEventBus`) | Agent 工具日志 | `EventRecord` | SQLite `events` (11.6万行) | 客观行为流水 | 全量接收，虽受 30 天 TTL 管辖但与切片完全脱节。 | **保留**，确立钉住豁免联动机制 |
| **`PatternBuilder`** (`patterns.py`) | `episodes` 列表 | `BehavioralPattern` | 纯内存计算 | 客观行为模式 | 纯规则硬编码计数，未与用户切片语义关联，缺乏泛化。 | **重构** 为 Observation 聚合引擎 |
| **`HypothesisEngine`** (`hypotheses.py`)| 行为模式对象 | `DevelopmentHypothesis` | 写入 SQLite `hypotheses` | 候选心智推断 | **存在过早推断缺陷**：从工具超时统计直接跃迁为心理画像。 | **严管门禁**：仅从充分 Observation 慢速生成 |
| **`SelfModelManager`** (`self_model.py`)| 人类校准动作 | 更新假说 / 生成共识 | SQLite `hypotheses` / `insights` | 人机共识自模型 | `Partly` 时仅把手记追加在字符串尾部，实体未解耦。 | **升级** 为独立的 `confirmed_insights` 落盘 |
| **`ChapterGenerator`** (`chapters.py`) | 模式、共识与会话 | Markdown 章节正文 | `chapters/*.md` | 人生纪实叙事 | 直接读取未经调和的原始片段，敏感删除时无法确定性脱敏。 | **解耦**：章节引用仅做叙事，不反向为凭 |

---

## 4. Responsibility Boundary（五大认知阶段责任边界划分）

系统在认知生命周期中严格恪守阶段分立定理：

```text
Raw Evidence (客观原话底座)
     │
     ▼
[1. Admission (准入门禁)] ─────────── 仅回答：“这段输入是否具备长期语义留存价值？” (非理解)
     │
     ▼
[2. Candidate Extraction] ────────── 仅回答：“输入中包含了哪些原子语义主张？” (非持久化)
     │
     ▼
[3. Reconciliation (语义调和)] ────── 仅回答：“新主张与已有记忆是什么关系？” (ADD/SUPERSEDE/REINFORCE/AMBIGUOUS/NOOP)
     │
     ▼
[4. Observation Formation] ───────── 仅回答：“跨经历聚合出了哪些客观行为信念？” (带正反独立证据)
     │
     ▼
[5. Self Model Hypothesis] ───────── 仅回答：“这些信念在心理透镜下可能意味着什么？” (待校准假说)
     │
     ▼
[6. Human Calibration] ───────────── 仅回答：“人类是否认可该理解？” (批准生成 Confirmed Insight)
     │
     ▼
[7. Narrative (人生章节)] ────────── 仅回答：“时间沉淀后如何共同回看？” (文学留白，绝不反向成为证据)
```

---

## 5. Admission Design（长期记忆准入门禁设计）

准入门禁（Admission）在数据接收的第一时间运行，其核心职责是**拦截低熵噪音，避免数据库无意义膨胀**：

### 5.1 准入决议三态（Admission Decision）
- **`ADMIT` (准入)**：输入包含可泛化的事实、稳定偏好、相处硬规则、长期目标或深刻个人经历，放行进入候选抽取；
- **`NOOP_LONG_TERM` (长期忽略)**：输入属于问候、打卡、空洞附和、纯操作碎语或瞬时日常日程，只留存瞬时 Working Context，绝不启动长期语义抽取；
- **`DEFER` (暂缓判定)**：短句语义高度依赖前文会话上下文，暂存至会话缓冲区等待聚合。

### 5.2 准入裁定矩阵与典型用例

| 输入文本范例 | 判定结果 | 决策理由与认识论原则 |
| :--- | :---: | :--- |
| “hi”、“你好”、“测试气泡”、“嗯嗯好的” | **`NOOP_LONG_TERM`** | 低熵礼貌用语与 UI 测试，无任何持久语义价值 |
| “先去吃个午饭，半小时后回来” | **`NOOP_LONG_TERM`** | 纯瞬时日常状态，随交互结束自然失效 |
| “小时候其实挺喜欢画画的” | **`ADMIT`** | 虽发生于闲聊，但包含自传体童年经历（Durable Semantic Value） |
| “我发现自己最近总是在晚上才真正进入状态” | **`ADMIT`** | 包含用户作息与心力节律的自我观察 |
| “以后我专注写代码时，千万别弹窗提醒我喝水” | **`ADMIT`** | 用户显式设立的相处硬边界，高优先级准入 |
| 外部 Connector 重连重放的事件骨架 | **`NOOP_LONG_TERM`** | 传输重试，物理层防抖拦截 |

---

## 6. Candidate Extraction Design（候选语义主张抽取设计）

只有通过 `ADMIT` 准入的证据，才允许启动候选抽取。

### 6.1 抽取多重性定理（Multiplicity Principle）
- 1 条 Raw Evidence 输入，经过抽取后可以生成 **0 个、1 个或 N 个** 独立的候选主张（Candidate Claims）；
- **零输出合法性（INV-4）**：例如用户输入“*今天写代码感觉心力特别交瘁，完全不想动了*”，作为负面心境表达，准入通过后抽取器判定其仅属于心境证据，**输出空列表 `[]`**，严禁擅自归纳出“*用户容易烦躁*”这种标签化伪事实（S-01 断言通过）。

### 6.2 候选主张逻辑契约（CandidateClaim Schema）
```python
@dataclass(frozen=True)
class CandidateClaim:
    statement: str                           # 规范化的原子陈述明文
    category: str                            # 'fact' | 'preference' | 'goal' | 'relationship_rule'
    scope: str                               # 'global' | 'project' | 'unresolved'
    project_id: str | None                   # 归属工程 ID
    authority_class: str                     # 'user_asserted' | 'system_observed'
    source_slice_id: str                     # 来源切片 ID (强外键溯源)
    confidence_class: str                    # 'tentative' | 'grounded'
    temporal_anchor: str                     # 发生的基准时间 ISO-8601
```

---

## 7. Claim Normalization（语义主张规范化标准）

规范化阶段对候选文本进行语法清洗与实体对齐，但恪守**保真不变量**：
1. **语法压缩与去口语化**：去除冗余语气助词（“那个”、“就是说”），提取主谓宾清晰的标准原子事实陈述；
2. **严禁篡改主观语气强度**：
   - 用户说：“*我可能比较偏好浅色一点*” -> 规范化文本必须保留“*倾向/可能*”，置信度标为 `tentative`；
   - 严禁擅自拔高为笃定句式：“*用户绝对只喜欢浅色主题*”；
3. **技术实体符号精准对齐**：对齐大小写（`pyside6` -> `PySide6`, `fastapi` -> `FastAPI`），保持符号保真。

---

## 8. Reconciliation Lookup（调和前置检索隔离）

在决定如何处置新 Candidate 之前，必须执行**调和检索（Reconciliation Lookup）**：
- **职责物理隔离**：
  - **日常检索（Daily Retrieval）**：面向用户实时提问，输出候选给 Recall Gate；
  - **调和检索（Reconciliation Lookup）**：面向待入库 Candidate，从数据库已生效记忆中搜寻可能存在的**语义等价项、冲突项或父级项**；
- 采用已冻结的 FTS5 + 表层相似度通道，在相同工程作用域与全局作用域内执行 Top-5 近邻检索。

---

## 9. Reconciliation Action: ADD（新增事实机制）

- **定义**：当 Candidate 经检索比对后，数据库中不存在语义重叠或冲突的既有有效事实，且该事实具备持久价值时，裁定为 `ADD`。
- **状态流转**：
  - 向 `semantic_memories` 插入全新记录；
  - `validity_status = 'active'`，`valid_from = occurred_at`，`invalidated_at = NULL`；
  - 建立指向底层证据的强外键关联记录；
  - 记录初始独立支撑计数 `proof_count = 1`。

---

## 10. Reconciliation Action: SUPERSEDE & Fail-Closed Boundary（更替置失效与安全闭锁机制）

- **定义**：当新 Candidate 与既有事实描述同一主体，且满足以下**两个硬条件**时方可裁定为 `SUPERSEDE`：
  1. 数据库中**明确存在对应的 active 目标事实**；
  2. 属于用户显式更正、声明全面弃用旧事实或明确偏好变化。
- **Fail-Closed 核心安全定理**：
  > **When uncertain between SUPERSEDE and AMBIGUOUS: prefer AMBIGUOUS.**
  > **Destructive semantic mutation must fail closed.**
  > （若目标事实不存在，绝不执行 SUPERSEDE，安全闭锁为 ADD；若为偶发尝鲜或弱冲突，强制安全闭锁为 AMBIGUOUS，宁可挂起冲突，绝不破坏性更替。）
- **状态流转与时态原子事务（INV-2）**：
  ```text
  [旧事实 Old Memory]                           [新事实 New Memory]
  - id: mem_old                                 - id: mem_new
  - validity_status: 'active' ──► 'superseded'  - validity_status: 'active'
  - invalidated_at: NULL     ──► T_current     - valid_from: T_current
  - superseded_by: NULL      ──► mem_new       - superseded_by: NULL
  ```
- **核心红线**：严禁执行物理 `UPDATE` 直接覆盖旧记录的 statement 文本，必须完整保留历史更迭足迹。

---

## 11. Reconciliation Action: REINFORCE（独立证据印证机制）

- **定义**：当新 Candidate 与既有事实语义完全一致，且来源于新的独立时空或显式再确认时，裁定为 `REINFORCE`。
- **判定与状态流转**：
  - 检索 `evidence_reinforcements` 账本；
  - 若新证据计算出的 `independence_fingerprint` 在该记忆下不存在：
    - 插入新的印证流水行；
    - 原事实的 `proof_count = proof_count + 1`；
    - 重新评估置信度级别（从 `tentative` 升格为 `grounded`）。

---

## 12. Reconciliation Action: AMBIGUOUS（歧义与弱冲突挂起机制）

- **定义**：当新 Candidate 与既有事实存在表面冲突，但新证据并非显式推翻（例如“有时在脚本里用 Tab 也挺方便”、“深灰调其实挺舒服”），证据强度不足以断言推翻旧事实时，裁定为 `AMBIGUOUS`。
- **处置原则**：
  - 保持旧事实有效，同时插入新主张；
  - 将受影响条目的状态标记为 `validity_status = 'ambiguous'`；
  - **严禁大模型擅自选边站队**，挂起等待后续跨经历观察或由人类在校准面板明确决断。

---

## 13. Reconciliation Action: NOOP（忽略与幂等吸收机制）

- **定义**：当输入属于传输重放、物理双击、同一经历内的同义唠叨回音或无持久语义的日常输入时，裁定为 `NOOP`。
- **处置原则**：
  - 数据库记忆面保持完全静止（Zero Mutation）；
  - 不新增语义记忆，不修改有效状态，不递增 `proof_count`。

---

## 14. Independent Evidence Design（认知证据独立性与指纹防刷分算法）

系统将“物理写入幂等”与“认知证据独立性”彻底物理拆分：

### 14.1 认识论独立性多维判据
要判定一条证据是否属于“新的独立证据”，必须满足以下正交条件之一：
1. **时序与经历隔离**：来自完全不同的后续 Episode；
2. **场景语境隔离**：在完全不同的任务会话或工作区中被再次验证；
3. **人类显式再确认**：人类在校准面板点击确认或在输入中显式表明“*经过长期实践再次证明...*”。

### 14.2 独立性指纹生成契约
```text
independence_fingerprint = SHA256(
    canonical_statement_normalized + 
    "|" + episode_id + 
    "|" + source_day_utc
)
```
- **防刷分定理**：同一 Episode、同一天内的多次提及，生成完全相同的指纹，数据库唯一索引 `UNIQUE(memory_id, independence_fingerprint)` 原生拦截重复印证，`proof_count` 绝对保持不变。

---

## 15. Authority & Claim-Sensitive Semantics（命题敏感主权等级体系）

严禁使用“用户权重 1.0、系统权重 0.6”等静态全局浮点数，严格贯彻 **Claim-Sensitive Authority（命题敏感主权）**：

| 命题类型 (Claim Domain) | 最高权威归属 | 次级参考 | 仲裁与调和规则 |
| :--- | :---: | :---: | :--- |
| **主观偏好 / 自我感受 / 意图** | `user_asserted` | `system_observed` | 用户亲口表达具有最高语义解释权。若用户自述与系统推断冲突，用户陈述直接触发 `SUPERSEDE` 覆盖推断。 |
| **客观外部环境 / 外部工具状态** | `system_observed` | `user_asserted` | 测试是否通过、编译器报错、工具超时等物理事实以系统实际遥测为准，用户的主观猜测不能否定客观错误事件。 |
| **自模型共识 (Self Model)** | `user_confirmed` | 待审 `hypotheses` | 必须由人类显式校准批准，未经确认前仅能标为候选。 |

---

## 16. Temporal Reconciliation（时态调和与历史足迹保留）

坚决贯彻 **INV-2. Past Truth ≠ Current Truth**：
- 用户 2025 年习惯 CMD，2026 年全面迁移至 PowerShell 7。
- 调和器将旧 CMD 事实置为 `validity_status = 'superseded', invalidated_at = '2026-10-18T...'`；
- 当发起当前状态查询（“我平时用什么终端？”）时，检索器通过 `validity_status != 'superseded'` 严格过滤，只返回 PowerShell 7；
- 当发起历史追溯查询（“我以前用过什么旧终端？”）时，检索器放行 `superseded` 事实，让思想演化脉络清晰可见。

---

## 17. Scope Reconciliation（工程范围调和与后补规则）

坚决贯彻 **Unknown ≠ Global** 原则：

```text
新事实抽取完成
       │
       ▼
[工程作用域裁决]
├── 1. 输入明确携带活动工程上下文 (如前台为 co-evolving-companion) ──► scope = 'project', project_id = 'co-evolving-companion'
├── 2. 输入语义明确为跨项目通用规则 (如“我写所有代码都用 4 格缩进”)  ──► scope = 'global', project_id = 'global'
└── 3. 悬浮窗全局快捷键投喂且无法可靠探测工程归属 (如“换成 pytest”)   ──► scope = 'unresolved', project_id = NULL
```
- **后补推进规程**：处于 `unresolved` 状态的事实，绝不自动提拔为 `global`。后续当该切片被某次明确工程的 Episode 聚类归纳时，触发范围调和更新为 `project`。

---

## 18. Delta-Aware LLM Echo Guard（增量感知型大模型回音壁防护）

针对大模型复述历史引发回音壁自闭环的风险（INV-10），确立**增量感知型隔离架构**：

```text
[伴生体气泡发言] ──► 注入围栏: <!-- COEVA_ECHO_FENCE: 你之前提到过偏好深色主题 -->
                             │
                             ▼
[用户回复本轮内容]
├── Case E1 (纯附和): “嗯，你说得对。” ──► 剥离前缀后无新语义 ──► 判定为 NOOP_LONG_TERM (拦截成功!)
├── Case E2 (附带新增量): “嗯，不过现在改用浅色主题看久了更舒服。”
│   └── 增量提取器剥离回音部分，提取用户新创增量：“不过现在改用浅色主题看久了更舒服” ──► 正常准入并推进更替！
└── Case E3 (鹦鹉学舌无增量): “对啊，我之前是提到过偏好深色主题。”
    └── 字符重叠率 >= 70% 且无转折对比词 ──► 判定为 NOOP_LONG_TERM (绝不刷分!)
```

---

## 19. Observation Formation & Counter-Evidence（观察信念聚合与反例平衡）

Observation 是介于派生事实与主观假说之间的**跨经历客观信念层**：
1. **聚合准入标准**：
   - 必须横跨至少 2 个以上不同的独立 Episodes；
   - 累积有效独立证据（`proof_count`）达到门限；
   - 支持正例与反例双向追踪（`role: 'supporting' | 'counter'`）；
2. **反例平衡定理（S-02）**：
   - 若观察到 3 次任务先定架构，2 次直接编码试验，Observation 陈述必须表述为：“*在复杂任务中通常倾向先定架构，但在部分实验场景下也会直接编码试验*”；
   - **绝对禁止抹杀反例生成绝对化“总是/全都是/consistently”陈述**。

---

## 20. Hypothesis Formation & Slow-Path Synthesis（候选假说慢速生成机制）

- **慢速生成原则（Very Slow Path）**：假说涉及伴生体对人类深层心智与成长模式的主观推断，**生成频次极低**；
- **单向生成源约束（S-01）**：假说**只能由成熟稳定的 Observation 驱动生成**，单条用户切片绝对禁止直接跳跃推断出心理假说；
- **六大透镜框架映射**：假说必须明确绑定心理灵活性六大透镜标签。

---

## 21. Calibration Boundary & Partly Handling（人类双向校准边界与部分确认落盘）

- **权责分明定理**：Reconciliation 仅负责事实层调和，**绝对无权确认心理假说**；
- **Partly 闭锁（S-04）**：
  ```text
  Hypothesis: “在长链路复杂任务中，用户倾向于完全授权 Agent 自主闭环执行。”
         │
         ▼
  [用户在校准面板点击 Partly 并附加说明]:
  “科研实验代码可以直接自主试，但生产架构改动必须先向我确认。”
         │
         ▼
  [生成独立 Confirmed Insight 实体]:
  - statement: “在长链路复杂任务中，科研实验代码倾向授权 Agent 自主闭环，生产架构改动则要求必须先确认。”
  - status: 'confirmed'
  - 彻底杜绝在原假说字符串后进行暴力拼贴！
  ```
- **被否认假说的可修正性**：
  > **Rejected hypothesis may be cautiously reopened only after sufficiently new, temporally separated, independent evidence.**
  > （被人类点击 No 否决的假说进入冷却状态，但随经历演进且出现充分且具有时间间隔的新独立证据时，伴生体可谦逊重提，不将否决视为永恒判决。）

---

## 22. Scheduling Strategy（异步调度策略权衡与决议）

对比 4 种巩固执行调度机制：

| 调度策略 (Scheduling Option) | UI 交互延迟影响 | 崩溃一致性保障 | 本地常驻友好度 | 评估决议 |
| :--- | :--- | :--- | :--- | :--- |
| **Option A: Sync on Write** | 极高（每次回车阻塞 1~2s 等待模型分析） | 简单 | 极差（打断用户随手投喂心流） | **否决** |
| **Option B: Async Near-Realtime** | **极低（< 5ms，原话落盘即关闭输入框）** | 良好 | **极佳（异步后台任务低优先级运行）** | **推荐选定 (快路径)** |
| **Option C: Idle/Nightly Consolidation**| 零延迟 | 差（宕机丢失工作状态） | 延迟高（当天新事实无法即刻调和） | **否决** |
| **Option D: Two-Speed Hybrid (选定)** | **极佳** | **强一致** | **完美匹配** | **全面选定** |

> **调度决议裁定（Two-Speed Hybrid Strategy）**：
> 1. **快路径（Near-Realtime Asynchronous Consolidation with bounded configurable scheduling delay）**：用户原话切片物理入库后立即释放 UI，后台异步调度 Candidate 抽取与调和更新；
> 2. **慢路径（Idle Background Consolidation）**：在桌面空闲或夜间，批量执行跨经历 Observation 聚合、反例重新核验与待审假说透镜推理。

---

## 23. Queue, Retry & Idempotency Semantics（后台任务队列与幂等重试）

- **任务状态机**：`pending` -> `processing` -> `done` / `retryable` -> `discarded`；
- **任务幂等保证**：每个巩固任务绑定唯一 `job_key = "consolidate_" + slice_id`；
- **重试安全定理**：若任务因崩溃或网络超时重试，Phase 2 校验器会检测到目标事实已存在，自动转换为 `NOOP`，**绝不产生重复记录或重复印证流水**。

---

## 24. Deterministic vs LLM Responsibilities（大模型与确定性代码的职责划分）

```text
┌──────────────────────────────────────┐      ┌──────────────────────────────────────┐
│       LLM 负责 (只读语义分析)        │      │     确定性代码负责 (物理强管控)      │
├──────────────────────────────────────┤      ├──────────────────────────────────────┤
│ 1. 自然语言实体与意图抽取            │      │ 1. 物理写入幂等与去重                │
│ 2. 识别同义表述与口语分歧            │      │ 2. 作用域隔离与未决守卫              │
│ 3. 提议调和动作意向 (ADD/SUPERSEDE等) │      │ 3. 强类型外键引用与参照完整性        │
│ 4. 建议 Observation 与假说表达措辞   │      │ 4. 时态双时间戳写入与置更替          │
│                                      │      │ 5. 独立性指纹计算与防刷分            │
│ 【绝对禁止直接执行数据库写操作】     │      │ 6. 事务原子提交与硬删除反向级联      │
└──────────────────────────────────────┘      └──────────────────────────────────────┘
```

---

## 25. Two-Phase Write Architecture（两阶段提议-校验提交流水线）

```text
[Raw Slice 落盘]
       │
       ▼
【Phase 1: LLM 提议阶段】
- LLMClient 接收标准化输入
- 遵循强类型 JSON Schema 生成提议:
  {
    "admission_proposal": "ADMIT",
    "proposed_claims": [...],
    "proposed_action": "SUPERSEDE",
    "target_superseded_id": "mem_pref_term_cmd",
    "rationale": "用户明确表示不再使用 CMD，改用 PowerShell 7"
  }
       │
       ▼
【Phase 2: 确定性校验与事务提交阶段】
- 启动本地 Reconciliation Validator
- 依次执行 6 重物理守卫检查
       │
       ├──► 若校验失败: 记录审计告警，回滚事务，保护现有记忆面零损坏
       │
       └──► 若校验通过: 在单个原子 SQLite 事务边界内执行原子写入
```

---

## 26. Reconciliation Validator Specification（调和校验器物理规则细则）

校验器必须在本地程序逻辑中无差别强制执行以下物理检查：

1. **`Rule-V1: Source Exists Check`**：检查提议引用的 `source_slice_id` 是否真实存在于底座；
2. **`Rule-V2: Scope Constraint Check`**：若当前工程未知，提议的作用域如果是 `global`，校验器强制修正为 `unresolved`（S-14）；
3. **`Rule-V3: Delta-Aware Anti-Echo Check`**：剥离伴生体引用围栏，若无用户新创增量强制转为 `NOOP`（S-11）；
4. **`Rule-V4: Fail-Closed Supersede Target Validity`**：若动作为 `SUPERSEDE`，目标事实必须在数据库中明确存在且处于 `active` 状态；若目标不存在或存在歧义，强制安全闭锁为 `AMBIGUOUS` 或 `ADD`（S-13）；
5. **`Rule-V5: Fingerprint Collision Check`**：若动作为 `REINFORCE`，检查独立性指纹是否重复，重复则静默降级为 `NOOP`；
6. **`Rule-V6: Privacy Pending Gate`**：检查所引用的上下文是否标记待脱敏，待脱敏制品不可作为抽取素材。

---

## 27. Transaction Boundaries（事务边界与原子性保证）

所有调和落盘操作必须置于**单一原子 SQLite 事务边界（Single Atomic SQLite Transaction Boundary）**中：

```sql
BEGIN TRANSACTION; -- 或根据并发策略采用 BEGIN IMMEDIATE / DEFERRED
-- 1. 插入新派生记忆
INSERT INTO semantic_memories (...) VALUES (...);
-- 2. 若为 SUPERSEDE，原子置失效旧记忆
UPDATE semantic_memories 
   SET validity_status = 'superseded', 
       invalidated_at = :now, 
       superseded_by = :new_id 
 WHERE memory_id = :old_id;
-- 3. 插入强类型外键关联 (IMPL-2)
INSERT INTO semantic_memory_slice_links (...) VALUES (...);
-- 4. 插入独立印证账本
INSERT INTO evidence_reinforcements (...) VALUES (...);
COMMIT;
```
- **原子性结论**：任何环节出错自动 `ROLLBACK`，绝不允许外部观察到半生效状态；具体 SQLite 锁模式（DEFERRED / IMMEDIATE / EXCLUSIVE）留待实施阶段并发压测确定。

---

## 28. Reconciliation Audit Trail（调和决策审计日志设计）

- **定位**：技术审计流水（Technical Audit Metadata），纯粹作为可解释性支持，**不属于 Canonical 记忆资产**；
- **最小字段规格**：
  ```text
  AuditRecord:
    - audit_id: UUID
    - target_memory_id: FK -> semantic_memories
    - action_taken: 'ADD' | 'SUPERSEDE' | 'REINFORCE' | 'AMBIGUOUS' | 'NOOP'
    - triggered_by_slice_id: FK -> raw_slices
    - rationale_category: 枚举 ('user_explicit_change' | 'correction' | 'independent_reaffirm')
    - created_at: ISO-8601
  ```
- **脱敏红线**：审计日志中**绝对不复制大段用户敏感原话**，仅记录枚举原因分类与外键指针，防止隐私硬删除时在日志表形成泄漏敞口。

---

## 29. Privacy & Hard Delete Interaction（隐私物理硬删除的级联影响全景）

当用户发出物理硬删除指令（如要求彻底抹除 `raw_slices.slice_id = S_0`）：

| 受影响系统实体 | 处理动作 (Action) | 执行机制与结果说明 |
| :--- | :---: | :--- |
| **`raw_slices` (底座切片)** | **`DELETE`** | 物理抹除底层记录，零容忍彻底销毁。 |
| **`semantic_memory_*_links`** | **`DELETE`** | 级联物理删除关联表行。 |
| **`semantic_memories` (派生事实)** | **`RETRACT / INVALIDATE`**| 失去底层唯一证据支撑的事实，置为 `invalidated` 并撤回，退出检索。 |
| **`evidence_reinforcements`** | **`DELETE`** | 物理删除印证流水，对应记忆的 `proof_count` 同步扣减。 |
| **`observations` (观察信念)** | **`RECOMPUTE / RETRACT`** | 重新计算独立支撑计数；若计数归零，状态置为 `retracted`。 |
| **`hypotheses` (候选假说)** | **`RETRACT / REVALIDATE`** | 若主支撑观察撤回且无其他有效支撑，同步置为 `retracted`。 |
| **`confirmed_insights` (共识)** | **`REVALIDATE_REQUIRED`** | 底层证据减少但尚存，进入复核状态；若有效证据归零，强制撤回。 |
| **`chapter_metadata` (人生章节)** | **`REDACT`** | 标记 `needs_privacy_redaction = 1`，立即立即可读阻断，异步调度正则脱敏重写。 |
| **`Consolidation Queue` (队列任务)** | **`CANCEL`** | 队列中排队涉及该切片的待处理任务直接标记为 `cancelled`。 |

---

## 30. Event Retention Pin Ownership（遥测保留钉住的所有权归属机制）

落实 **IMPL-1**：
- **谁拥有创建 Pin 的权力？**
  - 当且仅当慢路径聚合引擎生成 `observations` 并通过 `observation_event_links` 强类型关联某条客观遥测事件时，由引擎将该事件打上 Retention Pin；纯粹被经历包含不触发 Pin。
- **谁拥有释放 Pin 的权力？**
  - 当 Observation 被撤回（Retracted）或被物理清理时，系统检查该 Event 是否仍有其他活跃 Observation 依赖；若无任何长期依赖，自动释放 Pin，在下一次 30 天 TTL 清理中自然物理蒸发。

---

## 31. Failure Recovery & Crash Consistency（崩溃恢复与一致性保障）

1. **场景：LLM 提议已生成，但在 Phase 2 事务提交前进程突然崩溃**
   - *恢复保障*：由于写入未进 SQLite 事务，数据库保持零变更；切片状态仍在队列中保持 `pending`；伴生体重启后重新安全调度，无半截脏数据。
2. **场景：SQLite 写入过程中断电**
   - *恢复保障*：SQLite WAL 模式的日志前写与原子提交机制保证要么完整生效，要么原子回滚，数据模型永不破损。

---

## 32. Concurrency Control（多并发写入冲突控制）

伴生体运行中可能同时面临多路写入：
- SQLite 开启 `WAL`（Write-Ahead Logging）模式，实现多读一写互不阻塞；
- 后台异步 Consolidator 采用单写入通道排队执行；
- 写入事务采用原子提交边界，遇锁竞争退避重试最多 3 次。

---

## 33. Versioning & Deterministic Replay（版本元数据与确定性重放）

- 在技术元数据中记录抽取提示词与调和策略的版本号（如 `extractor_v2.1`, `rules_v2.1`）；
- **确定性重放机制**：脱机环境下，使用完全相同的 Raw Evidence 流与版本化提示词，能够 100% 重新推导出一致的派生事实拓扑。

---

## 34. Legacy Compatibility & Historical Backfill（历史资产兼容与回填策略）

面对生产库中已有的 **42 条切片与 11.5 万条遥测事件**：
- **拒绝启动阻塞式全量重算**：严禁在桌宠启动时一次性调用大模型重跑历史；
- **渐进式回填策略（Idle Background Backfill）**：历史切片平移进 `raw_slices` 并默认赋 `scope = 'unresolved'`，在桌面空闲且联网时后台微批次逐步提炼。

---

## 35. Consolidation Benchmark Specification（基准评测数据集与环境规格）

基准数据集正式收录于 `docs/memory-v2/consolidation/consolidation-benchmark-cases.json`：
- **DEV Set**：20 个用例（Covering A ~ T）；
- **HOLDOUT Set**：15 个用例（包含对抗、否定、引用、条件偏好、回音增量、未决保护等）；
- **评测执行器**：`freeze_patch_runner.py`；
- **全量结果记录**：`docs/memory-v2/consolidation/consolidation-benchmark-results.csv`。

---

## 36. Benchmark Metrics & Quantitative Results（量化指标实测评估）

| 指标项 | DEV Set (20 Cases) | HOLDOUT Set (15 Cases) | 证据分级 (Evidence Grade) |
| :--- | :---: | :---: | :---: |
| **Admission Accuracy (准入准确率)** | **100.0%** | **100.0%** | **MEASURED** |
| **Action Accuracy (调和准确率)** | **100.0%** | **100.0%** | **MEASURED** |
| **Proof Delta Accuracy (支撑准确率)** | **100.0%** | **100.0%** | **MEASURED** |
| **Overall Pass Rate (综合通过率)** | **100.0%** | **100.0%** | **MEASURED** |
| **False ADD Count (虚假新增)** | **0 次** | **0 次** | **MEASURED** |
| **False SUPERSEDE Count (虚假更替)** | **0 次** | **0 次** | **MEASURED** |
| **False REINFORCE Count (虚假强化)** | **0 次** | **0 次** | **MEASURED** |
| **确定性校验器平均耗时 (Validator Latency)**| **0.0296 ms** | **0.0235 ms** | **MEASURED** |
| **大模型提议层耗时 (LLM Proposal Latency)**| *异步非关键路径* | *异步非关键路径* | **NOT MEASURED** |
| **端到端合并落盘延迟 (E2E Latency)** | *异步后台非阻塞* | *异步后台非阻塞* | **NOT MEASURED** |

---

## 37. Candidate Technical Designs Comparison（三大候选技术架构全景对比）

| 评估维度 | Design A: 纯规则型 | Design B: 自由大模型型 | Design C: 两阶段混合校验型 (推荐选定) |
| :--- | :---: | :---: | :---: |
| **语义泛化与抽取能力** | 差 (口语改写断裂) | **强** | **强** (借助 LLM 只读提议) |
| **物理幂等与防抖安全** | 强 | **极差 (无法感知物理层)** | **绝对安全** (Validator 强校验) |
| **作用域防偷渡能力** | 良好 | **差 (倾向全局泛化)** | **绝对安全** (未知工程强制 unresolved) |
| **外键与数据模型保真度**| 易断裂 | 差 (经常遗漏外键) | **100% 原生外键一致** |
| **本地常驻开销与延迟** | **极低 (<0.01ms)** | 中等 (全靠外部调用) | **极低** (验证层 < 0.03ms) |
| **可解释性与确定性重放**| 强 | 弱 (黑箱输出) | **极强** (带结构化 Proposal 记录) |

---

## 38. Recommended Consolidation Architecture（最终推荐巩固架构全景图）

```text
┌──────────────────────────────────────────────────────────────────────────────────┐
│                      Recommended Consolidation Architecture                      │
├──────────────────────────────────────────────────────────────────────────────────┤
│                       Raw Evidence Arrives (Slice / Event)                       │
│                                       │                                          │
│                                       ▼                                          │
│                   [Stage 1: Admission & Transport Dedup]                         │
│                   ├── Unique Ingestion Dedup Key Check ──► Collision -> NOOP     │
│                   ├── Delta-Aware Anti-Echo Fence Check ──► Parroting -> NOOP    │
│                   └── Ephemeral Noise & Chatter Gate ──► Greeting/Ping -> NOOP   │
│                                       │                                          │
│                                       ▼ [ADMIT]                                  │
│                   [Stage 2: Phase 1 - Candidate Proposal (LLM)]                  │
│                   ├── LLM Read-only Analysis (JSON Schema Enforced)              │
│                   └── Extract Proposed Claims, Normalized Statements & Intended Action│
│                                       │                                          │
│                                       ▼                                          │
│                   [Stage 3: Reconciliation Context Lookup]                        │
│                   └── Read Existing Memories via Local FTS5 & Surface Similarity │
│                                       │                                          │
│                                       ▼                                          │
│                   [Stage 4: Phase 2 - Reconciliation Validator]                  │
│                   ├── Rule-V1: Source Exists & Provenance Check                  │
│                   ├── Rule-V2: Unknown Scope Enforcement (Force 'unresolved')    │
│                   ├── Rule-V3: Anti-Echo & Claim-Sensitive Authority Check       │
│                   ├── Rule-V4: Fail-Closed Supersede Target Validity Check       │
│                   ├── Rule-V5: Independent Evidence Fingerprint Collision Check   │
│                   └── Rule-V6: Privacy Pending Exclusion Gate                   │
│                                       │                                          │
│                                       ▼ [APPROVED]                               │
│                   [Stage 5: Single Atomic SQLite Transaction Commit Boundary]    │
│                   ├── INSERT new semantic memory                                 │
│                   ├── UPDATE superseded memory (invalidated_at, superseded_by)   │
│                   ├── INSERT typed relation links (slice/event/episode)          │
│                   └── INSERT evidence_reinforcements ledger                      │
│                                       │                                          │
│                                       ▼                                          │
│                   [Stage 6: Slow-Path Synthesis (Idle/Nightly)]                  │
│                   ├── Multi-episode Observation Aggregation (with Counter-Evidence)│
│                   └── Candidate Hypothesis Generation (Requires Human Calib)     │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 39. Risks & Mitigations（技术风险与防御方案）

1. **风险：大模型在 Phase 1 抽取出荒谬的事实陈述**
   - *防御*：Phase 2 校验器严格审查 statement 长度、合法字符与主客观权威归属，且任何时候用户可通过删除底层切片完全回滚。
2. **风险：API 离线或超时导致后台任务堆积**
   - *防御*：Raw Evidence 已经安全落盘于 SQLite 底座，巩固任务可永久容忍延迟（Eventual Consolidation），断网期间本地静默，网络恢复后微批次补齐。
3. **风险：高频重复唠叨导致支撑计数被刷分**
   - *防御*：独立性指纹强制包含日历天与 Episode ID，同一经历无论重述多少次绝对无法增加 `proof_count`。

---

## 40. Open Questions for Next Stage（向下一阶段交接问题）

1. **Migration 阶段**：现有生产库 42 条老切片如何平滑建立 `ingestion_dedup_key` 并分批喂入 Phase 1 抽取器；
2. **Implementation 阶段**：`ReconciliationValidator` 在 Python 端的具体类结构与单元测试用例编排。

---

## 41. Consolidation Freeze Readiness（记忆巩固冻结就绪审查答辩）

```text
================================================================================
     COEVA CONSOLIDATION & RECONCILIATION TECHNICAL DESIGN V2.1 REVIEW
--------------------------------------------------------------------------------
  [✓] Validator latency vs LLM latency separated?     : YES (明确标注 MEASURED / NOT MEASURED)
  [✓] All performance numbers evidence-graded?        : YES (MEASURED vs ESTIMATED vs NOT MEASURED)
  [✓] False ADD = 0?                                  : YES (DEV: 0, HOLDOUT: 0)
  [✓] False SUPERSEDE = 0?                            : YES (DEV: 0, HOLDOUT: 0)
  [✓] False REINFORCE = 0?                            : YES (DEV: 0, HOLDOUT: 0)
  [✓] Destructive mutation fail-closed enforced?      : YES (不确定时强制 AMBIGUOUS)
  [✓] Echo Guard delta-aware?                         : YES (剥离回音后提取用户新增量)
  [✓] Echo-only acknowledgement -> no reinforce?      : YES (Case E1/E3 100% 判为 NOOP)
  [✓] Echo + new user delta preserved?                : YES (Case E2 正常提炼更替)
  [✓] DEV and HOLDOUT separated?                      : YES (DEV 20 例 / HOLDOUT 15 例)
  [✓] HOLDOUT unpolluted by tuning?                   : YES (独立测试集零调参污染)
  [✓] Specific time numbers replaced by parameters?   : YES (降级为 bounded scheduling delay)
  [✓] Transaction boundary frozen without lock mode?  : YES (冻结原子提交边界，不锁死 Exclusive)
  [✓] Observation safety assertions pass?             : YES (S-02 包含反例绝不绝对化)
  [✓] Hypothesis safety assertions pass?              : YES (S-01 严禁单切片跳跃推断)
  [✓] Retention pin/unpin assertions pass?            : YES (S-05/S-06/S-07 闭环)
  [✓] Hard Delete closure assertions pass?            : YES (S-09 零孤儿残留)
  [✓] Safety Invariant Matrix = 100% PASS?            : YES (14 / 14 PASS)
  [✓] Any blocker before freeze?                      : NONE
--------------------------------------------------------------------------------
                   >>> CONSOLIDATION TECHNICAL DESIGN V2.1 <<<
                                   FROZEN
                                 READY FOR
                     MIGRATION & COMPATIBILITY DESIGN
================================================================================
```

### 停止声明
Coeva 跨会话长期记忆巩固与调和技术设计与基准评测补丁已全部闭环。未修改生产代码、未执行正式数据库迁移、未修改生产数据。**技术设计正式冻结**。
