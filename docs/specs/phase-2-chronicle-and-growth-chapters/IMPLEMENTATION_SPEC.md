---
id: companion-memory-v2.1-implementation
type: module-design
title: 跨会话长期记忆 V2.1 工程实施计划与施工规程规范
parent: companion-phase-2-growth-core-and-chronicle
status: active
version: 1.0
depends-on:
  - companion-phase-2-growth-core-and-chronicle
  - companion-architecture-design
tags:
  - memory-v2
  - implementation-plan
  - wbs
  - staged-rollout
  - strangler-fig
---

# 跨会话长期记忆 V2.1 工程实施计划与施工规程规范

> **规范元数据与事实源绑定**：
> - **阶段定位**：Implementation Specification (V2.1 Implementation Plan)
> - **状态**：`STAGE 0 & STAGE 1 SIGNED OFF; STAGE 2 (RAW EVIDENCE WRITE PATH) IMPLEMENTED & VERIFIED`
> - **核心实施文件集**（位于 `docs/memory-v2/implementation/`）：
>   1. [`implementation-plan.md`](../../memory-v2/implementation/implementation-plan.md) —— 总体实施规划大纲与工程纪律
>   2. [`work-breakdown.md`](../../memory-v2/implementation/work-breakdown.md) —— WP-0 至 WP-14 全量工作分解结构 (WBS)
>   3. [`dependency-graph.md`](../../memory-v2/implementation/dependency-graph.md) —— 施工依赖 DAG 与关键路径分析
>   4. [`file-change-map.md`](../../memory-v2/implementation/file-change-map.md) —— 改动、新增与退役文件完整清单 (31 个新增模块、15 个修改文件、3 项退役资产)
>   5. [`staged-rollout.md`](../../memory-v2/implementation/staged-rollout.md) —— Stage 0 至 Stage 11 绞杀者分阶推进路线 (Stage 10A~10D 分阶启用)
>   6. [`test-gates.md`](../../memory-v2/implementation/test-gates.md) —— 各阶段客观物理退出门禁与测试矩阵 (对齐 Frozen Benchmark)
>   7. [`rollback-plan.md`](../../memory-v2/implementation/rollback-plan.md) —— R0~R2 三大回滚地平线与前向修复优先边界
>   8. [`implementation-risk-register.md`](../../memory-v2/implementation/implementation-risk-register.md) —— 十二大工程风险防御与闭环处置

---

## 1. 实施目标与 10 大安全断言 (I-S01 ~ I-S10)

本实施规程将 Architecture V2.1、Logical Data Model V2.1、Technical Retrieval V2.1、Consolidation V2.1 与 Migration V2.1 五大冻结上位规范转化为可执行工程步骤，全周期受 10 大实施安全断言管辖：

1. **I-S01 (Pre-Cutover Writer Boundary)**：割接前 V2 写入器可沙箱实现，但生产环境 `memory_v2_storage = OFF`，旧 V1 库绝对维持权威主写；
2. **I-S02 (Durable Rollback Invariant)**：任何回滚绝不可丢弃已向用户或调用方返回成功确认（ACK）的写入；
3. **I-S03 (Post-Cutover Restore Boundary)**：生产割接后产生新 V2 数据后严禁直接物理覆盖旧库，前向修复（Forward-Fix）为默认恢复策略；
4. **I-S04 (Staged Decoupled Rollout)**：生产割接（Stage 10A）与高层心智开关（10B 检索、10C 整合、10D 假说与叙事）解耦分阶启用；
5. **I-S05 (Feature Flag Fail-Closed)**：特性开关依赖校验，非法组合在启动时直接 Fail-Closed 阻断；
6. **I-S06 (Technical Job Metadata Isolation)**：队列数据明确为技术运行元数据，绝对不是第 21 个 Memory 实体，不入检索/不入自模型；
7. **I-S07 (Hard Delete Dependency Closure)**：硬删除失效闭环必须覆盖完整 8 步依赖图谱；
8. **I-S08 (Grounded Retrieval Gates)**：实施阶段检索门禁 100% 严格继承冻结基准实测事实（DEV $\ge 93.1\%$, Holdout $100\%$, Forbidden $0\%$, 延迟基准 ~1.88ms）；
9. **I-S09 (All Required Safety Gates Prerequisite)**：生产割接必须汇聚全部生产必需安全工作包（WP-0, 1, 2, 7, 8, 10, 11, 13）；
10. **I-S10 (Backfill Non-Blocking)**：历史数据异步回填（WP-12）属于割接后的后台低优先级增强，绝对不阻碍生产割接。

---

## 2. 施工工作包拆解 (WBS WP-0 ~ WP-14)

施工全过程拆解为 15 个标准化工作包：
- **WP-0**: Safety Harness & Feature Flags（特性开关与测试基建，依赖校验矩阵）
- **WP-1**: V2.1 Storage Layer & Schema Abstraction（20 个强类型表结构与 CRUD）
- **WP-2**: Typed Provenance & Lifecycle Infrastructure（类型化关系表与 Hard Delete 8步依赖闭环）
- **WP-3**: Admission & Candidate Extraction（准入过滤与候选语义提议提取）
- **WP-4**: Reconciliation Validator & Deterministic Engine（调和校验器与确定性原子提交）
- **WP-5**: Consolidation Scheduler & Near-Real-Time Queue（近实时后台队列与防抖调度，队列元数据隔离）
- **WP-6**: Observation, Hypothesis & Calibration Pipeline（观察慢路径与用户双向校准）
- **WP-7**: Technical Retrieval V2.1 Pipeline（五阶技术检索流水线，零向量依赖）
- **WP-8**: Recall Gate & Sanctuary Mode Integration（回忆门控与避风港物理熔断）
- **WP-9**: Chapter & Privacy Redaction Integration（人生章节与隐私脱敏重写集成）
- **WP-10**: Migration Tooling & MigrationBarrier（独立迁移 CLI 工具与 Hard Quiesce 屏障）
- **WP-11**: Legacy Compatibility Layer & Dual-Master Elimination（兼容视图与单主写入终结）
- **WP-12**: Background Backfill Engine（后台低优先级历史数据异步回填，I-S10）
- **WP-13**: Full Canary Migration & Safety Rehearsal（生产全量副本金丝雀演练与 M-S01~M-S18 断言）
- **WP-14**: Production Cutover & Post-Cutover Verification（生产原子割接与 Stage 10A 验证，I-S09）

---

## 3. 施工演进与阶段状态记录

### 历史完成阶段
1. **Stage 0 (WP-0: Safety Harness & Feature Flags)**：`COMPLETED & SIGNED OFF`
   - 细粒度特性开关、依赖矩阵校验（I-S05）、Fail-Closed 启动门禁与 10 大实施不变量追溯测试全部通过。
2. **Stage 1 (WP-1: V2.1 Storage Layer & Schema Abstraction)**：`COMPLETED & SIGNED OFF`
   - 20 大实体与 4 大技术元数据 DDL、不可变强类型模型、显式事务底座、漂移防御完成；
   - 完成外键删除语义治理：18 处关键外键切换为 `ON DELETE RESTRICT`，彻底断绝盲目级联删除；
   - 完成 IMPL-2 强类型多源溯源（支持切片、事件、经历）与零证据记忆阻断，S1-D01~D07 及 S1-P01~P06 测试通过。

### 当前阶段：Stage 2 (WP-2: Raw Evidence Write Path)
- **状态**：`IMPLEMENTED & VERIFIED — READY FOR REVIEW`
- **交付成果**：
  - `src/memory/v2/write_service.py`：`RawEvidenceWriteService`（切片内容保真、未分配项目安全降入 `unresolved`、事件隐私脱敏严格丢弃 Prompt/CoT/返回值）；
  - 核心物理写入不变量：`ACKED WRITE MUST BE DURABLE`（提交落盘后方返回成功 ACK，事务失败零残留）；
  - 幂等与冲突防御：相同 Payload 重放 `idempotent_replay`，变异 Payload 立即 `WriteConflictError` 阻断；
  - `src/memory/v2/router.py`：路由抽象（生产环境默认保持 V1，沙箱测试显式切 V2）；
  - `tests/memory_v2/` 5 个新增测试模块（20 个针对性用例，W-S01 ~ W-S12 全覆盖通过）；
  - 生产数据库 `data/companion_chronicle.db` 保持 100% 物理零触碰。

当前状态：

`STAGE 2 IMPLEMENTATION COMPLETE — READY FOR REVIEW — DO NOT ENTER STAGE 3`
