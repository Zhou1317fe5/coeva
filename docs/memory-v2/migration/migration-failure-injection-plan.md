# Co-evolving Companion：跨会话长期记忆 V2.1 迁移故障注入与防御预案 (Migration Failure Injection Plan · Final Freeze Edition)

> **文档元数据**：
> - **阶段定位**：Migration & Compatibility Specification (Failure Injection)
> - **设计目标**：确保在任何步骤突发崩溃、断电、磁盘满、句柄冲突或实时并发写入时，系统均能回到确定性的安全状态，零数据损坏。

---

## 1. 十二大极端故障场景与确定性防御响应矩阵 (F1 ~ F12 Failure Matrix)

```text
[系统升级流程启动] ──► 监测各阶段异常 ──► 执行针对性安全熔断与回滚
```

| 故障编号 | 故障场景与注入点 (Injected Failure) | 物理破坏风险 | 自动化防御与恢复动作 (Recovery Action) | 恢复后预期安全状态 (Safe State) |
| :---: | :--- | :--- | :--- | :--- |
| **F1** | **备份过程断电或被杀**<br>（发生在 `src.backup()` 期间） | 产生未写完的 `.db.backup` 坏文件 | 1. 捕获未完成信号；<br>2. 物理删除临时备份文件；<br>3. 原生产库主文件与 WAL 文件零改动。 | 原生产库 100% 完整，旧版程序正常启动运行。 |
| **F2** | **影子库建表后崩溃**<br>（建表完成但数据未平移） | 磁盘残留空库 `shadow_companion_v2.db` | 1. 重启检测到 `user_version == 0` 但存在影子文件；<br>2. 检查 `_schema_migrations` 无完成记录；<br>3. 物理 `unlink` 删除影子文件。 | 状态回到初始态，允许安全发起全新迁移。 |
| **F3** | **事件批量导入中途中断**<br>（11.6 万条传输到 5 万条时断电） | 影子库数据不完整，行数撕裂 | 1. 大事务未执行 `COMMIT`，SQLite 自动回滚；<br>2. 影子库仍处于未就绪状态；<br>3. 重启直接丢弃半截影子文件。 | 原生产库完好无损，零脏数据污染。 |
| **F4** | **后置验收检查未通过**<br>（行数不对齐或外键违规） | 潜在的逻辑脏数据扩散至生产 | 1. 验证器抛出 `MigrationValidationError`；<br>2. 严禁进入原子切换阶段；<br>3. 触发自动化 `ROLLBACK`，清理影子库并报警。 | 割接流程被彻底中止，生产数据库保持旧版正常运行。 |
 | **F5** | **磁盘空间耗尽 (< 225.94MB)**<br>（基于实际文件集共存模型） | 产生 `disk I/O error` 甚至损坏正在写入的库 | 1. 前置检查（Preflight）阶段读取真实文件集（db+wal+shm+snapshot+shadow+backup+50MB）；<br>2. 若可用空间小于动态门禁（实测 225.94 MB），直接硬阻断迁移；<br>3. 弹出系统级桌面通知提示清理磁盘。 | 迁移不会启动，系统保持绝对安全 (M-S09)。 |
| **F6** | **文件原子切换遭遇 Windows 锁占用**<br>（发生在 `os.replace` 重命名阶段） | 抛出 `PermissionError`，导致切换中断 | 1. 捕获重命名文件锁定异常；<br>2. 记录告警并安全退避 500ms，重试最多 3 次；<br>3. 若仍被未知进程占用，取消割接，原库原封不动。 | 影子库保留在临时目录待手动排查，生产环境继续使用原库。 |
| **F7** | **旧版可执行程序打开新版数据库**<br>（割接后用户误用老版 exe） | 旧代码用老 Schema 强行写新库造成表损坏 | 1. 旧版程序启动前置检查 `PRAGMA user_version`；<br>2. 若版本大于等于 20261018，直接弹出退出框拒绝连接；<br>3. 实现 Fail-Fast 物理防御。 | 新版数据库结构得到物理保护，零外键破坏。 |
| **F8** | **升级运行后用户显式要求回滚**<br>（割接 10 分钟内用户需要退回旧版） | 新旧版本割接反向恢复 | 1. 伴生体停止服务；<br>2. 将 `.pre_v2_backup` 文件原子覆盖回 `companion_chronicle.db`；<br>3. 恢复旧版程序启动。 | 系统完全倒退回迁移前一刻状态。 |
| **F9** | **影子迁移期间生产库发生实时写入**<br>（T0~T1 构建期间产生 Live Writes） | 迁移后新旧切片与遥测事件被覆盖丢失 | 1. 实施 Option A Hard Quiesce 写入确认屏障（未落盘绝不 ACK）；<br>2. Option D 权威主键差集补齐并校验 Payload。 | 增量数据 100% 挽救，Data Loss = 0 (M-S01/S02/S03)。 |
| **F10** | **Windows 进程打开句柄阻断重命名**<br>（P0-3 句柄安全） | `os.replace` 抛出拒绝访问 | 1. 自动执行连接池与句柄强制 Close；<br>2. 指数退避 500ms 重试 3 次；<br>3. 失败时绝对禁止强行覆盖，保持 V1 可恢复。 | 生产主库零损坏 (M-S07)。 |
| **F11** | **割接时影子库含有未合流 WAL**<br>（P0-3 WAL 脏页） | 切换后新主库缺失部分最新同步页 | 1. 强制在断开连接前执行 `PRAGMA wal_checkpoint(TRUNCATE)`；<br>2. 校验 WAL 与 SHM 文件尺寸归零；<br>3. 主库文件自包含全量数据。 | 零脏页丢失，WAL 状态完整 (M-S06)。 |
 | **F12** | **在旧库重命名后、新库就位前进程被杀**<br>（极窄原子切换窗口崩溃） | 生产主文件名缺失 | 1. 启动自检检测到无 `companion_chronicle.db` 但存在 `.pre_v2_backup`；<br>2. 自动将备份原子恢复为生产库名。 | 单库一致性得到保障，零悬空丢失 (M-S08)。 |
 | **F13** | **T0 后删除最大 RowID 导致回退复用**<br>（M-S13/M-S14 对抗注入） | `rowid > t0_max` 增量条件失效，新行被永久漏掉 | 1. 彻底废止 ROWID 水位查询，采用 `NOT EXISTS` 权威主键集合差分；<br>2. Option A MigrationBarrier 阻断并发删除。 | 新插入切片与事件 100% 捕获，零数据丢失 (M-S13/M-S14 PASS)。 |
 | **F14** | **增量同步网络/重试产生重复重放**<br>（M-S15 场景） | 产生重复业务行破坏去重键 | 1. 基于权威主键做差集插入；<br>2. 对已有 ID 校验 Payload 一致后判为合法幂等 NOOP。 | 影子库生成且仅生成唯一样本，Duplicate Canonical Rows = 0 (M-S15 PASS)。 |
| **F15** | **增量同步遭遇同 ID 篡改冲突**<br>（M-S16 对抗注入） | `INSERT OR IGNORE` 掩盖冲突篡改 | 1. 确定性冲突检测发现同 ID 内容不一致；<br>2. 抛出 `MigrationConflictError`，硬报错阻断割接并触发安全回滚。 | 严禁掩盖冲突，保证 Canonical 正确性 (M-S16 PASS)。 |
| **F16** | **Barrier 期间进程突发崩溃**<br>（M-S17/M-S18 注入） | 内存队列丢失已承诺用户的写入 | 1. 严格遵守 `ACKED WRITE MUST BE DURABLE`；<br>2. 飞行中写入未持久化前绝不发出 Success ACK；<br>3. 崩溃后用户获知未完成可安全重试，已 ACK 写入早已落盘。 | 零已确认数据丢失，No Acknowledged Data Lost (M-S17/M-S18 PASS)。 |

---

## 2. 故障恢复核心断言 (Recovery Invariant Assertions)

- **断言 1 (Zero Half-State)**：任何步骤失败，系统要么处于完全升级成功的 V2.1 状态，要么处于原封不动的 V1 状态，**绝对不允许存在半迁移的中间分裂状态**；
- **断言 2 (Zero Raw Loss)**：任何故障注入场景下，`raw_slices` 原始用户输入明文**损失率绝对为 0**；
 - **断言 3 (Zero Write Gap)**：即使在迁移构建窗口内持续写入，Option A/D 混合割接协议确保**实时写入数据损失率为 0**；
- **断言 4 (Fail-Closed Conflict)**：任何同 ID 内容冲突篡改均被确定性捕获并硬阻断，**严禁通过 `INSERT OR IGNORE` 隐蔽掩盖**；
- **断言 5 (Acked Write Durability)**：严禁内存队列假装持久化，任何获得成功确认的写入**在任何崩溃场景下 100% 可恢复**。
