# Co-evolving Companion：跨会话长期记忆 V2.1 检索基准评测计划 (Retrieval Benchmark Plan · Freeze Patch Edition)

> **文档元数据**：
> - **阶段定位**：Technical Retrieval Design & Benchmark (Freeze Patch)
> - **上位冻结规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
> - **实施不变量**：显式遵守 IMPL-1（Episode 不等于 Retention Pin）、IMPL-2（派生记忆强外键多源溯源）、IMPL-3（隐私待脱敏制品立即可读阻断）。

---

## 1. 评测目标与核心原则

针对 Coeva 伴生体桌宠在 Windows 本地轻量运行环境下的真实跨会话记忆需求，本评测旨在回答：
1. **真实失败模式**：当前基于 `LIKE %kw%` 与简单时间正则的 V1 检索器在面对同义改写、跨项目技术混淆、时态置失效及无记忆常识查询时存在哪些量化瓶颈？
2. **多通道收益与消融**：Lexical 通道、Surface Similarity 通道、Contextual/Temporal 通道以及硬前置过滤（Scope / Validity / Privacy）各自带来多少准确度增益？是否需要引入重型本地 Embedding 模型？
3. **避风港语义闭环 (P0 Sanctuary)**：验证避风港模式在熔断反思性自模型回忆（Reflective Recall）的同时，能否精准放行基础任务连续性上下文（Minimum Task Continuity）；
4. **方法学纠偏 (P0 Precision@K)**：建立三级真实 Gold 标注（`must_retrieve` 必须召回、`acceptable_retrieve` 允许召回、`must_not_retrieve` 严禁召回），严格区分**查询级通过率（Query Pass Rate）**与**候选级精确率（Candidate Precision@3）**；
5. **数据集分离与参数验证 (P1 DEV/Holdout)**：彻底分离 29 个 DEV 开发集与 15 个独立未见过的 HOLDOUT 验证集，避免检索参数（0.6 / 0.4 / 0.16）过拟合；
6. **资源与运行时边界**：在零外部重型服务（无 Docker、无外部 Vector DB、无 Redis/PostgreSQL）前提下，对启动耗时、首查延迟、稳态延迟与内存增量做严格的测量分级（MEASURED vs PROJECTED）。

---

## 2. 评测硬件与软件基线

- **操作系统**：Windows 11 Professional (AMD64)
- **执行环境**：Python 3.11.15 (`.venv` 虚拟环境，由 `uv` 管理)
- **数据库**：SQLite 3.53.1 (WAL 模式，支持内置 FTS5 虚拟表扩展)
- **生产数据源**：`data/companion_chronicle.db`（包含 42 条真实切片与 11.5 万条脱敏遥测骨架）
- **性能测量工具**：Python `time.perf_counter()` 高精度计时器

---

## 3. 评测数据集设计（DEV Set 29 用例 + HOLDOUT Set 15 用例）

评测数据集定义在 `docs/memory-v2/retrieval/retrieval-benchmark-cases.json`，分为两个完全独立的子集：

### 3.1 开发调优集 (DEV Set · 29 Cases)
涵盖 A ~ Q 17 大类基础场景及 7 大对抗句式：
- **A. No-memory-needed**：通用编程语法与外部常识，期望 100% 返回空（NO_MEMORY）；
- **B. Exact factual recall**：物理设备/硬件规格事实精确符号匹配；
- **C. Paraphrased semantic recall**：口语同义偏好改写（如“刺眼浅色”对应“暗黑模式”）；
- **D. Project-scoped recall**：当前活动工程（`co-evolving-companion`）绑定的技术决策（PySide6）；
- **E. Cross-project contamination traps**：在 CRM 项目中问前端框架，严禁召回桌宠项目的 PySide6；
- **F. Current vs historical preference**：当前状态查询只返回 active 事实；
- **G. Superseded memory**：显式历史更迭查询，允许且要求召回 superseded 事实；
- **H. Ambiguous memory**：存在冲突未决事实（代码单双引号），保留 ambiguous 标记；
- **I. Explicit episodic query**：显式经历回顾（“上周排查 PySide6 闪退”）；
- **J. Weak reference / continuity**：极弱文本指代（“和上次一样”、“还是那个”），依赖时序连续性；
- **K. Relationship rule**：相处硬边界（“对我提建议的原则”）；
- **L. Emotional false-recall traps**：负面情绪抱怨，避风港模式闭锁反思回忆，返回空；
- **M. Duplicate evidence**：重复投喂去重与独立证据计数核验；
- **N. Unresolved scope**：未决范围事实严禁在特定活动工程中武断生效；
- **O. Mixed Chinese-English entities**：中英技术词混排保真匹配；
- **P. Time-qualified recall**：明确时间限定（“昨天聊了什么”），严格区间过滤；
- **Q. No relevant memory**：知识库无对应记忆，100% 判为 NO_MEMORY；
- **ADV. Adversarial Cases**：对抗句式与 IMPL-3 隐私待脱敏制品强力阻断测试。

### 3.2 独立验证集 (HOLDOUT Set · 15 Cases)
不参与任何权重与阈值调参，专门检验泛化能力：
- **HOLD_S1 (P0 Sanctuary Continuity)**：“*烦死了，又是刚才那个报错。*”（`sanctuary=True`，要求放行最近任务报错，严禁历史受挫与心理推断）；
- **HOLD_S2 (P0 Sanctuary Suppression)**：“*最近我是不是越来越容易烦躁？*”（`sanctuary=True`，反思性回忆 100% 闭锁）；
- **HOLD_PRE_01 (P1 Fast-Gate Precedence)**：“*我们之前是怎么解决 PySide 闪退问题的？*”（包含“怎么”但有“之前”，历史意图高于通用QA快筛，严禁误杀）；
- **HOLD_SEM_01**：“*做复杂东西前我更希望先把框架定下来*”（同义改写：框架定下来 -> 先稳定架构设计）；
- **HOLD_SEM_02**：“*别老提醒我休息喝水*”（同义改写：别提醒休息 -> 不希望被频繁打断）；
- **HOLD_NEG_01 (Hard Negative)**：“*机械键盘的手感和静音红轴有什么渊源？*”（字面很像但属于常识，必须返回空）；
- **HOLD_XPROJ_01**：CRM 项目询问构建命令，严禁召回桌宠项目测试命令；
- **HOLD_MULTI_01**：多重合法项目技术候选，验证 Top-3 容纳度；
- **HOLD_UNRES_01**：未知临时工程，严禁未决 pytest 记忆跨界生效；
- **HOLD_SUPER_01**：CRM 前端当前打包工具，必须返回 Vue3+Vite，拒绝废弃的 React；
- **HOLD_THRESH_01**：边界通用提问，验证阈值拦截；
- **HOLD_MIX_01**：开发机显存多大；
- **HOLD_AMBIG_01**：Python 项目引号规范；
- **HOLD_PRIV_01 (IMPL-3)**：请总结第一章内容（正在脱敏中，100% 阻断）；
- **HOLD_PAST_01**：最初习惯的命令行终端（显式旧事实 CMD）。

---

## 4. 对比评测臂设计 (Benchmark Arms)

- **Arm 0: Current V1 Baseline（当前生产基线）**：纯 `LIKE %kw%` + 简单停用词 + 天数正则；
- **Arm 1: Improved Lexical-Only（改进词法通道）**：基于 SQLite FTS5 的 Unigram + Bigram 分词匹配；
- **Arm 2: Surface Similarity Only（表层统计相似度通道）**：纯 N-gram TF-IDF 向量余弦打分；
- **Arm 3: Lexical + Surface (No Hard Filters)**：词法与统计向量融合，但不带前置硬过滤；
- **Arm 4: Proposed Coeva V2.1 Pipeline（V2.1 候选混合流水线）**：
  五阶架构：优先级意图快筛门 -> 目标数据面选择 -> 四重强类型硬过滤 -> 0.6 词法 + 0.4 表层相似度融合打分 -> 置信度阈值门控 (0.16)。

---

## 5. 核心评估指标定义（方法学纠偏）

1. **Query Pass Rate (查询通过率)**：
   $$\text{Query Pass Rate} = \frac{\text{结果完全满足 must 命中、无 forbidden 侵入且符合 NO\_MEMORY 预期的查询数}}{\text{总查询数}}$$
2. **Recall@3 (必须召回率)**：
   $$\text{Recall@3} = \frac{\text{命中的 must\_retrieve 实体总数}}{\text{期望的 must\_retrieve 实体总数}}$$
3. **Candidate Precision@3 (候选级精确率)**：
   $$\text{Candidate Precision@3} = \frac{\text{返回候选列表中属于 must 或 acceptable 的条目数}}{\text{返回的全部候选条目总数}}$$
4. **NO_MEMORY Accuracy (静默判决准确率)**：
   $$\text{NO\_MEMORY Acc} = \frac{\text{无记忆期望场景下实际返回空列表的次数}}{\text{无记忆期望场景总数}}$$
5. **False Recall Rate (误召回率)**：
   $$\text{False Recall Rate} = \frac{\text{无记忆期望场景下错误召回出记忆项的次数}}{\text{总查询数}}$$
6. **Forbidden Retrieval Rate (禁止召回率)**：
   $$\text{Forbidden Rate} = \frac{\text{命中 must\_not 列表中条目的次数}}{\text{总查询数}}$$（目标必须为 0.00%）
7. **Cross-Project Contamination Count (跨项目污染次数)**：
   返回属于其他独立工程记忆的累计次数（目标必须为 0 次）。
8. **Privacy Leakage Count (待脱敏制品泄漏次数)**：
   返回 `needs_privacy_redaction == 1` 制品的累计次数（目标必须为 0 次）。
