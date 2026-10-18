# Co-evolving Companion：跨会话长期记忆 V2.1 架构设计规范
## ——语义本体、四域分立、认识论分层、时态调和与双阶表达门控

> **文档状态与元数据**：
> - **阶段定位**：Product Semantics + System Architecture + Information Model Design (V2.1 Freeze Edition)
> - **版本状态**：`Architecture Revision: v2.1 (Frozen)`
> - **唯一事实基线**：
>   1. `docs/research/cross-session-long-term-memory-fact-audit.md` (Coeva 长期记忆现状事实审计)
>   2. `docs/research/long-term-memory-reference-architecture-study.md` (外部参考架构调研)
>   3. `docs/specs/cross-session-long-term-memory-v2-architecture.md` (V2.0 基础架构骨架)
> - **硬性架构边界**：
>   - 本文档**严格限定在产品语义、概念模型与系统边界**；
>   - **不涉及代码实现、不写具体 SQL Schema、不决定具体 Embedding 模型或本地向量运行时**；
>   - 所有数值阈值下放至 Technical Design 可调参数，架构层零硬编码数字。

---

## 1. V2.1 Architecture Corrections & Freeze Patch

### 1.1 V2.1 核心架构修正汇总
在 V2.0 确立的“平级伙伴而非用户画像器”主骨架基础上，V2.1 排查并根治了 10 处内部语义冲突与过早技术定案：
1. **移除架构层过早技术选型**：解耦 FTS5 / Vector / RRF(k=60)，抽象为标准能力通道，融合策略为 implementation-defined；
2. **剔除未经基准验证的性能数字**：移除冷启动与内存具体数字，降级为性能指标门禁；
3. **记忆面内部确立双阶分立**：Raw Evidence 绝不可改写，Derived Semantic Memory 允许调和置失效；
4. **时态心境严格物理二分**：Current Mood State（瞬时 Context）与 Historical Mood Evidence（客观 Raw Evidence）彻底解耦；
5. **硬删除恪守溯源不变量**：底层唯一证据归零时高层信念同步撤回或降级重验，消除无凭孤儿共识；
6. **被否认假说恢复时间性与可修正性**：确立 `Rejected ≠ Eternally False`，随新时空与独立证据允许微小重启；
7. **表达门控前置为双阶防御**：拆分为 Pre-generation Expression Policy 与 Post-generation Output Guard；
8. **可调参数移出架构不变量**：轮数、分钟、字符数与权重数值降级为 Technical Design 可调参数；
9. **解耦综合重要性指标**：拆分为独立的 Importance、Relevance、Recency、Confidence、Validity 五大维度；
10. **隐私硬删除绝对覆盖文学叙事**：隐私删除发生时，人生章节必须执行脱敏重写，隐私权高于叙事稳定性。

### 1.2 V2.1 Freeze Patch 专项修正（最终冻结补丁）
在正式冻结前，对最后 6 个残余语义边界完成精准闭环：
1. **彻底清扫残留具体数值**：Current Mood 生命周期由固定“4~8小时”改为“bounded transient lifetime”；认识论权威由“1.0/0.6数值”改为“Authority Classes（user_asserted / user_confirmed / system_observed / system_inferred）”；
2. **Episode 明确为组织容器而非原始证据**：确立 `Episode ≠ Raw Evidence`，Episode 是组织真实经历的结构化容器（Container），其总结摘要是派生制品，不自动升级为 Raw Evidence；
3. **准入层消除“纯闲聊即NOOP”偏见**：将准入标准从“任务 vs 闲聊”修正为“是否具备持久语义价值（Durable Semantic Value）”，确保闲聊中流露的童年经历、人际约束与深度喜恶能正常进入长期候选；
4. **REINFORCE 明确基于独立证据**：`proof_count` 仅在来自不同时段、不同 Episode、不同独立来源或用户显式再确认时递增，同句重发、接口重试与单会话重复不递增计数；
5. **统一 Hard Delete 语义**：明确 Hide/Mute/Archive/Forget 是检索与可见性控制，而 Hard Delete 无论原因均触发物理抹除与依赖重算；“Privacy-sensitive”仅代表额外对叙事层触发脱敏重写；
6. **Provenance 解耦 raw_quote 强制性**：确立“每条派生项必须有溯源，但非每项溯源都必须有 raw_quote”；用户原话使用 `user_raw_quote`，而外部 Agent 遥测严格遵守隐私边界，仅引用结构化事件骨架（`structured_event_reference`）。

---

## 2. 顶层四域分立（Top-Level Four Domains）

Coeva V2.1 确立了四大顶层认知领域的单向治理拓扑：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 语境域 (Context)        │ "现在正在发生什么"                             │
│    - 角色与职责            │ 瞬时多轮工作上下文、当前心境状态、活动工程与即时环境│
│    - 读写控制              │ 随交互自由流转，空闲/退出时自动挥发，非必要不入长期库│
├────────────────────────────┼────────────────────────────────────────────────┤
│ 2. 记忆域 (Memory)         │ "过去真实发生过什么 / 用户亲口表达过什么"       │
│    2.1 原始证据 (Evidence) │ 用户原话、行为遥测骨架 (不可篡改底座)          │
│    2.2 经历容器 (Episode)  │ 关联时空、任务与原始证据的经历结构 (Grouping)  │
│    2.3 派生记忆 (Semantic) │ 从证据提炼的原子事实、偏好、关系规则 (可调和更替)   │
├────────────────────────────┼────────────────────────────────────────────────┤
│ 3. 理解域 (Understanding)  │ "这些经历可能意味着什么"                        │
│    - 角色与职责            │ 观察信念 (Observation) 与双向校准共识 (Insights) │
│    - 读写控制              │ 伴生体主观推断，需用户确认，绝不可伪装成客观事实写回│
├────────────────────────────┼────────────────────────────────────────────────┤
│ 4. 叙事域 (Narrative)      │ "经过时间沉淀后，我们如何共同回看一段时期"      │
│    - 角色与职责            │ 宏观人生章节 (Growth Chapters) 与里程碑长文本   │
│    - 读写控制              │ 阶段性双人共写留白，只读归档，100% 豁免于日常微观检索│
└────────────────────────────┴────────────────────────────────────────────────┘
```

### 2.1 读写矩阵与防污染单向规则
```text
Raw Evidence:
  append (新增) / archive (归档) / redact (脱敏) / user delete (删除)

Episode Container:
  group (组织) / close (闭环) / summarize (派生摘要) / re-scope (重组)

Derived Semantic Memory:
  reconcile (调和) / supersede (更替置失效) / invalidate (作废) / regenerate (重构)

Understanding:
  read Memory (读取记忆作为证据), never rewrite Memory (绝不反向改写记忆事实)

Narrative:
  read Memory & Understanding (读取记忆与理解进行叙事), never become evidence (叙事文本绝不反向作为证据)
```

---

## 3. Architecture Invariants（架构不可违背定理 · V2.1 冻结版）

| 编号 | 架构定理 | 严格内涵与工程约束 |
| :--- | :--- | :--- |
| **INV-1** | **Evidence ≠ Interpretation**<br>（证据不等于解释） | 原始输入原话与行为骨架是客观事实（Raw Evidence）；从证据抽取的语义事实及高层假说是主观解释（Interpretation）。解释必须具备溯源指针，但永远不得改写或伪装成证据。 |
| **INV-2** | **Past Truth ≠ Current Truth**<br>（过去真实不等于当前有效） | “过去喜欢 X”与“现在喜欢 Y”同为真实。系统通过置失效（Invalidation）表达当前有效状态，历史状态退出当前决策上下文，但完整保留思想演化足迹。 |
| **INV-3** | **Retrieved ≠ Injected ≠ Spoken**<br>（召回不等于注入，注入不等于开口） | 检索命中（Retrieved）只代表后台想起；注入上下文（Injected）需经过背景相关度与预算裁决；开口表达（Spoken）必须通过双阶表达门控审批。三权物理分离。 |
| **INV-4** | **Silence Is Valid**<br>（沉默是合法且受尊重的常态） | 检索返回空是常态；检索命中但系统决定不注入是常态；注入了但回复中保持沉默更是常态。伴生体严禁通过刻意提及往事来炫耀记忆力。 |
| **INV-5** | **User Voice > Telemetry Inference**<br>（用户亲口表达高于行为遥测推断） | 对涉及用户自身偏好、意图、感受和自我认知的主张，用户明确表达具有最高语义权威；Telemetry 只能作为外部行为证据，不得单独覆盖用户自述。高 authority 不等同于永恒真理，仍受时间演化管辖。 |
| **INV-6** | **Candidate Understanding ≠ Confirmed Insight**<br>（候选假说绝非确定共识） | 伴生体对用户的任何性格、工作模式的理解，未经用户明确校准（Yes / Partly）前，始终属于“候选假说（Candidate）”，在推理上下文中必须标明不确定性。 |
| **INV-7** | **No High-level Belief Without Valid Provenance**<br>（无有效溯源则无高层信念） | 伴生体的任何高层判断必须能够枚举出其支撑的底层证据链。若微观证据被物理硬删除导致支撑归零，高层信念必须同步撤回（Retract）或转为待重新校准，严禁无依据信念。 |
| **INV-8** | **Deletion Must Propagate Semantically**<br>（删除必须发生语义级联传播） | 当用户执行物理硬删除时，Raw Evidence 抹除，Derived Semantic Memory 删除/重算，以此为核心支撑的高层假说撤回，人生章节必须执行脱敏重写。隐私删除绝对优先于叙事稳定。 |
| **INV-9** | **Sanctuary Overrides Reflective Expression**<br>（避风港熔断绝对覆盖反思表达） | 当用户处于烦躁、疲惫、高负荷或受挫时，反思性回忆、主动反思和翻旧账被强制闭锁，系统仅允许保留必要的工作连续性上下文，优先提供极简接纳与静谧陪伴。 |
| **INV-10**| **Memory Must Not Self-Reinforce Through LLM Echo**<br>（记忆绝不可通过大模型回音壁自我污染） | 伴生体在回复中复述的历史记忆必须携带 Feedback 围栏，下一轮交互将该消息存盘时自动剥离历史围栏内容，彻底阻断自产记忆自我强化的死循环。 |

---

## 4. 记忆面内部三元架构：Raw Evidence、Episode 与 Derived Semantic Memory

V2.1 彻底澄清记忆域内部三者的职责边界：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Memory Layer (记忆域)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2.3 派生语义事实 (Derived Semantic Memory)                                   │
│     - 单元: Atomic Facts (项目事实), Preferences (偏好), Rules (相处规则)   │
│     - 行为: 可调和 (Reconcile), 可置失效 (Invalidate), 可更替 (Supersede)   │
│     - 溯源: 强引用底层 Raw Evidence 标识 (用户原话带 quote, 遥测带 ref)     │
│     - 作用: 供日常检索 (Daily Retrieval) 与当前有效状态判断使用             │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2.2 经历结构容器 (Episode)                                                  │
│     - 语义: 组织真实经历的结构化容器 (Grouping Artifact)，非原始事实本身   │
│     - 关联: 聚合时空窗口内的一组 Raw Evidence，并承载任务标签与上下文范围   │
│     - 特征: 摘要是派生制品 (Derived Artifact)，不能作为新的 Raw Evidence    │
├─────────────────────────────────────────────────────────────────────────────┤
│ 2.1 原始证据底座 (Raw Evidence)                                             │
│     - 单元: 用户原话切片 (Raw Slices), 允许记录的结构化事件骨架 (Skeletons) │
│     - 行为: 只追加 (Append-only), 只归档 (Archive), 用户可物理删除 (Delete) │
│     - 约束: 模型绝不得篡改、润色或伪造用户原话                               │
│     - 作用: 作为不可推翻的真实发生凭证，供派生与溯源回溯使用                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. 时态心境的双重概念澄清：Current Mood 与 Historical Mood Evidence

### 5.1 Current Mood State（当前心境状态）
- **所属领域**：`Context（语境面）`
- **语义定义**：用户“此刻/今天”的身心负荷与情绪倾向；
- **产生方式**：由最近交互输入的情绪特征动态计算；
- **生命周期**：**Bounded transient lifetime**（具有上限的短时生命周期，随上下文切换、会话结束或时间衰减自然失效，具体时限由实现定义）；
- **核心作用**：驱动 Desktop Body 姿态（如疲惫趴卧）、调节主动关怀气泡阈值、触发 Sanctuary Guard 熔断；
- **红线约束**：**绝对不进入日常长期检索通道**，严禁长期累积后给用户打上静态性格标签。

### 5.2 Historical Mood Evidence（历史心境证据）
- **所属领域**：`Raw Evidence（原始证据底座）`
- **语义定义**：在特定历史时空下，用户曾表达过某种强烈心境的客观发生快照；
- **产生方式**：作为原始输入不可变存盘；
- **生命周期**：长期保留在经历档案中；
- **核心作用**：作为心理灵活性“抗挫力/情境适应”的分析证据；在用户主动查证往事或共创人生章节时提供真实细节；
- **红线约束**：**不代表用户当前仍然处于该状态**，日常技术问答时严禁主动唤醒。

---

## 6. Memory Admission（准入机制：基于持久语义价值）

准入机制的目标是拦截噪音，但**绝对不能把所有闲聊一律当成无用信息**：

```text
                          ┌──────────────────────────┐
                          │   用户输入进入准入层     │
                          └─────────────┬────────────┘
                                        │
                    ┌───────────────────┴───────────────────┐
                    ▼                                       ▼
       [低熵/操作性/无持久价值信息]               [具备持久语义价值 (Durable)]
        - 浅层问候 (hi/早安)                       - 闲聊流露的个人经历/童年回忆
        - 界面调试 (测试气泡/探头)                 - 长期工作偏好 (习惯/约束)
        - 无实质意义的简单应答 (嗯/好的)           - 关系相处要求 (不要提醒我休息)
        - 一次性操作性备忘 (等会改按钮)            - 项目客观事实 (技术栈/架构)
        - 纯瞬时状态报备 (去吃饭了)                - 深度个人反思 (心智复盘)
                    │                                       │
                    ▼                                       ▼
            【直接拒绝长期留存】                     【提取候选原子事实】
        Action = NOOP_LONG_TERM                     进入 Write-time Reconciliation
        (仅在当前 Context 消费)                     准备调和存盘
```

- **准入核心判据**：是否具备**持久语义价值（Durable Semantic Value）**，而不是“任务相关还是生活闲聊”。用户在闲聊中说出“我从小喜欢画画”与任务无关，但具有极高的自传记忆（Autobiographical Memory）价值，必须准入。

---

## 7. Two-Phase Reconciliation & REINFORCE 语义规范

在写入时调和（Write-time Reconciliation）阶段，裁决动词的语义严格规范如下：

```text
Candidate Facts 到达调和层
    ↓ (预检相似历史)
Semantic Reconciliation Decision:
    ├── ADD       : 全新信息，生成新派生记忆入库
    ├── SUPERSEDE : 观点反转/更新 (老记忆标记 invalidated_at，建立 superseded_by 链接)
    ├── REINFORCE : 既有记忆的独立印证 (仅在满足独立性时递增 proof_count)
    ├── AMBIGUOUS : 冲突但置信度不足以推翻 (保留两者，标记歧义待用户校准)
    └── NOOP      : 已被存量记忆完全包含，或纯属重复投喂，丢弃不入库
```

### 7.1 REINFORCE 独立证据约束定理
> **架构定理**：**`proof_count` 统计的是具备充分独立性的支撑证据（Independent Supporting Evidence），绝对不是数据库记录数量。**

- **允许增加证据计数的场景**：
  1. 来自不同时间段的新经历；
  2. 来自不同独立 Episode 的再次印证；
  3. 来自不同数据源（如用户投喂与实际开发事实）的交叉佐证；
  4. 用户显式的再次强调确认。
- **严禁增加证据计数的场景**：
  1. 同一句话在短时间内连续重复发送；
  2. 前端重试、Connector 抓取重放（Replay）；
  3. 同一会话（Episode）内部的重复记录；
  4. UI 双写产生的冗余行。

---

## 8. 认识论层级与 Authority Classes（权威类别划分）

V2.1 彻底废除将认识论权威简化为“1.0 / 0.6 固定数值”的写法，确立权威类别体系：

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                       认识论权威类别 (Authority Classes)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. user_confirmed  │ 双方明确校准确认的共识 (最高权威，伴生体与用户共同认可)│
├────────────────────┼────────────────────────────────────────────────────────┤
│ 2. user_asserted   │ 用户亲口表达陈述的事实/偏好 (高语义权威，非永恒真理)   │
├────────────────────┼────────────────────────────────────────────────────────┤
│ 3. system_observed │ 系统客观检测到的结构化事件 (如工具有效执行、测试通过)  │
├────────────────────┼────────────────────────────────────────────────────────┤
│ 4. system_inferred │ 伴生体从统计模式中归纳推断的心智结论 (待审假说，需校准)│
└─────────────────────────────────────────────────────────────────────────────┘
```

- **User Voice 权威语义澄清**：对涉及用户自身偏好、意图、感受和自我认知的主张，`user_asserted` 拥有最高语义解释权，`system_inferred` 不得单独推翻；但这并不意味着用户亲口说的话等于“永恒客观真理”——用户可能开玩笑、引用他人、表达短期状态，或者在数月后自然改变偏好。时效性演化仍然有效。

---

## 9. 统一的 Hard Delete 语义与隐私深度清除

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                             删除语义层级分明                                │
├─────────────────────────────────────────────────────────────────────────────┤
│ A. 非物理删除操作 (Soft / State Operations)                                  │
│    - Hide (隐藏) / Mute (不提及) / Archive (冷库归档) / Decay (衰减降权)     │
│    - 表现: 数据物理保留，仅改变检索可见性、打分权重或表达门控，不破坏证据链 │
├─────────────────────────────────────────────────────────────────────────────┤
│ B. 物理硬删除 (Hard Delete)                                                 │
│    - 触发: 用户明确要求物理彻底删除某条记录                                 │
│    - 表现:                                                                  │
│      1. Raw Evidence 物理抹除，索引彻底驱逐;                                │
│      2. 所有依赖该证据的 Derived Semantic Memory 触发依赖重算;              │
│      3. 引用此证据的 Observation proof_count 递减;                          │
│      4. 若唯一证据被删 (proof == 0) -> Observation 撤销, 对应 Insight 降级为│
│         'revalidation_required' (严守 INV-7，不留无依据信念);               │
│      5. 若仍有其他独立证据 -> 派生认知继续存活，仅更新溯源外键。            │
├─────────────────────────────────────────────────────────────────────────────┤
│ C. 隐私敏感硬删除 (Privacy-Sensitive Hard Delete)                           │
│    - 范围: 在标准 Hard Delete 基础上额外要求 Narrative 深度语义清除         │
│    - 表现: 对人生章节 (Chapter) 中涉及该敏感词的段落强制执行脱敏重写        │
│            (Redaction / Regeneration)，隐私权绝对覆盖叙事稳定性。           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 10. Provenance Reference 抽象：解耦 raw_quote 强制性

为解决外部 Agent 遥测不采正文与溯源要求的冲突，确立普适的溯源引用抽象：

```text
Provenance Reference (溯源指针抽象)
  ├── UserRawQuoteReference
  │     - 适用: user_asserted 切片与原话
  │     - 包含: raw_quote (文本原话), episode_id, timestamp
  │
  ├── StructuredEventReference
  │     - 适用: system_observed 外部工具遥测
  │     - 包含: event_id, event_type, tool_name, session_id (严禁 Prompt/CoT 正文)
  │
  ├── EpisodeReference
  │     - 适用: 针对特定经历整体的提炼
  │     - 包含: episode_id, time_window, contextual_scope
  │
  └── DerivedReference
        - 适用: 高层信念对底层 Observation 的引用
        - 包含: observation_ids, proof_count_snapshot
```

> **定理**：**每条派生项必须有溯源指针（Valid Provenance）；但非每项溯源都必须有 raw_quote。对遥测证据而言，结构化事实指针就是完全合法的溯源。**

---

## 11. 双阶表达门控与三级解耦系统（Dual-Stage Expression Layer）

```text
                  ┌───────────────────────────────────────────┐
                  │ 检索候选结果到达 (Retrieved Candidates)   │
                  └─────────────────────┬─────────────────────┘
                                        │
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ 1. 回忆门控 (Recall Gate)                 │
                  │    - 职责: 此刻情境是否允许唤醒记忆?       │
                  │    - 门槛: Sanctuary / 纯问路不翻旧账 / 意图 │
                  └─────────────────────┬─────────────────────┘
                                        │ 放行 (Pass)
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ 2. 注入门控 (Injection Gate)              │
                  │    - 职责: 以何种结构、预算注入上下文?     │
                  │    - 规则: 物理字符预算硬约束、非强制性协议│
                  └─────────────────────┬─────────────────────┘
                                        │ 确定上下文形态
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │ 3. 表达控制层 (Expression Layer)          │
                  │                                           │
                  │  3.1 Pre-generation Expression Policy     │
                  │      - 生成前注入指令: 明确指示模型当前   │
                  │        memory_usage 是 "background_only"  │
                  │        还是 "explicit_reference_allowed"  │
                  │                     │                     │
                  │                     ▼                     │
                  │             大模型生成回复草稿            │
                  │                     │                     │
                  │                     ▼                     │
                  │  3.2 Post-generation Output Guard         │
                  │      - 生成后兜底审查: 拦截刻意炫耀记忆、 │
                  │        避风港破防、黑料翻旧账与过度说教   │
                  └─────────────────────┬─────────────────────┘
                                        │ 最终输出
                                        ▼
                           桌面端气泡文字展示 (Spoken)
```

---

## 12. V2.1 冻结架构总图（Frozen Master Architecture Diagram）

```text
                               Context (语境域)
                        "现在正在发生什么 / 瞬时输入与心境"
                                     │
                             Admission Gate
                       (低熵瞬时丢弃 / 持久语义放行)
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │    Raw Evidence     │
                          │   客观真实发生底座   │
                          │(不可篡改原话/事件骨架)│
                          └──────────┬──────────┘
                                     │
                     ┌───────────────┴───────────────┐
                     │ groups into                   │
                     ▼                               ▼
          ┌─────────────────────┐         Two-Phase Reconciliation
          │       Episode       │         (ADD / SUPERSEDE / REINFORCE
          │  结构化经历容器     │          AMBIGUOUS / NOOP)
          │(时间边界/上下文关联) │                    │
          └─────────────────────┘                    ▼
                                          ┌─────────────────────┐
                                          │Derived Semantic Mem │
                                          │ 派生事实 / 有效偏好 │
                                          │(双时间戳/valid_from/ │
                                          │  invalidated_at)    │
                                          └──────────┬──────────┘
                                                     │
                   ┌─────────────────────────────────┴─────────────────────────────────┐
                   │                                                                   │
                   ▼                                                                   ▼
        Candidate Generation                                                  Observation Layer
        - Lexical-capable channel                                             (基于独立证据统计与
        - Semantic-capable channel                                             指针聚合的信念)
        - Temporal/Context channel                                                     │
                   │                                                                   ▼
             Fusion & Rank                                                      Hypothesis Layer
        [implementation-defined]                                               (心理灵活性透镜推理)
                   │                                                                   │
              Recall Gate                                                      Human Calibration
        (Sanctuary / 意图门控)                                                 (Yes / Partly / No)
                   │                                                                   │
             Injection Gate                                                            ▼
        (字符预算 / 非强制协议)                                                 Confirmed Insight
                   │                                                           (已确认共识自模型)
                   ▼                                                                   │
        Pre-generation Policy                                                          ▼
        (prohibited/background/explicit)                                        Behavior Policy
                   │                                                           (相处默契/节律提示)
                   ▼                                                                   │
              LLM Context                                                              ▼
                   │                                                           Narrative Synthesis
                   ▼                                                           (宏观共写留白生成)
                Response                                                               │
                   │                                                                   ▼
         Post-generation Guard                                                   Growth Chapters
         (去油说教 / 极简审查)                                                  (只读人生章节 Markdown)
                   │
                   ▼
         Desktop Bubble Spoken
```

---

## 13. Freeze Consistency Check Matrix（最终冻结一致性自检表）

| 审查项 (Check Item) | 预期判定 (Expected) | 实际审计结论与支撑机制 |
| :--- | :---: | :--- |
| **Any architecture-level hardcoded tuning numbers left?** | **NO** | 4~8小时、30分钟、300字符、权重数字全部降级为 Technical Design 可调参数。 |
| **Any `user_asserted = 1.0`-style numeric truth left?** | **NO** | 彻底改为四级 Authority Classes，明确高 authority 不等于客观永恒 truth。 |
| **Is Episode clearly separated from Raw Evidence?** | **YES** | Episode 定义为引用证据的结构化经历容器，其摘要为派生制品，不混同于底层证据。 |
| **Can casual conversation contain durable memory?** | **YES** | 准入标准定位于持久语义价值，闲聊中透露的自传经历与长期偏好正常准入。 |
| **Does REINFORCE require independent evidence?** | **YES** | 明确规定同句重发、接口重试、单会话内重复不递增 proof_count。 |
| **Is Hard Delete semantically consistent across all data?** | **YES** | 物理抹除与依赖重算全局统一，底层证据归零时高层信念撤回，无孤儿共识。 |
| **Does privacy deletion extend Hard Delete instead of redefining it?**| **YES** | 隐私删除仅在此基础上追加对人生章节的深度脱敏重写，不破坏基础删除定义。 |
| **Is provenance possible without raw text?** | **YES** | 引入结构化事实指针，外部 Agent 遥测不采正文依然具备合法溯源。 |
| **Is telemetry privacy boundary preserved?** | **YES** | 严禁采集 Agent CoT、工具返回与 Prompt 正文，红线绝对闭锁。 |
| **Are Raw Evidence / Semantic Memory / Understanding / Narrative still separate?** | **YES** | 顶层四域单向治理与读写矩阵严密自洽，无反向污染漏洞。 |

---

## 14. Architecture Freeze Review（架构正式冻结审查结论）

```text
================================================================================
       COEVA CROSS-SESSION LONG-TERM MEMORY ARCHITECTURE V2.1 REVIEW
--------------------------------------------------------------------------------
  [✓] Product semantics stable?                       : YES
  [✓] Ontology boundaries stable?                     : YES
  [✓] Evidence semantics stable?                      : YES
  [✓] Episode semantics stable?                       : YES
  [✓] Temporal semantics stable?                      : YES
  [✓] Provenance semantics stable?                    : YES
  [✓] Deletion semantics stable?                      : YES
  [✓] Admission semantics stable?                     : YES
  [✓] Gating semantics stable?                        : YES
  [✓] Privacy boundary stable?                        : YES
  [✓] Any blocker before Data Model Design?           : NONE
--------------------------------------------------------------------------------
                         >>> ARCHITECTURE FROZEN <<<
                     READY FOR DATA MODEL DESIGN
================================================================================
```

### 本轮停止声明
Coeva 跨会话长期记忆架构 V2.1 已通过全部 6 项残余语义修正与冻结一致性审查，架构正式冻结。

**本轮立即停止。不进入 SQL Schema 设计、不写数据表字段、不进行模型评测与代码编写。后续工程任务将正式基于本规范，稳健进入下一阶段：Data Model Design → Technical Retrieval Design → Implementation Plan。**
