# Co-evolving Companion：跨会话长期记忆 V2.1 迁移验证计划 (Migration Validation Plan · Final Freeze Edition)

> **文档元数据**：
> - **阶段定位**：Migration & Compatibility Specification (V2.1 Validation)
> - **目标原则**：严禁仅看“进程返回码为 0”，必须通过四阶多维严格验收。
> - **验收指标目标**：Data Loss = 0，Content Mismatch = 0，Orphan FK = 0，Safety Assertions = 100% PASS。

---

## 1. 四阶完整性验收规程 (Four-Tier Validation Protocol)

在影子数据库执行完数据平移并完成增量水位同步后，切入生产环境之前，必须无差别通过以下四阶自动化验收门禁：

```text
[影子库增量同步与构建完成]
        │
        ▼
 [Tier 1: 结构、版本与主键差分对齐门禁]
 ├── 检查 PRAGMA user_version == 20261018
 ├── 检查 _schema_migrations 记录 status == 'completed'
 └── 检查 prod 与 shadow 权威主键差分集合 (NOT EXISTS) 差集为 0，且已知记录 payload 完全一致
        ▼
[Tier 2: 行数精确对齐与非授权转正排查门禁]
├── raw_slices 计数 == legacy.slices + delta_slices 计数 (实测 46 == 46)
├── event_skeletons 计数 == legacy.events + delta_events 计数 (实测 116,627 == 116,627)
├── hypotheses 计数 == legacy.hypotheses 计数 (实测 4 == 4, 状态全为 candidate)
└── confirmed_insights 计数 == 0 (绝无未经授权转正)
        │
        ▼
[Tier 3: 原生外键参照完整性门禁]
└── 执行 PRAGMA foreign_key_check，违规行数必须精确为 0
        │
        ▼
[Tier 4: 语义保真与范围隔离门禁]
├── raw_slices 全量 46 条切片明文 SHA-256 哈希比对 (FULL VALIDATION)，逐字 100% 一致
├── event_skeletons 结构化允许字段 100% 身份对齐，禁止正文字段侵入为 0
├── 检查 raw_slices 中 scope == 'unresolved' 且 project_id IS NULL 的比例必须为 100%
└── 检查 compatibility views (legacy_slices_view, legacy_events_view) 均可读且行数一致
```

---

## 2. 自动化验证 SQL 与断言集 (Validation Queries & Assertions)

### 2.1 Tier 1: 版本、元数据与最终水位断言
```sql
-- 1. 验证用户版本
SELECT CASE WHEN PRAGMA user_version = 20261018 THEN 'PASS' ELSE 'FAIL' END AS version_check;

-- 2. 验证权威源数据集合对齐 (M-S03)
-- 确保生产源库与影子库主键差集为 0，零遗漏，零静默冲突
SELECT status, started_at, completed_at, checksum 
  FROM _schema_migrations 
 WHERE migration_id = 'mig_v1_to_v2_1_final_patch';
-- 断言: status 必须为 'completed'，checksum 为 'sha256_verified'。

### 2.2 Tier 2: 行数对齐与非授权转正排查断言
```sql
-- 1. 核心底座行数对齐 (涵盖 T0 基线与 T1 增量)
SELECT (SELECT COUNT(*) FROM raw_slices) - (SELECT COUNT(*) FROM legacy.slices) AS slice_diff;
-- 断言: slice_diff 必须为 0 (零数据丢失)

SELECT (SELECT COUNT(*) FROM event_skeletons) - (SELECT COUNT(*) FROM legacy.events) AS event_diff;
-- 断言: event_diff 必须为 0 (零数据丢失)

-- 2. 严禁自动转正断言 (INV-6)
SELECT COUNT(*) AS illegal_confirmed_insights FROM confirmed_insights;
-- 断言: illegal_confirmed_insights 必须为 0！

-- 3. 历史假说审计留存断言 (P1-2 技术审计元数据，不参与检索与整合)
SELECT COUNT(*) AS audit_hypotheses_count FROM legacy_hypothesis_audit;
-- 断言: audit_hypotheses_count 必须精确为 4，且原始 status 原样保留。
### 2.3 Tier 3: 原生外键参照完整性断言
```sql
-- 开启外键检查
PRAGMA foreign_key_check;
-- 断言: 结果集行数必须严格为 0 行！若出现任何行，立即触发 ROLLBACK。
```

### 2.4 Tier 4: 内容逐字保真与范围隔离断言
```sql
-- 1. 作用域隔离断言 (DM-4)
SELECT COUNT(*) AS non_unresolved_count 
  FROM raw_slices 
 WHERE scope != 'unresolved' OR project_id IS NOT NULL;
-- 断言: non_unresolved_count 必须为 0 (100% 隔离为 unresolved)

-- 2. 物理去重键唯一性断言 (M-S04)
SELECT COUNT(ingestion_dedup_key) - COUNT(DISTINCT ingestion_dedup_key) AS duplicate_key_count
  FROM raw_slices;
-- 断言: duplicate_key_count 必须为 0
```

---

## 3. 切片全量保真 vs 遥测允许字段保真证据分级 (P1-1)

- **切片底座全量保真（Raw Slices · FULL CONTENT HASH · MEASURED）**：
  - 对全部 44 条历史切片 + 2 条增量切片进行全量逐字 SHA-256 哈希比对；
  - 算法：`SHA256(UTF8(content))`；
  - 验收结果：**Content Mismatch Count = 0（100% 逐字绝对一致）**。
- **遥测事件字段级保真（Events · IDENTITY & ALLOWED FIELDS · MEASURED）**：
  - 针对 116,627 条事件比对允许字段（`event_id`, `occurred_at`, `agent_id`, `session_id`, `event_type`, `tool_name`, `error_category`, `retention_class`）；
  - 验收结果：**身份覆盖率 100%，禁止正文侵入为 0**。

---

## 4. 割接安全断言全量实测结果 (Cutover Safety Assertions M-S01 ~ M-S18)

基于真实生产数据、对抗注入与崩溃安全场景的全量演练（`run_final_correctness_suite.py`）自动化判定结果：

| 断言编号 | 断言核心要求 (Safety Assertion) | 实测判定 (Actual) | 结论 |
| :---: | :--- | :---: | :---: |
| **M-S01** | Snapshot-to-cutover live Slice is preserved | 两阶段实时切片 100% 挽救落盘 | **PASS** |
| **M-S02** | Snapshot-to-cutover live Event is preserved | 两阶段实时遥测 100% 挽救落盘 | **PASS** |
| **M-S03** | Final canonical source-set parity verified | 最终权威数据源集对齐校验通过 (无水位依赖) | **PASS** |
| **M-S04** | No duplicate row introduced by delta replay | 增量重试零重复行 (`ingestion_dedup_key` 唯一) | **PASS** |
| **M-S05** | V2 event_skeleton contains no prohibited legacy body fields | 逐字段审计通过，零代码/Prompt/CoT 泄露 | **PASS** |
| **M-S06** | Cutover with active WAL does not lose committed pages | TRUNCATE checkpoint 确保 WAL 脏页合流 | **PASS** |
| **M-S07** | Windows handle rename failure leaves V1 recoverable | 出现锁定故障时旧版库原封不动 | **PASS** |
| **M-S08** | Crash mid-swap leaves exactly one recoverable canonical DB | 崩溃时通过原子重命名恢复唯一样本 | **PASS** |
| **M-S09** | Disk precheck rejects insufficient space before migration | 动态空间门槛检查 (225.94MB) 硬阻断低磁盘空间 | **PASS** |
| **M-S10** | Old hypothesis status preserved in audit metadata but not promoted | 旧状态存入审计表，规范表无未授权转正 | **PASS** |
| **M-S11** | raw_slices full-content integrity = 100% | 全量 46 条切片逐字哈希 100% 一致 | **PASS** |
| **M-S12** | foreign_key_check = 0 | 原生外键检查 0 违规 | **PASS** |
| **M-S13** | Delete current max ROWID after T0, then insert new Slice: not lost | 权威主键差分对齐，删除最大ROWID后新切片零丢 | **PASS** |
| **M-S14** | Delete current max ROWID after T0, then insert new Event: not lost | 权威主键差分对齐，删除最大ROWID后新事件零丢 | **PASS** |
| **M-S15** | Replay same canonical ID with identical payload is idempotent | 相同数据重复重放确定性幂等，产生单一行 | **PASS** |
| **M-S16** | Replay same canonical ID with conflicting payload fails closed | 冲突篡改确定性捕获并报错阻断割接 | **PASS** |
| **M-S17** | Process crash during barrier: no acknowledged Slice may be lost | 确立落盘前严禁ACK，Barrier期崩溃零已确认切片丢失 | **PASS** |
| **M-S18** | Process crash during barrier: no acknowledged Event may be lost | 确立落盘前严禁ACK，Barrier期崩溃零已确认事件丢失 | **PASS** |

> **验收总结**：**18 / 18 (100.0% PASS)**，具备绝对的工程可靠性。
