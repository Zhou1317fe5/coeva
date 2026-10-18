# Co-evolving Companion：跨会话长期记忆 V2.1 迁移与兼容性架构决策记录 (Migration Decision Record · MDR)

> **决策状态与元数据**：
> - **决策编号**：MDR-2026-01 (Technical Migration & Compatibility Architecture Decision)
 > - **决策状态**：`ACCEPTED & FROZEN` (Cutover Correctness Patch Completed & Verified)
> - **上位规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
>   - `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
>   - `docs/memory-v2/consolidation/consolidation-reconciliation-design.md` (Consolidation V2.1 Frozen)
> - **实证支持**：
  - `run_final_correctness_suite.py` (全量 11.6 万数据金丝雀演练与 M-S01~M-S18 断言套件)
>   - `docs/memory-v2/migration/migration-benchmark-plan.md` (实测基准报告 · Final Freeze 版)
>   - `docs/memory-v2/migration/migration-validation-plan.md` (四阶验证方案 · Final Freeze 版)

---

## 1. 核心上下文与问题陈述 (Context)

Coeva 正在使用的生产数据库 `data/companion_chronicle.db`（体积约 47.55 MB）包含 44 条珍贵用户投喂原话切片与 116,625 条客观行为遥测骨架。在升级至 V2.1 强类型数据模型时，必须解决三大核心工程挑战：
1. **快照至割接的实时写入保护**：避免在 1.5 秒影子构建期间丢失新产生的切片与遥测事件；
2. **遥测隐私边界保真**：杜绝以“无损迁移”为由将不可见的 Prompt/CoT 或非规范字段带入 V2.1 规范表；
3. **Windows 文件锁与 SQLite WAL 多文件状态切换**：杜绝单文件简单重命名的脆弱假设。

---

## 2. 核心架构决议汇总 (Decisions)

### 决议 1：选定“写入确认硬静默屏障与主键集合差分”无损切换架构 (Option A/D Hybrid: Hard Quiesce Barrier & Set Difference Delta Sync)
- **决议**：
  - 严禁原地修改（In-place ALTER）；
  - **彻底废止不可靠的普通 ROWID 水位线**：生产库 `slices` 与 `events` 采用 `TEXT PRIMARY KEY` 且非 `AUTOINCREMENT`，DELETE 后新 INSERT 会导致 ROWID 回退复用（已由实测确凿证实），无法满足单调 CDC 序列要求；
  - **写入确认硬性不变量（`ACKED WRITE MUST BE DURABLE`）**：严禁执行“写入内存队列即返回成功”的脆弱假象；任何向调用方或用户返回成功的写入，必须已落盘至当前权威库或持久化日志；
  - **Option A (Hard Quiesce Migration Barrier 写入持久化屏障)**：在迁移全周期（~1.58s）暂停生产库所有写者（`record_slice`, `LocalEventBus`, `HermesConnector`）与删除者（`RetentionCleaner`），应用层写入处于同步挂起或延迟响应状态（未落盘绝不返回 Success ACK）；
  - **Option D (Canonical ID Set Difference 集合差分与确定性冲突检测)**：废止 `rowid > t0_max` 与掩盖冲突的 `INSERT OR IGNORE`，采用权威业务主键（`id` / `slice_id` / `event_id`）集合差分对齐；
  - **三态冲突判定规程**：
    1. *同 ID 且 Payload 完全一致*：合法幂等重放，视为 **NOOP**；
    2. *同 ID 但 Payload 不一致*：判定为 **MIGRATION CONFLICT**，验证硬报错，**禁止割接并回滚**；
    3. *新 ID*：执行 **INSERT**。
- **依据**：真实数据演练验证，M-S13~M-S18 六大对抗与崩溃断言 100% 通过，杜绝任何静默冲突掩盖、ROWID 复用丢数据以及内存队列崩溃丢数据。
### 决议 2：严格执行字段级遥测隐私审计与过滤 (P0-2)
- **决议**：
  - 逐字段审计确认 `error_message` 仅包含脱敏错误摘要（如 `bash failed`），100% 映射为 `error_category`；
  - 遗留非规范字段 `provenance` 从规范模型中剥离；
  - 严禁任何 Prompt、CoT 或工具执行正文进入 `event_skeletons`。

### 决议 3：确立 Windows + SQLite WAL 数据库状态完整割接协议 (P0-3)
- **决议**：
  - 严禁仅重命名 `.db` 单文件；
  - 必须依次执行：应用程序连接句柄释放 -> 对生产库与影子库分别执行 `PRAGMA wal_checkpoint(TRUNCATE)` 确保 WAL/SHM 尺寸归零 -> 利用 `os.replace` 原子置换主文件 -> 重新打开连接并校验版本 `PRAGMA user_version == 20261018`。

 ### 决议 4：确立 Dynamic WAL-Aware 实际文件集空间模型与安全门禁 (P0-4)
 - **决议**：
   - 废止单一静态 3x 简化假定；前置空间检查必须动态读取真实文件集：`required_free_space = prod_db_bytes + prod_wal_bytes + prod_shm_bytes + snapshot_projected_bytes + shadow_projected_bytes + backup_bytes + safety_margin (50MB)`；
   - 保留 `floor_heuristic = MAX(150 MB, 3.0 * Production_DB_Size)` 作为兜底基准；
   - 最终前置门禁：`final_required_free_space = MAX(required_free_space, floor_heuristic)`（当前生产库实测门禁为 **225.94 MB**）。
### 决议 5：确立三项最高迁移安全红线 (Migration Safety Invariants)
- **红线 1 (未知范围强制 unresolved)**：旧切片全部映射为 `scope = 'unresolved', project_id = NULL`，严禁未经证实默认升级为全局；
- **红线 2 (历史假说绝对禁止自动转正，审计表属非规范技术元数据)**：旧假说原样平移，状态强制设为 `candidate`；原始状态留存在 `legacy_hypothesis_audit` 表中（属于技术审计元数据，不参与检索与整合，不属于冻结数据模型）；
- **红线 3 (遥测事件严禁凭空打 Pin)**：11.6 万条遥测骨架保留原 Hash 与 transient 属性，迁移过程不打 Retention Pin，不立即执行 TTL 清空；
- **红线 4 (写入确认必已落盘 ACKED WRITE MUST BE DURABLE)**：绝不向未物理提交于磁盘的飞行中数据发出 Success ACK。

### 决议 6：切断双主双写，确立 SQLite 唯一权威事实源 (Single Canonical Master)
- **决议**：应用层全面废除向 `raw_slices.jsonl` 的直接写入；切片仅写入 SQLite `raw_slices`；`raw_slices.jsonl` 降级为 SQLite 事务提交后的异步单向导出流。

### 决议 7：兼容视图基于零访问指标退场 (Bounded Deprecation)
- **决议**：在 V2.1 数据库中提供零开销只读兼容视图 `legacy_slices_view` 与 `legacy_events_view`；当所有读取组件改造完毕且连续 7 天零访问时，方可调度 DROP。

---

## 3. 结果与影响 (Consequences)

### 正向收益 (Positive)
1. **绝对数据安全与可逆性**：原库全程不动，Hard Quiesce 与 Set-Difference 消除任何 ROWID 复用漏写、静默冲突与崩溃丢已确认数据的风险；
2. **极速顺滑升级**：11.6 万行数据 1.58 秒完成迁移，增量补齐 0.28ms，文件置换 < 1ms，用户零感知；
3. **全量 18 项安全断言保障**：新增 M-S13~M-S18，防范删除后插入、重复重放、冲突篡改与 Barrier 期突发崩溃；
3. **彻底终结双主裂脑**：消除了两处双写带来的不一致隐患；
4. **完全自洽于上位规范**：未新增任何未冻结的实体或字段，100% 遵从 Architecture、Data Model、Retrieval 与 Consolidation 四大冻结规范。

### 实施边界 (Implementation Boundary)
- 本决策记录代表迁移方案与架构规范正式冻结；
 - 正式生产割接执行需在下一阶段（Implementation Plan）完成后，按照操作规程统一推进。
- **冻结声明**：全套规范同步更新与 M-S01~M-S18 终审验证已 100% 通过，本决策正式重新签发为 `ACCEPTED & FROZEN`。未执行生产迁移、未修改生产数据。
