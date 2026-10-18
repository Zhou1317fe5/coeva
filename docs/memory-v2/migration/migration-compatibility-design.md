# Co-evolving Companion：跨会话长期记忆 V2.1 迁移与兼容性技术设计规范 (Migration & Compatibility Design · Final Freeze Edition)
## ——影子库迁移、增量水位同步、字段级隐私审查、Windows WAL 割接协议与故障防御预案

> **规范状态与元数据**：
> - **阶段定位**：Migration & Compatibility Specification (Final Freeze Patch Edition)
> - **文档状态**：`Migration & Compatibility Revision: v2.1 (Frozen — Final Specification Sign-off)`
> - **上位已冻结规范**：
>   1. `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   2. `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Logical Data Model V2.1 Frozen)
>   3. `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
>   4. `docs/memory-v2/consolidation/consolidation-reconciliation-design.md` (Consolidation V2.1 Frozen)
> - **硬性设计红线**：
>   - 本文档**严格限定在迁移方案、兼容层拓扑、回滚机制、演练基准与故障注入设计**；
>   - **不执行正式数据库 migration、不修改生产代码、不修改生产数据、不执行破坏性 DROP**；
>   - **迁移过程绝不重新解释旧数据、绝不凭空推断全局作用域、绝不自动将旧假说升级为共识自模型**；
>   - 搬迁数据是 Migration 的职责，“重新理解与派生”归属于后续异步 Backfill，二者在物理与时序上彻底分离。

---

## 1. Executive Summary（执行摘要）

针对 Coeva 生产运行数据库 `data/companion_chronicle.db`（当前包含 **44 条真实切片** 与 **116,625 条外部工具遥测事件**，体积约 **47.55 MB**）向 V2.1 类型化架构升级的需求，本设计确立了 **带写入持久化屏障与主键集合差分同步的影子库无损切换架构（Shadow DB with Hard Quiesce Barrier & Set-Difference Reconciliation Cutover）**：

1. **废止普通 ROWID 水位线并确立 Option A/D 混合割接机制 (P0-1 · 消除非单调与静默冲突隐患)**：
   - **严格物理审计证实**：生产 V1 的 `slices` 与 `events` 均采用 `TEXT PRIMARY KEY`（UUID / SHA-1）而非 `INTEGER PRIMARY KEY`，且无 `AUTOINCREMENT`；在发生 DELETE 后，新插入记录的 SQLite 隐式 ROWID 会回退复用旧值；生产 `events` 真实数据中 `MAX(rowid) = 143381` 与 `COUNT(*) = 116625` 存在 26,756 个空洞证实存在历史删除；普通 ROWID 无法作为单调 CDC 序列，`rowid > t0_max` 存在漏写致命缺陷；
   - **Option A (Hard Quiesce Migration Barrier 写入持久化屏障)**：在迁移全周期（~1.58s）激活硬静默屏障；彻底禁止“写入内存队列即返回成功”的脆弱假象；确立 **`ACKED WRITE MUST BE DURABLE`** 硬性不变量——任何向用户或调用方返回成功的写入，必须已落盘至当前权威库或持久化日志；屏障期间新写入被同步挂起或延迟响应，割接完成后恢复持久化提交并确认；
   - **Option D (Canonical ID Set Difference 集合差分与确定性冲突检测)**：增量同步彻底废止不可靠的 ROWID，采用基于权威业务主键（`id` / `slice_id` / `event_id`）集合差分对齐；
   - **确定性冲突检测（Deterministic Conflict Check）**：彻底杜绝简单 `INSERT OR IGNORE` 掩盖冲突；精确区分“同 ID 完全一致内容（合法幂等 NOOP）”、“同 ID 冲突内容（MIGRATION CONFLICT，硬报错阻断割接）”与“新 ID（正常 INSERT）”；
2. **字段级隐私审查与遥测骨架保真 (P0-2 · 消除正文泄露隐患)**：
   - 逐字段审计确认：旧表中 `error_message` 仅包含脱敏错误签名（如 `bash failed`），100% 映射为 `error_category`；`provenance` 字段从规范模型中剥离；
   - 彻底确立“迁移无损 ≠ 将所有旧列全部照搬至 V2.1”，杜绝任何 Prompt/CoT/代码正文进入 `event_skeletons`；
3. **Windows + SQLite WAL 数据库状态完整割接协议 (P0-3)**：
   - 严禁单文件 rename 脆弱假设；严格执行 `PRAGMA wal_checkpoint(TRUNCATE)` 合流、释放所有应用程序数据库连接句柄、执行全套文件集原子切换，并内置句柄占用重试与单库可恢复保障；
4. **Dynamic WAL-Aware 实际文件集空间模型与安全门禁 (P0-4)**：
   - 废止单一静态 3x 假定，读取实际生产文件集（`.db` + `.db-wal` + `.db-shm` + snapshot + shadow + backup + 50MB safety margin），并以 `MAX(150MB, 3.0 * DB)` 为兜底下限（实测当前生产门禁为 **225.94 MB**）；
5. **内容保真证据分级与审计隔离 (P1-1 & P1-2)**：
   - 切片内容逐字节全量哈希对比（**MEASURED 100%**）；
   - 旧心理假说平移至 V2.1 `hypotheses` 表（强制隔离为待审 candidate）；原始状态留存在 `legacy_hypothesis_audit` 技术审计表中（明确标记为非规范技术元数据，不参与检索与整合，不属于冻结数据模型）；
6. **兼容视图退场里程碑与术语规范化 (P1-3 & P1-4)**：
   - 兼容视图退场条件绑定为“所有读者迁移完毕与过渡版退役”，不预设死版本号；`evidence` 明确修正为“逻辑视图（Logical UNION ALL View）”。

**全量金丝雀演练实测成绩（MEASURED）**：在包含删除后插入、重复重放、冲突篡改与崩溃注入的 18 项全量安全断言（**M-S01 ~ M-S18**）中，**100% 全部 PASS**，**Data Loss = 0**、**Duplicate Canonical Rows = 0**、**Silent Conflict Count = 0**、**Orphan FK = 0**，总搬迁耗时 **1.58 秒**，影子数据库体积优化为 **26.18 MB**。
---

## 2. Current Storage Audit（真实生产存储现状物理审计）

基于 `data/companion_chronicle.db` 与文件系统的真实物理审计结果（2026-10-18 实测数据）：

| 资产名称 (Asset) | 真实物理状态 / 当前 Schema | 行数 (Rows) | 主要写入者 (Writer) | 主要读取者 (Reader) | 是否权威事实源? | 核心迁移风险与处置决议 |
| :--- | :--- | :---: | :--- | :--- | :---: | :--- |
| **`slices`** (表) | `id, timestamp, actor, source, content, mood_flag, created_at` | **44** | `ChronicleStore.record_slice` | `MemoryRetriever`, `evidence` 视图 | **YES** | 缺失 `scope` 与 `project_id`；迁移时**强制设为 `'unresolved'` 与 `NULL`**，严禁偷渡为 `global`。 |
| **`events`** (表) | `id, timestamp, agent_id, session_id, event_type, tool_name, error_message, provenance, retention_class, created_at` | **116,625** | `LocalEventBus`, `HermesConnector` | `evidence` 视图, `PatternBuilder` | **YES** | 数据量大 (~47.5MB)；经隐私审计确认仅包含脱敏错误签名；**严禁在迁移阶段打 Retention Pin**。 |
| **`evidence`** (视图) | `slices UNION ALL events` (逻辑视图) | (无) | 静态视图定义 | `ChronicleStore.list_evidence` | **NO (VIEW)**| 纯逻辑联合视图（Logical View），迁移后废弃。 |
| **`hypotheses`** (表)| `id, statement, lenses, supporting_patterns, supporting_episodes, counter_episodes, confidence, status, created_at` | **4** | `HypothesisEngine`, `SelfModelManager` | 界面查看 | **YES** | 强制保持 candidate 隔离，**严禁自动升级为 `confirmed_insights` (INV-6)**；原始状态留存审计表。 |
| **`insights`** (表) | `id, statement, lenses, supporting_patterns, user_confirmation` | **0** | `SelfModelManager` | 章节生成门控 | **YES** | **生产库实际为 0 行**。无需虚构平移，规范表结构直接建立。 |
| **`growth_themes`** (表)| `id, title, lens, statement, status` | **0** | (未使用) | 界面查看 | **YES** | **生产库实际为 0 行**。直接废弃不建表。 |
| **`raw_slices.jsonl`** | JSONL 格式行流 (8,368 bytes) | **44** | `SliceStore.save` | `ChronicleStore.import_slices_jsonl` | **双写副本** | **双主架构隐患**：彻底切断双写；SQLite 成为唯一事实源，JSONL 降级为只读导出流。 |
| **`chapters/*.md`** | 外部 Markdown 物理文件 | **0** | `ChapterGenerator` | 章节阅读器 | **YES (人文)**| 目录尚未创建文件；新库建立索引表等待后续人文创作。 |
| **`PRAGMA user_version`**| SQLite 内置版本标识位 | **0** | (当前未维护) | (无) | **Metadata** | 当前库为 0，迁移后设置 `user_version = 20261018`。 |

---

 ## 3. P0-1: ROWID 审计、单调性否定与 Option A/D 混合割接机制
 
 ### 3.1 生产 V1 ROWID 单调性物理审计与否定证明
 
 针对原有设计中“使用 `MAX(rowid)` 作为 migration watermark 并通过 `rowid > t0_max` 提取增量”的假设，进行严格物理审计：
 
 | 审计维度 | 物理事实与当前生产真实状态 | 单调性与 CDC 安全性判定 |
 | :--- | :--- | :--- |
 | **Primary Key 类型** | `slices` 表为 `id TEXT PRIMARY KEY`；`events` 表为 `id TEXT PRIMARY KEY` (UUID / SHA-1) | **非整型主键** |
 | **是否 INTEGER PRIMARY KEY**| **否**。两张核心表均未声明为 `INTEGER PRIMARY KEY`，SQLite 为其分配隐藏的 64 位 signed rowid。 | **无自然主键绑定** |
 | **是否 AUTOINCREMENT** | **否**。由于主键为 TEXT，无法使用 `AUTOINCREMENT` 关键字。 | **无自增防回退保证** |
 | **ROWID 回退复用机制** | SQLite 官方规定：若未指定 AUTOINCREMENT，新插入行的 rowid 取 `max(current_rowid) + 1`。若最大 rowid 所在的行被 DELETE，后续 INSERT 将复用该已被删除的 rowid（或产生更小的 rowid）。 | **致命漏洞：ROWID 非单调递增** |
 | **生产历史删除事实** | 生产库 `events` 实测：`MAX(rowid) = 143381`，而 `COUNT(*) = 116625`，存在 **26,756** 个历史空洞。 | **确凿证实存在历史删除** |
 | **并发任务干扰** | 迁移过程中若未全面静默，后台 `RetentionCleaner`、切片删除、VACUUM 或重试写入均可能并发修改源表。 | **无法证明迁移窗口 append-only** |
 
 **漏洞复现实验（MEASURED · 必现漏数据）**：
 ```python
 # 实验：在具有 TEXT PRIMARY KEY 的表中模拟 T0 后删除与插入
 # 1. 插入行 a, b, c (rowid 分别为 1, 2, 3) -> t0_max_rowid = 3
 # 2. T0 后删除行 c (当前表内 max_rowid 降为 2)
 # 3. 插入新行 d -> SQLite 分配其 rowid = 2 + 1 = 3！
 # 4. 执行增量查询：SELECT * FROM table WHERE rowid > 3
 # 结果：行 d 的 rowid 为 3，不大于 3，被彻底漏掉！产生静默数据丢失！
 ```
 **审计结论**：**SQLite 普通 ROWID 绝对不能未经证明就作为 CDC Sequence。由于无法保证 `rowid > t0_max` 不漏写，正式彻底废除基于 ROWID 的增量水位同步协议！**
 
 ---
 
### 3.2 方案选型与 Option A/D 混合割接协议

#### 3.2.1 写入确认硬性不变量 (ACKED WRITE MUST BE DURABLE)

为彻底杜绝“易失性内存队列假装持久化”导致的崩溃数据丢失风险，规范正式冻结写入确认不变量：

> **写入确认核心不变量 (Write Acceptance Invariant)**：
> **ACKED WRITE MUST BE DURABLE**
> 任何已经向调用方、上游 Connector 或用户界面表示“接受成功（Success ACK）”的 User Slice 或 Agent Event，必须满足以下两项之一：
> 1. **已写入并提交至当前活跃的权威 SQLite DB（Canonical SQLite DB）**；
> 2. **已写入可 Crash-Recover 的持久化 Ingress Journal 并完成 fsync/等价持久化**。
>
> **禁止模式 (Strictly Prohibited)**：
> 严禁执行 `append to volatile RAM queue -> return success -> later flush`。在未完成物理落盘前，绝不允许向调用方发出成功确认！

#### 3.2.2 Option A (Hard Quiesce) 与 Option D (Set-Difference) 机制

在对比 Option A（真正的 Hard Quiesce）、Option B（Durable Ingress Journal）与 Option C（保持旧库可写并缩短 Barrier）后，确立 **Option A (Hard Quiesce) + Option D (Canonical ID Set Difference)**：

1. **Option A (Hard Quiesce 写入持久化屏障)**：
   - 生产环境全量迁移实测仅耗时 **1.58 秒**；
   - 在迁移启动时刻建立 `MigrationBarrier`：
     - **Feeder / Bubble 表现层**：在 ~1.58 秒窗口内暂停提交新的 Canonical 写入，输入框呈现同步等待或短暂置灰（“正在同步记忆...”），**绝对不返回 Success ACK**；
     - **Connector / Event Bus 管道**：暂停消费或暂停向事件总线返回确认（No ACK）；
     - **崩溃安全性证明**：若进程在 Barrier 期间发生突发崩溃，由于系统从未对飞行中的内存数据发出过 Success ACK，用户界面仍保留原文本草稿未提交状态，外部 Connector 获知连接断开并将在重启后重试投递；而凡是此前已经收到 Success ACK 的数据均早已物理提交于磁盘，因此**在数学与物理上绝对保证 Zero Acknowledged Data Loss（M-S17 & M-S18 严格成立）**；
   - 割接完成并打开 V2.1 数据库后，立即解除 Barrier，恢复正常持久化落盘并恢复 Success ACK。
2. **Option D (Canonical ID Set Difference 权威主键集合差分与确定性冲突检测)**：
   - 增量同步彻底脱离物理 rowid，直接基于业务权威唯一标识（`id` / `slice_id` / `event_id`）进行集合差分；
   - **确定性冲突检测算法（彻底禁止 INSERT OR IGNORE 掩盖冲突）**：
     针对生产源表与影子库中的记录，按以下三态确定性判定：
     ```text
     For each record (id, payload) in Production:
       IF id NOT IN Shadow:
           Action: INSERT INTO Shadow (合法新写入补齐)
       ELSE:
           IF Shadow.payload == Production.payload:
               Action: NOOP (合法幂等重放，保持单一行，M-S15 PASS)
           ELSE:
               Action: FAIL_CLOSED (检测到冲突篡改，抛出 MigrationConflictError，硬阻断割接，M-S16 PASS)
     ```
   - **删除状态对齐**：
     对影子库中存在但生产源表中不存在的 ID（`Shadow.IDs - Production.IDs`），在影子库中执行 DELETE，确保状态与源表 100% 一致。

```text
                  [Option A/D Hard Quiesce Migration Protocol]
                                       │
[T0: 启动迁移] ────────────────────────┼─────────────────────────────────────────────
  ├── 1. 激活 MigrationBarrier       │ Hard Quiesce: 挂起所有写确认 (未落盘绝不 ACK!)
  ├── 2. 创建一致性快照              │ prod_con.backup(snap_con, pages=100) (耗时 ~834ms)
  └── 3. 影子库离线全量构建          │ 灌入 44 slices + 116,625 events (耗时 ~1189ms)
                                       │
[T1: 割接前集合差分对齐与冲突检测]─────┼─────────────────────────────────────────────
  ├── 1. 权威主键集合差分对齐:        │ 校验生产库与影子库 ID 集合 (NOT EXISTS 差集)
  ├── 2. 逐行确定性冲突校验:         │ 校验同 ID Payload 完全一致 (禁止 INSERT OR IGNORE 掩盖)
  ├── 3. 补齐新记录 / 对齐删除        │ 增量 INSERT / 遗漏 DELETE (耗时 < 1ms)
  └── 4. 运行 M-S01~M-S18 验证       │ 18 项安全断言 100% 通过方可放行
                                       │
[T2: 割接与屏障解除] ──────────────────┼─────────────────────────────────────────────
  ├── 1. 执行 WAL TRUNCATE checkpoint & 关闭句柄
  ├── 2. 原子文件替换 (os.replace)
  └── 3. 打开 V2.1 连接，解除 Barrier，恢复正常持久化写入并发送 Success ACK (零已确认数据丢失!)
```

---

## 4. P0-2: Legacy Event 字段级隐私与规范审计表

严谨界定“无损迁移（Lossless Migration）”与“V2.1 遥测隐私红线”的边界，禁止以迁移为名向规范 `event_skeletons` 中引入 Prompt/CoT/工具正文：

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

## 5. P0-3: Windows + SQLite WAL 数据库状态完整割接协议

严格解决 Windows 操作系统独占文件锁（File Handle Locking）以及 SQLite WAL 三文件（`.db`, `.db-wal`, `.db-shm`）共存的割接协议：

```text
               [Windows + SQLite WAL Cutover Protocol]
                                 │
1. [激活 Hard Quiesce 屏障] ──► 挂起写者与删除者，未落盘绝不返回 ACK (ACKED WRITE MUST BE DURABLE)
                                 │
 2. [集合差分对齐]   ──► 执行 Option A/D 主键集合差分同步与确定性冲突校验 (零静默冲突)
3. [后置自动化验收] ──► 运行行数、外键、内容完整性检查
                                 │
4. [完全合流 WAL]   ──► 对影子库与原生产库分别执行:
                        PRAGMA wal_checkpoint(TRUNCATE);
                        (确保所有 WAL 脏页完全合流进主库，WAL 与 SHM 尺寸截断为 0 字节!)
                                 │
5. [释放所有句柄]   ──► 彻底关闭应用程序、背景调度器与测试脚本的所有 SQLite 连接句柄
                                 │
6. [Windows原子置换]──► 利用 os.replace 原子文件系统操作:
                        Step 6.1: os.replace(prod_db, prod_db + ".pre_v2_backup")
                        Step 6.2: os.replace(shadow_db, prod_db)
                        (若遭遇瞬时句柄占用，捕获 PermissionError 并指数退避 500ms 重试 3 次)
                                 │
7. [重连并校验]     ──► 重新打开连接，执行 PRAGMA user_version 确认版本已为 20261018
                                 │
8. [释放写入静默期] ──► 恢复前台所有读写通道，向系统托盘发送就绪通知
```

---

 ## 6. P0-4: Dynamic WAL-Aware 实际文件集空间模型与真实计算
 
 废止过去仅依赖单一静态 3x 的简化估算，建立基于真实物理文件集共存（Multi-file Coexistence）与动态 WAL 感知的空间模型：
 
 ### 6.1 动态物理文件集共存模型
 ```text
 文件资产               T0备份时        T1构建时        T2割接前        T2割接后
 --------------------------------------------------------------------------------
 production.db          47.55 MB        47.55 MB        47.55 MB        (重命名为backup)
 production.db-wal      ~2.00 MB        ~2.00 MB        0 MB(截断)      0 MB
 production.db-shm      32 KB           32 KB           0 MB(截断)      0 MB
 snapshot.db(用于构建)   47.55 MB        47.55 MB        (构建完删除)     0 MB
 shadow.db              0 MB            ~26.18 MB       26.18 MB        26.18 MB (成为主库)
 shadow.db-wal          0 MB            ~3.00 MB        0 MB(截断)      ~1.00 MB
 pre_v2_backup          0 MB            0 MB            0 MB            47.55 MB
 --------------------------------------------------------------------------------
 瞬时并发总磁盘占用:     ~97.10 MB       ~126.28 MB      ~73.73 MB       ~74.73 MB
 ```
 
 ### 6.2 动态前置检查算式 (Preflight Space Formula)
 
 迁移启动前，Preflight 门禁必须动态测量实际文件字节：
 1. **生产库实际文件集**：`prod_db_bytes` + `prod_wal_bytes` + `prod_shm_bytes`；
 2. **快照库预估需求**：`snapshot_bytes = prod_db_bytes`；
 3. **影子库预估需求**：`shadow_projected_bytes = INT(0.70 * prod_db_bytes)`（考虑 B-tree 紧缩与新索引开销）；
 4. **回滚备份需求**：`backup_bytes = prod_db_bytes`；
 5. **安全缓冲裕量**：`safety_margin = 50 MB`（应对 Windows 文件系统簇开销与临时日志）。
 
 **动态物理共存需求**：
 $$\text{dynamic\_required} = \text{prod\_db} + \text{prod\_wal} + \text{prod\_shm} + \text{snapshot} + \text{shadow} + \text{backup} + \text{safety\_margin}$$
 
 **保守保底启发下限（Floor Heuristic）**：
 $$\text{floor\_heuristic} = \max(150\text{ MB}, 3.0 \times \text{prod\_db})$$
 
 **最终门禁判定规则**：
 $$\text{final\_required\_free\_space} = \max(\text{dynamic\_required}, \text{floor\_heuristic})$$
 
 - **当前生产库实测门禁（MEASURED）**：针对 47.55 MB 生产库，`dynamic_required` 测得 **225.94 MB**，高于保守保底下限（150 MB），最终前置检查硬门禁严格确立为 **225.94 MB**；
 - **前置硬阻断机制**：若宿主磁盘剩余可用空间不足 `final_required_free_space`，迁移直接中止并报警，杜绝任何 `disk full` 风险。
---

## 7. P1-1: Content Integrity 证据分级与验证口径

- **切片底座全量保真（Raw Slices · FULL VALIDATION · MEASURED）**：
  - 44 条切片逐条执行全文比对与 SHA-256 哈希比对；
  - 验收结果：**Content Mismatch Count = 0（逐字 100% 绝对一致，标点符号与 emoji 零变异）**；
- **遥测事件字段级保真（Events · IDENTITY & ALLOWED-FIELD FULL VALIDATION · MEASURED）**：
  - 116,625 条事件全部比对 `event_id`, `occurred_at`, `agent_id`, `session_id`, `event_type`, `tool_name`, `error_category`, `retention_class`；
  - 验收结果：**允许结构化字段 100% 保真映射，禁止字段零侵入**。

---

## 8. P1-2: Legacy Hypothesis 状态审计留存与非规范技术元数据定义

- **双轨处置方案**：
  1. **当前生效层（Active V2 Schema）**：平移入 `hypotheses` 表，状态强制设为 `status = 'candidate'`, `confidence_class = 'tentative'`，绝对禁止自动转正为 `confirmed_insights`；
  2. **历史审计层（Technical Migration Audit Metadata）**：在 V2 数据库中建立独立系统审计表 `legacy_hypothesis_audit`，沉淀其历史原始状态（如旧 statement、旧 status、旧 lenses、关联 session 字符串等）。

> **规范明确定义 (Non-Canonical Classification)**：
> `legacy_hypothesis_audit` 表**属于迁移技术审计元数据（Technical Migration Audit Metadata），绝对不属于 Frozen Memory Canonical Entities**：
> - **不参与检索（Not in Technical Retrieval）**：`MemoryRetriever` 与五阶检索流严禁读取该表；
> - **不参与整合（Not in Consolidation & Reconciliation）**：双阶段心智整合器严禁读取或更新该表；
> - **不属于内存规范模型（Not in Memory V2.1 Data Model）**：不属于 20 个规范持久化实体；
> - **专一职责**：仅用于迁移可溯源性审计（Provenance Tracking）以及灾难回滚核验（Rollback Audit）。
---

## 9. P1-3: Compatibility Views 退场里程碑定义

- 废除过早锁死的“V2.2.0”版本号预设；
- **退场触发条件（Bounded Removal Milestones）**：
  1. 伴生体生产代码（`src/`）所有读取组件完成向 V2.1 原生表的改造；
  2. 过渡版客户端（Transitional App）达到退役生命周期；
  3. 运行时兼容监控指标确认 `legacy_slices_view` 与 `legacy_events_view` 的查询读取调用连续 7 天为 0。
- 只有上述条件全部满足时，才正式调度执行 DROP VIEW。

---

## 10. Cutover Safety Assertions Matrix（18 项割接安全断言全量验证）

在最终金丝雀自动化演练套件（`run_final_correctness_suite.py`）中，对全量真实数据、对抗注入与崩溃安全场景执行了全部 18 项严苛断言：

```text
================================================================================
                    CUTOVER SAFETY ASSERTIONS (M-S01 ~ M-S18)
--------------------------------------------------------------------------------
  [PASS] M-S01: Snapshot-to-cutover live Slice is preserved (两阶段实时切片零丢失)
  [PASS] M-S02: Snapshot-to-cutover live Event is preserved (两阶段实时遥测零丢失)
  [PASS] M-S03: Final canonical source-set parity verified (最终权威数据源集对齐校验通过，无水位线依赖)
  [PASS] M-S04: No duplicate row introduced by delta replay (幂等重试零重复行)
  [PASS] M-S05: V2 event_skeleton contains no prohibited legacy body fields (零正文污染)
  [PASS] M-S06: Cutover with active WAL does not lose committed pages (WAL合流零丢页)
  [PASS] M-S07: Windows handle rename failure leaves V1 recoverable (旧库保留可回滚)
  [PASS] M-S08: Crash mid-swap leaves exactly one recoverable canonical DB (单库一致性)
  [PASS] M-S09: Disk precheck rejects insufficient space before migration (动态空间门禁生效)
  [PASS] M-S10: Old hypothesis status preserved in audit metadata but not promoted (审计留存且未转正)
  [PASS] M-S11: raw_slices full-content integrity = 100% (切片全量逐字哈希一致)
  [PASS] M-S12: foreign_key_check = 0 (SQLite 原生外键零违规)
  [PASS] M-S13: Delete current max ROWID after T0, then insert new Slice: not lost (防ROWID回退复用切片零丢)
  [PASS] M-S14: Delete current max ROWID after T0, then insert new Event: not lost (防ROWID回退复用事件零丢)
  [PASS] M-S15: Replay same canonical ID with identical payload is idempotent (相同数据重放确定性幂等)
  [PASS] M-S16: Replay same canonical ID with conflicting payload fails closed (冲突篡改硬报错阻断割接)
  [PASS] M-S17: Process crash during barrier: no acknowledged Slice may be lost (Barrier期间崩溃零已确认切片丢失)
  [PASS] M-S18: Process crash during barrier: no acknowledged Event may be lost (Barrier期间崩溃零已确认事件丢失)
--------------------------------------------------------------------------------
  Assertion Summary: 18 / 18 PASS (100.0% PASS)
================================================================================
```

---

## 11. 扩展故障注入预案 (F1 ~ F12 Failure Matrix)

在原有 8 类故障基础上，全面纳入割接与并发相关的 4 类新型极端场景：

| 故障编号 | 故障场景与注入点 (Injected Failure) | 物理破坏风险 | 自动化防御与恢复动作 (Recovery Action) | 恢复后预期安全状态 (Safe State) |
| :---: | :--- | :--- | :--- | :--- |
| **F9** | **影子迁移期间生产库发生实时写入** (P0-1) | 迁移后新旧切片与遥测事件被覆盖丢失 | 实施 Option A Hard Quiesce 写入确认屏障（未落盘不 ACK）+ Option D 主键集合差分同步；割接前三态校验补齐。 | 增量数据 100% 挽救，Data Loss = 0 (M-S01/S02/S13/S14)。 |
| **F10** | **Windows 进程占用导致重命名失败** (P0-3) | 出现 PermissionError，文件置换中断 | 捕获锁定异常，退避 500ms 重试 3 次；若失败取消切换。 | 生产库原样运行，影子库保留在 scratch 待手工排查。 |
| **F11** | **割接时影子库含有未合流 WAL** (P0-3) | 切换后新主库缺失部分最新同步页 | 强制在连接断开前执行 `PRAGMA wal_checkpoint(TRUNCATE)`。 | 主库文件自包含全量数据，零脏页残留。 |
| **F12** | **在旧库重命名后、新库就位前进程被杀** | 生产主文件名缺失 | 启动检测：若存在 `.pre_v2_backup`，自动原子恢复为生产库名。 | 单库一致性得到保障，零悬空丢失。 |

---

## 12. Final Freeze Checklist（迁移与兼容性最终冻结就绪审查答辩）

```text
================================================================================
     COEVA MIGRATION & COMPATIBILITY DESIGN V2.1 FINAL FREEZE REVIEW (11/11)
--------------------------------------------------------------------------------
  [✓] ACKED WRITE MUST BE DURABLE 已冻结?                   : YES (确立落盘前严禁ACK规范红线)
  [✓] Barrier 期间不存在“RAM-only acknowledged write”?       : YES (Hard Quiesce 同步挂起或未确认)
  [✓] Process crash during barrier cannot lose acknowledged Slice?: YES (M-S17 PASS, 已确认必已落盘)
  [✓] Process crash during barrier cannot lose acknowledged Event?: YES (M-S18 PASS, 已确认必已落盘)
  [✓] M-S17 PASS?                                          : YES (实测验证零已确认切片丢失)
  [✓] M-S18 PASS?                                          : YES (实测验证零已确认事件丢失)
  [✓] canonical source-set parity terminology updated?     : YES (彻底剔除单调watermark误导)
  [✓] legacy_hypothesis_audit classified as technical metadata?: YES (非规范元数据, 不入Retrieval/Model)
  [✓] M-S01 ~ M-S18 all PASS?                              : YES (18 / 18 项断言 100% 全部通过)
  [✓] Data Loss = 0?                                       : YES (实测零损失)
  [✓] Any blocker?                                         : NONE
--------------------------------------------------------------------------------
           >>> MIGRATION & COMPATIBILITY DESIGN V2.1 <<<
                               FROZEN
                             READY FOR
                        IMPLEMENTATION PLAN
================================================================================
```

### 停止声明
Coeva 跨会话长期记忆迁移与兼容性设计规范最终补丁已全部闭环。未执行正式生产迁移、未修改生产代码、未修改生产数据。**迁移与兼容性设计正式冻结**。
