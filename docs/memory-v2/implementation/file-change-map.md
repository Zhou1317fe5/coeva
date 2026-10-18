# Co-evolving Companion：跨会话长期记忆 V2.1 文件级变更映射表 (File Change Map · Final Consistency Edition)
## ——改动文件、新增模块、待退役资产与测试清单全量详勘

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 File Change Map)
> - **审计口径**：以真实 Git 代码库拓扑为准，杜绝虚构文件路径；精确盘点每一个新增与修改文件，消除统计歧义（P1-4）。

---

## 1. 现有需修改文件清单 (Existing Files to Modify · 共 15 个文件)

| 序号 | 现有文件路径 | 所属子系统 | 影响工作包 (WP) | 具体改动点与接口重构 (Changes & Interfaces) |
| :---: | :--- | :--- | :---: | :--- |
| **1** | **`run_companion.py`** | 桌面入口与装配中心 | WP-0, WP-8, WP-11, WP-14 | 1. 注入 `MemoryFeatureFlags` 启动依赖校验；<br>2. 预备 V2 存储与检索接入分支；<br>3. 切片投喂与气泡回复接入 `RecallGate`；<br>4. 优化退出关机流程，确保 Raw Evidence 优先刷盘。 |
| **2** | **`src/connectors/settings.py`** | 配置管理 | WP-0 | 扩展 `AgentSettingsStore`，增加 `memory_v2_*` 开关项持久化与读取接口。 |
| **3** | **`src/feeder/storage.py`** | 投喂存储 | WP-11 | 废除作为主写事实源的角色；改造为 SQLite 事务提交后的单向可选异步导出器。 |
| **4** | **`src/connectors/event_bus.py`** | 事件总线 | WP-10, WP-11 | 接入 `MigrationBarrier` 状态检测；在 Barrier 激活期间暂停发出确认；更新事件持久化契约至 V2 规范。 |
| **5** | **`src/core/sanctuary.py`** | 避风港守卫 | WP-8 | 增加向 `RecallGate` 暴露的细粒度属性（区分瞬时负向情绪与深度抗拒）。 |
| **6** | **`src/core/self_model.py`** | 共同自模型 | WP-6 | 改造 `ConfirmedInsight` 交互逻辑，确保必须源于 `DevelopmentHypothesis` 的用户显式校准，支持 `calibrated_statement`。 |
| **7** | **`src/core/hypotheses.py`** | 假说引擎 | WP-6 | 调整假说生成来源，从绑定单会话 Pattern 改为消费 V2.1 `observations`。 |
| **8** | **`src/core/chapters.py`** | 人生章节 | WP-9 | 1. 生成上下文仅允许消费 `confirmed_insights` 与合法经历；<br>2. 增加 `needs_privacy_redaction` 即时禁读与异步脱敏重写逻辑。 |
| **9** | **`src/core/personality.py`** | 提示词渲染 | WP-8 | 格式化记忆片段时支持 `RetrievedCandidate` 的来源透出与时间标签。 |
| **10**| **`src/body/chronicle_window.py`**| 足迹查看器 | WP-9, WP-11 | 适配 V2.1 实体展示；支持显示作用域（scope）与隐私状态标签。 |
| **11**| **`src/body/settings_window.py`** | 设置窗口 | WP-0 | 在设置界面增加“高级功能 / 长期记忆 V2.1”特性开关调试选项（仅在 Debug 模式可见）。 |
| **12**| **`src/connectors/history/harvester.py`** | 历史会话挖掘器 | WP-10 | 增加事件字段级隐私过滤，确保挖掘出的历史事件骨架 100% 不含 Prompt/CoT。 |
| **13**| **`src/memory/__init__.py`** | 记忆包入口 | WP-1, WP-7 | 暴露 `ChronicleStoreV2` 与 `MemoryRetrieverV2`。 |
| **14**| **`src/memory/store.py`** | 存量存储单体 | WP-11 | 保持存量接口签名不变，内部桥接至 V2 兼容视图与 Repository，作为过渡兼容门面。 |
| **15**| **`src/memory/retriever.py`** | 存量检索器 | WP-8 | 保持存量签名，当 `memory_v2_retrieval` 开启时透明转发给 V2 五阶检索流水线。 |

---

## 2. 新增模块与包清单 (New Modules to Create · 共 31 个文件)

所有新增文件分类清晰，物理隔离在 `src/memory/v2/` 与对应核心目录下：

### 2.1 核心通用与存储模块 (Core & Storage · 共 10 个文件)
| 序号 | 新增文件路径 | 所属工作包 (WP) | 核心暴露类 / 函数 / 契约 |
| :---: | :--- | :---: | :--- |
| **1** | `src/core/flags.py` | WP-0 | `MemoryFeatureFlags`, `get_flags()`, `override_flags()` |
| **2** | `src/core/recall_gate.py` | WP-8 | `RecallGate` (Sanctuary hard block & 80/15/5 guard) |
| **3** | `src/memory/v2/__init__.py` | WP-1 | 导出 V2 核心 API 入口 |
| **4** | `src/memory/v2/entities.py` | WP-1 | 20 个强类型不可变实体类 `@dataclass(frozen=True)` |
| **5** | `src/memory/v2/schema.sql` | WP-1 | 20 张物理表、FTS5 虚表、触发器与索引 DDL SQL |
| **6** | `src/memory/v2/store.py` | WP-1 | `ChronicleStoreV2`, `RawEvidenceRepository`, `SemanticRepository` |
| **7** | `src/memory/v2/provenance.py` | WP-2 | `ProvenanceRef`, `TypedLinkAccessor` |
| **8** | `src/memory/v2/lifecycle.py` | WP-2 | `MemoryLifecycleManager` (Hard Delete 8步依赖闭环) |
| **9** | `src/memory/v2/compatibility.py` | WP-11 | `CompatibilityViewMonitor`, `LegacyViewAdapter` |
| **10**| `src/memory/v2/backfill.py` | WP-12 | `BackfillEngine`, `BackfillProgressTracker` |

### 2.2 心智整合与理解模块 (Consolidation & Understanding · 共 9 个文件)
| 序号 | 新增文件路径 | 所属工作包 (WP) | 核心暴露类 / 函数 / 契约 |
| :---: | :--- | :---: | :--- |
| **11**| `src/memory/v2/admission.py` | WP-3 | `AdmissionFilter`, `AdmissionDecision` |
| **12**| `src/memory/v2/extractor.py` | WP-3 | `CandidateExtractor`, `ProposedFactCandidate` |
| **13**| `src/memory/v2/proposal_provider.py` | WP-4 | `ProposalProvider` (ABC), `OpenAIProposalProvider` |
| **14**| `src/memory/v2/echo_guard.py` | WP-4 | `EchoGuard` (Strip echoes, preserve user delta) |
| **15**| `src/memory/v2/reconciliation.py` | WP-4 | `DeterministicReconciliationValidator`, `CommitPlan` |
| **16**| `src/memory/v2/queue.py` | WP-5 | `ConsolidationTaskQueue` (明确为技术运行元数据) |
| **17**| `src/memory/v2/scheduler.py` | WP-5 | `ConsolidationScheduler` (防抖近实时调度器) |
| **18**| `src/memory/v2/observation.py` | WP-6 | `ObservationPipeline` (跨会话聚类慢路径) |
| **19**| `src/memory/v2/calibration.py` | WP-6 | `CalibrationManager` (用户双向校准四态管理) |

### 2.3 技术检索子包 (Technical Retrieval Subpackage · 共 8 个文件)
| 序号 | 新增文件路径 | 所属工作包 (WP) | 核心暴露类 / 函数 / 契约 |
| :---: | :--- | :---: | :--- |
| **20**| `src/memory/v2/retrieval/__init__.py` | WP-7 | 导出 `MemoryRetrieverV2` |
| **21**| `src/memory/v2/retrieval/router.py` | WP-7 | Stage 1: `IntentRouter` |
| **22**| `src/memory/v2/retrieval/scope.py` | WP-7 | Stage 2: `ScopeFilter` |
| **23**| `src/memory/v2/retrieval/lexical.py` | WP-7 | Stage 3A: `FTSLexicalChannel` |
| **24**| `src/memory/v2/retrieval/surface.py` | WP-7 | Stage 3B: `SurfaceSimilarityChannel` |
| **25**| `src/memory/v2/retrieval/reranker.py` | WP-7 | Stage 4: `TemporalContextReranker` |
| **26**| `src/memory/v2/retrieval/fusion.py` | WP-7 | Stage 5: `FusionSelector` & `NO_MEMORY` |
| **27**| `src/memory/v2/retrieval/pipeline.py` | WP-7 | 统一流水线 `MemoryRetrieverV2` |

### 2.4 迁移与运维子包 (Migration Subpackage & CLI · 共 4 个文件)
| 序号 | 新增文件路径 | 所属工作包 (WP) | 核心暴露类 / 函数 / 契约 |
| :---: | :--- | :---: | :--- |
| **28**| `src/memory/v2/migration/__init__.py` | WP-10 | 导出迁移工具入口 |
| **29**| `src/memory/v2/migration/barrier.py` | WP-10 | `MigrationBarrier` (Hard Quiesce 写入确认屏障) |
| **30**| `src/memory/v2/migration/executor.py` | WP-10 | `MigrationExecutor` (快照、影子构建、差分校验与原子置换) |
| **31**| `src/memory/v2/migration/cli.py` | WP-10 | 命令行独立入口 `python -m src.memory.v2.migration.cli` |

---

## 3. 待退役资产与废除计划 (Files to Retire / Deprecate · 共 3 项)

| 序号 | 资产路径 | 资产性质 | 退役触发条件 (Retirement Gate) | 替代方案 |
| :---: | :--- | :--- | :--- | :--- |
| **1** | **`data/raw_slices.jsonl` (双主写入身份)** | 物理数据文件 | Stage 10A 实施完毕，SQLite 成为唯一权威主写 | 降级为 SQLite 事务提交后的单向可选导出镜像。 |
| **2** | **`src/core/patterns.py`** | 废弃代码模块 | WP-6 上线运行稳定后 | 完全由 `src/memory/v2/observation.py` 替代。 |
| **3** | **`legacy_slices_view` / `legacy_events_view`** | SQLite 兼容视图 | 伴生体生产组件完成向 V2 改造且连续 7 天零读取 | 执行 `DROP VIEW` 彻底退场。 |

---

## 4. 自动化测试文件清单 (Test Harness Files · 共 14 个文件)

```text
tests/
├── test_flags.py                  # WP-0: 特性开关与依赖矩阵单元测试
└── memory_v2/
    ├── test_schema.py             # WP-1: 20张表结构、外键、约束验证
    ├── test_lifecycle.py          # WP-2: 硬删除 8 步依赖闭环测试
    ├── test_admission.py          # WP-3: 准入与候选抽取基准测试
    ├── test_reconciliation.py     # WP-4: 35 个冻结用例与 S-01~S-14 断言
    ├── test_scheduler.py          # WP-5: 防抖队列与并发整合测试
    ├── test_observation.py        # WP-6: 观察慢路径与校准状态机测试
    ├── test_retrieval.py          # WP-7: 44 个 DEV/HOLDOUT 检索基准测试
    ├── test_sanctuary_recall.py   # WP-8: 避风港模式物理熔断测试
    ├── test_chapter_privacy.py    # WP-9: 章节脱敏即时阻断测试
    ├── test_migration_cli.py      # WP-10: 迁移命令行与断点恢复测试
    ├── test_compatibility.py      # WP-11: 兼容视图与单主写入测试
    ├── test_backfill.py           # WP-12: 异步回填限频与幂等测试
    └── canary_rehearsal.py        # WP-13: 全量 M-S01~M-S18 金丝雀测试套件
```
