# Co-evolving Companion：跨会话长期记忆 V2.1 实施风险登记册 (Implementation Risk Register · Final Consistency Edition)
## ——十二项工程风险定级、物理防御动作与自动化监测规程

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Risk Register)
> - **编制目标**：系统性识别编码与落地过程中的各类风险，确保每个风险均有对应的严重度评定、防御措施与监测机制；融入三大回滚地平线与 I-S01~I-S10 实施不变量。

---

## 1. 核心风险总览与定级矩阵 (Risk Assessment Matrix)

| 风险编号 | 风险名称 (Risk Description) | 发生概率 (Likelihood) | 破坏影响 (Impact) | 风险等级 (Severity) | 核心应对策略 (Mitigation Strategy) | 运行时监测与捕获机制 (Detection) |
| :---: | :--- | :---: | :---: | :---: | :--- | :--- |
| **RSK-01** | **SQLite Schema Mismatch**<br>(代码实体与数据库 DDL 字段不一致) | Medium | High | **HIGH** | 严格基于 Frozen Data Model 生成 `entities.py`；在 WP-1 建立结构一致性自动化测试，逐字段校验。 | `test_schema.py` 自动化比对实体字段与 `PRAGMA table_info`。 |
| **RSK-02** | **Qt Thread Blocking**<br>(密集计算或网络 I/O 阻塞 Qt UI 主循环) | High | High | **CRITICAL** | 确立严格线程行为约束：检索、整合、迁移与回填在独立工作线程中运行，主线程帧延迟超过 16ms 报警。 | UI 帧率监测守护器；开发模式下主线程慢操作自动告警。 |
| **RSK-03** | **Dual Writer Regression**<br>(旧代码意外继续写入 `raw_slices.jsonl`) | Medium | High | **HIGH** | 在 WP-11 彻底重构 `SliceStore.save`，将其设为只读或仅在 SQLite 事务成功后触发异步导出，消除双写裂脑。 | 注入文件监听器（Watcher），若检测到未通过 SQLite 代理的独立写入则告警。 |
| **RSK-04** | **Orphan Provenance**<br>(高层认知引用的底层证据被删除变成孤儿) | Medium | High | **HIGH** | 在 WP-2 优先落地 `MemoryLifecycleManager`，强制执行硬删除 8 步完整依赖闭环（I-S07）与撤回。 | `PRAGMA foreign_key_check` 与 `test_lifecycle.py` 8 步孤儿扫描。 |
| **RSK-05** | **False SUPERSEDE**<br>(心智整合误将独立偏好判定为替代) | Medium | High | **HIGH** | 强制执行 Fail-Closed 策略：当置信度不足或存在歧义时，一律判定为 `AMBIGUOUS` 或 `NOOP`，严禁擅自覆盖。 | 持续运行 35 个 Consolidation 基准测试，断言 False SUPERSEDE = 0。 |
| **RSK-06** | **Echo Self-Reinforcement**<br>(伴生体把自身说过的话误当成用户新论据) | High | Medium | **HIGH** | 在 WP-4 落地 `EchoGuard`，剥离镜像复述，纯确认回响判定为 `NOOP_LONG_TERM`，且同会话重试不递增证明计数。 | 35 个基准测试中包含 Echo 用例，断言递增数严格为 0。 |
| **RSK-07** | **Privacy Stale Artifact**<br>(用户隐私删除后，章节或提示词仍输出旧明文) | Low | Critical | **CRITICAL** | 落实 `IMPL-INV-7`：删除发生时立刻标记 `needs_privacy_redaction = 1`，检索与组装器即时物理过滤旧明文。 | `test_chapter_privacy.py` 验证带标记章节物理不可读。 |
| **RSK-08** | **Post-Cutover Rollback Data Loss**<br>(割接后发生故障，直接覆盖旧库导致新切片被抹除) | Medium | Critical | **CRITICAL** | 确立 R2 地平线铁律：生产已接受新 V2 写入后**严禁覆盖旧库**；前向修复（Forward-Fix）为默认恢复策略（I-S02, I-S03）。 | CLI 工具禁止在已存在后置写入时执行 `--rollback`，除非携带显式导出确认参数。 |
| **RSK-09** | **Connector ACK Loss**<br>(Barrier 期间进程崩溃导致已确认写入丢失) | Low | Critical | **CRITICAL** | 冻结 `ACKED WRITE MUST BE DURABLE` 不变量；Hard Quiesce 期间外部写入未落盘前绝不发出 Success ACK。 | 崩溃注入断言 M-S17 / M-S18 100% 验证覆盖。 |
| **RSK-10** | **Backfill Resource Spike**<br>(历史数据回填导致 CPU 飙升或桌宠卡顿) | High | Medium | **MEDIUM** | 回填引擎设定严格的设计预算目标（CPU $< 5\%$），与应用关机信号联动，1.0 秒内优雅挂起（I-S10）。 | 资源监测守护器，超出阈值自动挂起回填进程。 |
| **RSK-11** | **Invalid Flag Combinations**<br>(特性开关非法组合导致逻辑半态) | Low | High | **HIGH** | 建立特性开关依赖矩阵（I-S05）；在应用启动初始化时强制校验依赖，非法组合直接 Fail-Closed 拒绝启动。 | `test_flags.py` 专项覆盖非法依赖组合启动阻断。 |
| **RSK-12** | **Sanctuary Mode Leakage**<br>(用户心烦受挫时，桌宠仍不合时宜地翻旧账) | Low | High | **HIGH** | 在 `RecallGate` 处建立硬熔断门禁，若 `SanctuaryGuard.is_active` 为真，反思性回忆与心理洞察直接清空为 0。 | `test_sanctuary_recall.py` 专项断言在受挫场景下召回集合为空。 |

---

## 2. 风险处置闭环流程 (Risk Closed-Loop Protocol)

```text
[识别潜在异常] ──► [自动记录 memory_v2.error 日志] ──► [触发防御性 Fallback]
                                                            │
    ┌───────────────────────────────────────────────────────┘
    ▼
[等级判定]:
  ├── CRITICAL / HIGH ──► 自动关停对应 Feature Flag，退回 V1 安全通道并向托盘发送告警 (Pre-cutover)
  │                       或执行 Forward-Fix 前向补丁修复 (Post-cutover R2 地平线)
  └── MEDIUM / LOW     ──► 降级为 NOOP / 挂起后台任务，维持前台主流程不受损
```

- **脱敏日志规范**：任何错误日志（`memory_v2.operation`）仅记录 `job_id`, `entity_id`, `decision`, `duration`, `error_type`，**绝对禁止在日志中打印用户敏感原话（Content Sanitization）**。
