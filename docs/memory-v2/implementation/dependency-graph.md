# Co-evolving Companion：跨会话长期记忆 V2.1 依赖关系有向无环图 (Dependency DAG · Final Consistency Edition)
## ——关键路径分析、串行约束与无歧义 DAG

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Dependency DAG)
> - **核心原则**：明确哪些工作包必须严格串行等待，哪些工作包可以在接口冻结后并行推进；确保施工过程零死锁、零依赖环，严禁伪允许割接的缺陷 DAG。

---

## 1. WBS 依赖关系总览表 (Work Package Dependency Table)

| 工作包编号 | 名称 (Work Package) | 直接前置依赖 (Direct Prerequisites) | 关键路径节点 (Critical Path)? | 割接前置阻塞要求 (Pre-Cutover Blocker)? |
| :--- | :--- | :--- | :---: | :---: |
| **WP-0** | Safety Harness & Feature Flags | (无) | **YES** | **YES** |
| **WP-1** | V2.1 Storage Layer & Repository Abstraction | WP-0 | **YES** | **YES** |
| **WP-2** | Typed Provenance & Lifecycle Infrastructure | WP-1 | **YES** | **YES** |
| **WP-3** | Admission & Candidate Extraction | WP-1 | NO | **YES** (调和前提) |
| **WP-4** | Reconciliation Validator & Deterministic Engine | WP-2, WP-3 | **YES** | **YES** (调和前提) |
| **WP-5** | Consolidation Scheduler & Near-Real-Time Queue | WP-3, WP-4 | NO | **YES** (调度前提) |
| **WP-6** | Observation, Hypothesis & Calibration Pipeline | WP-2, WP-5 | NO | **YES** (自模型前提) |
| **WP-7** | Technical Retrieval V2.1 Pipeline | WP-1 | **YES** | **YES** (回忆前提) |
| **WP-8** | Recall Gate & Sanctuary Mode Integration | WP-7 | **YES** | **YES** (回忆安全前提) |
| **WP-9** | Chapter & Privacy Redaction Integration | WP-2, WP-6 | NO | **YES** (叙事安全前提) |
| **WP-10**| Migration Tooling & MigrationBarrier | WP-1, WP-2 | **YES** | **YES** (工具前提) |
| **WP-11**| Legacy Compatibility Layer & Dual-Master Elimination | WP-1, WP-10 | **YES** | **YES** (兼容前提) |
| **WP-13**| Full Canary Migration & Safety Rehearsal | WP-10, WP-11 | **YES** | **YES** (安全演练终审) |
| **WP-14**| Production Cutover & Post-Cutover Verification | WP-0 ~ WP-13 全部通过 (I-S09) | **YES** | **YES** (生产切换) |
| **WP-12**| Background Backfill Engine | WP-4, WP-5, WP-14 (I-S10) | NO | **NO (Post-cutover 可选增强)** |

---

## 2. 施工依赖无歧义有向无环图 (Dependency DAG)

```text
[WP-0: Safety Harness & Feature Flags]
       │
       ▼
[WP-1: V2.1 Storage Layer & Schema Abstraction]
       │
       ├─────────────────────────────────────────────┬────────────────────────────────┐
       ▼                                             ▼                                ▼
[WP-2: Typed Provenance & Lifecycle]          [WP-3: Admission]                [WP-7: Technical Retrieval V2.1]
       │                                             │                                │
       ├───────────────────────┬─────────────────────┤                                ▼
       │                       ▼                     │                         [WP-8: Recall Gate & Sanctuary]
       │              [WP-4: Reconciliation]         │                                │
       │                       │                     │                                │
       │                       ▼                     │                                │
       │              [WP-5: Sched & Queue]◄─────────┘                                │
       │                       │                                                      │
       │                       ▼                                                      │
       │              [WP-6: Observation/Hyp]                                         │
       │                       │                                                      │
       ▼                       ▼                                                      │
[WP-9: Chapter & Privacy]      │                                                      │
       │                       │                                                      │
       ├───────────────────────┴─────────────────────┐                                │
       ▼                                             ▼                                │
[WP-10: Migration Tooling & Barrier]                 │                                │
       │                                             │                                │
       ▼                                             │                                │
[WP-11: Legacy Compatibility Layer]                  │                                │
       │                                             │                                │
       ▼                                             │                                │
[WP-13: Full Canary Migration Rehearsal]◄────────────┴────────────────────────────────┘
       │
       ▼
[WP-14: Production Cutover & Stage 10A Verification] (I-S09: 必须汇聚全部安全工作包)
       │
       ├─────────────────────────────────────────────┐
       ▼                                             ▼
[Stage 10B/10C/10D 语义功能灰度开启]           [WP-12: Background Backfill Engine] (I-S10)
```

---

## 3. 依赖规则与安全断言对齐

1. **WP-3 在 WP-4 之前**：调和校验器以候选提取对象 `ProposedFactCandidate` 为输入，因此 WP-3 必须前置于 WP-4；
2. **WP-5 依赖 WP-3 与 WP-4**：近实时调度队列必须同时调度准入抽取与调和校验，因此依赖前二者；
3. **WP-8 依赖 WP-7**：回忆门控与避风港熔断直接包裹五阶检索流水线，严格继承 WP-7 接口；
4. **WP-11 必须在 WP-14 之前**：只读兼容视图与双主切除准备必须在生产割接前就绪，确保割接后旧组件读取无缝；
5. **WP-14 生产割接汇聚全部前置安全包（I-S09）**：生产割接严禁仅依赖迁移工具，必须经由 WP-13 金丝雀演练验证过存储、关系、检索门控与调和校验全套闭环；
6. **WP-12 移出割接前置关键路径（I-S10）**：历史数据回填明确依赖生产已处于 V2（WP-14 之后），绝对不阻碍生产割接。
