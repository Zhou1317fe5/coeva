# Co-evolving Companion：跨会话长期记忆 V2.1 分阶段演进与推进路线 (Staged Rollout · Final Consistency Edition)
## ——从 Stage 0 到 Stage 11 的绞杀者演进与系统保活方案

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Staged Rollout)
> - **核心目标**：确保伴生体在长达数周的研发推进中，桌面端始终 100% 正常运行，无任何“黑屏施工期”或功能断崖。

---

## 1. 演进阶段路线图 (Staged Evolution Roadmap)

```text
 Stage 0 ──► Stage 1 ──► Stage 2 ──► Stage 3 ──► Stage 4 ──► Stage 5 ──► Stage 6 ──► Stage 7 ──► Stage 8 ──► Stage 9 ──► Stage 10A ──► Stage 10B/C/D ──► Stage 11
(安全基建)  (存储底座)  (沙箱写入)  (关系生命)  (检索流水)  (整合快路)  (理解慢路)  (叙事集成)  (迁移工具) (金丝雀演练)  (存储割接)    (高层灰度开启)    (后台回填)
```

---

## 2. 各阶段详细演进规程 (Detailed Stage Specifications)

### Stage 0: Safety Harness & Feature Flags（安全基建）
- **核心动作**：
  1. 引入 `src/core/flags.py`，实现特性开关依赖校验矩阵（I-S05）；
  2. 搭建 `tests/memory_v2/` 基础测试框架；
  3. 导入检索与整合的 DEV / HOLDOUT 黄金基准集。
- **运行时状态**：全量 Flags 默认 `False`，伴生体 100% 运行于 V1 原生代码。
- **旧系统可用性保障**：100% 完全不受任何影响。
- **阶段产出**：通过 `test_flags.py`。

---

### Stage 1: V2 Storage on Temporary / Fixture DB（存储底座）
- **核心动作**：
  1. 编写 V2.1 `schema.sql`、`entities.py` 与 `store.py`；
  2. 在内存数据库与临时 SQLite 文件中运行全套 DDL；
  3. 实现基础 CRUD 与显式事务管理器 `with store.transaction():`。
- **运行时状态**：V2 存储仅被单元测试消费，主程序不连接 V2 存储。
- **旧系统可用性保障**：生产主程序继续读写 `companion_chronicle.db`（V1），零干扰。
- **阶段产出**：通过 `test_schema.py`，20 张表与外键检查全部绿灯。

---

### Stage 2: Raw Evidence V2 Writer Implementation & Sandbox Verification（沙箱写入验证）
- **核心动作**：
  1. 编码实现 V2.1 Raw Evidence 写入器（`RawEvidenceRepository`）；
  2. 在沙箱测试库（Sandbox DB）中验证切片与结构化事件写入；
  3. **严格遵守 I-S01 禁令**：生产环境 `memory_v2_storage = OFF`，生产主写必须保持旧 V1 库，绝对不提前切换生产数据格式；
  4. 验证 `ACKED WRITE MUST BE DURABLE` 契约在沙箱环境下完全成立。
- **运行时状态**：生产环境 100% 继续走旧版写入逻辑与旧双写管道。
- **旧系统可用性保障**：生产环境零配置变动，零物理接触。
- **阶段产出**：通过沙箱写入测试，断言新写入器在沙箱库中落盘成功且未越界影响生产。

---

### Stage 3: Typed Provenance, Lifecycle & Hard Delete（关系生命周期）
- **核心动作**：
  1. 实现 `provenance.py` 与关联表访问器；
  2. 落地 `MemoryLifecycleManager`，实现 Hard Delete 完整 8 步依赖闭环遍历（I-S07）；
  3. 落实底层唯一证据归零时的高层撤回（Retract）与隐私阻断（Privacy Pending）。
- **运行时状态**：支持强类型关联增删改查；硬删除具备物理级联防御。
- **旧系统可用性保障**：V1 界面继续正常展示，底层删除操作调用 V2 级联算法。
- **阶段产出**：通过 `test_lifecycle.py`，断言孤儿关联为 0，8 步依赖闭环逻辑完备。

---

### Stage 4: Retriever V2 on V2 Fixture & Parallel Evaluation（检索流水线）
- **核心动作**：
  1. 编码五阶技术检索流水线（`IntentRouter` $\rightarrow$ `ScopeFilter` $\rightarrow$ `FTSLexical` + `SurfaceSimilarity` $\rightarrow$ `Reranker` $\rightarrow$ `FusionSelector`）；
  2. 支持 `NO_MEMORY` 判定与 `RetrievedCandidate`；
  3. 在沙箱与临时库中运行 44 个 DEV/HOLDOUT 冻结用例进行回归评估（I-S08）。
- **运行时状态**：生产环境仍走旧版检索器；新检索器作为库内服务就绪。
- **旧系统可用性保障**：旧版气泡回忆零干扰。
- **阶段产出**：44 个基准用例完全对齐冻结线（HOLDOUT 100% 通过，Forbidden 0%），同硬件环境实测耗时在 ~1.88ms 基线范围内。

---

### Stage 5: Consolidation Fast Path（心智整合快路径）
- **核心动作**：
  1. 落地 `AdmissionFilter`、`CandidateExtractor` 与 `DeterministicReconciliationValidator`；
  2. 抽象 `ProposalProvider`，接入本地/API 大模型；
  3. 实现增量感知防回声守卫（`EchoGuard`）；
  4. 建立持久化队列元数据 `consolidation_jobs`（明确为技术运行元数据，I-S06）并启动后台调度器。
- **运行时状态**：在测试沙箱中完成异步合并流转验证，生产环境保持只读。
- **旧系统可用性保障**：前台气泡秒级响应，心流零打断。
- **阶段产出**：通过 35 个 Consolidation 冻结基准用例，False SUPERSEDE = 0。

---

### Stage 6: Observation, Hypothesis & Calibration Slow Path（理解慢路径）
- **核心动作**：
  1. 实现 `ObservationPipeline`，在系统空闲时对跨会话经历聚类生成 Observation；
  2. 结合 ACT 六大透镜生成候选假说（Hypothesis），严格隔离为 candidate；
  3. 接入用户双向校准（Human Calibration），实现向 `confirmed_insights` 的转正。
- **运行时状态**：在沙箱中验证心智演化逻辑，生产环境不加载新假说。
- **旧系统可用性保障**：未校准前绝不主动输出高层心理结论，严格保持 80/15/5 静默原则。
- **阶段产出**：通过 `test_observation.py`，验证假说非校准不转正。

---

### Stage 7: Chapter Integration & Privacy Redaction（人生章节与隐私集成）
- **核心动作**：
  1. 改造 `ChapterGenerator`：仅消费已验证共识与合法经历；
  2. 接入 `needs_privacy_redaction` 物理禁读守卫与后台脱敏重写 Worker；
  3. 确保叙事文本绝不反向污染为认知证据。
- **运行时状态**：章节逻辑改造完成，等待底层生产割接。
- **旧系统可用性保障**：无新章节生成时静默；隐私删除时即时展示“脱敏重写中”。
- **阶段产出**：通过 `test_chapter_privacy.py`。

---

### Stage 8: Migration Tooling & MigrationBarrier（独立迁移工具）
- **核心动作**：
  1. 实现命令行独立迁移工具（`MigrationCLI`）与 `MigrationBarrier`；
  2. 实现动态文件集磁盘空间检查门禁；
  3. 实现主键集合差分同步与确定性冲突检查；
  4. 严格禁止在应用启动中静默自动迁移。
- **运行时状态**：迁移工具作为独立维护脚本存在，生产库保持运行。
- **旧系统可用性保障**：未执行迁移前，生产库原封不动。
- **阶段产出**：CLI dry-run 演练通过，`test_migration_cli.py` 100% PASS。

---

### Stage 9: Canary Migration Rehearsal（隔离金丝雀全量演练）
- **核心动作**：
  1. 抓取真实生产数据库快照副本（47.55MB，11.6万事件）；
  2. 运行 `canary_rehearsal.py`；
  3. 注入全部对抗故障（删除最大ROWID后插入、重复重放、冲突篡改、Barrier期崩溃）；
  4. 检验 M-S01 ~ M-S18 全部 18 项安全断言（I-S09）。
- **运行时状态**：演练在沙箱目录完成，生产系统正常服务用户。
- **旧系统可用性保障**：零物理接触生产库。
- **阶段产出**：18 / 18 PASS，Data Loss = 0，切片逐字哈希 100% 一致。

---

### Stage 10: Production Cutover & Staged Feature Activation（生产割接与解耦分阶启用）

彻底废除“割接同时开启全量开关”的 Big-Bang 做法，拆分为解耦的四步演进（I-S04）：

#### Stage 10A — Storage Cutover（存储底座割接）
- **核心动作**：
  1. 伴生体安全关机；
  2. 运行 `python -m src.memory.v2.migration.cli --execute`；
  3. 完成在线备份、影子构建、差分校验与原子替换，生成 `.pre_v2_backup`；
  4. 生产主库版本置为 `user_version = 20261018`；
  5. 启动伴生体，**正式激活 `memory_v2_storage = ON`**；
  6. 建立只读兼容视图，切断 `raw_slices.jsonl` 双主写入，确立 SQLite 唯一权威主写；
  7. **高层语义开关（retrieval, consolidation, self_model）继续保持 OFF**。
- **产出**：存储层平稳过渡至 V2.1，存量功能完全正常。

#### Stage 10B — Retrieval Enable（检索流水启用）
- **核心动作**：在存储割接运行平稳后，开启 `memory_v2_retrieval = ON`，五阶检索流水线正式接管桌面气泡回忆。
- **产出**：跨会话高精回忆上线，避风港模式熔断生效。

#### Stage 10C — Consolidation Enable（整合快路启用）
- **核心动作**：先在 Dry-run/Audit 模式观察提议质量，确认无异常后开启 `memory_v2_consolidation = ON`，允许本地确定性原子提交。
- **产出**：近实时原子事实提炼上线，防回声守卫持续生效。

#### Stage 10D — Self Model & Chapter Enable（自模型与叙事启用）
- **核心动作**：开启 `memory_v2_self_model = ON`，激活低频观察聚合、候选假说生成与用户双向校准，章节生成接入新记忆。
- **产出**：完整长期心智体系全部就绪。

---

### Stage 11: Background Backfill Engine（历史数据后台回填）
- **核心动作**：
  1. 启动独立后台回填进程：`python -m src.memory.v2.backfill_cli --run`（I-S10）；
  2. 倒序读取存量历史切片，低优先级提炼原子事实；
  3. 严格限制 CPU 占用 $< 5\%$（设计预算目标），支持随应用关机秒级挂起。
- **运行时状态**：存量切片逐步被提炼为原子事实，历史自模型不断丰满。
- **旧系统可用性保障**：后台低优先级运行，桌面伴生体前台流畅自如。
- **阶段产出**：回填完成，长期自模型与经历体系高度自洽。
