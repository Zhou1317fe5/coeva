# MaiBot 行为演化、主动性与意图连续性深度技术审计报告
> **File**: `MAIBOT_DEEP_DIVE_BEHAVIOR_AUTONOMY.md`  
> **Target Repo**: `https://github.com/Mai-with-u/MaiBot` (Latest `main` codebase snapshot)  
> **Audited By**: Coeva Architecture Working Group  
> **Date**: 2026-10-21  

---

## 1. Executive Findings

本次审计聚焦于 MaiBot 最新开源代码中是否存在能够帮助 Coeva 解决“长期行为演化、自主主动性、意图连续性”的真实工程闭环。经过对 `src/maisaka`、`src/chat`、`src/A_memorix`、`src/learners`、`src/plugin_runtime` 以及全部数据库迁移脚本（v1 到 v45）的穿透式审计，核心结论如下：

1. **Behavior Learning（行为学习系统）：已经物理下线并彻底废弃（NOT PRODUCTION-WIRED）**。
   - 早期版本（v18 ~ v41）曾设计过一套复杂的 `behavior_scene_clusters` $\to$ `behavior_actions` $\to$ `behavior_outcomes` $\to$ `behavior_experience_paths` 图谱；
   - 但在 **v41 $\to$ v42 数据库迁移（`src/common/database/migrations/v41_to_v42.py`）中，官方彻底删除了全部 24 张 behavior 数据表**。
   - 现役代码中的“学习”仅剩下**表层语言风格模仿（`ExpressionLearner`）**、**群聊黑话挖掘（`JargonLearner`）**与**基础人物属性提取（`PersonFactWritebackService`）**，不存在任何行为策略自适应闭环。
2. **Proactive Trigger（主动触发）：本质是“会话内事件通知适配器”，非独立生命自驱力**。
   - `maisaka.proactive.trigger` 必须显式绑定已存在的 `stream_id`（群聊/私聊 Session ID）；若无聊天会话上下文，根本无法触发任何动作；
   - 它的工作机制是将外部任务包装为一条带 `<plugin_proactive_task>` 标签的内部伪消息注入会话历史，强制唤醒聊天 Planner。
3. **Intent Persistence（意图持久性）：完全依赖上下文窗口的“伪连续性”，无持久意图对象**。
   - 虽实现了微观层面的生成打断（`PlannerInterruptController` + `ReqAbortException`），但打断后仅将未完成文字原样拼回历史（`[Planner 已被新消息打断，以下为未完成输出]`）；
   - 不存在跨 Cycle、跨 Session、结构化的“悬挂意图（Unfinished Intent）”或恢复现场令牌（Resume Token）。
4. **DynamicReplyGate（动态回复门禁）：具备极高参考价值的闭环控制工程实证**。
   - 采用真实的离线数据训练（L2 正则化 Logistic 回归），预测外部消息触发实际回复的必要性概率；
   - 结合闭环 P-控制器（比例增益负反馈），动态计算 1 小时滑动窗口内的百分比截断阈值，配合指数退避（`IdleBackoff`），实现了群聊高频消息下的有效静默压制。
5. **Memory $\to$ Behavior：纯粹的知识与句式注入，无策略条件化**。
   - 记忆进入 Planner 的形式仅有 `Knowledge Injection`（人物属性、经历片段）与 `Style Injection`（口癖、黑话），不存在 `Behavior Policy Conditioning`（因为过去某种行为体验不佳而在策略上抑制该动作）。

---

## 2. Behavior Learning Data Flow（历史设计追溯）

在 MaiBot v18 ~ v41 期间，曾存在如下试图构建“经历 $\to$ 行为演化”的设想链路：

```text
       外部聊天交互事件
              │
              ▼
    1. Scene Node 生成 (场景节点)
       - 提取自然语言情境标签 (tag_kind, tag)
       - 存入 behavior_scene_nodes 与 behavior_scene_node_tags
              │
              ▼
    2. Scene Clustering (场景聚类)
       - 统计标签分布 (tag_distribution JSON)
       - 聚类到 behavior_scene_clusters (已移除 score 字段)
              │
              ▼
    3. Action Node (行为节点)
       - 记录 Bot 或他人采取的动作 (action_hash, action_name)
       - 存入 behavior_actions
              │
              ▼
    4. Outcome Node (结果节点)
       - 用户后续反馈或对话延续状态 (outcome_hash)
       - 存入 behavior_outcomes
              │
              ▼
    5. Experience Path 沉淀 (经验路径)
       - 聚合 UNIQUE(session_id, scene_cluster_id, action_id, outcome_id, actor_type, learning_type)
       - 记录 activation_count, success_count, failure_count, score
       - 存入 behavior_experience_paths
```

---

## 3. Behavior Learning Reality Check（现状真相）

### 3.1 真实工程状态判定：`D. 基本未接入生产路径（且已被物理清理）`
- **代码事实 1（表清理）**：`src/common/database/migrations/v41_to_v42.py`
  ```python
  BEHAVIOR_TABLES = (
      "behavior_experience_paths_v21",
      "behavior_scene_nodes_v22",
      "behavior_scene_clusters_v23",
      "behavior_actions_v24",
      "behavior_experience_paths_v24",
      "behavior_outcomes_v24",
      "behavior_patterns",
      "behavior_experience_paths",
      "behavior_scene_clusters",
      "behavior_actions",
      "behavior_outcomes",
      # ... 共 24 张关联表
  )
  def migrate_v41_to_v42(context: MigrationExecutionContext) -> None:
      """删除当前及历史行为学习数据表，清理行为学习相关数据。"""
      for table_name in BEHAVIOR_TABLES:
          context.connection.exec_driver_sql(f'DROP TABLE IF EXISTS "{table_name}"')
  ```
- **代码事实 2（测试与现役模型断言）**：`pytests/test_database_migration_v41_to_v42.py:32`
  ```python
  def test_current_models_and_schema_detection_do_not_require_behavior_tables():
      with create_engine("sqlite://").begin() as connection:
          SQLModel.metadata.create_all(connection)
          snapshot = SQLiteSchemaInspector().inspect(connection)
          assert not any(snapshot.has_table(name) for name in BEHAVIOR_TABLES)
          assert LatestSchemaVersionDetector().detect_version(snapshot) == 42
  ```
- **代码事实 3（生产运行时扫描）**：
  在 `src/maisaka/`、`src/chat/` 与 `src/learners/` 的所有活跃代码中，检索 `behavior_experience`、`behavior_scene` 或 `experience_path` 结果均为 **0 处引用**。

### 3.2 为什么 MaiBot 放弃了这套行为学习？
1. **Outcome（成败判定）在聊天中无法闭环**：
   在群聊中，用户发问号、发表情、换话题、隔 5 分钟回复，根本无法用规则或 LLM 可靠判定为“这次动作是 Success 还是 Failure”。
2. **场景聚类（Scene Clustering）严重稀疏与漂移**：
   以标签分布（`tag_distribution`）做聚类，面对自然语言的无穷多变性，相同意图被分散在大量孤立 Cluster 中，命中率极低。
3. **经验注入干扰 Prompt 与角色一致性**：
   官方日志（`changelogs/changelog.md:825`）曾记录：“*降低行为参考对回复风格的干扰*”。当把历史行为路径作为经验强行塞给模型时，模型往往被带偏，甚至为了所谓“正向反馈”产生极其谄媚或死板的套路。

---

## 4. Proactive Trigger Data Flow（主动触发机制审计）

### 4.1 触发链路追踪
- **API 暴露点**：`src/plugin_runtime/capabilities/core.py:331` (`_cap_maisaka_proactive_trigger`)
- **调用端点**：`src/plugin_runtime/capabilities/registry.py` 注册为 `maisaka.proactive.trigger`
- **运行时方法**：`src/maisaka/runtime.py:646` (`enqueue_proactive_task`)

```text
[Plugin / External Timer]
       │
       ▼ RPC Call: maisaka.proactive.trigger(stream_id, intent, reason, priority, metadata)
[Core Capability Handler] (capabilities/core.py:331)
       │
       ├─ 校验 stream_id 是否存在 ──► 缺失或 session 不存在则直接 FAIL
       ▼
[MaisakaHeartFlowChatting.enqueue_proactive_task()] (runtime.py:646)
       │
       ├─ 1. 构造 task_id = f"proactive:{plugin_id}:{timestamp}"
       ├─ 2. 组装可见文本:
       │     <plugin_proactive_task id="..." plugin_id="...">
       │     外部插件请求发起一次对话：{intent}
       │     任务原因：{reason} | 优先级：{priority}
       │     结合当前上下文和任务意图，自行决定是否回复以及如何表达。
       │     </plugin_proactive_task>
       ├─ 3. 将其作为 InternalContextMessage 追加到 self._chat_history
       ├─ 4. self._arm_forced_turn_state(message_id=task_id, reason="主动触发任务就绪")
       ├─ 5. self._queue_proactive_turn(proactive_trigger_message)
       ▼
[MaisakaReasoningEngine.run_loop()] (reasoning_engine.py:853)
       │
       ▼ 启动 Planner LLM 决策
       ├─ Action 1: reply(...) -> 发送消息给群/用户
       ├─ Action 2: wait(N)    -> 等待观察
       └─ Action 3: stop()     -> 经过思考决定不发送任何消息 (拒绝主动事件)
```

### 4.2 核心问题审查
1. **Trigger Schema**：
   - `stream_id`（必填，目标群聊/私聊流 ID）
   - `intent`（必填，主动任务意图）
   - `reason`（选填，触发理由）
   - `priority`（选填，优先级标识）
   - `metadata`（选填，附加字典）
2. **是否必须绑定 Chat Stream？**
   **YES，100% 必须**。`capabilities/core.py:340` 显式判定：
   `if not stream_id: return {"success": False, "error": "缺少必要参数 stream_id"}`。
   若没有聊天流，MaiBot 无法产生任何自主行为。
3. **Planner 是否可以拒绝主动事件？**
   **YES**。Prompt 明确要求模型“*自行决定是否回复*”，模型若判断当前时机不适合说话，可以直接调用内置工具 `stop()` 结束本轮循环，不发出任何可见消息。
4. **多个主动事件冲突处理**：
   没有优先级抢占式队列。所有主动任务都是作为内部消息顺序压入 `_chat_history`，后到的任务排在后面，依赖 Planner 在单次或多次推理中依次消费。
5. **定性判断**：
   > **MaiBot 的 Proactive 机制本质是一个“向特定聊天流投递内部系统通知、触发模型决策的高级通知适配器”，并不是独立数字生命的主动意图引擎。**

---

## 5. Intent Persistence / Interruption / Resume（意图持久性审计）

### 5.1 审计分类结论：`C. 只有 conversation context 带来的伪连续性`

### 5.2 核心证据：打断与恢复的真实实现
- **代码位置**：`src/maisaka/reasoning_engine.py:563` (`_handle_planner_interrupt`)
- **打断捕获**：
  当 Planner 调用 LLM 过程中收到高优先级消息（如用户艾特），`PlannerInterruptController` 触发并抛出 `ReqAbortException`。
- **打断现场保存方式**：
  ```python
  partial_text = partial_output.display_text() if partial_output is not None else ""
  if partial_text:
      interrupted_text = f"[Planner 已被新消息打断，以下为未完成输出]\n\n{partial_text}"
  # 直接将打断文字作为 Assistant 文本塞回聊天历史
  self._runtime._chat_history.extend(interrupted_response.raw_messages)
  ```
- **所谓的 Resume**：
  系统随后吸纳新收到的消息，直接重启 Planner：
  `interrupted_messages = await self._ingest_pending_messages()`
  `return PlannerInterruptResult(interrupted_response, extra_lines, interrupted_messages)`
- **缺失的真实持久性**：
  1. 没有结构化的 `Intent`、`Goal` 或 `Task` 实体；
  2. 没有意图执行的进度标记（未完成步数、中断前变量）；
  3. 跨 Cycle（当本轮推理结束）之后，未完成意图完全淹没在普通聊天文本历史中，模型是否继续完全取决于上下文窗口翻滚时 LLM 是否自发想起来。

---

## 6. DynamicReplyGate 数学与工程事实审计

### 6.1 Logistic 参数来源：真实离线训练（Offline Training via L2 Logistic Regression）
在 `scripts/fit_reply_necessity.py` 中保留了完整的模型训练代码：
- **训练数据**：从历史运行日志 `logs/maisaka_prompt/planner/*/*.json` 中提取上万次真实请求；
- **真实标签（Label）**：
  `no_reply = int(not any(name != 'wait' for name in tools))`
  （即 Planner 最终决定 `stop`、无工具调用或仅 `wait`，定义为负样本；产生 `reply` 定义为正样本）；
- **优化目标**：在保证极低漏回复率（`max_miss <= 0.02~0.05`）的前提下，最大化跳过无效 Planner 调用的比例（`skip_rate`），以节省 Token；
- **训练产出常数（`src/maisaka/turn_trigger/reply_likelihood.py`）**：
  - `_INTERCEPT = -1.2005`
  - `_WEIGHT_MENTION_BOT = +1.5852`（提到 Bot 名称显著提升回复率）
  - `_WEIGHT_AT_OTHER = -1.1157`（艾特其他人显著压低回复率）
  - `_WEIGHT_QUESTION_MARK = +0.4807`（疑问句提升）
  - `_WEIGHT_PLACEHOLDER_ONLY = -1.0281`（纯表情/图片压低）
  - `_WEIGHT_RECENT_SELF_RATIO = +2.6525`（自己刚参与过对话大幅提升，维持上下文粘性）
  - `_WEIGHT_RECENT_MESSAGE_COUNT = -0.0367`（消息爆刷时负反馈抑制）
  - `_WEIGHT_PENDING_COUNT = +0.1012`（积压消息适度提升）

### 6.2 动态阈值算法与控制类型定性
- **代码位置**：`src/maisaka/turn_trigger/dynamic_gate.py:165` (`evaluate`)
- **控制类型定性**：**自适应百分位数门禁 + 比例负反馈调节器（Adaptive Percentile Gate with P-like Feedback）**。
- **算法细节**：
  1. **滑动窗口**：`REPLY_WINDOW_SECONDS = 3600.0`（1 小时）；
  2. **目标计算**：$\text{target\_replies} = \text{frequency} \times \text{expected\_total}$；
  3. **前馈比例**：$\text{feedforward\_ratio} = \frac{\text{target\_replies} - \text{expected\_forced}}{\text{expected\_proactive}}$；
  4. **P 反馈因子**：
     $$\text{feedback\_factor} = \min\left(1.0, \max\left(0.0, 1.0 + \frac{\text{target\_replies} - \text{actual\_replies}}{\max(1.0, \text{target\_replies})}\right)\right)$$
  5. **最终保留比例**：$\text{keep\_ratio} = \text{feedforward\_ratio} \times \text{feedback\_factor}$；
  6. **动态阈值推导**：将 1 小时窗口内的所有历史分数降序排列，按 $\text{budget} = \text{keep\_ratio} \times \text{expected\_proactive}$ 累加，切分出的边界概率即为当前阈值 $\text{threshold}$。

### 6.3 极端边界工况分析
1. **长时间无人说话（冷场）**：
   - 窗口内没有样本（`len(scores) == 0`），直接退化使用预设的经验静态阈值表 `_STATIC_KEEP_RATIO_THRESHOLDS`，**不会无限降低阈值造成乱说话**；
2. **突然大量消息（刷屏）**：
   - `_WEIGHT_RECENT_MESSAGE_COUNT`（-0.0367）直接削减 Logit，且窗口内历史样本激增导致竞争激烈，动态阈值迅速抬高，有效抵御刷屏；
3. **连续 `stop()`**：
   - `IdleBackoffController` 介入，以 $T = \text{base} \times 2^{(\text{count} - \text{start})}$ 指数级增加静默延迟（直至封顶 cap_seconds），自动降低采样检查频率；
4. **@ 用户消息**：
   - 在 `scheduler.py` 中直接识别为强制触发（Forced Turn），**完全绕过动态门禁**，秒级响应。

### 6.4 对 Coeva 的最大启示：非对称抑制策略（Asymmetric Suppression）
Coeva **绝对不能引入“为了满足最低回复指标（Minimum Reply Quota）而强迫开口”** 的逻辑。
但其**反向抑制逻辑（Over-Interaction Suppression）**对 Coeva 极具价值：
- 当用户长时间高频打字/编码（心流状态）时，伴生体最近的发话密度计数器快速饱和；
- 此时单向大幅提升介入门槛，强迫伴生体维持安静；
- 当伴生体长时间未发言时，**绝不因为“太安静”而主动触发动作**，仅将阈值恢复至标准状态。

---

## 7. Memory $\to$ Behavior Data Flow（记忆与行为链路审计）

对各类记忆流入 Planner 真实路径的审查结果如下：

| 记忆单元 | 存储位置 | 进入 Planner 的形式 | 属于分类 (A/B/C) | 是否影响行为策略 (Policy)？ |
| :--- | :--- | :--- | :--- | :--- |
| **Person Profile** | `metadata_profile.py` | Prompt 拼接：`build_person_profile_injection_messages` | **A. Knowledge Injection** | 否（仅告诉模型用户叫什么、是哪类人） |
| **Episode** | `metadata_episode.py` | Tool 查询：`query_memory` 返回文本 | **A. Knowledge Injection** | 否（仅作为工具返回值供阅读） |
| **Relation Memory** | `metadata_store.py` | Tool 查询：`query_memory` 返回三元组 | **A. Knowledge Injection** | 否（仅提供实体关系） |
| **Fact** | `metadata_fact.py` | Tool 查询：`query_memory` 返回客观事实 | **A. Knowledge Injection** | 否（仅提供客观事实） |
| **Behavior Experience** | `behavior_*` | **已在 v42 物理删除** | **无** | **完全无影响** |
| **Expression** | `expressions` 表 | 模板注入：`maisaka_expression_selector.py` | **B. Style Injection** | 否（仅提供句式口头禅模仿） |
| **Jargon** | `jargons` 表 | Reference 消息注入：`_refresh_jargon_reference_message` | **A. Knowledge Injection** | 否（仅提供专业黑话解释） |

### 核心结论
MaiBot 目前 **100% 属于 `Memory-informed conversation`（记忆辅助对话）**，**0% 属于 `Memory-conditioned behavior`（记忆调控行为）**。记忆没有参与动作空间（Action Space）的概率缩放或策略路由。

---

## 8. Engagement Optimization Risk（互动率优化风险审计）

1. **MaiBot 现存代码是否存在在线强化学习（RL/Reward）优化互动率？**
   - **源码事实**：不存在。代码中没有在线 Reward 计算或根据用户回复时长调优模型权重的在线闭环。
2. **是否存在隐式 Sycophancy（谄媚/刷存在感）风险？**
   - **存在显著风险**。
   - **根因 1（回复概率模型特征）**：`_WEIGHT_RECENT_SELF_RATIO` 高达 **+2.6525**（全特征中最高正权重）。这意味着只要 Bot 一旦开口，它就极度倾向于“继续聊下去”，在群聊中不断寻找话茬，形成类似真人水群的粘性。
   - **根因 2（风格挖掘）**：`ExpressionLearner` 专注于挖掘群内被高频使用的口头禅并模仿，本质是在通过顺从群内亚文化来博取认可（Sycophancy）。
3. **对 Coeva 的红线警示**：
   Coeva 的核心目标是“安静陪伴、80% 沉默守候”。**绝不能把 `recent_self_ratio` 作为高正向反馈**，否则伴生体一旦开口就会喋喋不休，破坏桌面圣域。

---

## 9. Coeva 核心机制抽象与映射（Mechanism Mapping）

| 机制抽象名称 | MaiBot 对应实现事实 | Coeva-Native 概念对应 | 评估标记 |
| :--- | :--- | :--- | :--- |
| **M1: 显式沉默出口** | `stop()` 内置 Tool（直接结束本轮循环） | `BehaviorIntent.SILENCE` 或 `PetState.IDLE` | **REUSE CONCEPT** |
| **M2: 观察挂起状态** | `wait(seconds)` 内置 Tool（挂起等待新动态） | `PetActivity(name="quiet_watching", ttl=N)` | **REUSE CONCEPT** |
| **M3: 单向互动抑制** | `DynamicReplyGate`（基于发言密度的阈值调节） | `InterventionPolicy.over_activity_suppression` | **ADAPT** |
| **M4: 意图打断与现场保存** | 粗暴拼入文本 `[已被打断，以下为未完成...]` | 结构化 `ResumeToken(intent_id, step, context)` | **ADAPT** |
| **M5: 经验驱动行为** | `behavior_experience_paths`（**已因漂移在 v42 废弃**） | 慢路径 `Observation` $\to$ `Hypothesis` 驱动体态 | **WATCH** |
| **M6: 风格迎合模仿** | `ExpressionLearner` 提取群友口癖 | 绝对不做口头禅迎合，仅保留专业术语对齐 | **REJECT** |
| **M7: 聊天强制绑定** | 必须传入 `stream_id` 才能执行 proactive | 身体动作完全独立常驻，不依赖聊天流 | **REJECT** |

---

## 10. Updated REUSE / ADAPT / REJECT

### 10.1 REUSE CONCEPT（仅借鉴概念设计）
- **C1: 决策引擎的显式沉默 Tool（`stop`）**  
  将 `stop()` 作为心智模型的合法输出之一。心智在处理前台事件或切片后，如果判断用户处于心流或负面情绪状态，可主动执行 `stop()` 保持安静，不向前端吐露任何多余字句。

### 10.2 ADAPT（改造为 Coeva 原生架构）
- **A1: 非对称发言抑制门禁（Asymmetric Quota Suppression）**  
  借用 MaiBot 的滑动窗口统计与负反馈系数，仅用于“伴生体发话过多时单向提高沉默阈值”，严禁引入任何“最低回复下限”。
- **A2: 结构化恢复现场令牌（Structured Resume Token）**  
  吸取 MaiBot 将打断内容直接作为散装文本塞进历史的教训。Coeva 在动作被用户点击、拖拽打断时，应将当前未完成的 `BehaviorIntent` 保存为带时效的结构化令牌，待动作结束后由 `Behavior Arbiter` 决定是否恢复原现场。

### 10.3 REJECT（坚决拒绝引入）
- **R1: 已被 MaiBot 官方证明失败的 `behavior_scene_clusters` / `experience_paths` 图谱**。  
  MaiBot 在实战中花费 24 个版本演进该图谱，最终因场景聚类爆炸、成败评估失真、风格带偏而在 v42 彻底物理 DROP。Coeva 绝不能重蹈覆辙去搞聊天级的行为图谱。
- **R2: 迎合式的群聊口头禅学习（`ExpressionLearner`）**。
- **R3: 强绑会话流的主动通知体系**。

---

## 11. Answers to Q1–Q4（核心问题专题解答）

### Q1: Coeva 是否真的需要独立的 Salience Layer（显著性层）？
**结论：不需要独立的物理代码模块，直接内嵌在 `Mind / LifeContext` 即可。**
- **工程证据**：
  MaiBot 没有独立的 Salience 层，而是在 `scheduler.py` 中通过 `ReplyLikelihoodInput` 进行轻量特征加权过滤。
- **Coeva 裁定**：
  如果为显著性单独建一个 Layer，会造成过度工程化。只需在 `LifeContext` 中增加一个纯函数方法 `is_salient_event(event) -> bool`（例如：Hermes 单次工具调用忽略，连续 3 次报错或执行超过 10 分钟标记为 `salient`），滤除无关低信噪比事件即可。

### Q2: Coeva 是否真的需要 Motivation Core（动机核心）？
**结论：现阶段不需要建立独立引擎，定义语义驱动字段（Drive State）即可，避免过度工程。**
- **工程证据**：
  MaiBot 所谓的主动性，仅仅是插件调 API 给聊天会话灌伪消息。缺乏自主生命感的根因在于没有内在张力。
- **Coeva 语义定义**：
  无需设计一个复杂的 `MotivationEngine` 类。只需在桌宠的常驻状态中维护两个轻量标量字段：
  - `energy_level: float`（精力值：随时间与伴生陪伴消耗，自然引导打瞌睡）；
  - `curiosity_tension: float`（探索张力：长时间无交互时缓慢上升，引导翻看资料或自娱自乐）。
  让 `Life Scheduler` 查表时以这两个标量作为偏移权重，即可让桌宠表现出内在动机，成本几乎为零。

### Q3: Persistent Intent 最合适属于哪一层？
**结论：必须属于 `Mind / LifeContext`，由 `Behavior Arbiter` 负责生命周期调度。**
- **分层理由**：
  1. `BehaviorIntent` 是不可变的数据契约（Value Object，表示 WHAT/WHY），不应持有运行时可变状态；
  2. `PetActivity` 是表现层（HOW，动作与动画映射），根本不理解心智；
  3. `Life Scheduler` 只是触发器。
- **正确定位**：
  持久意图本质是伴生体当前正在推进的“短期心智任务”（如：专心研究某段逻辑、观察窗外发呆）。它应当以 `ActiveGoal` 的形式保存在 `LifeContext` 中；当被用户交互事件（如摸头、拖动）打断时，`Behavior Arbiter` 挂起该 Goal；交互结束后，若该 Goal 未过期（TTL 内），Arbiter 重新拉起对应的 `BehaviorIntent`。

### Q4: Behavior Learning 是否值得成为 Coeva 下一阶段正式能力？
**结论：绝对不值得搞泛化的强化学习！如果做，只允许做“共享生活习惯（Shared Habit）”的极简统计，其余坚决不学。**
- **可以学（极低风险、高温暖感）**：
  - `Shared Habit`（共享作息与习惯）：统计用户通常几点开始高频写代码、通常周五几点下班，让伴生体的节律偏向与用户同频；
  - `Contextual Convention`（桌面相处约定）：例如用户在投喂切片中明确说“编码时不要跳跃”，经由 Memory V2.1 形成确定性约束。
- **绝对严禁学习（已在 MaiBot 中暴雷）**：
  - **严禁学习“某种回复用户是否爱听”并计算 Score**（必然导致伴生体为了刷好评而谄媚讨好）；
  - **严禁自动构建 Scene-Action-Outcome 行为图谱**（MaiBot 的 v42 DROP 已经证明这是无底洞死胡同）；
  - **严禁模仿用户口头禅与语言风格**（破坏平级伙伴克制真诚的基调）。

---

## 12. Recommended Roadmap Delta（路线图影响评估）

```text
KEEP AS-IS（维持当前 Phase 2.5 路线图，仅做参数与出口微调）
```

现有规划：
1. `Pet Behavior Semantics`
2. `Pet Manifest / Capability Contract`
3. `Vasu v2 Reference Pet`
4. `Activity Registry + Fallback`
5. `Behavior Arbiter`
6. `Life Scheduler`
7. `Circadian / autonomous life`

**微调建议（不新增 Work Package，仅在实现中落实三点事实）**：
1. 在 WP-5（`Behavior Arbiter`）中：增加对 `stop()`（显式沉默）与被动打断恢复（`ResumeToken`）的处理逻辑；
2. 在 WP-6（`Life Scheduler`）中：不要使用纯随机数选动作，将 Circadian 时钟与简化的精力标量做轻量加权；
3. 长期记忆保持 Memory V2.1，拒绝任何重型图谱或外挂学习系统的侵入。

---

## 13. Source Evidence Appendix（关键源码证据清单）

| 机制 / 结论 | MaiBot 权威源码文件路径 | 核心类 / 函数 / 符号 | 核心代码事实证据 |
| :--- | :--- | :--- | :--- |
| **行为学习物理删除** | `src/common/database/migrations/v41_to_v42.py` | `migrate_v41_to_v42` / `BEHAVIOR_TABLES` | 显式遍历并 DROP 了全部 24 张 `behavior_*` 数据表，彻底移出 schema |
| **现役模型断言无行为表** | `pytests/test_database_migration_v41_to_v42.py` | `test_current_models_and_schema...` | 断言 SQLModel 生成的全部当前表结构中不得存在任何 `behavior_*` 表 |
| **显式沉默与等待 Tool** | `src/maisaka/builtin_tool/stop.py`<br>`src/maisaka/builtin_tool/wait.py` | `handle_tool` | 模型可直接调用无参 `stop()` 终结推理，或 `wait(seconds)` 挂起观察 |
| **主动触发必须绑定聊天** | `src/plugin_runtime/capabilities/core.py:340` | `_cap_maisaka_proactive_trigger` | `if not stream_id: return {"success": False, "error": "缺少必要参数 stream_id"}` |
| **主动任务包装为伪消息** | `src/maisaka/runtime.py:664` | `enqueue_proactive_task` | 包装为 `<plugin_proactive_task id="...">` 文本塞进 `_chat_history` |
| **打断仅作为文本历史** | `src/maisaka/reasoning_engine.py:584` | `_handle_planner_interrupt` | 组装 `[Planner 已被新消息打断，以下为未完成输出]` 作为普通文本 append 到历史 |
| **Logistic 回归权重** | `src/maisaka/turn_trigger/reply_likelihood.py:27` | `estimate_reply_probability` | `_INTERCEPT = -1.2005`, `_WEIGHT_RECENT_SELF_RATIO = 2.6525`, `_WEIGHT_AT_OTHER = -1.1157` |
| **Logistic 离线训练证据** | `scripts/fit_reply_necessity.py:200` | `_fit`, `_cv`, `load_samples` | 基于历史 prompt 日志中的 `no_reply` 标签，用 L2 正则梯度下降拟合参数 |
| **闭环 P-反馈门禁算法** | `src/maisaka/turn_trigger/dynamic_gate.py:165` | `DynamicReplyGate.evaluate` | `feedback_factor = 1.0 + (target_replies - actual_replies) / target_replies`，动态排序选阈值 |
| **指数退避无行动阻断** | `src/maisaka/turn_trigger/idle_backoff.py:21` | `IdleBackoffController._get_backoff_seconds` | $T = \text{base} \cdot 2^{(\text{count} - \text{start})}$，封顶 `cap_seconds` |
| **记忆流入纯属知识注入** | `src/maisaka/reasoning_engine.py:258` | `_build_planner_injected_user_messages` | 仅并行提取画像文本、启发式记忆文本与图片描述，直接作为 user message 注入 |
