# Co-evolving Companion：跨会话长期记忆 V2.1 工作分解结构 (Work Breakdown Structure · WBS)
## ——WP-0 至 WP-14 全量标准化工程工作包规程 (Final Consistency Edition)

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Work Breakdown)
> - **编写原则**：禁止泛泛而谈的概括标题；每个工作包严格遵循 13 字段标准化模板，具备绝对的代码级可执行性；
> - **工作包清单**：
>   - **WP-0**: Safety Harness & Feature Flags（安全基建与特性开关）
>   - **WP-1**: V2.1 Storage Layer & Repository Abstraction（V2.1 存储底座与仓储抽象）
>   - **WP-2**: Typed Provenance & Lifecycle Infrastructure（类型化溯源与生命周期基建）
>   - **WP-3**: Admission & Candidate Extraction（准入过滤与候选语义抽取）
>   - **WP-4**: Reconciliation Validator & Deterministic Engine（调和提议校验器与确定性引擎）
>   - **WP-5**: Consolidation Scheduler & Near-Real-Time Queue（整合调度器与运行队列元数据）
>   - **WP-6**: Observation, Hypothesis & Calibration Pipeline（观察、假说与校准慢路径）
>   - **WP-7**: Technical Retrieval V2.1 Pipeline（五阶技术检索流水线）
>   - **WP-8**: Recall Gate & Sanctuary Mode Integration（回忆门控与避风港熔断集成）
>   - **WP-9**: Chapter & Privacy Redaction Integration（人生章节与隐私脱敏集成）
>   - **WP-10**: Migration Tooling & MigrationBarrier（独立迁移工具与静默屏障）
>   - **WP-11**: Legacy Compatibility Layer & Dual-Master Elimination（兼容层与双主终结）
>   - **WP-12**: Background Backfill Engine（后台低优先级回填引擎）
>   - **WP-13**: Full Canary Migration & Safety Rehearsal（金丝雀演练与全量断言验证）
>   - **WP-14**: Production Cutover & Post-Cutover Verification（生产原子割接与终审就绪）

---

## WP-0: Safety Harness & Feature Flags（安全基建与特性开关）

- **Goal**：建立细粒度特性开关系统（Feature Flags）、依赖校验矩阵与金丝雀测试框架，为绞杀者平滑演进提供零风险回滚底座。
- **Inputs**：系统配置字典、环境变量、用户设置存储器 `AgentSettingsStore`。
- **Files affected**：`src/core/flags.py`, `src/connectors/settings.py`, `tests/test_flags.py`。
- **New modules**：`src/core/flags.py`（定义 `MemoryFeatureFlags`，支持环境变量 `COEVA_FLAG_*` 与本地配置覆盖）。
- **Modified modules**：`src/connectors/settings.py`（注入 Flags 读写接口）。
- **Dependencies**：无（最优先实施基础包）。
- **Frozen invariants**：IMPL-INV-1（绞杀者单向演进）；**I-S05（特性开关依赖非法组合直接 Fail-Closed 阻断）**。
- **Implementation steps**：
  1. 定义 `MemoryFeatureFlags` 数据结构，包含 6 个独立布尔开关：
     - `memory_v2_storage` (默认 False)
     - `memory_v2_retrieval` (默认 False)
     - `memory_v2_consolidation` (默认 False)
     - `memory_v2_self_model` (默认 False)
     - `memory_v2_migration` (默认 False)
     - `memory_v2_backfill` (默认 False)
  2. 实现严格的开关依赖校验规则：
     - `retrieval_v2` 依赖兼容 V2 存储/读取层；
     - `consolidation_v2` 依赖 `storage_v2` + WP-2 生命周期；
     - `self_model_v2` 依赖 `consolidation_v2` / 观察管道；
     - `backfill_v2` 依赖 `storage_v2` + `consolidation_v2`；
     - 非法组合在应用初始化时直接抛出 `InvalidFlagConfigurationError` 并拒绝启动（Fail-Closed）；
  3. 提供便捷的上下文管理器 `@override_flags(**kwargs)` 与 `with flag_context(...)`，供单元测试使用。
- **Tests**：`tests/test_flags.py`（覆盖默认值、配置文件持久化、环境变量动态覆盖、非法依赖组合 Fail-Closed 测试）。
- **Failure modes**：配置文件损坏或 JSON 解析失败时降级为全局 False（安全默认态）；非法依赖组合阻断启动。
- **Rollback**：直接回滚 `src/core/flags.py` 文件，无数据库变动。
- **Exit criteria**：6 个独立开关完全支持动态切换，非法组合 100% Fail-Closed，单元测试 100% PASS。
- **Estimated complexity**：Low (1 天)。

---

## WP-1: V2.1 Storage Layer & Repository Abstraction（V2.1 存储底座与仓储抽象）

- **Goal**：在独立命名空间实现 V2.1 完整 20 个强类型实体与关系表结构，建立显式事务边界与细粒度 Repository 抽象，在测试/临时数据库中验证全套 DDL 与 CRUD。
- **Inputs**：`docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md`。
- **Files affected**：`src/memory/v2/schema.sql`, `src/memory/v2/store.py`, `src/memory/v2/entities.py`, `tests/memory_v2/test_schema.py`。
- **New modules**：
  - `src/memory/v2/entities.py`（定义 20 个强类型 `@dataclass(frozen=True)` 实体）；
  - `src/memory/v2/schema.sql`（包含 V2.1 权威 DDL、FTS5 虚表、触发器与索引定义）；
  - `src/memory/v2/store.py`（实现 `ChronicleStoreV2`，包含 `RawEvidenceRepository`, `SemanticMemoryRepository`, `UnderstandingRepository`）。
- **Modified modules**：无（不碰旧版 `src/memory/store.py`）。
- **Dependencies**：WP-0。
- **Frozen invariants**：Logical Data Model V2.1 全部表结构契约；`PRAGMA foreign_keys = ON`；`PRAGMA journal_mode = WAL`；**I-S01（Pre-cutover 期间生产环境绝对保持 OFF，旧 V1 库维持权威）**。
- **Implementation steps**：
  1. 编写 `src/memory/v2/schema.sql`，严格覆盖 20 张表与 FTS5 虚表定义；
  2. 编写 `src/memory/v2/entities.py`，实现不可变业务实体与 JSON 序列化；
  3. 编写 `ChronicleStoreV2`，实现连接初始化、显式事务管理器 `with store.transaction():` 与外键约束检查；
  4. 实现底层最小 Repository 接口（`RawEvidenceStore`, `SemanticStore` 等），杜绝上层业务裸写 `conn.execute`。
- **Tests**：`tests/memory_v2/test_schema.py`（表结构完备性校验、外键级联检查、唯一索引冲突测试、WAL 模式验证）。
- **Failure modes**：SQLite DDL 语法错误或索引定义遗漏；测试发现后修复 SQL。
- **Rollback**：删除 `src/memory/v2/` 目录，清理测试临时文件。
- **Exit criteria**：20 张表在 SQLite 内存库与磁盘临时库顺利初始化，`PRAGMA foreign_key_check` 为 0，全部 CRUD 基础测试 100% 通过。
- **Estimated complexity**：Medium (2~3 天)。

---

## WP-2: Typed Provenance & Lifecycle Infrastructure（类型化溯源与生命周期基建）

- **Goal**：实现类型化关联表访问 API，建立底层 Raw Evidence 发生硬删除（Hard Delete）时的完整依赖闭环（Impact Traversal）、高层撤回（Retract）与隐私脱敏挂起（Privacy Pending）基建。
- **Inputs**：Logical Data Model V2.1 候选关联表契约；Architecture V2.1 溯源不变量。
- **Files affected**：`src/memory/v2/lifecycle.py`, `src/memory/v2/provenance.py`, `tests/memory_v2/test_lifecycle.py`。
- **New modules**：
  - `src/memory/v2/provenance.py`（强类型 `ProvenanceRef` 与关联表访问器）；
  - `src/memory/v2/lifecycle.py`（`MemoryLifecycleManager`，负责 Hard Delete 传播、引用计数与撤回重算）。
- **Modified modules**：`src/memory/v2/store.py`。
- **Dependencies**：WP-1。
- **Frozen invariants**：IMPL-2（强类型多源溯源，杜绝伪多态）；IMPL-3（`needs_privacy_redaction == 1` 物理禁读）；**I-S07（硬删除失效必须覆盖完整 8 步依赖闭环）**。
- **Implementation steps**：
  1. 实现 `observation_slice_links`, `observation_event_links`, `hypothesis_observation_links` 等关系表的存取 API；
  2. 实现 Hard Delete 完整依赖闭环遍历算法：
     - Step 1: Raw Evidence delete $\rightarrow$ 标记底层事实物理移除；
     - Step 2: Semantic Memory 依据剩余证据重新计算、置失效或撤回（Retract）；
     - Step 3: Observation 重新计算论据支撑强度，归零则撤回；
     - Step 4: Hypothesis 触发重新验证（revalidation_required）或撤回；
     - Step 5: Confirmed Insight 触发重新验证或撤回；
     - Step 6: 伴生体行为推断立即停止使用无效共识；
     - Step 7: Retention Pin 依据长期依赖重新计算，无引用则解除留存锁（unpin）；
     - Step 8: 检索索引立刻排除被删数据，受影响章节立即标记 `needs_privacy_redaction = 1` 物理禁读；
  3. 提供可独立测试的 lifecycle invalidation hook / stub。
- **Tests**：`tests/memory_v2/test_lifecycle.py`（全流程验证 8 步级联闭环，断言撤回与降级行为 100% 符合规范）。
- **Failure modes**：遍历死循环（由 DAG 拓扑检测防御）；外键约束报错（由单事务拓扑排序防御）。
- **Rollback**：回滚新增的 lifecycle/provenance 模块，不影响 V1。
- **Exit criteria**：通过复杂的 5 层关系级联删除验证，完整 8 步依赖闭环测试 100% 通过。
- **Estimated complexity**：Medium-High (2~3 天)。

---

## WP-3: Admission & Candidate Extraction（准入过滤与候选语义抽取）

- **Goal**：实现心智整合的第一阶段前置链路：对输入的切片与结构化事件进行耐久语义价值（Durable Semantic Value）准入判定，并抽取候选语义提议。
- **Inputs**：`RawSlice`, `event_skeletons`, Consolidation V2.1 准入规则。
- **Files affected**：`src/memory/v2/admission.py`, `src/memory/v2/extractor.py`, `tests/memory_v2/test_admission.py`。
- **New modules**：
  - `src/memory/v2/admission.py`（准入过滤器 `AdmissionFilter`）；
  - `src/memory/v2/extractor.py`（候选命题提取器 `CandidateExtractor`）。
- **Modified modules**：无。
- **Dependencies**：WP-1。
- **Frozen invariants**：消除“纯闲聊即NOOP”偏见；低信息量问候/测试切片过滤；严禁 Prompt/CoT 侵入。
- **Implementation steps**：
  1. 实现 `AdmissionFilter`：
     - 识别低熵无信息问候（hi, 早安）与测试气泡 $\rightarrow$ `REJECT_LOW_ENTROPY`；
     - 识别即时易失性指令（如“把窗口调大点”） $\rightarrow$ `REJECT_TRANSIENT_COMMAND`；
     - 识别具备持久语义价值的用户偏好、童年经历、约束与事实 $\rightarrow$ `ACCEPT`；
  2. 实现 `CandidateExtractor`：将通过准入的文本与遥测骨架结构化封装为 `ProposedFactCandidate`。
- **Tests**：`tests/memory_v2/test_admission.py`（复用冻结的 DEV 与 HOLDOUT 准入测试用例）。
- **Failure modes**：误过滤有价值闲聊；通过基准用例测试确保召回率。
- **Rollback**：代码级回滚。
- **Exit criteria**：准入用例通过率 100%，无有效长程语义切片被误杀。
- **Estimated complexity**：Low-Medium (1~2 天)。

---

## WP-4: Reconciliation Validator & Deterministic Engine（调和提议校验器与确定性引擎）

- **Goal**：实现心智整合第二阶段的物理守门员：抽象可替换的大模型提议接口，并用纯本地代码实现 6 大物理不变量校验与原子事务提交引擎。
- **Inputs**：`ProposedFactCandidate`, Consolidation V2.1 Frozen 规范, S-01~S-14 物理断言集。
- **Files affected**：`src/memory/v2/reconciliation.py`, `src/memory/v2/echo_guard.py`, `src/memory/v2/proposal_provider.py`, `tests/memory_v2/test_reconciliation.py`。
- **New modules**：
  - `src/memory/v2/proposal_provider.py`（抽象只读提议器协议 `ProposalProvider`）；
  - `src/memory/v2/echo_guard.py`（增量感知防回声守卫 `EchoGuard`）；
  - `src/memory/v2/reconciliation.py`（`DeterministicReconciliationValidator` 与提交引擎）。
- **Modified modules**：无。
- **Dependencies**：WP-2, WP-3。
- **Frozen invariants**：IMPL-INV-5（LLM 只读提议，禁止写库）；IMPL-INV-6（Delta-aware Echo Guard）；不确定时破坏性操作 Fail-Closed 判定为 AMBIGUOUS。
- **Implementation steps**：
  1. 定义 `ProposalProvider` 接口，支持 OpenAI-compatible、Ollama 与离线 Mock；
  2. 实现 `EchoGuard`：剥离伴生体镜像复述，保留用户增量语义；纯回响判定为 `NOOP_LONG_TERM`；
  3. 实现本地确定性校验器，严格验证 6 大不变量：
     - S-01: 权威等级检查（非最高权威不得单凭系统推断置失效用户自述）；
     - S-02: 溯源外键完备性检查；
     - S-03: 作用域合法性（project/global/unresolved）；
     - S-04: 冲突检测与破坏性变更 Fail-Closed（疑歧义降级为 `AMBIGUOUS`）；
     - S-05: 独立证据递增规则（同会话重试不递增 `proof_count`）；
  4. 组装 `CommitPlan` 并在单一 SQLite 事务中完成原子落盘与状态更新。
- **Tests**：`tests/memory_v2/test_reconciliation.py`（运行 35 个冻结 Benchmark 用例，确保 S-01~S-14 100% PASS，False ADD/SUPERSEDE = 0）。
- **Failure modes**：LLM 提议格式非法或超时 $\rightarrow$ 校验器捕获并直接降级为 `NOOP`，零脏写。
- **Rollback**：代码级回滚。
- **Exit criteria**：35 个基准用例 100% 通过，单次校验耗时低于 0.1ms（实测标杆 0.02ms）。
- **Estimated complexity**：High (3~4 天)。

---

## WP-5: Consolidation Scheduler & Near-Real-Time Queue（整合调度器与运行队列元数据）

- **Goal**：建立后台非阻塞任务调度器，管理持久化任务队列元数据，实现 Semantic Memory 的近实时异步整合，隔离桌面伴生体前台心流。
- **Inputs**：`RawSlice` 写入事件、空闲计时器。
- **Files affected**：`src/memory/v2/scheduler.py`, `src/memory/v2/queue.py`, `tests/memory_v2/test_scheduler.py`。
- **New modules**：
  - `src/memory/v2/queue.py`（任务队列管理，持久化待处理 Job 状态）；
  - `src/memory/v2/scheduler.py`（后台调度器 `ConsolidationScheduler`，监听空闲并调度快路径整合）。
- **Modified modules**：无。
- **Dependencies**：WP-3, WP-4。
- **Frozen invariants**：**I-S06（任务队列元数据属于技术运行元数据，绝对不是第 21 个 Memory 实体，不入检索/不入自模型）**；IMPL-INV-9（Qt 主线程零阻塞）。
- **Implementation steps**：
  1. 建立技术运行状态表 `consolidation_jobs`（明确标记为非规范元数据）；
  2. 调度器在后台工作线程中消费队列，执行防抖窗口（Debounce Window，例如静默 2 秒再触发）；
  3. 实现优雅停止接口 `scheduler.stop(timeout=1.0)`；关机时未完成任务安全回滚或标记待重试。
- **Tests**：`tests/memory_v2/test_scheduler.py`（测试防抖触发、多任务顺序处理、进程退出取消正在执行的任务）。
- **Failure modes**：网络断网或 LLM 挂起 $\rightarrow$ 任务标记为 `FAILED` 并指数退避重试，不影响前台。
- **Rollback**：代码级回滚。
- **Exit criteria**：后台平稳消费整合队列，Qt UI 界面帧率零下降。
- **Estimated complexity**：Medium (2 天)。

---

## WP-6: Observation, Hypothesis & Calibration Pipeline（观察、假说与校准慢路径）

- **Goal**：实现深层理解域（Understanding Domain）的慢路径管道：基于证据聚类生成 Observation，定期推断待审假说（Hypothesis），并实现严格的用户双向校准（Human Calibration）。
- **Inputs**：Raw Evidence, Episodes, Derived Semantic Memories, ACT 六大透镜。
- **Files affected**：`src/memory/v2/observation.py`, `src/core/self_model.py`, `src/core/hypotheses.py`, `tests/memory_v2/test_observation.py`。
- **New modules**：
  - `src/memory/v2/observation.py`（慢路径观察管道 `ObservationPipeline`）；
  - `src/memory/v2/calibration.py`（用户校准与转正状态机 `CalibrationManager`）。
- **Modified modules**：`src/core/self_model.py`, `src/core/hypotheses.py`。
- **Dependencies**：WP-2, WP-5。
- **Frozen invariants**：`Hypothesis ≠ Confirmed Insight`；历史假说隔离为 candidate，严禁未经校准自动转正；用户选择 PARTLY 时必须留存 `calibrated_statement`。
- **Implementation steps**：
  1. 实现 `ObservationPipeline`：以低频后台 Job 方式对多会话证据进行跨情境聚合，写入 `observations` 与关联表；
  2. 实现假说生成逻辑：由 `observations` 支撑推断候选假说，填充 `hypothesis_observation_links`；
  3. 重构用户校准流（`CalibrationManager`）：
     - `YES` $\rightarrow$ 创建 `confirmed_insights` 并关联源假说，激活共识；
     - `PARTLY` $\rightarrow$ 记录用户补充修正词，生成带澄清的衍生项；
     - `NO` $\rightarrow$ 标记假说为 `rejected`（退出回忆与行为偏好）；
     - `NOT_NOW` $\rightarrow$ 维持 `candidate`，严禁随时间自动转正。
- **Tests**：`tests/memory_v2/test_observation.py`（覆盖校准转正、部分修正、拒绝归档及未授权转正 0 容忍测试）。
- **Failure modes**：后台推理耗时较长；通过限频与异步线程防护。
- **Rollback**：代码级回滚。
- **Exit criteria**：校准流严格遵循四态闭环，生产库 0 假说转正的约束得到代码级保障。
- **Estimated complexity**：Medium-High (3 天)。

---

## WP-7: Technical Retrieval V2.1 Pipeline（五阶技术检索流水线）

- **Goal**：完整实现已冻结的技术检索五阶流水线，达成毫秒级、零向量依赖、高精度跨会话回忆。
- **Inputs**：用户即时 Query、上下文心境、活动项目标识、Technical Retrieval Design V2.1。
- **Files affected**：`src/memory/v2/retrieval/` (完整子包), `tests/memory_v2/test_retrieval.py`。
- **New modules**：
  - `src/memory/v2/retrieval/router.py`（Stage 1: Intent Routing 意图路由器）；
  - `src/memory/v2/retrieval/scope.py`（Stage 2: Scope Filter 作用域过滤器）；
  - `src/memory/v2/retrieval/lexical.py`（Stage 3A: FTS5 Lexical Channel 词法通道）；
  - `src/memory/v2/retrieval/surface.py`（Stage 3B: Surface N-gram Cosine 特征相似度通道）；
  - `src/memory/v2/retrieval/reranker.py`（Stage 4: Temporal & Contextual Reranker 时空心境重排器）；
  - `src/memory/v2/retrieval/fusion.py`（Stage 5: Fusion Selector 融合裁决与 `NO_MEMORY` 判定器）；
  - `src/memory/v2/retrieval/pipeline.py`（统一入口 `MemoryRetrieverV2`）。
- **Modified modules**：无。
- **Dependencies**：WP-1。
- **Frozen invariants**：RDR-2026-01；禁引入外置向量库/重型嵌入模型；`needs_privacy_redaction == 1` 物理阻断；**I-S08（检索门禁严格基于已冻结实测事实：DEV $\ge 93.1\%$, HOLDOUT $100\%$, Forbidden $0\%$, 延迟基准 ~1.88ms，不得擅自捏造 100% Top-1 或脱离硬件的超低延迟）**。
- **Implementation steps**：
  1. 编码 Stage 1：区分显式记忆提问、任务上下文连续性与无记忆闲聊；
  2. 编码 Stage 2：实现 `project_id` 匹配与 `global` 作用域过滤；
  3. 编码 Stage 3A & 3B：实现 SQLite FTS5 查询通道与 N-gram TF-IDF 表面相似度双通道并发召回；
  4. 编码 Stage 4：结合时间衰减（Exponential Decay）与心境匹配度调整得分；
  5. 编码 Stage 5：执行加权融合与阈值门控，输出 `RetrievedCandidate` 或触发 `NO_MEMORY`。
- **Tests**：`tests/memory_v2/test_retrieval.py`（运行全量 44 个 DEV 与 HOLDOUT 用例，验证指标不劣于冻结基线）。
- **Failure modes**：FTS5 语法转义错误 $\rightarrow$ 增加输入清洗器 `sanitize_fts5_query()`。
- **Rollback**：代码级回滚。
- **Exit criteria**：44 个基准用例指标完全对齐冻结线（HOLDOUT 100% 通过，Forbidden 0%），同硬件环境实测耗时在 ~1.88ms 基线范围内。
- **Estimated complexity**：High (3~4 天)。

---

## WP-8: Recall Gate & Sanctuary Mode Integration（回忆门控与避风港熔断集成）

- **Goal**：将五阶检索流水线接入伴生体气泡渲染与大模型提示词组装层，严格实现避风港模式（Sanctuary Mode）下的物理回忆熔断。
- **Inputs**：`SanctuaryGuard`, `InterventionPolicy`, `MemoryRetrieverV2`。
- **Files affected**：`src/core/recall_gate.py`, `src/core/personality.py`, `run_companion.py`, `tests/test_sanctuary_recall.py`。
- **New modules**：`src/core/recall_gate.py`（`RecallGate` 统筹检索前置准入与后置表达守卫）。
- **Modified modules**：`src/core/personality.py`, `run_companion.py`。
- **Dependencies**：WP-7。
- **Frozen invariants**：Sanctuary 激活时，硬阻断一切反思性回忆与心理洞察，仅保留最低限度任务连续性；80/15/5 表达守卫。
- **Implementation steps**：
  1. 编写 `RecallGate`：在调用 `MemoryRetrieverV2` 前检查 `SanctuaryGuard.is_active`；
  2. 若避风港激活：强制屏蔽心理洞察与高层假说，仅允许返回当前活跃工程的最近未完成命令或错误摘要；
  3. 改造 `run_companion.py._recall_memories`：接入 `RecallGate`，受 `memory_v2_retrieval` 特性开关控制。
- **Tests**：`tests/test_sanctuary_recall.py`（测试心烦受挫切片输入时，记忆召回被物理清空；正常交互时精准召回）。
- **Failure modes**：避风港误放行 $\rightarrow$ 编写断言测试确保无漏网反思进入提示词。
- **Rollback**：切换 `memory_v2_retrieval` 特性开关为 False，退回旧版 Retriever。
- **Exit criteria**：避风港激活下反思性召回率精确为 0，旧版气泡交互零回归。
- **Estimated complexity**：Medium (2 天)。

---

## WP-9: Chapter & Privacy Redaction Integration（人生章节与隐私脱敏集成）

- **Goal**：升级人生章节生成与档案库模块，确保文学创作仅消费已验证共识（Confirmed Understanding）与合法经历，并在隐私删除发生时实现脱敏即时阻断与异步重写。
- **Inputs**：`ChapterGenerator`, `chapter_metadata`, `needs_privacy_redaction`。
- **Files affected**：`src/core/chapters.py`, `src/body/chronicle_window.py`, `tests/test_chapter_privacy.py`。
- **New modules**：无。
- **Modified modules**：`src/core/chapters.py`, `src/body/chronicle_window.py`。
- **Dependencies**：WP-2, WP-6。
- **Frozen invariants**：IMPL-INV-7（`needs_privacy_redaction == 1` 即时禁读）；叙事文本绝不反向作为认知证据；隐私权高于叙事稳定性。
- **Implementation steps**：
  1. 改造 `ChapterGenerator` 的提示词上下文构建器：只允许传入 `confirmed_insights` 与合法经历，禁止直接灌入未清洗的原始遥测；
  2. 接入隐私阻断：在读取章节时检查 `needs_privacy_redaction`，若为 1 则界面展示“*章节因隐私更新正在脱敏重写中...*”，禁止输出旧明文；
  3. 调度后台重写 Worker：剔除被删除的切片与事件，重新生成章节，完成后清除阻断标记。
- **Tests**：`tests/test_chapter_privacy.py`（切片物理删除后触发章节禁读，异步脱敏重写后恢复展示）。
- **Failure modes**：异步重写失败 $\rightarrow$ 保持禁读状态，记录可诊断告警。
- **Rollback**：代码级回滚。
- **Exit criteria**：涉及隐私删除的章节即时不可读率 100%，脱敏后生成文本不含已删除原话。
- **Estimated complexity**：Medium (2 天)。

---

## WP-10: Migration Tooling & MigrationBarrier（独立迁移工具与静默屏障）

- **Goal**：实现独立命令行形式的迁移执行器（Migration Executor），完整落实 Option A Hard Quiesce 写入确认屏障、SQLite Online Backup API、Windows WAL 合流协议与原子重命名。
- **Inputs**：Migration & Compatibility V2.1 Frozen 规范, M-S01~M-S18 断言集。
- **Files affected**：`src/memory/v2/migration/` (完整子包), `tests/test_migration_cli.py`。
- **New modules**：
  - `src/memory/v2/migration/barrier.py`（`MigrationBarrier` 写入持久化屏障管理器）；
  - `src/memory/v2/migration/executor.py`（`MigrationExecutor` 核心调度器）；
  - `src/memory/v2/migration/cli.py`（命令行入口 `python -m src.memory.v2.migration.cli`）。
- **Modified modules**：无（迁移作为独立维护命令，绝不与应用启动耦合）。
- **Dependencies**：WP-1, WP-2。
- **Frozen invariants**：`ACKED WRITE MUST BE DURABLE`；全写者与删除者覆盖；动态文件集磁盘空间门禁；零单调 ROWID 依赖；全量 M-S01~M-S18 断言保障；**I-S04（DB Cutover 绝不等于开启全部高层开关）**。
- **Implementation steps**：
  1. 编写 `MigrationBarrier`：提供 `acquire()` 与 `release()`，挂起前台写确认（未落盘绝不 ACK）；
  2. 编写 `MigrationExecutor`：
     - Step 1: Preflight 动态计算磁盘空间门禁（实测门槛 225.94 MB）；
     - Step 2: 建立一致性快照（SQLite Online Backup）；
     - Step 3: 影子库构建 Schema 并灌入数据（`slices` 映射 unresolved, `events` 映射 error_category，旧假说存入 `legacy_hypothesis_audit`）；
     - Step 4: 集合差分对齐（NOT EXISTS）与确定性冲突检查；
     - Step 5: 后置自动化验证（运行 M-S01~M-S18）；
     - Step 6: 双 WAL TRUNCATE checkpoint，断开连接，Windows 原子置换文件。
- **Tests**：`tests/test_migration_cli.py`（CLI 参数解析、Dry-run 模式测试、中断恢复测试）。
- **Failure modes**：磁盘不足或校验失败 $\rightarrow$ 抛出异常并硬阻断，清理影子库，生产库完好。
- **Rollback**：处于 R1 地平线时利用生成的 `.pre_v2_backup` 文件可一键原子恢复。
- **Exit criteria**：CLI 独立运行，全套流程无人工干预自动化完成。
- **Estimated complexity**：High (3 天)。

---

## WP-11: Legacy Compatibility Layer & Dual-Master Elimination（兼容层与双主终结）

- **Goal**：切断对 `raw_slices.jsonl` 的双主写入，确立 SQLite 唯一权威源；在 V2.1 数据库中建立兼容视图（Compatibility Views），实现存量读取组件零感知过渡。
- **Inputs**：`SliceStore`, `ChronicleStore`, `legacy_slices_view`, `legacy_events_view`。
- **Files affected**：`src/feeder/storage.py`, `src/memory/v2/compatibility.py`, `run_companion.py`, `tests/test_compatibility_layer.py`。
- **New modules**：`src/memory/v2/compatibility.py`（只读兼容适配器与视图生命周期监控器）。
- **Modified modules**：`src/feeder/storage.py`, `run_companion.py`。
- **Dependencies**：WP-1, WP-10。
- **Frozen invariants**：IMPL-INV-3（SQLite 唯一权威事实源）；兼容视图退场基于连续 7 天零读取监控指标；**I-S01（生产环境双主切除与 V2 主写切换必须在割接时才正式生效）**。
- **Implementation steps**：
  1. 改造 `SliceStore`：将其从主写组件重构为只读回退或“SQLite 事务提交后的异步导出器”，彻底终结双写裂脑；
  2. 在 V2.1 Schema 中创建 `legacy_slices_view` 与 `legacy_events_view`；
  3. 实现兼容视图访问监控计数器（Access Counter）；
  4. 在 Pre-cutover 阶段通过开关保护写路径；割接完成后正式切换。
- **Tests**：`tests/test_compatibility_layer.py`（验证旧版读取代码通过兼容视图查询，结果与原库完全一致；验证 JSONL 异步导出正确）。
- **Failure modes**：旧组件读取报错 $\rightarrow$ 适配器透明捕获并重定向。
- **Rollback**：回滚适配器代码。
- **Exit criteria**：生产库写路径 100% 收敛于 SQLite，双写彻底消除，兼容视图稳定可查。
- **Estimated complexity**：Medium (2 天)。

---

## WP-12: Background Backfill Engine（后台低优先级回填引擎）

- **Goal**：实现完全解耦于迁移工具的历史数据异步回填引擎（Backfill Engine），在系统空闲时对存量切片与关键经历进行语义提炼，丰富长期自模型。
- **Inputs**：迁移后的 V2.1 数据库, WP-3 抽取器, WP-4 调和引擎。
- **Files affected**：`src/memory/v2/backfill.py`, `src/memory/v2/backfill_cli.py`, `tests/test_backfill.py`。
- **New modules**：
  - `src/memory/v2/backfill.py`（回填调度器 `BackfillEngine`）；
  - `src/memory/v2/backfill_cli.py`（独立回填管理命令）。
- **Modified modules**：无。
- **Dependencies**：WP-4, WP-5, WP-10。
- **Frozen invariants**：Migration $\neq$ Backfill（迁移不回填，回填不影响迁移）；近期切片优先；遥测事件不盲目进入语义回填；**I-S10（Backfill 绝非生产割接前置阻塞项）**；资源预算目标 CPU $< 5\%$。
- **Implementation steps**：
  1. 实现回填进度游标记录表 `backfill_progress`；
  2. 调度策略：倒序（最新切片优先）批量读取未处理的切片；
  3. 调用准入与抽取流水线，提交给 `ReconciliationValidator` 处理；
  4. 采用非阻塞运行机制（线程/进程选型留给真实环境实测），限制休眠间隔（设计目标 CPU $< 5\%$）；
  5. 响应关机或系统负载信号，支持秒级安全挂起与断点续传。
- **Tests**：`tests/test_backfill.py`（测试断点续传、资源限频控制、重复执行幂等性）。
- **Failure modes**：LLM 额度超限或不可用 $\rightarrow$ 回填引擎自动休眠，不影响伴生体正常运行。
- **Rollback**：停止回填进程，重置回填游标。
- **Exit criteria**：存量切片有序提炼为原子事实，系统资源无尖峰，伴生体无任何卡顿。
- **Estimated complexity**：Medium (2~3 天)。

---

## WP-13: Full Canary Migration & Safety Rehearsal（金丝雀演练与全量断言验证）

- **Goal**：在完全真实的生产数据副本上，端到端执行全套迁移与割接演练，通过对抗性破坏测试验证 M-S01 ~ M-S18 全部 18 项安全断言。
- **Inputs**：生产数据库真实副本 `data/companion_chronicle.db`（47.55MB），`run_final_correctness_suite.py`。
- **Files affected**：`tests/memory_v2/canary_rehearsal.py`。
- **New modules**：`tests/memory_v2/canary_rehearsal.py`（集成化自动化金丝雀测试套件）。
- **Modified modules**：无。
- **Dependencies**：WP-10, WP-11。
- **Frozen invariants**：M-S01 ~ M-S18 全部 18 项割接断言 100% PASS；Data Loss = 0；Orphan FK = 0；**I-S09（所有必需工作包未通过前严禁进入 WP-14）**。
- **Implementation steps**：
  1. 复制真实生产库至临时隔离沙箱；
  2. 调用 `MigrationExecutor` 执行完整构建；
  3. 在迁移构建期间注入对抗性故障：
     - 删除最大 ROWID 后并发插入新切片与新事件（验证 M-S13 / M-S14）；
     - 注入相同 ID 内容的重复重放（验证 M-S15 幂等 NOOP）；
     - 注入相同 ID 内容的冲突篡改（验证 M-S16 Fail-Closed 阻断）；
     - 模拟在 Barrier 期间进程崩溃（验证 M-S17 / M-S18 零已确认数据丢失）；
  4. 执行原子切换并运行全套完整性比对（44 条切片逐字哈希一致）。
- **Tests**：`pytest tests/memory_v2/canary_rehearsal.py`。
- **Failure modes**：任何一项断言失败均视为阻断，禁止进入 WP-14。
- **Rollback**：清理沙箱临时文件。
- **Exit criteria**：M-S01 ~ M-S18 连续 3 次演练 100% 全部通过，总耗时低于 3.0 秒。
- **Estimated complexity**：Medium (2 天)。

---

## WP-14: Production Cutover & Post-Cutover Verification（生产原子割接与终审就绪）

- **Goal**：在用户确认的维护窗口内，执行真实生产数据库的正式割接，验证生产新库完整性，激活 Stage 10A 存储基底，并规划高层心智的逐层灰度开启。
- **Inputs**：生产数据库 `data/companion_chronicle.db`，WP-10 迁移工具，WP-13 演练报告。
- **Files affected**：`data/companion_chronicle.db`（产生 `.pre_v2_backup` 并原子置换为 V2.1），`agent_settings.json`（激活对应特性开关）。
- **New modules**：无。
- **Modified modules**：`run_companion.py`（启用新版运行时）。
- **Dependencies**：WP-0 至 WP-13 全部验收通过（**I-S09 强约束**）。
- **Frozen invariants**：Zero Data Loss；Windows 文件句柄安全；版本标识 `PRAGMA user_version = 20261018`；**I-S02 / I-S03（R2 地平线产生新写后严禁覆盖旧库，前向修复为主）**；**I-S04（分阶启用 10A $\rightarrow$ 10B $\rightarrow$ 10C $\rightarrow$ 10D）**。
- **Implementation steps**：
  1. 伴生体退出运行，确保无外部进程占用数据库文件；
  2. 运维执行命令：`python -m src.memory.v2.migration.cli --execute`；
  3. 工具自动完成：空间检查 $\rightarrow$ 快照备份 $\rightarrow$ 影子库构建 $\rightarrow$ 差分校验 $\rightarrow$ WAL 截断 $\rightarrow$ 原子重命名；
  4. 启动伴生体，激活 Stage 10A（`memory_v2_storage = ON`），验证底层切片与遥测读写正常；
  5. 按照规划后续逐层激活 Stage 10B（检索）、10C（整合）与 10D（自模型与章节）。
- **Tests**：运行生产后置验收脚本，确认 44 条切片全文哈希一致，事件骨架完好，外键违规为 0。
- **Failure modes**：Windows 文件占用报错 $\rightarrow$ 自动指数退避重试，若重试 3 次仍失败则取消割接，原库未动。
- **Rollback**：在 R1 地平线（未产生新 V2 写入前）可一键回滚还原；进入 R2 后遵循前向修复规程。
- **Exit criteria**：伴生体在新版 V2.1 架构下平稳启动运行，用户投喂与记忆召回功能完全正常。
- **Estimated complexity**：Medium (1 天)。
