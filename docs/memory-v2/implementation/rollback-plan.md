# Co-evolving Companion：跨会话长期记忆 V2.1 回滚预案与崩溃恢复 (Rollback Plan · Final Consistency Edition)
## ——三大回滚地平线、前向修复优先边界与全场景崩溃自愈规程

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Rollback Plan)
> - **核心安全规则 (Implementation Safety Rule)**：
>   **`A rollback must never discard an acknowledged post-cutover write (I-S02, I-S03).`**
>   （任何回滚绝不可丢弃已向用户或调用方返回成功确认的生产写入；割接后一旦产生新 V2 数据，禁止直接覆盖旧库，前向修复为默认策略。）

---

## 1. 三大物理回滚地平线 (Three Rollback Horizons)

打破虚假的“任何时刻一键恢复旧库”幻想，依据系统是否已产生持久化新写入，将回滚严格划分为三大物理地平线：

```text
       [Pre-cutover 阶段]               [割接但未产生新写入]             [割接后已产生新 V2 写入]
───────────────┼────────────────────────────────┼────────────────────────────────────────► 时间
        R0 地平线                        R1 地平线                        R2 地平线
   (完全无损回滚区)                 (安全恢复旧库区)                (前向修复为主，禁止直接覆盖)
```

### R0 地平线 —— Pre-cutover 阶段 (Stage 0 ~ Stage 9)
- **系统状态**：生产库 `data/companion_chronicle.db` 仍运行于 V1；V2 仅在沙箱、临时库或 Dry-run 模式下运行；生产环境 `memory_v2_storage = OFF`；
- **回滚手段**：
  1. **特性开关秒级回滚**：设置 `COEVA_FLAG_*=false`，无需重启退回 V1；
  2. **代码级回滚**：Git revert 当前工作包提交，V2 代码全部分离在 `src/memory/v2/` 命名空间下，零污染；
  3. **沙箱测试库重置**：直接删除临时 `test_*.db*` 与 `shadow_*.db*`；
- **安全性保证**：**100% 绝对安全无损**。

### R1 地平线 —— Cutover before accepting new V2 ACK writes (Stage 10 割接维护窗口)
- **系统状态**：生产库已执行原子重命名切换为 V2，但系统处于维护静默期或刚启动自检，**尚未接受并确认任何新切片或事件（Zero new ACK writes exist）**；
- **回滚手段**：运行 `python -m src.memory.v2.migration.cli --rollback`，将 `.pre_v2_backup` 文件原子覆盖回原库名；
- **安全性保证**：由于尚未向用户或调用方发出过新的写入 ACK，**恢复旧库 100% 绝对无损**。

### R2 地平线 —— Post-cutover after new V2 ACK writes exist (Stage 10 生产运行期与 Stage 11)
- **系统状态**：伴生体已在 V2 下正式向用户提供服务，用户已投喂了新的切片，或者外部 Connector 已产生了新的事件并获得了 Success ACK；
- **铁律约束**：**严禁使用 `.pre_v2_backup` 简单粗暴覆盖当前主库**（否则已向用户承诺落盘的新数据被彻底抹除，直接击穿 `ACKED WRITE MUST BE DURABLE` 规范底线）；
- **官方降级规范声明**：
  > **`Post-cutover downgrade is not guaranteed lossless; forward-fix is the default recovery strategy.`**
  > （割接后降级不保证无损；前向修复为生产故障的默认恢复策略。）
- **恢复与处置手段**：
  1. **高层心智开关热熔断**：若检索或整合逻辑异常，关停对应 Feature Flag（如 `memory_v2_retrieval=OFF`, `memory_v2_consolidation=OFF`），底层存储继续以 V2 Canonical 运行；
  2. **前向修复（Forward-Fix）**：针对代码缺陷快速发布补丁修复；
  3. **非降级兜底反向合并**：若必须恢复 V1 架构，严禁直接覆盖，必须执行专用的双向反向导出工具（Reverse Export Tool），将割接后产生的新增切片（`occurred_at > t_cutover`）完整导出再注入旧表，绝不丢弃单条已确认数据。

---

## 2. 分阶段回滚控制矩阵 (Per-Stage Rollback Matrix)

| 施工阶段 (Stage) | 故障场景与异常现象 | 所属地平线 | 实施回滚动作 (Action) | 回滚后预期安全状态 (Safe State) |
| :--- | :--- | :---: | :--- | :--- |
| **Stage 0: 安全基建** | 特性开关无法解析或导致配置损坏 | R0 | Git revert `src/core/flags.py` | 系统使用硬编码默认 False，V1 原样运行 |
| **Stage 1: 存储底座** | V2.1 DDL 语法报错或索引建立冲突 | R0 | 清空 scratch 临时测试库，修改 `schema.sql` | 生产库完全不感知，测试重新执行 |
| **Stage 2: 沙箱写入** | 沙箱写入报锁冲突或格式异常 | R0 | 修复写入器代码（生产库保持 OFF） | 生产环境零影响，沙箱重新测试 |
| **Stage 3: 关系生命** | 级联删除出现死循环或外键冲突 | R0 | 回退 `lifecycle.py`，重置测试库 | 存量切片与事件不受影响 |
| **Stage 4: 检索流水** | 检索耗时超标或漏召回关键记忆 | R0 | 优化重排参数，不接触生产 | 气泡回忆继续走旧版，零影响 |
| **Stage 5: 整合快路** | 大模型提议格式异常或出现误置失效 | R0 | 强化本地校验器，保持生产只读 | 生产环境无任何脏数据写入 |
| **Stage 6: 理解慢路** | 假说生成逻辑死锁或产生不当推断 | R0 | 修复观察管道与校准流 | 假说严格隔离为 candidate，无越权 |
| **Stage 7: 叙事集成** | 人生章节脱敏重写异常 | R0 | 维持章节禁读状态，修复代码 | 隐私数据绝不泄露 |
| **Stage 8: 迁移工具** | CLI 语法错误或预检公式计算不正确 | R0 | 修复 CLI 代码，不接触生产库 | 生产环境平稳运行 |
| **Stage 9: 金丝雀演练** | 注入故障下 M-S01~M-S18 某一项失败 | R0 | 自动丢弃影子库，修复后重跑 | 严禁进入割接，生产库安全隔离 |
| **Stage 10A 维护窗口**| 割接自检未通过且**零新写产生** | **R1** | `python -m src.memory.v2.migration.cli --rollback` | 恢复 `.pre_v2_backup`，秒级回退至 V1 |
| **Stage 10B/C/D 运行期**| 割接后伴生体服务中且**已有新写入** | **R2** | **关停对应高级语义开关，执行 Forward-Fix** | 保持 V2 存储主写，绝不丢弃已确认新数据 |
| **Stage 11: 历史回填**| 回填导致 CPU 占用高或报错 | R2 | 停止回填进程，重置 `backfill_progress` | 伴生体正常服务，回填断点记录保存 |

---

## 3. 全生命周期崩溃恢复规程 (Crash Recovery Protocol)

| 突发崩溃场景 (Crash Point) | 崩溃时物理状态 | 进程重启后的自愈与恢复动作 (Recovery Behavior) | 幂等性与事实源保证 (Guarantee) |
| :--- | :--- | :--- | :--- |
| **Crash after Raw Write**<br>(切片已写入 SQLite 但应用即刻断电) | SQLite WAL 事务已持久化落盘，但未更新 UI | 启动时 SQLite 自动从 WAL 重做事务；切片物理存在；由于已落盘，无数据丢失。 | 满足 `ACKED WRITE MUST BE DURABLE`，数据 100% 存在。 |
| **Crash before Consolidation**<br>(切片写入已确认，异步整合未启动即崩溃) | 任务记录存在于 `consolidation_jobs` (状态为 `pending`) | 调度器重启后扫描未完成的 `pending` 任务，自动排队重新整合。 | 任务按自增主键排序重放，保证最终一致性。 |
| **Crash during Reconciliation**<br>(调和校验通过，正在执行大事务提交时崩溃) | 事务处于未提交状态 | SQLite 自动 ROLLBACK 未完成事务；状态回滚至提交前；Job 保持未完成状态待重试。 | 零脏数据残留，重试执行满足幂等性。 |
| **Crash during Observation Job**<br>(慢路径正在聚类多会话经历时断电) | 临时聚类中间态在内存中 | 慢路径未提交事务自动丢弃；重启后在下一次空闲调度窗口重新计算。 | 慢路径计算为只读派生，崩溃对主库无任何破坏。 |
| **Crash during Migration**<br>(影子库灌入 11.6 万数据时断电) | 存在未完成的 `shadow_*.db` 文件 | 迁移执行器检测到 `status != 'completed'`，直接物理 `unlink()` 清理影子坏文件。 | 原生产库 100% 完整，允许安全重试全新迁移。 |
| **Crash during Cutover**<br>(旧库已重命名为 backup，新库未置换到位时崩溃) | 目录缺少主库文件名，但存在 `.pre_v2_backup` | 伴生体启动自检检测到无主库但存在 backup，自动原子恢复为生产库名。 | 单库一致性得到保障，零文件悬空。 |
| **Crash during Backfill**<br>(历史切片回填到第 20 条时断电) | `backfill_progress` 记录了最近一次成功提交的切片 ID | 回填引擎重启后从该游标位置继续向后处理。 | 已经处理的切片不再重复处理，幂等安全。 |
