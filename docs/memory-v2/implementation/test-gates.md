# Co-evolving Companion：跨会话长期记忆 V2.1 验收门禁与测试矩阵 (Test Gates · Final Consistency Edition)
## ——各阶段物理退出门禁、量化指标标准与黄金基准回归规程

> **文档元数据**：
> - **阶段定位**：Implementation Engineering Specification (V2.1 Test Gates)
> - **核心原则**：阶段推进以自动化客观证据为准绳；**验收门禁严格继承 Frozen Benchmark 实测事实，严禁凭空捏造未冻结指标（I-S08）**；任何未达标阶段禁止强行进入下一阶段。

---

## 1. 黄金回归测试套件架构 (Golden Regression Harness)

在实施各阶段中，建立统一的回归自动化测试集，分为四大类：

1. **存量保活回归套件 (Legacy Regression Suite)**：
   - 包含原工程 `tests/test_memory.py`, `tests/test_memory_retriever.py`, `tests/test_feeder.py` 等 19 个核心测试用例；
   - 目标：确保在 V2.1 实施全过程中，**存量功能 100% 保持通过，零破坏**。
2. **检索黄金基准套件 (Retrieval Golden Suite)**：
   - 复用已冻结的 29 个 DEV 用例与 15 个 HOLDOUT 用例（共 44 个用例，涵盖显式时间、主题长尾、歧义问答与 NO_MEMORY 闲聊）；
   - 目标：验证新检索流水线的指标完全不劣于冻结基线（**DEV 查询通过率 $\ge 93.10\%$，HOLDOUT 查询通过率 $100.0\%$，Forbidden 召回率 $0.00\%$，延迟基线 ~1.88ms**）。
3. **心智整合黄金基准套件 (Consolidation Golden Suite)**：
   - 复用已冻结的 20 个 DEV 用例与 15 个 HOLDOUT 用例（共 35 个用例）；
   - 目标：验证 **False ADD = 0, False SUPERSEDE = 0, False REINFORCE = 0 以及 S-01~S-14 物理安全断言 100% PASS**。
4. **割接安全断言套件 (Cutover Safety Assertions Suite)**：
   - 包含 M-S01 ~ M-S18 全部 18 项割接断言；
   - 目标：在金丝雀和生产演练中验证零数据丢失、零静默冲突掩盖、Crash-Safe 与 WAL 完整性。

---

## 2. 各阶段物理退出门禁 (Per-Stage Exit Criteria)

| 阶段编号 | 阶段名称 | 核心物理验证手段 | 必须满足的量化指标门禁 (Exit Criteria) | 未达标处置 |
| :---: | :--- | :--- | :--- | :--- |
| **Stage 0** | 安全基建 | `pytest tests/test_flags.py` | 1. 6 个特性开关支持层级覆盖；<br>2. 校验非法组合 100% Fail-Closed；<br>3. 存量 19 个测试 100% PASS。 | 阻断推进，修复 Flags |
| **Stage 1** | 存储底座 | `pytest tests/memory_v2/test_schema.py` | 1. 20 张物理表与 FTS5 虚表顺利建立；<br>2. `PRAGMA foreign_key_check` 违规行数 = 0；<br>3. 基础 CRUD 事务与约束测试 100% PASS。 | 阻断推进，修复 Schema |
| **Stage 2** | 沙箱写入 | `pytest tests/memory_v2/test_canonical_write.py` | 1. 切片与事件在测试沙箱库写入成功；<br>2. **生产环境 `memory_v2_storage = OFF` 零变动 (I-S01)**；<br>3. 沙箱满足 `ACKED WRITE MUST BE DURABLE` 契约。 | 阻断推进，修复写入器 |
| **Stage 3** | 关系生命 | `pytest tests/memory_v2/test_lifecycle.py` | 1. 孤儿关联（Orphan Links）违规数 = 0；<br>2. **硬删除 8 步依赖闭环测试 100% PASS (I-S07)**；<br>3. 唯一证据硬删除后高层假说自动 Retract 率 = 100%；<br>4. 隐私删除触发 `needs_privacy_redaction = 1` 物理禁读率 = 100%。 | 阻断推进，修复级联算法 |
| **Stage 4** | 检索流水 | `pytest tests/memory_v2/test_retrieval.py` | **严格对齐 Frozen Benchmark (I-S08)**：<br>1. HOLDOUT 查询通过率 = 100.0% (15/15)；<br>2. HOLDOUT 必须召回率 = 100.0%，Forbidden 召回率 = 0.00%；<br>3. DEV 查询通过率 $\ge 93.10\%$；<br>4. NO_MEMORY 判定正确率 = 100.0%；<br>5. 同硬件环境单次检索耗时符合 ~1.88ms 基线，常驻内存增量 $< 5\text{MB}$。 | 阻断推进，优化重排参数 |
| **Stage 5** | 整合快路 | `pytest tests/memory_v2/test_reconciliation.py` | 1. 35 个 Consolidation 用例 100% PASS；<br>2. False ADD = 0, False SUPERSEDE = 0, False REINFORCE = 0；<br>3. S-01~S-14 物理不变量全量 PASS；<br>4. 队列数据明确隔离为非规范元数据 (I-S06)；<br>5. 单次校验耗时 $< 0.1\text{ms}$。 | 阻断推进，强化校验器 |
| **Stage 6** | 理解慢路 | `pytest tests/memory_v2/test_observation.py` | 1. Observation 成功聚类 Raw Evidence 与 Episode；<br>2. 候选假说全部隔离为 candidate，未经校准自动转正数 = 0；<br>3. 用户校准四态（YES/PARTLY/NO/NOT_NOW）流转 100% 吻合规范。 | 阻断推进，修复状态机 |
| **Stage 7** | 叙事集成 | `pytest tests/memory_v2/test_chapter_privacy.py` | 1. 章节生成仅消费 confirmed_insights 与合法经历；<br>2. 遇到 `needs_privacy_redaction == 1` 时物理禁读率 = 100%；<br>3. 异步脱敏重写后文本不含已删除敏感切片。 | 阻断推进，修复脱敏流 |
| **Stage 8** | 迁移工具 | `pytest tests/memory_v2/test_migration_cli.py` | 1. 命令行参数支持 `--dry-run`, `--execute`, `--rollback`；<br>2. 动态磁盘门禁计算公式正确；<br>3. 不与伴生体启动耦合，仅通过显式调用触发。 | 阻断推进，重构 CLI |
| **Stage 9** | 金丝雀演练 | `pytest tests/memory_v2/canary_rehearsal.py` | 1. 在生产全量 47.55MB 数据副本上运行；<br>2. **M-S01 ~ M-S18 全部 18 项安全断言 100% PASS (I-S09)**；<br>3. 44 条切片逐字哈希一致，事件骨架保真；<br>4. 注入故障下零已确认数据丢失。 | **最高硬阻断：严禁进入生产割接** |
| **Stage 10A**| 存储割接 | 生产后置校验脚本 | 1. 生产库 `PRAGMA user_version == 20261018`；<br>2. 切片内容完整性 = 100%，外键违规数 = 0；<br>3. 激活 `memory_v2_storage = ON`，切断 JSONL 双写；<br>4. **高层语义开关保持 OFF (I-S04)**。 | 触发原子回滚脚本还原旧库 |
| **Stage 10B/C/D**| 语义功能启用 | 灰度回归验证 | 依次启用检索、整合与自模型，系统指标稳定。 | 关停对应特性开关降级 |
| **Stage 11**| 后台回填 | `pytest tests/memory_v2/test_backfill.py` | 1. 回填进程支持断点续传与幂等重试；<br>2. 设计预算目标（Performance Budget）：CPU 峰值占用 $< 5\%$；<br>3. 应用关机信号下 1.0 秒内优雅挂起。 | 调大休眠间隔或挂起回填 |

---

## 3. 测试分类矩阵 (Testing Matrix)

| 模块 / 目标功能 | 单元测试 (Unit) | 集成测试 (Integration) | 压力/性能测试 (Benchmark) | 故障注入测试 (Failure Injection) |
| :--- | :---: | :---: | :---: | :---: |
| **特性开关 (WP-0)** | `test_flags.py` | `test_flags_live.py` | (无) | 非法依赖组合 Fail-Closed 测试 |
| **存储仓储 (WP-1)** | `test_entities.py` | `test_schema.py` | 批量写入吞吐测试 | 并发多连接争用测试 |
| **生命周期 (WP-2)** | `test_provenance.py` | `test_lifecycle.py` | (无) | 硬删除 8 步依赖闭环测试 |
| **准入抽取 (WP-3)** | `test_admission.py` | `test_extractor.py` | (无) | 低熵异常输入测试 |
| **调和引擎 (WP-4)** | `test_echo_guard.py` | `test_reconciliation.py` | 校验器耗时标杆测试 | 篡改冲突提议注入 |
| **任务队列 (WP-5)** | `test_queue.py` | `test_scheduler.py` | 高频投喂防抖测试 | 关机突发中断测试 |
| **观察慢路 (WP-6)** | `test_calibration.py` | `test_observation.py` | (无) | 自动转正越权测试 |
| **技术检索 (WP-7)** | `test_channels.py` | `test_retrieval.py` | 44个基准集延迟与内存评测 | FTS5 语法注入测试 |
| **回忆门控 (WP-8)** | `test_recall_gate.py` | `test_sanctuary_recall.py` | (无) | 避风港极限压力测试 |
| **人生章节 (WP-9)** | `test_firewall.py` | `test_chapter_privacy.py` | (无) | 隐私未脱敏强读测试 |
| **迁移工具 (WP-10)**| `test_migration_cli.py`| `test_barrier.py` | 动态空间公式测试 | 磁盘不足中断测试 |
| **兼容层 (WP-11)** | `test_adapter.py` | `test_compatibility.py` | (无) | 双主旧写入注入 |
| **金丝雀 (WP-13)** | (无) | `canary_rehearsal.py` | 生产数据 1.58s 演练 | 删除最大RowID、篡改、崩溃注入 |
| **回填引擎 (WP-12)**| `test_backfill_tracker.py`| `test_backfill.py` | CPU 限频资源监控 | 中途中断断点续传测试 |
