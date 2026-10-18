# Co-evolving Companion (Coeva)：跨会话长期记忆 V2.1 工程实施总体规划 (Implementation Plan · Final Consistency Edition)
## ——绞杀者演进、特性开关依赖矩阵、分阶启用路线、真实基准门禁与工程全景蓝图

> **文档状态与元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Implementation Plan)
> - **规范状态**：`IMPLEMENTATION PLAN SIGNED OFF — READY TO START STAGE 0`
> - **上位已冻结规范**：
>   1. `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   2. `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Logical Data Model V2.1 Frozen)
>   3. `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
>   4. `docs/memory-v2/consolidation/consolidation-reconciliation-design.md` (Consolidation V2.1 Frozen)
>   5. `docs/memory-v2/migration/migration-compatibility-design.md` (Migration & Compatibility V2.1 Frozen)
> - **工程施工纪律**：
>   - **严禁 Big-Bang 一次性重写**：必须采用 Strangler Fig（绞杀者模式），保证旧版伴生体在每一施工阶段均可正常运行；
>   - **严格禁止在规划阶段修改生产代码或生产数据库**：不执行生产迁移，不修改 `data/companion_chronicle.db`，不执行历史 Backfill，不启动 Stage 0 实施；
>   - **若实现细节与 Frozen Spec 冲突，严禁擅改 Spec，必须提出 Spec Change Request 并中止相关工作包**。

---

## 1. Executive Summary（执行摘要与核心目标）

针对 Coeva 生产运行数据库 `data/companion_chronicle.db`（当前包含 **44 条真实切片** 与 **116,625 条外部工具遥测事件**，体积约 **47.55 MB**）以及伴生体多 Agent 感知运行时的平滑升级需求，本实施规划将已全部冻结的五层上位设计转化为**可执行、可分阶段、可测试、可回滚、低风险**的工程施工方案。

本规划回答施工全周期的 8 大核心工程问题：
1. **具体改动哪些文件**：精确映射到 15 个改动文件、18 个新增模块与 3 项退役资产（详见 `file-change-map.md`）；
2. **施工先后顺序**：严格按照 `WP-0 (安全基建) -> WP-1~2 (存储与关系) -> WP-3~5 (整合快路径) -> WP-6 (观察慢路径) -> WP-7~9 (检索与集成) -> WP-10~11 (迁移与兼容) -> WP-13 (金丝雀) -> WP-14 (生产割接) -> WP-12 (异步回填)` 执行；
3. **分阶段验证标准**：每个 Stage 设立物理 Exit Gate，其指标 100% 严格继承已冻结的基准实测事实，不擅自捏造新门槛（详见 `test-gates.md`）；
4. **并行与串行约束**：底层存储与基建严格串行推进；检索、整合与心智观察在接口稳定后可高度并行；
5. **旧系统持续可用性保障**：通过 `FeatureFlags` 细粒度控制与双向适配器（Compatibility Adapters），旧系统始终作为 Fallback 路径保活；
6. **Pre-cutover 与 Post-cutover 严格分离**：
   - **Pre-cutover (Stage 0 ~ Stage 9)**：V2 Writer 在沙箱与临时库中实现和验证，但生产环境 `memory_v2_storage = OFF`，生产 V1 DB 保持绝对权威主写；
   - **Post-cutover (Stage 10)**：正式迁移且后置检查通过后，才激活 `memory_v2_storage = ON`，并终结 JSONL 双写；
7. **数据割接与功能启用解耦 (DB Cutover ≠ All Features On)**：
   - 生产割接仅切换存储基底（Stage 10A），后续高层心智（10B 检索、10C 整合、10D 假说与叙事、11 回填）按灰度节奏逐层开启；
8. **写入持久化红线与真实回滚地平线**：
   - 全周期恪守 `ACKED WRITE MUST BE DURABLE`；
   - 严禁虚假承诺“任何时候均可秒级恢复旧库”：一旦割接后产生已确认的 V2 新写入，禁止直接覆盖旧库丢弃数据，前向修复（Forward-Fix）为默认恢复策略。

---

## 2. 真实仓库实现审计（Repository Implementation Audit）

基于对 `src/` 源码树与真实运行态的物理审计，梳理出存量核心组件的职责、缺陷与 V2.1 处置方案：

| 现有模块 / 组件 | 文件路径 | 当前核心职责与实现机制 | 存在缺陷与架构包袱 | V2.1 演进目标 | 处置决议 |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **`ChronicleStore`** | `src/memory/store.py` | 管理本地 SQLite WAL 数据库，维护 `slices`, `events`, `hypotheses`, `insights`, `growth_themes` 与 `evidence` 视图 | 单连接跨线程复用（`check_same_thread=False`）；缺乏业务事务抽象；存在伪多态外键；未实现类型化关系 | 重构为细粒度 Typed Repositories，提供显式事务边界与连接池安全，支持 20 个强类型实体 | **REPLACE & WRAP** |
| **`MemoryRetriever`** | `src/memory/retriever.py` | 字符串正则匹配、停用词过滤、相对时间解析（昨天/前天），调用 LIKE 模糊查询切片 | 仅支持单一切片子串检索；缺乏语义意图路由；无项目/全局作用域过滤；无 FTS5 索引与表面特征余弦匹配 | 升级为五阶检索流水线（Intent $\rightarrow$ Scope $\rightarrow$ Lexical/Surface $\rightarrow$ Contextual $\rightarrow$ Fusion），支持 `NO_MEMORY` | **REPLACE** |
| **`SliceStore`** | `src/feeder/storage.py` | 维护 `data/raw_slices.jsonl` 文件追加写入与读取 | 与 SQLite `slices` 构成双主双写，存在严重裂脑与一致性撕裂风险 | 废除双主写入；降级为 SQLite 事务提交后的可选单向异步导出器 | **MODIFY** |
| **`LocalEventBus`** | `src/connectors/event_bus.py` | 内存事件分发，直接调用 `store.record_event` | 直接向旧 `events` 表写入，未做 `error_category` 结构化转换；无 Hard Quiesce 写入确认屏障 | 接入 V2.1 存储网关，支持 `MigrationBarrier` 挂起与 `ACKED WRITE MUST BE DURABLE` | **MODIFY** |
| **`SanctuaryGuard`** | `src/core/sanctuary.py` | 评估用户负面情绪关键词，维护 `is_active` 状态 | 仅作为简单布尔状态，未深入阻断检索层的反思性回忆 | 接入 `RecallGate`，当避风港激活时硬阻断反思性回忆与心理洞察，仅保留最低限度任务连续性 | **MODIFY** |
| **`HypothesisEngine`** | `src/core/hypotheses.py` | 从 `BehavioralPattern` 规则派生候选假说 | 同步执行，逻辑僵化；假说直接落库，缺乏与底层 Observation 的类型化关联 | 重构为后台慢路径（Slow Path），基于 `observations` 派生候选假说，填充 `hypothesis_observation_links` | **MODIFY** |
| **`SelfModelManager`** | `src/core/self_model.py` | 管理 `ConfirmedInsight` 与 `GrowthTheme` 的用户校准状态 | 旧校准逻辑直接拼接字符串，缺乏审计溯源；缺少未决状态处理 | 严格实施 `Observation -> Hypothesis -> Human Calibration -> Confirmed Insight`；解耦生长主题 | **MODIFY** |
| **`PatternBuilder`** | `src/core/patterns.py` | 按会话简单聚类事件并统计频次 | 纯统计频次，缺乏对 Raw Evidence 与 Episode 的深层聚合能力 | 重构为 `ObservationPipeline`，在后台聚合证据形成结构化观察 | **REPLACE** |
| **`ChapterGenerator`** | `src/core/chapters.py` | 基于四道门控，调用 LLM 生成 Markdown 格式人生章节 | 章节生成依赖未过滤的原始数据；缺少隐私硬删除脱敏联动 | 严格限定输入必须来自 Confirmed Insights 与合法 Episodes；接入 `needs_privacy_redaction` 即时阻断 | **MODIFY** |
| **`MultiAgentHistoryHarvester`**| `src/connectors/history/harvester.py` | 离线挖掘 Hermes/Pi/Codex 历史会话 | 产生大量非规范字段；可能将 Prompt/CoT 写入事件表 | 增加严格隐私清洗管道，生成纯净结构化事件骨架与脱敏错误分类 | **MODIFY** |
| **`CompanionApp`** | `run_companion.py` | PySide6 应用程序编排中心，管理 UI、定时器、托盘与生命周期 | 初始化逻辑混杂；启动时直接运行未隔离的 `prune()`；未实现优雅关机落盘顺序 | 引入细粒度 `FeatureFlags`；接入后台任务调度器；关机时严格优先刷盘 Raw Evidence | **MODIFY** |
| **`ChronicleViewerWindow`** | `src/body/chronicle_window.py` | 桌面伴生体只读足迹查看窗口 | 直接绑定旧 `ChronicleStore.list_slices` 与旧实体字段 | 通过只读兼容适配器或 V2 原生 API 读取，支持作用域展示与隐私标记 | **MODIFY** |

---

## 3. 总体工程实施不变量与安全断言 (Implementation Plan Safety Assertions)

在整个编码实施周期中，所有工作包与 Stage 必须无条件服从以下不可协商的 10 大实施安全断言（**I-S01 ~ I-S10**）：

> ### 10 大实施安全断言 (Implementation Safety Assertions)
> - **I-S01 (Pre-Cutover Writer Boundary)**：在生产割接（Stage 10）之前，V2 存储写入器可以被编码实现与沙箱测试，但**绝对禁止成为生产权威主写**（生产环境 `memory_v2_storage = OFF`，旧 V1 库维持权威事实源）。
> - **I-S02 (Durable Rollback Invariant)**：任何特性开关回退或版本回退，**绝对禁止丢弃已经向用户或调用方返回成功确认（ACK）的写入**。
> - **I-S03 (Post-Cutover Restore Boundary)**：在生产割接并接受了新的 V2 确认写入后，**严禁直接用 `.pre_v2_backup` 物理覆盖当前库**，除非存在经过验证的双向合并脚本；默认恢复策略为前向修复（Forward-Fix）。
> - **I-S04 (Staged Decoupled Rollout)**：生产数据库割接（DB Cutover）**绝对不等于激活全量特性开关**；存储基底割接后，检索、整合、自模型与章节功能必须解耦逐层启用（Stage 10A $\rightarrow$ 10B $\rightarrow$ 10C $\rightarrow$ 10D）。
> - **I-S05 (Feature Flag Fail-Closed)**：特性开关存在严格依赖拓扑；若检测到非法配置组合（如 `self_model_v2=ON` 但 `storage_v2=OFF`），系统**在启动校验中直接 Fail-Closed 并报警，严禁进入异常半态**。
> - **I-S06 (Technical Job Metadata Isolation)**：异步任务队列（`consolidation_jobs` 等）属于**技术运行元数据（Technical Operational Metadata）**，绝对不是第 21 个 Memory 权威实体，不参与检索，不参与自模型论据，不属于数据模型事实源。
> - **I-S07 (Hard Delete Dependency Closure)**：硬删除失效闭环必须覆盖完整依赖图谱：`Raw Evidence -> Semantic Memory -> Observation -> Hypothesis -> Confirmed Insight -> Behavior derivation -> Retention pin -> Retrieval index -> Chapter privacy block`。
> - **I-S08 (Grounded Retrieval Gates)**：实施阶段的检索退出门禁必须**100% 严格继承已冻结的基准实测事实**（DEV $\ge 93.1\%$, HOLDOUT $100\%$, Forbidden $0\%$, 延迟基准 ~1.88ms），严禁凭空捏造未冻结的绝对 100% 门槛或脱离硬件的更低延迟。
> - **I-S09 (All Required Safety Gates Prerequisite)**：生产割接（WP-14）必须等待所有生产必需的工作包（WP-0, 1, 2, 7, 8, 10, 11, 13）全部验收通过，严禁跳过安全门禁提前割接。
> - **I-S10 (Backfill Non-Blocking)**：历史数据异步回填（WP-12）属于割接后的后台低优先级增强，**绝对不是生产割接（WP-14）的前置阻塞依赖**。

---

## 4. 特性开关依赖矩阵与启动校验 (Feature Flag Dependency Matrix)

为杜绝不可能状态在生产运行，确立 6 大开关的严格依赖矩阵：

| 特性开关 (Flag) | 默认值 | 严格前置依赖 (Prerequisites) | 非法组合与错误模式 (Illegal Combination) | 启动校验行为 (Validation Action) |
| :--- | :---: | :--- | :--- | :--- |
| **`memory_v2_storage`** | `False` | 生产已完成 V2 Schema 割接且后置检查 PASS | 生产仍为 V1 Schema 时开启 | **Hard Fail**：启动自检阻断并退出 |
| **`memory_v2_retrieval`** | `False` | 依赖 `memory_v2_storage=ON` 或具备只读兼容读取层 | `storage_v2=OFF` 且无兼容层时开启 | **Fail-Closed**：自动降级为旧版 Retriever |
| **`memory_v2_consolidation`**| `False` | 依赖 `memory_v2_storage=ON` + WP-2 生命周期基建 | `storage_v2=OFF` 时开启 | **Fail-Closed**：自动保持只读，不写库 |
| **`memory_v2_self_model`** | `False` | 依赖 `memory_v2_consolidation=ON` + 观察慢路径 | `consolidation_v2=OFF` 时开启 | **Fail-Closed**：清空候选，不生成假说 |
| **`memory_v2_migration`** | `False` | 维护工具专用；与前台写者互斥（受 MigrationBarrier 管辖） | 前台正常读写未 Quiesce 时强制执行 | **Hard Fail**：迁移 CLI 拒绝执行 |
| **`memory_v2_backfill`** | `False` | 依赖 `storage_v2=ON` + `consolidation_v2=ON` | 核心整合未激活时开启回填 | **Fail-Closed**：回填引擎直接退出 |

---

## 5. 真实回滚地平线规划 (Rollback Horizons)

打破虚假的“任何时刻一键恢复旧库”幻想，将回滚划分为三大具有确定性边界的物理阶段：

```text
       [Pre-cutover 阶段]               [割接但未产生新写入]             [割接后已产生新 V2 写入]
───────────────┼────────────────────────────────┼────────────────────────────────────────► 时间
        R0 地平线                        R1 地平线                        R2 地平线
   (完全无损回滚区)                 (安全恢复旧库区)                (前向修复为主，禁止直接覆盖)
```

1. **R0 地平线 —— Pre-cutover 阶段 (Stage 0 ~ Stage 9)**：
   - **状态**：生产库仍运行于 V1；V2 仅在沙箱、临时库或 Dry-run 中运行；
   - **回滚手段**：代码 Git revert、特性开关关闭、测试临时文件直接删除；
   - **安全性**：**100% 绝对安全无损**。
2. **R1 地平线 —— Cutover before accepting new V2 ACK writes (Stage 10 割接瞬间)**：
   - **状态**：生产库已执行原子重命名切换为 V2，但系统处于维护静默期或刚启动自检，尚未接受并确认任何新切片或事件；
   - **回滚手段**：运行 `python -m src.memory.v2.migration.cli --rollback`，将 `.pre_v2_backup` 文件原子覆盖回原库名；
   - **安全性**：由于零新数据产生，**恢复旧库 100% 绝对无损**。
3. **R2 地平线 —— Post-cutover after new V2 ACK writes exist (Stage 10 运行期与 Stage 11)**：
   - **状态**：伴生体已在 V2 下正式向用户提供服务，用户已投喂了新的切片，或者外部 Connector 已产生了新的事件并获得了 Success ACK；
   - **铁律约束**：**严禁使用 `.pre_v2_backup` 简单粗暴覆盖当前主库**（否则已承诺用户的新数据被彻底抹除，直接击穿 `ACKED WRITE MUST BE DURABLE` 红线）；
   - **恢复策略**：**前向修复（Forward-Fix）为默认恢复策略**；
   - **非降级兜底**：若出现严重逻辑 Bug，关停高层开关（如切回旧检索或暂停整合），保持存储层继续单主运行；若必须倒退存储格式，必须运行专用的反向导出合并工具，将割接后产生的新切片导出再并入旧库，绝不允许直接丢弃。

---

## 6. 生产割接与解耦分阶启用路线 (Staged Post-Cutover Rollout)

彻底废除“割接同时开启全量开关”的 Big-Bang 做法，确立解耦的四步灰度激活路线：

```text
[Stage 10A: 存储底座割接] ──► 生产升级为 V2 Schema, 启用 V2 Canonical Writer, 保持高层心智 OFF
             │
[Stage 10B: 检索流水启用] ──► 影子对比验证后，开启 memory_v2_retrieval，五阶检索接管气泡回忆
             │
[Stage 10C: 整合快路启用] ──► 经 Proposal 审计通过后，开启 memory_v2_consolidation 允许确定性提交
             │
[Stage 10D: 自模型与叙事] ──► 开启 memory_v2_self_model，激活双向校准与人生章节
             │
[Stage 11: 异步历史回填]  ──► 启动后台低优先级 Backfill，逐步提炼历史切片
```

---

## 7. 行为约束与执行模型解耦 (Decoupled Execution Model)

为避免在缺乏跨平台实测证据的情况下过早将线程或进程模型写死：
- **实施规范仅冻结行为约束与契约**：
  1. **零阻塞约束**：任何后台任务（整合、回填、迁移）**绝对禁止阻塞 Qt UI 主循环（单帧延迟 $< 16\text{ms}$）**；
  2. **连接所有权约束**：每个后台任务必须持有**完全独立的 SQLite 连接**，严禁跨线程跨协程共享连接实例；
  3. **资源预算（Performance Budget）**：后台回填以 CPU 占用率 $< 5\%$ 为设计预算目标，在应用退出信号发出时必须在 1.0 秒内响应挂起；
- **具体执行模型（Worker Thread vs QThreadPool vs Process）**：保持架构弹性，留给对应 Stage 的技术任务在 Windows 真实环境下实测选型。

---

## 8. Definition of Done（最终完工验收标准）

V2.1 长期记忆实施方案已正式签署（Signed Off），允许启动 Stage 0：
1. **五层上位规范 100% 自洽**：无任何破坏上位冻结契约的实施漏洞；
2. **Pre/Post-cutover 边界清晰**：Stage 2 严格限制在沙箱验证，生产主写必须在割接后才切换；
3. **回滚承诺完全真实**：明确 R0~R2 地平线，杜绝已确认新数据在回滚中被丢弃；
4. **门禁完全对齐基准**：检索与整合退出门禁严格源于冻结 benchmark 数据；
5. **DAG 依赖无死锁无环路**：生产割接前置依赖覆盖全部安全工作包，回填安全移出关键路径。

```text
================================================================================
             COEVA MEMORY V2.1 IMPLEMENTATION PLAN
                          SIGNED OFF

                    READY TO START
        STAGE 0 — SAFETY HARNESS & FEATURE FLAGS
================================================================================
```
