# Co-evolving Companion：跨会话长期记忆 V2.1 记忆巩固与调和评测计划 (Consolidation Benchmark Plan)

> **文档元数据**：
> - **阶段定位**：Consolidation / Reconciliation Technical Design & Benchmark
> - **上位冻结规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
>   - `docs/memory-v2/retrieval/technical-retrieval-design.md` (Technical Retrieval V2.1 Frozen)
> - **三大实施不变量约束**：IMPL-1（Episode 不等于 Retention Pin）、IMPL-2（派生记忆强外键多源溯源）、IMPL-3（待脱敏制品不可读）。

---

## 1. 评测目标与核心挑战

记忆巩固（Consolidation）与调和（Reconciliation）回答的是：
> **“发生过的原始证据（Raw Evidence）如何被安全、准确地转化为值得长期留存的派生记忆（Derived Semantic Memory / Observation），并在冲突、重复、变化、否定、删除与不确定情况下保持可追溯与可逆。”**

核心评测目标包括：
1. **准入门禁有效性 (Admission)**：闲聊、问候、UI 测试与非持久性状态能否被 100% 拦截并判定为 `NOOP_LONG_TERM`；
2. **调和动作判决精度 (Reconciliation Actions)**：在 `ADD`、`SUPERSEDE`、`REINFORCE`、`AMBIGUOUS`、`NOOP` 五类动作中是否出现误操作（特别是最危险的 `False ADD`、`False SUPERSEDE`、`False REINFORCE`）；
3. **回音壁与重放防御 (Anti-Echo & Dedup)**：伴生体自我复述的历史记忆被用户附和确认时，能否彻底阻断回音壁自闭环；Connector 崩溃重放能否被幂等抑制；
4. **范围与主权边界 (Scope & Authority)**：未知工程能否稳定停留在 `unresolved` 状态，用户主观自我陈述能否压倒系统对遥测行为的心理猜测；
5. **候选架构对比与裁定 (Designs A vs B vs C)**：对比纯规则型、纯大模型型与两阶段混合型（LLM 提议 + 确定性校验器）的正确率、抗风险性与可解释性。

---

## 2. 评测数据集设计（20 类基准场景 · Covering A ~ T）

评测数据集定义在 `docs/memory-v2/consolidation/consolidation-benchmark-cases.json`：

| 场景代号 | 场景名称与测试目标 | 输入特征 | 预期准入与调和动作 |
| :--- | :--- | :--- | :--- |
| **A** | **New fact → ADD** | 全新客观事实（主显示器型号） | `ADMIT` -> `ADD` (proof=1) |
| **B** | **Duplicate transport → NOOP** | 2秒内按钮双击重试（物理 dedup 键命中） | `NOOP_LONG_TERM` -> `NOOP` (proof=0) |
| **C** | **Same meaning new evidence → REINFORCE** | 跨月跨会话重申显示器很舒服 | `ADMIT` -> `REINFORCE` (proof+1) |
| **D** | **Explicit preference change → SUPERSEDE** | 宣布全面迁移到 pwsh7，不再用 CMD | `ADMIT` -> `SUPERSEDE` (CMD更替) |
| **E** | **Weak conflict → AMBIGUOUS** | 夸奖 2 格缩进（与 4 格偏好表面冲突） | `ADMIT` -> `AMBIGUOUS` (保留冲突) |
| **F** | **User correction → SUPERSEDE** | 纠错：“刚才说错了，是 PySide6 不是 PyQt5” | `ADMIT` -> `SUPERSEDE` (用户最高权威) |
| **G** | **Short-lived statement → NOOP** | “先去吃午饭，半小时后回来” | `NOOP_LONG_TERM` -> `NOOP` (无持久价值) |
| **H** | **Relationship rule → ADD** | 设立相处规则：“专注时千万别弹窗提醒喝水” | `ADMIT` -> `ADD` (category='relationship_rule') |
| **I** | **Relationship rule changed → SUPERSEDE** | 改变相处规则：“工作超3小时可以轻微提醒” | `ADMIT` -> `SUPERSEDE` (规则非永恒) |
| **J** | **Same-episode repetition → NOOP** | 同一经历内反复唠叨夸奖 PySide6 | `ADMIT` -> `NOOP` (proof 不递增) |
| **K** | **Cross-episode reaffirmation → REINFORCE** | 经历数月新时空宏观复盘确认 PySide6 | `ADMIT` -> `REINFORCE` (proof+1) |
| **L** | **Connector replay → NOOP** | 外部 Agent 崩溃重启重放的失败遥测 | `NOOP_LONG_TERM` -> `NOOP` (幂等抑制) |
| **M** | **LLM echo → no self-reinforce** | 伴生体说“你喜欢深色对吧”，用户说“嗯” | `NOOP_LONG_TERM` -> `NOOP` (剥离回音) |
| **N** | **Unknown scope → unresolved** | 全局输入框投喂“测试框架换成 pytest” | `ADMIT` -> `ADD` (scope='unresolved') |
| **O** | **Project-scoped fact → project only** | 明确 CRM 项目后台用 FastAPI | `ADMIT` -> `ADD` (scope='project') |
| **P** | **User self-desc vs telemetry conflict** | “我中断是因为工具慢，不是逃避挫折” | `ADMIT` -> `SUPERSEDE` (用户声音优先) |
| **Q** | **Historical fact remains queryable** | 被置失效的历史事实（CMD） | 保持 `superseded`，历史检索可读 |
| **R** | **Event pin / unpin (IMPL-1)** | 工具遥测被信念采纳时钉住，信念撤回后释放 | 验证 Retention Pin 状态机流转 |
| **S** | **Hard Delete recompute** | 物理抹除底层切片 | 派生记忆置失效，原话残留为零 |
| **T** | **Partly calibration** | 假说校准点击“部分认同”并附带细微区别说明 | 生成独立的 `confirmed_insights` 实体 |

---

## 3. 对比技术候选架构 (Candidate Designs)

- **Design A: Rule-first Deterministic Reconciliation（纯规则型）**：
  依靠前台硬编码正则表达式与停用词逻辑。极快（<0.01ms），但面对复杂口语分歧、从属从句、同义转折与多事实复合输入时极其脆弱。
- **Design B: LLM-first Free-form Reconciliation（自由大模型型）**：
  单次 Prompt 直接输入用户输入与历史，要求大模型自由决策并输出 SQL 或修改指令。灵活，但极易发生物理防抖失效、幻觉篡改作用域（把未决直接当成全局）、遗漏外键约束。
- **Design C: Two-phase Hybrid Architecture（两阶段提议+校验器架构 · 推荐选定）**：
  - **Phase 1 (提议阶段)**：LLM 仅作为只读分析器，根据强类型 JSON Schema 提议语义主张（Candidate Claims）与动作意向；
  - **Phase 2 (校验与提交阶段)**：确定性校验器（Reconciliation Validator）以本地代码强制检查：
    1. 物理幂等防抖键；
    2. 回音壁围栏剥离；
    3. 作用域守卫（未知强制 unresolved）；
    4. 强类型外键存在性；
    5. 时态双时间戳约束；
    6. 独立性指纹计算（防同一会话反复刷分）。
  - 校验通过后，在单一 ACID 数据库事务中原子落盘。

---

## 4. 核心评估指标定义

1. **Admission Accuracy (准入准确率)**：
   $$\text{Admission Acc} = \frac{\text{准入判定与预期完全一致的用例数}}{\text{总用例数}}$$
2. **Action Accuracy (调和动作准确率)**：
   $$\text{Action Acc} = \frac{\text{调和动作 (ADD/SUPERSEDE/REINFORCE/AMBIGUOUS/NOOP) 与预期一致数}}{\text{总用例数}}$$
3. **False ADD Rate (虚假新增率)**：
   本应是更替、增强或忽略的输入，被错误当成新事实创建的比例（越低越好，目标 0）。
4. **False SUPERSEDE Rate (虚假更替率)**：
   在弱冲突或歧义下，草率判定推翻旧事实的比例（越低越好）。
5. **False REINFORCE Rate (虚假强化率)**：
   同一经历内重述或重放回音被错误计算为独立支持的比例（越低越好）。
6. **Overall Pass Rate (全链路完全通过率)**：
   准入、动作、证明计数与作用域完全正确的综合用例比例。
