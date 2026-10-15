# Hermes 行为归因与用户成长建模设计

> 项目：Co-evolving AI Companion / 共生型 AI 成长伙伴  
> 文档主题：Hermes 自主行为与用户行为的归因边界  
> 版本：v0.1  
> 日期：2026-10-15  
> 状态：需求与心智模型设计阶段

---

# 1. 为什么需要单独讨论 Hermes 行为归因

在前期设计中，我们曾把 Hermes 的以下信息视作潜在用户行为数据：

- 任务开始与结束；
- 工具调用；
- 搜索；
- 重试；
- 测试；
- 任务耗时；
- 上下文切换；
- 是否完成；
- 多轮自主迭代。

但进一步分析后发现：

> **Hermes 的大量行为其实是 Agent 自主完成的，并不能直接代表用户。**

例如：

- Hermes 自动搜索 40 次；
- Hermes 自动重试 8 次；
- Hermes 自动切换方案；
- Hermes 内部多轮 reasoning；
- Hermes 自己决定继续调用工具；
- Hermes 自己展开一个长链路任务。

这些信息首先反映的是：

- Agent 的执行策略；
- 当前任务复杂度；
- 系统摩擦；
- 工具稳定性；
- 模型行为；
- Workflow 设计。

它们不能被直接解释成：

- 用户焦虑；
- 用户喜欢重复尝试；
- 用户无法停止；
- 用户信息搜集欲强；
- 用户控制欲强；
- 用户追求绝对闭环。

因此必须建立一个严格的归因规则。

---

# 2. 核心原则

最重要的一条规则是：

> **Never infer the user from autonomous agent behavior alone.**

中文：

> **绝不单独依据 Agent 自主行为推断用户。**

这应该成为整个用户成长建模系统的硬约束。

任何深层用户画像、人格假设、成长假设，都必须能追溯到：

- 用户主动行为；
- 用户明确决策；
- 用户对 Agent 状态的响应；
- 多个独立情境中的稳定交互模式。

而不能仅仅依赖：

- Agent 调用了多少工具；
- Agent 搜索了多少次；
- Agent 重试了多少轮；
- Agent 自己工作了多久。

---

# 3. 四层行为归因模型

为了避免混淆，整个系统应该至少区分四层。

---

## 3.1 Environment / Task

这一层描述：

> 当前任务与环境本身是什么样的。

例如：

- 任务是否复杂；
- 是否存在不确定性；
- 是否存在多个可行方案；
- 是否已有足够证据；
- 是否出现外部错误；
- 是否存在网络故障；
- 是否有 deadline；
- 是否已经形成可执行方案；
- 是否存在未闭环问题。

示例：

```json
{
  "task_complexity": "high",
  "uncertainty": "medium",
  "external_errors": 3,
  "feasible_solution_available": true
}
```

这一层不能直接用于人格判断。

它主要用于：

> 给用户行为提供情境背景。

---

## 3.2 Agent Behavior

这一层描述：

> Hermes 自己做了什么。

例如：

- 自动搜索；
- 自动重试；
- 自动规划；
- 自动调用工具；
- 自动更换策略；
- 自动执行测试；
- 自动展开 research；
- 自动总结；
- 自动继续多轮迭代。

示例：

```json
{
  "agent_search_count": 37,
  "agent_retry_count": 8,
  "tool_calls": 54,
  "agent_strategy_changes": 3
}
```

这些信息可以用于：

- 判断任务复杂度；
- 判断 Agent 执行成本；
- 判断系统效率；
- 判断用户当时面对的是什么状态。

但不能直接推出：

> 用户本人就是怎样的人。

---

## 3.3 User Behavior

这一层描述：

> 用户明确做了什么。

例如：

- 用户主动要求继续；
- 用户主动要求停止；
- 用户要求更多证据；
- 用户否决当前方案；
- 用户缩小范围；
- 用户扩大范围；
- 用户修改目标；
- 用户重新打开一个已经暂停的问题；
- 用户选择接受一个“不完全确定”的答案；
- 用户选择暂时不解决；
- 用户主动要求再验证一次；
- 用户主动要求立即落地实验。

示例：

```json
{
  "user_action": "continue_investigation",
  "after_agent_recommendation": "pause",
  "user_override": true
}
```

这一层是用户建模的重要信号。

---

## 3.4 Interaction Pattern

这一层是最有价值的。

它描述：

> 用户如何回应 Agent、失败、模糊性、不确定性、建议与结果。

例如：

```text
Agent 给出 80% 确定结论
↓
User 要求继续搜索直到得到更多证据
```

或者：

```text
Agent 建议暂停
↓
User 接受暂停
```

或者：

```text
Agent 连续失败
↓
User 改变目标，缩小范围
```

这一层比单独的用户文本更有价值，因为它保留了：

> **刺激 → 用户响应**

也就是用户在具体情境下如何做选择。

---

# 4. 为什么 Interaction Pattern 特别重要

传统用户画像常常只分析：

> 用户说了什么。

但对于长期成长系统，更重要的是：

> 用户在面临某种状态时，做出了什么选择。

例如：

- 面临失败时；
- 面临未完成时；
- 面临不确定性时；
- 面临多个可选方案时；
- 面临 Agent 建议暂停时；
- 面临已有“够用答案”时；
- 面临 deadline 时。

这些情况形成的响应模式，比单纯语言风格更能说明：

> 用户当前习惯如何处理现实。

---

# 5. 一个典型反例

假设 Hermes 自动执行：

```text
搜索 40 次
重试 8 次
切换 3 次方案
运行 12 次测试
```

错误推断：

> 用户有很强的信息搜集倾向。

或者：

> 用户无法接受失败。

这是不成立的。

因为这些都可能是：

> Hermes 默认工作方式。

真正需要观察的是：

```text
Hermes：
已经给出可行方案，并说明继续搜索的边际收益很低

User：
继续搜，先不要停

Hermes：
又找到一些重复证据

User：
再确认有没有遗漏
```

如果这种情况跨多个任务重复出现，才可能形成：

> 用户倾向在决策前要求较高的信息完备度。

随后才能进一步形成假设：

> 用户可能倾向通过增加信息获取来降低决策不确定性。

---

# 6. Agent 行为的真正价值

虽然 Agent 行为不能直接代表用户，但它仍然非常重要。

它主要承担两种作用。

---

## 6.1 提供任务背景

例如：

```text
Agent 已经尝试 6 种方案
↓
仍未解决
```

这告诉系统：

> 用户当前面对的是一个真正困难的问题。

这样用户要求继续，就不能轻易解释成“难以停止”。

---

另一个例子：

```text
Agent 已经找到稳定可行方案
↓
继续搜索只产生重复证据
```

如果此时用户仍持续要求更多搜索，才更有分析价值。

因此：

> **用户行为必须结合任务状态解释。**

---

## 6.2 提供“选择节点”

Agent 会自然产生大量用户选择机会。

例如：

- 要不要继续；
- 要不要停止；
- 要不要接受当前答案；
- 要不要再搜索；
- 要不要换方向；
- 要不要降低目标；
- 要不要暂时搁置；
- 要不要进一步验证。

因此 Hermes 的真正价值是：

> **它创造了大量可以观察用户决策方式的交互节点。**

---

# 7. Hermes 应该被视作“实验环境”

一个更准确的比喻是：

> **Hermes 是实验环境，而不是用户代理。**

它不是：

> 用户行为的镜像。

而是：

> 一个持续向用户呈现问题、结果、失败、建议和选择的环境。

我们观察的是：

> 用户如何回应这些状态。

---

# 8. 正确的证据链

用户人格与成长分析应采用：

```text
Task Context
↓
Agent State
↓
User Choice
↓
Repeated Interaction Pattern
↓
Development Hypothesis
↓
User Calibration
↓
Confirmed Insight
```

而不是：

```text
Agent Search Count
↓
User Personality
```

---

# 9. 可以用于用户分析的强信号

以下信号相对有价值。

---

## 9.1 明确用户决策

例如：

- “继续。”
- “先停。”
- “这个证据已经够了。”
- “还不够，再查。”
- “不要再优化了，先跑实验。”
- “先别做实验，我想把理论弄清楚。”
- “这个问题今天先不解决。”

这些都是强信号。

---

## 9.2 用户主动改变目标

例如：

```text
原目标：
完整解决问题

用户主动改为：
先找到一个可用 workaround
```

可以反映：

- 灵活性；
- 优先级调整；
- 对不确定性的接受；
- 执行策略变化。

---

## 9.3 用户主动重新打开任务

如果一个已经暂停的问题被用户多次主动重新打开，这比 Agent 自动 retry 更有意义。

---

## 9.4 用户面对“足够答案”的反应

这是非常重要的交互节点。

例如：

```text
Agent：
目前证据足够支持方案 A，但仍有约 10% 不确定性
```

用户可以：

- 接受；
- 要求继续验证；
- 转入实验；
- 要求寻找绝对确定答案。

长期模式很有分析价值。

---

## 9.5 用户面对失败后的选择

例如：

- 继续；
- 换方案；
- 缩小目标；
- 暂停；
- 求助；
- 承认暂时无解；
- 无限 retry。

但必须明确：

> 是用户做出的选择，而不是 Hermes 自动执行。

---

# 10. 弱信号

以下可以参考，但不能单独形成深层结论。

例如：

- 用户单次说“继续”；
- 单次长会话；
- 单次深夜工作；
- 单次要求更多证据；
- 单次否决方案；
- 单次高压任务。

这些可能只是：

- 任务特殊；
- deadline；
- 当前情境特殊。

所以需要：

> 跨时间、跨任务、跨情境复现。

---

# 11. 不应该用于直接推断用户的信号

以下行为原则上属于 Agent telemetry：

- Agent 搜索次数；
- Agent tool call 次数；
- Agent retry 次数；
- Agent reasoning token；
- Agent 自动 context switch；
- Agent 自动生成子任务数量；
- Agent 自动测试次数；
- Agent 自动运行时间。

这些主要用于：

- 系统效率；
- 任务复杂度；
- 交互背景；
- Agent 质量评估。

不是直接的用户画像证据。

---

# 12. 一条 Pattern 必须跨多个情境

例如：

```text
科研任务
↓
未完成时持续追查

服务器故障
↓
未完成时持续追查

工具配置
↓
未完成时持续追查
```

如果相似模式跨不同领域都存在，才可能形成：

> 稳定用户模式。

如果只有：

```text
论文 deadline 前
```

出现，则更可能是：

> 特殊情境效应。

因此每个 Pattern 应记录：

```json
{
  "contexts": [
    "research",
    "software_debugging",
    "tool_configuration"
  ],
  "cross_context": true
}
```

---

# 13. 推荐的 Event Schema

可以初步设计成：

```json
{
  "timestamp": "2026-10-15T13:00:00+08:00",
  "task_id": "xxx",
  "actor": "user",
  "event_type": "continue_request",
  "context": {
    "agent_status": "solution_available",
    "uncertainty": 0.2,
    "agent_recommendation": "stop"
  }
}
```

其中：

```text
actor
```

必须明确区分：

- user
- hermes
- system
- external_tool

这样能够避免数据层混淆。

---

# 14. 推荐增加 actor 字段

所有事件必须明确：

```text
actor = user
actor = agent
actor = system
actor = environment
```

不能只保存：

```text
retry
search
continue
```

否则未来分析时很容易错误归因。

---

# 15. 推荐增加 causality / trigger 字段

除了 actor，还应该知道：

> 用户为什么会做出这个动作。

例如：

```json
{
  "actor": "user",
  "action": "continue",
  "trigger": "agent_reported_uncertainty",
  "agent_recommendation": "pause"
}
```

或者：

```json
{
  "actor": "user",
  "action": "stop",
  "trigger": "repeated_evidence"
}
```

这样长期可以分析：

> 用户在什么刺激下容易做出什么选择。

---

# 16. 推荐增加 counterfactual context

有些用户行为必须结合：

> 当时是否已经有其他合理选择。

例如：

```text
如果 Agent 没有给出可行方案
↓
用户继续
```

很正常。

但：

```text
Agent 已经有可行方案
+
继续搜索边际收益很低
+
Agent 建议停止
↓
用户仍要求继续
```

这才有更强的心理 / 决策分析价值。

---

# 17. 推荐的 Interaction Event

可以比普通 Event 更丰富：

```json
{
  "event_type": "decision_point",
  "task_id": "research_x",
  "agent_state": {
    "solution_available": true,
    "confidence": 0.82,
    "marginal_gain_estimate": "low",
    "recommendation": "proceed_to_experiment"
  },
  "user_response": {
    "action": "continue_research",
    "reason": "want_more_evidence"
  }
}
```

这类数据非常适合未来形成 Pattern。

---

# 18. 从 Interaction Event 到 Pattern

多个事件可能形成：

```text
Decision Point A
Agent：已有可行答案
User：继续搜索

Decision Point B
Agent：已有可行答案
User：继续验证

Decision Point C
Agent：建议实验
User：继续理论分析
```

然后 Pattern Finder 才能提出：

> 用户在进入执行前，往往要求较高信息完备度。

注意：

这仍然是行为模式。

不是人格评价。

---

# 19. 从 Pattern 到 Hypothesis

一个 Pattern 可能对应多个解释。

例如：

> 用户在已有可行答案后仍继续搜索。

可能解释：

### H1

用户需要较高证据标准。

### H2

用户对不确定性较敏感。

### H3

科研任务本身需要严格证据。

### H4

用户过去曾因过早决策吃过亏。

### H5

当前项目的重要性特别高。

不能自动选择其中一个。

必须保留竞争假设。

---

# 20. 用户校准的重要性

当一个 Pattern 足够稳定后，可以让宠物问：

> “我发现当已经有一个可行答案时，你常常还是会继续找更多证据。你觉得更像是因为你重视严谨，还是因为‘还没有完全确定’本身会让你不舒服？”

这个问题本身就能帮助用户自我理解。

系统也会获得更可靠的信息。

---

# 21. 用户自己的解释优先级更高

用户反馈不一定绝对正确，但应该给予较高权重。

模型需要记录：

```json
{
  "hypothesis": "uncertainty_intolerance",
  "model_confidence": 0.67,
  "user_feedback": "partially_agree",
  "user_explanation": "mostly about scientific rigor"
}
```

之后继续观察。

---

# 22. Hermes 行为数据应该进入哪个系统

建议拆成两个数据域。

---

## 22.1 Agent Telemetry

记录：

- tool call；
- search；
- retry；
- runtime；
- error；
- reasoning；
- model；
- tokens；
- workflow；
- execution state。

用途：

- 系统优化；
- 任务复杂度；
- 性能；
- 背景分析。

---

## 22.2 User Interaction Evidence

只记录：

- 用户选择；
- 用户干预；
- 用户接受 / 拒绝；
- 用户改变目标；
- 用户要求继续 / 停止；
- 用户对不确定性的响应；
- 用户主动重新打开任务。

用途：

> 用户成长模型。

两类数据必须逻辑隔离。

---

# 23. 不应该直接把 Agent Telemetry 输入人格分析模型

错误架构：

```text
Hermes Logs
↓
LLM
↓
User Personality
```

推荐架构：

```text
Hermes Logs
↓
Task / Agent State Reconstruction
↓
Interaction Point Extraction
↓
User Response Extraction
↓
Pattern Finder
↓
Hypothesis
```

---

# 24. Hermes 与 ChatGPT 数据角色重新定义

经过这次修正，两者分工应该调整为：

---

## Hermes

主要提供：

- 任务上下文；
- Agent 状态；
- 执行结果；
- 决策节点；
- 用户对 Agent 的反馈；
- 用户主动控制行为。

它帮助系统知道：

> **用户在什么情况下做出了什么决定。**

---

## ChatGPT

主要提供：

- 用户自我表达；
- 自我反思；
- 价值观讨论；
- 决策理由；
- 长期主题；
- 自我叙事；
- 对自身变化的描述。

它帮助系统理解：

> **用户如何解释自己的经历。**

---

# 25. 两种数据结合后的真正价值

例如：

Hermes 数据显示：

```text
过去三个月
用户 17 次在 Agent 建议暂停后选择继续
```

ChatGPT 中用户曾说：

> “事情悬在那里我会一直想着。”

两个来源互相印证。

这时才能提高假设置信度：

> 未闭环状态可能对用户注意力有较强占用。

这种跨来源验证会比单一日志可靠得多。

---

# 26. Evidence Ledger 也必须记录来源类型

例如：

```text
Hypothesis:
Unresolved tasks may strongly occupy attention

Evidence For:

[User-originated]
用户明确说过：
“事情悬在那里我会一直想着”

[Interaction-derived]
多次在 Agent 建议停止时主动继续

[Cross-context]
research / debugging / configuration 均出现

[Agent-context]
多数情况下已经存在可行 stopping point
```

Evidence Against：

```text
多个低优先级问题能够长期保持未解决
```

这样才能形成真正可靠的长期模型。

---

# 27. Evidence 权重建议

可以初步定义：

```text
User explicit self-report
★★★★★

User repeated decision pattern
★★★★★

Cross-context interaction pattern
★★★★☆

Single user action
★★☆☆☆

Agent behavior
★☆☆☆☆

Agent autonomous telemetry alone
不得直接作为人格证据
```

---

# 28. 一个完整示例

假设某研究任务中：

### Hermes

- 已经调研 25 篇论文；
- 给出 3 个候选方案；
- 推荐先实现方案 A；
- 判断继续搜索边际收益低。

### User

> “再搜索一下 2026 年的相关工作。”

Hermes继续搜索后：

- 新结果与已有结果高度重复；
- 再次建议进入实验。

User：

> “再确认有没有直接利用数据流形的。”

如果这种行为只发生一次：

> 不形成稳定结论。

如果长期多次出现：

> Pattern：
> 用户倾向在执行前持续增加证据完整度。

随后产生竞争假设：

```text
H1 科研严谨性要求高
H2 对遗漏风险敏感
H3 对不确定性容忍较低
H4 习惯先最大化信息再行动
```

随后通过 ChatGPT 对话 / 用户校准确定：

> 主要是 H1 + H2。

最终 Insight 可能变成：

> “在重要研究决策中，你倾向先建立较高证据覆盖再行动。这提高了方案严谨性，但有时也延迟最小实验启动。”

这是一个有价值的成长洞察。

---

# 29. 用户成长建模真正应该关注什么

不是：

> Hermes 工作了多久。

而是：

> 用户如何做决定。

不是：

> Agent retry 多少次。

而是：

> 在已经出现失败信号之后，用户如何调整。

不是：

> Agent 搜索多少论文。

而是：

> 用户何时认为证据“够了”。

不是：

> Agent 跑了多少工具。

而是：

> 用户何时主动停止工具链。

---

# 30. 最重要的转变

原始想法：

> Hermes = 用户行为数据源。

修正后：

> **Hermes = Task Environment + Agent State + Interaction Decision Environment。**

真正进入用户成长模型的是：

> **User Choice + User Response + Cross-context Interaction Pattern。**

---

# 31. 与整个 Co-evolving Companion 的关系

这个修正会影响后续所有模块：

- User Model；
- Pattern Finder；
- Personality Lens；
- Development Hypothesis；
- Growth Narrative；
- Intervention；
- Shared Goals；
- Growth Chapters。

如果底层归因错误：

> 后面的“人格分析”再高级也没有意义。

因此：

# Attribution First

应该成为系统架构原则。

---

# 32. 新增系统硬规则

建议正式加入以下 Invariants：

### Invariant 1

**Agent autonomous behavior is never direct evidence of user personality.**

### Invariant 2

**Every behavioral event must have an explicit actor.**

### Invariant 3

**Deep user inference requires repeated user-originated or interaction-derived evidence.**

### Invariant 4

**Task context must be considered before interpreting user choices.**

### Invariant 5

**Cross-context repetition is required before a behavior becomes a stable Pattern.**

### Invariant 6

**Psychological interpretations remain hypotheses until calibrated by the user or strongly triangulated.**

---

# 33. 修正后的总体链路

最终推荐：

```text
Hermes / ChatGPT / Other Sources
              ↓
        Raw Events
              ↓
        Actor Attribution
              ↓
┌─────────────────────────────┐
│ Environment / Task          │
│ Agent Behavior              │
│ User Behavior               │
│ Interaction Pattern         │
└─────────────────────────────┘
              ↓
        User Evidence
              ↓
        Pattern Finder
              ↓
   Competing Hypotheses
              ↓
      User Calibration
              ↓
     Confirmed Insights
              ↓
      Growth Narrative
              ↓
   Companion Intervention
```

---

# 34. 当前结论

Hermes 仍然是整个项目极其重要的数据源，但它的价值需要重新定义。

不是：

> “通过 Hermes 的行为分析用户。”

而是：

> **通过 Hermes 重建用户所处的任务环境与选择节点，并观察用户如何回应这些状态。**

最值得分析的并不是：

> Agent 做了什么。

而是：

> **当 Agent 给出失败、建议、不确定答案、可行方案或停止信号时，用户选择了什么。**

这使 Hermes 从简单的 telemetry 数据源，变成：

> **一个高质量的人机决策行为观察环境。**

---

# 35. 下一阶段讨论建议

完成行为归因边界后，下一步最值得继续讨论：

## A. 什么情况下宠物可以主动介入？

需要明确：

- 什么行为只是观察；
- 什么情况值得提醒；
- 什么情况值得提出 Reflection；
- 什么情况允许 Challenge；
- 什么情况下必须沉默。

## B. 用户模型多久更新一次？

例如：

- session；
- daily；
- weekly；
- monthly；
- quarterly。

## C. 什么 Pattern 才值得进入长期记忆？

需要避免系统记住大量噪声。

## D. 如何设计用户可查看、可修改的 Personal Model？

用户是否能看到：

- Pattern；
- Hypothesis；
- Evidence；
- Confidence；
- Growth Chapter。

## E. 如何处理错误分析与“宠物误解用户”？

这会直接影响长期信任。

---

# 36. 一句话原则

> **Hermes 的自主行为说明 Agent 在做什么；用户如何回应 Hermes，才真正说明用户可能是什么样。**

或者更简洁：

> **Observe the choice, not the agent loop.**
