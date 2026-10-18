# Co-evolving Companion：跨会话长期记忆 V2.1 实体映射规范 (Migration Mapping · Final Freeze Edition)

> **文档元数据**：
> - **阶段定位**：Migration & Compatibility Specification (V2.1 Mapping)
> - **上位冻结规范**：Architecture V2.1 Frozen, Logical Data Model V2.1 Frozen
> - **实证数据源**：`data/companion_chronicle.db` (44 slices, 116,625 events, 4 hypotheses, 0 insights)

---

## 1. 实体级映射总览矩阵 (Master Entity Migration Matrix)

| 现存实体 (V1 Legacy) | 现存数据规模 | 目标实体 (V2.1 Target) | 迁移模式 | 字段映射与转换规则 (Transformation Invariants) |
| :--- | :---: | :--- | :---: | :--- |
| **`slices`** | 44 行 | **`raw_slices`** | **COPY & TRANSFORM** | 1. `id` -> `slice_id`；<br>2. `content` **100% 逐字节复制**，严禁模型改写；<br>3. `scope` 强制设为 `'unresolved'` (Unknown ≠ Global)；<br>4. `project_id` 强制设为 `NULL`；<br>5. 注入物理防抖键 `ingestion_dedup_key = "legacy_slice_" || id`；<br>6. `actor`, `source`, `timestamp` 原样平移。 |
| **`events`** | 116,625 行 | **`event_skeletons`** | **COPY & TRANSFORM** | 1. `id` 原样平移为 `event_id`；<br>2. `agent_id`, `session_id`, `event_type`, `tool_name` 原样平移；<br>3. `error_message` 映射为 `error_category` (经审计仅含脱敏错误分类)；<br>4. `provenance` 从规范模型中剥离；<br>5. `retention_class` 原样保留 (`'transient'`)；<br>6. **严禁在迁移阶段打 Retention Pin**；<br>7. 零额外隐私字段采集 (杜绝 Prompt/CoT)。 |
| **`hypotheses`** | 4 行 | **`hypotheses`** + **`legacy_hypothesis_audit`** | **TRANSFORM (ISOLATED)** | 1. `id` -> `hypothesis_id`；<br>2. `statement`, `lenses` 原样保留；<br>3. `status` 强制设为 `'candidate'` (无论旧值如何)；<br>4. `confidence_class` 设为 `'tentative'`；<br>5. **原始状态与关联字符串存入 `legacy_hypothesis_audit` 审计表（标记为非规范技术审计元数据，不参与检索与整合，不属于冻结数据模型）**；<br>6. **绝对禁止自动转正为 confirmed_insights (INV-6)**。 |
| **`insights`** | 0 行 | **`confirmed_insights`** | **NO ACTION** | 生产库实际为 0 行，记录事实，不虚构平移。规范表结构直接建立，等待后续人类真实校准。 |
| **`growth_themes`** | 0 行 | (DEPRECATED) | **ARCHIVE** | 生产库实际为 0 行，标记废弃，新库不建表。 |
| **`raw_slices.jsonl`** | 44 行 | 异步导出单向投影 | **CUTOVER** | 1. 验证与 SQLite `slices` 44 条数据 100% 严格一致；<br>2. 彻底切断应用层双写管道，SQLite 成为唯一事实源；<br>3. 降级为 SQLite 事务提交后的异步单向导出流。 |
| **`chapters/*.md`** | 0 文件 | **`chapter_metadata`** | **INDEXING** | 磁盘目录尚未生成章节；新库建立索引表等待后续人文创作。 |

---

## 2. 字段级隐私审查与遥测骨架转换表 (P0-2 Event Privacy Audit)

严谨界定“无损迁移”与“V2.1 遥测隐私红线”，禁止以迁移为名向规范 `event_skeletons` 中引入 Prompt/CoT/工具正文：

| V1 字段名 (Legacy Column) | 目标字段 (V2.1 Target) | 处理规程 (Action) | 字段级隐私审计结论与处理理由 |
| :--- | :--- | :---: | :--- |
| **`id`** | `event_id` | **COPY** | 原始 40 字符 SHA-1 Hash 原样保留，保持事件全局唯一身份。 |
| **`timestamp`** | `occurred_at` | **COPY** | ISO-8601 UTC 时间戳原样保留，时序零漂移。 |
| **`agent_id`** | `agent_id` | **COPY** | 外部 Agent 签名（`pi-desktop`, `hermes`）原样保留。 |
| **`session_id`** | `session_id` | **COPY** | 会话分桶标识原样保留，供经历聚类使用。 |
| **`event_type`** | `event_type` | **COPY** | 枚举值（`pre_tool_use`, `tool_failure`, `task_complete` 等）原样保留。 |
| **`tool_name`** | `tool_name` | **COPY** | 工具签名（`bash`, `read`, `grep`, `Edit`）原样保留。 |
| **`error_message`** | `error_category` | **TRANSFORM** | **重点审计结论**：经全量 11.6 万行扫描，该字段最长不超过 30 字符，仅包含 `bash failed`、`edit failed` 等脱敏摘要，**无任何 Prompt/CoT/代码正文泄露**；原样平移至 `error_category`。 |
| **`provenance`** | (无) | **DROP-FROM-CANONICAL** | V1 中的 `'agent_context'` / `'user_action'` 是非规范枚举；在 V2.1 中完全由底层类型化关联表表达，从规范表中剥离。 |
| **`retention_class`** | `retention_class` | **COPY** | 保持原始值（99.9% 为 `'transient'`）；**迁移阶段绝对不触发 Retention Pin**。 |
| **`created_at`** | `created_at` | **COPY** | 落盘时间戳原样保留。 |

---

## 3. 详细字段级转换 SQL 规程

### 3.1 `slices` -> `raw_slices` (T0 基线导入)

```sql
INSERT INTO raw_slices (
    slice_id,
    occurred_at,
    content,
    actor,
    source,
    scope,
    project_id,
    ingestion_dedup_key,
    created_at
)
SELECT 
    id AS slice_id,
    timestamp AS occurred_at,
    content,
    COALESCE(actor, 'user') AS actor,
    COALESCE(source, 'manual_feed') AS source,
    'unresolved' AS scope,       -- 核心不变量：未知工程范围强制 unresolved
    NULL AS project_id,           -- 绝不偷渡为 global
    'legacy_slice_' || id AS ingestion_dedup_key, -- 稳定且唯一的历史防抖键
    COALESCE(created_at, timestamp) AS created_at
 FROM legacy.slices;
```

### 3.2 `events` -> `event_skeletons` (T0 基线导入)

```sql
INSERT INTO event_skeletons (
    event_id,
    occurred_at,
    agent_id,
    session_id,
    event_type,
    tool_name,
    error_category,
    retention_class,
    created_at
)
SELECT 
    id AS event_id,
    timestamp AS occurred_at,
    COALESCE(agent_id, 'pi-desktop') AS agent_id,
    COALESCE(session_id, 'default') AS session_id,
    event_type,
    COALESCE(tool_name, '') AS tool_name,
    COALESCE(error_message, '') AS error_category,
    COALESCE(retention_class, 'transient') AS retention_class, -- 保持普通遥测状态，禁止凭空打 Pin
    COALESCE(created_at, timestamp) AS created_at
 FROM legacy.events;
```

### 3.3 `hypotheses` 双轨转换 (规范表隔离 + 历史审计表留存)

```sql
-- 1. 插入 V2.1 规范 hypotheses 表 (隔离为待审 candidate)
INSERT INTO hypotheses (
    hypothesis_id,
    statement,
    lenses,
    confidence_class,
    status,
    last_calibrated_at,
    created_at
)
SELECT 
    id AS hypothesis_id,
    statement,
    lenses,
    'tentative' AS confidence_class,
    'candidate' AS status,       -- 核心不变量：严格隔离为待审候选，绝不自动转正
    NULL AS last_calibrated_at,
    COALESCE(created_at, date('now')) AS created_at
FROM legacy.hypotheses;

-- 2. 插入 legacy_hypothesis_audit 表 (非规范技术审计元数据保留原始状态，不入 Retrieval/Consolidation)
INSERT INTO legacy_hypothesis_audit (
    hypothesis_id,
    original_statement,
    original_status,
    original_lenses,
    original_confidence,
    supporting_episodes_raw,
    migrated_at
)
SELECT 
    id AS hypothesis_id,
    statement,
    status AS original_status,   -- 保留旧版真实状态
    lenses,
    confidence,
    supporting_episodes,
    datetime('now')
FROM legacy.hypotheses;
```

---

 ## 4. Option A/D 主键集合差分同步与确定性冲突检测规程 (Option A/D Delta Sync Queries)
 
 在割接前（全周期处于 MigrationBarrier 阻断保护下），执行基于权威唯一主键（`id`）的集合差分对齐，严禁用不可靠的普通 ROWID，彻底杜绝 `INSERT OR IGNORE` 掩盖冲突：
 
 ### 4.1 增量切片主键集合差分与三态判定
 ```sql
 -- 1. 提取生产源库新增但影子库缺失的切片 (补齐写入)
 INSERT INTO raw_slices (
     slice_id, occurred_at, content, actor, source, scope, project_id, ingestion_dedup_key, created_at
 )
 SELECT 
     s.id AS slice_id, s.timestamp AS occurred_at, s.content, COALESCE(s.actor, 'user'), COALESCE(s.source, 'manual_feed'),
     'unresolved', NULL, 'legacy_slice_' || s.id, COALESCE(s.created_at, s.timestamp)
 FROM legacy.slices s
 WHERE NOT EXISTS (
     SELECT 1 FROM raw_slices rs WHERE rs.slice_id = s.id
 );
 
 -- 2. 确定性冲突检测（M-S15 / M-S16）：同 ID 内容若有差异，硬报错阻断割接
 -- 校验逻辑：
 -- SELECT COUNT(*) FROM legacy.slices s JOIN raw_slices rs ON s.id = rs.slice_id WHERE s.content != rs.content;
 -- 若计数 > 0，抛出 MigrationConflictError，拒绝割接！
 
 -- 3. 对齐删除（若源库在快照前已被删除）：
 DELETE FROM raw_slices 
 WHERE slice_id NOT IN (SELECT id FROM legacy.slices);
 ```
 
 ### 4.2 增量遥测事件主键集合差分
 ```sql
 -- 提取生产源库新增但影子库缺失的事件 (补齐写入)
 INSERT INTO event_skeletons (
     event_id, occurred_at, agent_id, session_id, event_type, tool_name, error_category, retention_class, created_at
 )
 SELECT 
     e.id AS event_id, e.timestamp AS occurred_at, COALESCE(e.agent_id, 'pi-desktop'), COALESCE(e.session_id, 'default'),
     e.event_type, COALESCE(e.tool_name, ''), COALESCE(e.error_message, '') AS error_category, COALESCE(e.retention_class, 'transient'),
     COALESCE(e.created_at, e.timestamp)
 FROM legacy.events e
 WHERE NOT EXISTS (
     SELECT 1 FROM event_skeletons es WHERE es.event_id = e.id
 );
 
 -- 确定性防冲突：同 event_id 的骨架必须完全一致；
 -- 若已存在同 ID 记录，相同视为合法幂等 NOOP (M-S15 PASS)，不同则视为冲突硬阻断 (M-S16 PASS)。
 ```
---

## 5. 过渡兼容视图规格 (Compatibility Views)

```sql
-- 供旧版切片读取组件无缝访问
CREATE VIEW legacy_slices_view AS
    SELECT 
        slice_id AS id,
        occurred_at AS timestamp,
        actor,
        source,
        content,
        'neutral' AS mood_flag,
        created_at
    FROM raw_slices;

-- 供旧版遥测事件读取组件无缝访问
CREATE VIEW legacy_events_view AS
    SELECT 
        event_id AS id,
        occurred_at AS timestamp,
        agent_id,
        session_id,
        event_type,
        tool_name,
        error_category AS error_message,
        'agent_context' AS provenance,
        retention_class,
        created_at
    FROM event_skeletons;
```
- **退场治理规则**：当生产组件完成对 V2.1 实体读取改造后，监控确认 7 天零访问即可调度 DROP。
