# Co-evolving Companion：跨会话长期记忆 V2.1 记忆巩固与调和架构决策记录 (Consolidation Decision Record · CDR)

> **决策状态与元数据**：
> - **决策编号**：CDR-2026-01 (Technical Consolidation & Reconciliation Architecture Decision)
> - **决策状态**：`ACCEPTED & FROZEN`
> - **上位规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
>   - `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
> - **实证支持**：
>   - `docs/memory-v2/consolidation/consolidation-benchmark-cases.json` (DEV 20 用例 + HOLDOUT 15 用例)
>   - `docs/memory-v2/consolidation/consolidation-benchmark-results.csv` (全量 35 次评测明细)
>   - `docs/memory-v2/consolidation/consolidation-ablation-report.md` (消融与量化评测报告 · Final Freeze Edition)

---

## 1. 核心上下文与问题陈述 (Context)

在技术检索层已正式冻结的前提下，系统必须解决**记忆写入与演化**的生命周期问题：
- 当前生产写入路径无任何准入门禁，低熵问候与测试碎语 100% 写入数据库，造成存储与检索噪音；
- 缺乏明确的调和状态机，新偏好到达时存在物理覆盖或简单追加的裂脑风险；
- 大模型复述历史的提问极易引发回音壁自闭环；
- 必须确立一套既能充分利用大模型自然语言抽取能力，又由本地确定性代码严密把控物理落盘与外键安全的坚固架构。

在 Freeze Patch 专项审查中，进一步闭环了性能口径分级、Fail-Closed 调和决策边界、增量感知型回音壁提取（Delta-Aware Echo Guard）、原子事务边界（不锁死锁模式）以及未见过的独立 HOLDOUT 集（15 用例）验证与 14 项安全不变量断言。

---

## 2. 核心架构决议汇总 (Decisions)

### 决议 1：全面选定 Design C 两阶段混合架构（Two-Phase Hybrid Architecture）
- **决议**：
  - **Phase 1 (提议阶段)**：大模型仅扮演只读语义分析器，通过标准化 JSON Schema 提议 Candidate Claims 与意向动作；
  - **Phase 2 (校验阶段)**：本地确定性代码（Reconciliation Validator）强制执行物理防抖、增量感知回音壁剥离、作用域安全与时态双时间戳 6 重硬校验；
  - **Fail-Closed 核心安全定理**：
    > **When uncertain between SUPERSEDE and AMBIGUOUS: prefer AMBIGUOUS.**
    > **Destructive semantic mutation must fail closed.**
    > （在更替与歧义存在不确定性时，强制裁决为 AMBIGUOUS；目标不存在时安全降级为 ADD；破坏性语义更替必须安全闭锁，宁可标记冲突，绝不草率覆盖。）
  - **绝对红线**：严禁赋予大模型任何直接数据库写权限，大模型提议必须经校验器核准后方可在单个原子 SQLite 事务边界内提交。
- **依据**：实测表明，Design C 在 DEV 集与独立 HOLDOUT 集上均达成 **100.0% 综合通过率**，**False ADD = 0**，**False SUPERSEDE = 0**，**False REINFORCE = 0**，且 14 项安全不变量断言 **100.0% 全部 PASS**。

### 决议 2：严格执行五类标准化调和动作 (ADD / SUPERSEDE / REINFORCE / AMBIGUOUS / NOOP)
- **`ADD`**：全新事实安全插入，初始 `proof_count = 1`；
- **`SUPERSEDE`**：原子置失效旧事实（`validity_status = 'superseded'`），写入新事实并建立指向关系，完整保留演变轨迹；
- **`REINFORCE`**：基于独立性指纹 `(memory_id, fingerprint)` 唯一键递增 `proof_count`，同一经历唠叨与重试绝对不递增；
- **`AMBIGUOUS`**：弱冲突保留双方，标记为 ambiguous，绝不擅自选边站；
- **`NOOP`**：重试、重放、回音壁与低熵闲聊一等忽略，记忆面保持零变更。

### 决议 3：确立快慢双速异步调度机制 (Two-Speed Hybrid Scheduling)
- **快路径（Near-Realtime Asynchronous Consolidation with bounded configurable scheduling delay）**：用户原话切片物理落盘后立即释放 UI，后台异步调度单条语义事实抽取与调和，杜绝阻塞用户输入心流；
- **慢路径（Idle Background Consolidation）**：在桌面空闲或夜间，批量执行跨多经历的 `observations` 聚合归纳与候选假说透镜推理。

### 决议 4：贯彻执行三大实施不变量 (Strict Invariants Enforcement)
- **IMPL-1 (Retention Pinning)**：外部工具遥测骨架受 30 天 TTL 管辖，仅当被 `observation_event_links` 明确作为长期信念锚点时方可触发 Retention Pin；经历归档后普通事件自然清理；
- **IMPL-2 (Multi-Source FK-safe Provenance)**：`semantic_memories` 通过强类型外键关联表与底层证据绑定（支持切片、遥测与经历），检索候选携带强类型 `ProvenanceRef(kind, id, role)`；
- **IMPL-3 (Privacy Redaction Block)**：任何处于 `needs_privacy_redaction == 1` 的章节制品在检索与上下文生成中物理阻断，绝无等待敞口。

### 决议 5：自模型校准边界与 Partly 独立共识落盘
- **校准权责**：Reconciliation 仅负责事实层调和，绝对无权确认心理假说；
- **Partly 闭锁**：假说校准为“部分认同”时，提取人类手记生成独立的 `calibrated_statement` 存入 `confirmed_insights` 实体，彻底杜绝字符串无痕覆盖；
- **被否认假说可修正**：被人类否决的假说在经历充分演进且出现新独立证据后可谨慎重提。

### 决议 6：性能证据口径分级与冻结范围
- **确定性校验器耗时**：**0.02 ~ 0.03 ms (MEASURED)**；
- **LLM 提议层与端到端耗时**：标记为 **NOT MEASURED**，其具体 Token、模型与并发延迟归属于实施阶段压测；
- **事务边界**：冻结单一原子提交边界，不锁死具体 SQLite 锁模式（DEFERRED / IMMEDIATE / EXCLUSIVE）。

---

## 3. 结果与影响 (Consequences)

### 正向收益 (Positive)
1. **彻底阻断记忆自污染与人格标签化**：增量感知型回音壁剥离与两阶段校验器阻断了一切因大模型自问自答而产生的事实刷分与虚假人格下结论；
2. **零阻塞极致桌面体验**：随手投喂物理原话瞬间写入，后台静默异步调和，用户零等待卡顿；
3. **100% 遵从已冻结规范**：未私自发明任何未冻结的数据库状态或关系表，与 Architecture、Data Model 及 Technical Retrieval 100% 保持自洽。

### 明确合规边界 (Compliance Boundary)
- 调和提议必须经过本地校验器核准；
- 严禁未经校验直接向数据库派生表执行写操作。
