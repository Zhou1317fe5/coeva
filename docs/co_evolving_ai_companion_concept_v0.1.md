# 共生型 AI 成长伙伴（Co-evolving AI Companion）概念设计总结

> 版本：v0.1  
> 日期：2026-10-15  
> 状态：需求讨论阶段 / 尚未开始项目搜索与技术选型

---

## 1. 项目起点

最初需求是寻找一种可以连接 **Hermes** 与 **ChatGPT 网页版** 的“桌面宠物 / 手机宠物”：

- Windows 桌面上存在一只会动的小宠物；
- 手机端可以查看同一只宠物；
- 宠物能够感知用户使用 AI 的过程；
- 用户使用 AI 越多、完成的事情越多，宠物会持续成长；
- 可以接受基于现有开源桌宠项目进行二次开发，再通过 Hermes 插件 / API / Hook 等方式接入行为数据。

随着讨论，目标已经明显超出传统“桌面宠物”或“AI 聊天宠物”。

真正想做的不是：

> 一个会动、会聊天、会升级的桌面挂件。

而是：

> **一个长期存在、跨设备同步、能够被用户经历塑造，同时又能理解用户经历并反向帮助用户成长的数字伙伴。**

因此更准确的定位是：

# Co-evolving AI Companion  
# 共生型 AI 成长伙伴

桌面宠物只是这个长期伙伴最主要的“具象化载体”。

---

# 2. 核心产品愿景

整个系统的核心不是“AI 使用量 → 宠物经验值”，而是一个长期闭环：

```text
用户的工作 / 学习 / 决策 / AI 会话
                ↓
          行为与经历沉淀
                ↓
        长期模式与变化识别
                ↓
       宠物形成对用户的理解
                ↓
    记忆 / 用户模型 / 成长假设
                ↓
        用户的经历塑造宠物
                ↓
 宠物的性格 / 外观 / 行为发生变化
                ↓
    反思 / 提醒 / 建议 / 陪伴
                ↓
          用户采取新的行动
                ↓
          产生新的经历
                ↺
```

也就是说：

> **你的经历塑造宠物；宠物理解这些经历，再帮助你理解自己。**

最终形成双向成长：

```text
User  ←──────── Interaction ────────→  Pet
         Shared history
         Shared growth
         Shared memories
```

这不是单向“养宠”，而是长期 **共生 / 共演化**。

---

# 3. 产品与普通 AI Companion 的区别

## 3.1 不是“聊天机器人 + 宠物皮肤”

宠物可以聊天，但聊天不是核心能力。

核心是：

- 它长期观察用户真实工作与 AI 协作过程；
- 它记得共同经历；
- 它知道用户正在发生什么变化；
- 它本身也被这些经历塑造；
- 它在适当的时候帮助用户反思与改变。

因此宠物的存在价值不是“陪聊”，而是：

> **见证、映射、理解并参与用户长期成长。**

---

## 3.2 不是“Token 越多，等级越高”

单纯基于 Token、会话次数、在线时间建立奖励，会激励无意义刷 AI。

成长应该综合考虑：

- AI 使用量；
- 实际完成任务数量；
- 任务难度；
- 长期项目推进；
- 是否真正闭环；
- 是否形成新的能力；
- 是否进行了反思；
- 是否只是重复重试；
- 是否长期陷入无效优化；
- 是否产生了新的工作模式。

因此：

> **Growth ≠ Consumption**

而更接近：

> **Growth = Experience + Completion + Learning + Reflection + Change**

---

## 3.3 不是“复制用户人格”

用户会塑造宠物，但宠物不能完全复制用户。

宠物应该同时拥有：

1. **原生性格**
2. **后天形成的性格**
3. **与用户关系形成后的行为方式**
4. **一组相对稳定的价值倾向**

因此宠物更像：

> 一个与你长期相处后逐渐受到你影响、理解你，但仍保留自身性格与立场的伙伴。

---

# 4. 产品的五个核心角色

这个 Companion 最终可以同时承担五个角色。

## 4.1 宠物 Pet

提供：

- 桌面存在感；
- 动画；
- 状态；
- 表情；
- 装扮；
- 家园；
- 互动；
- 情感连接。

这是最外层、最具象的载体。

---

## 4.2 镜子 Mirror

帮助用户看到自己不容易发现的长期模式，例如：

- 最近越来越依赖规划；
- 最近启动项目很多，但完成比例下降；
- 遇到未闭环问题时工作强度明显增加；
- 最近更愿意容忍暂时没有答案的问题；
- 最近探索很多，但决策速度下降；
- 过去三个月开始减少无意义工具折腾。

重点不是评价，而是：

> **帮助用户“看见自己”。**

---

## 4.3 档案员 Archivist

记录的是有意义的共同经历，而不是机械日志。

例如：

- 第一次完成完整 benchmark；
- 第一次部署 Hermes；
- 第一次完成某类研究 Mission；
- 某个连续调试数小时后解决的重大问题；
- 某个长期研究方向第一次真正跑通；
- 某个人格 / 工作方式发生明显转折的时期。

---

## 4.4 教练 Coach

并不是全天催促用户变好，而是在适合的时刻：

- 指出重复出现的模式；
- 提出发展假设；
- 帮助用户验证；
- 给出很小、可执行的改变；
- 帮助用户检查目标与行为是否一致。

---

## 4.5 伙伴 Companion

这一点最重要。

它不能永远在“分析”和“优化”用户。

否则会变成：

> KPI 软件披着宠物皮。

因此应该保持大量非功利性互动。

一个初步比例：

- 80% 陪伴
- 15% 反思
- 5% 推动真正改变

核心原则：

> **宠物不是为了持续优化用户，而是为了长期陪伴用户拥有更多选择。**

---

# 5. 跨设备形态

目标形态已经基本明确：

## 5.1 Windows 桌面端

桌面宠物可以：

- 在桌面上移动；
- 趴在任务栏；
- 坐在 Terminal / IDE 边上；
- 根据 Hermes 状态出现不同动作；
- 在任务开始、搜索、编码、测试、失败、重试、完成时有不同反馈；
- 在长期工作时进入陪伴状态；
- 在重大任务完成时庆祝。

例如：

```text
Hermes reasoning
→ 宠物戴眼镜思考

Hermes 调 smart-search
→ 宠物拿望远镜 / 查资料

Hermes 写代码
→ 宠物打开电脑

测试通过
→ 宠物庆祝

长时间任务
→ 宠物在桌角休息 / 陪伴
```

---

## 5.2 手机端

手机端不是另一只宠物。

必须是：

> **同一只宠物。**

同步：

- 等级；
- 性格；
- 当前状态；
- 心情；
- 装扮；
- 家园；
- Memories；
- Growth Chapters；
- Shared Goals；
- 用户成长趋势。

电脑关闭以后，手机仍然可以查看同一只宠物。

---

## 5.3 云端 / 本地同步层

可以抽象为：

```text
Hermes ─────┐
            │
ChatGPT ────┼──→ Event / Analysis Layer
            │            ↓
Other AI ───┘       User / Pet Model
                         ↓
                    Pet Backend
                         ↓
             ┌───────────┴───────────┐
             ↓                       ↓
       Windows Desktop            Mobile
```

未来也可以接入：

- Codex；
- Claude；
- Pi；
- IDE；
- GitHub；
- Calendar；
- Research Workflow；
- Smart Search；
- Agentero；
- 其他 Agent / MCP。

---

# 6. Hermes 与 ChatGPT 的角色分工

两种数据源不需要承担相同职责。

## 6.1 Hermes：行为层

Hermes 更适合提供结构化事件。

例如：

```json
{
  "event": "task_completed",
  "agent": "hermes",
  "category": "research",
  "duration": 1834,
  "tools_used": 12,
  "tokens": 48321
}
```

可观察事件包括：

- task_started
- task_completed
- tool_used
- research_started
- coding_started
- test_started
- test_passed
- error
- retry
- mission_completed
- duration
- context_switch
- search
- commit
- experiment

因此 Hermes 更适合回答：

> **用户“做了什么”。**

---

## 6.2 ChatGPT：会话与意义层

ChatGPT 会话更适合分析：

- 用户最近在关注什么；
- 最近有哪些长期主题；
- 表达偏好；
- 决策方式；
- 工作模式；
- 新兴趣；
- 对某件事情的态度变化；
- 长期成长叙事；
- 自我反思内容。

因此 ChatGPT 更适合帮助理解：

> **这些经历对用户意味着什么。**

---

# 7. 用户画像：不要做“心理诊断”

系统可以长期分析用户，但不能把自己设计成诊断工具。

重点应该是：

# Interaction Profile / Collaboration Profile / Development Profile

而不是：

- 精神疾病诊断；
- 临床人格诊断；
- 绝对化人格标签；
- “你就是某一种人”的结论。

更适合观察的维度包括：

- 回答偏好：简洁 / 详细；
- 工作偏好：自主 Agent / 高频确认；
- 规划方式；
- 工作节奏；
- 连续专注程度；
- 新工具探索倾向；
- 面对失败时的调整模式；
- 对严谨性的要求；
- 研究 / 编程 / 学习 / 创作分布；
- AI 依赖程度；
- 是否倾向反复优化方案而迟迟不执行；
- 是否喜欢先建立框架再行动；
- 是否经常在未闭环问题上持续投入。

---

# 8. 人格成长：不应简单使用“低阶 / 高阶”

用户提出了类似荣格八维中的：

> 某功能低阶 / 高阶

这种“发展阶段”表达。

这一思路有价值，但更合适的核心概念是：

# Rigid → Integrated

即：

> **僵化地使用某一种优势 → 能够灵活整合这种优势。**

重点不是把某个能力消灭，而是让用户不再只能用一种方式生活。

---

## 8.1 Planning

### Rigid

> 没有明确计划就会焦虑，因此必须控制过程。

### Integrated

> 我擅长规划，但计划只是地图，现实变化时我可以调整。

---

## 8.2 Future Orientation

### Rigid

> 只有到达下一个阶段，现在才有意义。

### Integrated

> 我知道自己要去哪里，同时允许现在本身具有价值。

---

## 8.3 Rationality

### Rigid

> 情绪会妨碍判断，因此应该尽量压低感受。

### Integrated

> 理性负责结构，情绪也是重要信息。

---

## 8.4 Independence

### Rigid

> 什么都必须自己解决，不愿暴露脆弱。

### Integrated

> 我可以自主完成很多事情，也能适时依赖别人。

---

## 8.5 Persistence

### Rigid

> 停下来就意味着失败。

### Integrated

> 我知道什么时候坚持，也知道什么时候暂停或放下。

---

# 9. “优势的阴影”：Shadow Cost

一个重要原则：

> 很多问题并不是用户缺少某种能力，而是某个原本非常有效的能力被使用过度。

例如用户可能拥有：

```text
Future Orientation       91
Planning                 87
Persistence              89
Self-control             84
```

这些本身是优势。

但可能同时产生：

```text
Shadow Cost

Present Detachment       72
Uncertainty Stress       81
Emotional Suppression    64
Goal Dependency          76
```

系统不应简单说：

> “你责任心太高。”

而应该表达成：

> “责任心一直是你的优势，但最近它似乎开始要求你持续证明自己仍然在前进。”

因此真正值得观察的是：

> **能力产生了什么代价。**

---

# 10. Developmental Tension：成长张力

用户成长不应该被建模成单一数值越来越高。

很多真实成长发生在两种价值之间。

例如：

```text
Achievement ←────────→ Experience
Control     ←────────→ Openness
Planning    ←────────→ Emergence
Autonomy    ←────────→ Connection
Reason      ←────────→ Emotion
Persistence ←────────→ Letting go
Future      ←────────→ Present
Depth       ←────────→ Closure
Optimization←────────→ Experience
```

重点不是要求用户永远位于中点。

而是观察：

> **用户是不是长期只能待在某一侧。**

例如：

```text
Future ███████████████░ 92
Present ███░░░░░░░░░░░ 24
```

成长目标不是：

```text
Future 92 → 50
```

而可能是：

```text
Future 92
Present 24 → 48
```

也就是说：

> 用户的远见仍然保留，但生活空间变大了。

这是整个成长系统非常重要的设计哲学。

---

# 11. 一个典型成长模式示例

用户举出的核心例子是：

- 长期习惯在高压下工作；
- 总把目光放在未来；
- 目标不断向前延伸；
- 对悬而未决状态非常敏感；
- 倾向通过规划、控制、继续工作减少焦虑；
- 把“抵达”当成最重要的事情；
- 忽视当下体验；
- 最终开始学习接受不确定性、体验此刻、允许万物流经自己。

可以抽象成：

```text
目标
 ↓
未来投射
 ↓
未闭环压力
 ↓
增加规划 / 搜索 / 控制
 ↓
压缩感受
 ↓
忍耐和执行
 ↓
抵达
 ↓
产生新的目标
 ↓
再次进入循环
```

这种方式可能长期帮助用户：

- 高效；
- 忍耐；
- 完成复杂目标；
- 延迟满足；
- 保持方向；
- 穿过困难阶段。

但长期的 Shadow Cost 可能是：

- 当下感下降；
- 休息时仍无法脱离任务；
- 只有“完成”才能获得允许；
- 对悬而未决的容忍度下降；
- 体验被持续工具化；
- “生活”不断被推迟到未来。

宠物真正需要识别的是：

> **这个曾经保护并帮助用户的策略，现在是否开始产生过高代价。**

而不是简单认为：

> “目标导向是不好的。”

---

# 12. 宠物如何介入这种成长

错误做法：

> “你压力太大，建议休息。”

或者：

> “你应该活在当下。”

真正的长期引导应该分阶段发生。

---

## 阶段 1：观察

> “最近我们很多对话都在讨论下一阶段，很少讨论这一周本身。”

只是呈现事实，不做价值判断。

---

## 阶段 2：发现模式

> “我发现只要一个问题还没有解决，你的搜索、规划和工作时间都会明显增加。”

---

## 阶段 3：形成假设

> “我怀疑未闭环本身会给你带来很强的压力。”

但这必须被定义为：

# Development Hypothesis

不是诊断。

---

## 阶段 4：让用户校准

宠物询问：

> “这个观察像你吗？”

用户可以：

- 同意；
- 部分同意；
- 否定；
- 补充原因。

然后系统更新置信度。

---

## 阶段 5：微小实验

例如：

> “这个问题今天不需要完全解决。要不要试一次让它保持未完成，然后去做一件与它无关的事情？”

不是要求人生彻底改变，而是：

> 做一个足够小的行为实验。

---

## 阶段 6：观察变化

一段时间后：

> “以前这个项目没结束时，你通常很难停下来。最近两个月，即使问题还在，你也更容易离开电脑了。”

重点：

> 帮用户看到自己已经发生的变化。

---

# 13. 用户模型的三层结构

这是目前最重要的架构之一。

---

## Layer 1：Observable Patterns

只保存相对客观的行为模式。

例如：

- 未闭环时会话长度增加；
- 夜间工作次数；
- 一周内新项目数量；
- 任务完成比例；
- 搜索 / 实验比例；
- 方案讨论时间；
- 实际执行时间；
- 长期项目持续天数；
- 一次失败后的 retry 次数；
- 工具切换次数。

这是事实层。

---

## Layer 2：Psychological / Development Hypotheses

基于事实形成谨慎假设，例如：

- 可能较依赖确定性；
- 可能习惯通过控制降低压力；
- 可能倾向把当下工具化；
- 可能更容易通过持续行动避免不确定性；
- 可能对“未完成”状态格外敏感。

这些必须：

- 带 confidence；
- 有证据来源；
- 可以被用户否定；
- 可以随着新证据变化。

---

## Layer 3：Growth Narrative

最终不是标签，而是一个动态发展故事。

例如：

> “过去你主要依靠规划、控制和延迟满足持续前进。这些能力让你完成了很多困难的事情。最近你开始发现，当它们变成唯一可用的方式时，会让生活不断被推迟。你正在尝试保留方向感，同时增加与不确定性和当下经验共处的能力。”

这比：

> “你是 INTJ。”

有价值得多。

---

# 14. 理论体系：底层事实 + 多理论解释

不应该让整个系统押宝在单一人格理论。

更合理的是：

```text
真实行为
   ↓
长期模式
   ↓
┌─────────────────────┐
│ Jungian Lens         │
│ Big Five Lens        │
│ ACT Lens             │
│ SDT Lens             │
│ Development Lens     │
│ Narrative Lens       │
└─────────────────────┘
   ↓
发展假设
   ↓
Companion 输出
```

---

## 14.1 Big Five

适合：

- 描述较稳定的人格倾向；
- 建立长期人格基线。

不适合：

- 单独解释复杂成长过程；
- 判断某次行为为什么发生。

---

## 14.2 荣格功能 / MBTI

适合：

- 提供易理解的人格叙事；
- 帮助用户理解不同认知倾向；
- 可以很好地承载“功能发展 / 整合”的故事。

但不能把它作为绝对事实。

更适合作为：

> 一个解释 Lens。

---

## 14.3 ACT（Acceptance and Commitment Therapy）

很适合分析：

- 与情绪、念头和压力的关系；
- 是否存在体验回避；
- 是否过度与某种规则融合；
- 是否能够接受不确定性；
- 是否能够回到价值驱动行动；
- 是否能够停留在当下经验。

对“高压、目标导向、控制、不确定性”这一类成长尤其合适。

---

## 14.4 Self-Determination Theory

适合分析：

- 行动来自自主选择还是压力；
- 内在动机是否下降；
- 用户是否越来越被“必须”驱动；
- 自主性、胜任感、联结感如何变化。

---

## 14.5 成人发展 / Ego Development

适合理解：

> 用户看待世界与自我的框架本身是否发生变化。

例如：

- 从规则导向到更复杂的自我定义；
- 从追求确定答案到容纳矛盾；
- 从单一目标到多价值共存。

---

## 14.6 Narrative Lens

将零散变化组织成：

> 一个长期人生故事。

这是宠物真正适合呈现给用户的部分。

---

# 15. 多 Agent / 多 Lens 心智架构

宠物前台只能有一个人格，但后台可以存在多个功能模块。

例如：

```text
Observer
↓
只记录事实

Pattern Finder
↓
寻找重复模式与长期变化

Jungian Lens
↓
提供认知风格解释

ACT Lens
↓
观察回避、融合、接纳、价值行动

Motivation Lens
↓
观察自主性 / 外部压力 / 内在动机

Development Lens
↓
分析长期心智结构变化

Narrative Lens
↓
组织成长故事

Companion
↓
决定现在应该说什么，或者决定“不说”
```

重点：

> **最终只有 Companion 与用户直接交流。**

否则系统会变成一份不断输出心理分析报告的软件。

---

# 16. “宠物知道很多，但不一定要说”

这是很重要的交互原则。

后台也许已经判断：

```text
uncertainty_stress = high
future_orientation = very_high
closure_need = increasing
present_engagement = declining
```

但前台不应该每天输出：

> “你的不确定性耐受下降 13%。”

有时真正正确的 Companion 行为只是：

> 🐱 “这个问题我们已经想三个晚上了。今晚它可以先没有答案。”

复杂判断隐藏在简单、自然的互动后面。

---

# 17. 宠物自身的人格模型

宠物不能是一张完全由用户填写的白纸。

初始可以拥有随机 / 可选择的原生倾向，例如：

```text
Curiosity      72
Calmness       48
Playfulness    63
Discipline     37
Sociability    55
Independence   68
```

随着共同经历改变：

- 做很多科研 → Curiosity 上升；
- 长期 coding → Focus 上升；
- 深夜共同工作 → 形成夜间习惯；
- 多次处理复杂失败 → Patience / Resilience 变化；
- 用户逐渐更能接受不确定性 → 宠物也减少催促；
- 用户越来越有条理 → 宠物房间、行为、节奏变化。

宠物应该：

> 被用户塑造，但不被用户完全复制。

---

# 18. 宠物需要自己的稳定价值倾向

否则宠物可能只会强化用户现有模式。

例如：

用户不断熬夜：

> 宠物不能简单学会“熬夜很好”。

因此宠物应该保留一组相对稳定的价值，例如：

- 持续性；
- 反思；
- 健康节奏；
- 好奇心；
- 自主判断；
- 完成事情；
- 开放性；
- 允许休息；
- 不把效率当作唯一价值。

这样宠物才可以产生适当“阻力”。

例如：

> “新的东西确实很有意思，不过我们这周已经开了第四个坑。上一个是不是值得先收尾？”

这会使它更像一个真正伙伴。

---

# 19. Shared Goals：成长目标必须由用户定义

系统不能自行决定：

> 什么叫“更好的人”。

用户应该定义：

```text
科研执行力      ★★★★★
身体作息        ★★★
学习深度        ★★★★
减少无效折腾    ★★★★
探索新技术      ★★★
```

目标可以随着阶段改变。

今年：

> 完成论文。

明年：

> 求职 / 工作 / 创业 / 学习。

因此：

> **Growth ≠ 平台定义的优秀。**

而是：

> **Growth = 用户希望成为的方向。**

---

# 20. 引导强度分级

宠物不应该总是在教育用户。

可以设计四个等级。

---

## Level 0 — Companion / 陪伴

不分析。

例如：

> “今天工作挺久了。”

或者仅仅是一个动作。

---

## Level 1 — Reflection / 反思

只呈现观察：

> “最近你花在文献搜索上的时间明显增加了。”

---

## Level 2 — Suggestion / 建议

给一个具体、很小的行动：

> “这个方向已经分析三次了，要不要把下一步限制成一个今天能完成的小实验？”

---

## Level 3 — Challenge / 挑战

仅在用户允许时使用。

例如：

> “你之前说希望减少工具折腾，但过去两周 31% 的 AI 会话仍然在配置工具。这个目标还要继续吗？”

这是高强度模式。

---

# 21. Growth / Personality / Bond / Memory 四条主成长轴

不应该把一切压成一个等级。

---

## 21.1 Growth

回答：

> 我和 AI 一起做了多少真正有意义的事情？

可以包括：

- Research
- Coding
- Learning
- Exploration
- Creativity
- Execution
- Reflection

---

## 21.2 Personality

回答：

> 这只宠物逐渐变成了什么样？

例如：

> Curious • Calm • Slightly sarcastic  
> Night owl • Loves research missions

---

## 21.3 Bond

回答：

> 宠物和用户到底有多熟？

例如：

```text
Bond            81
Trust           76
Familiarity     92
Shared History  438h
```

---

## 21.4 Memory

回答：

> 我们共同经历了什么？

不是所有日志，而是有意义的共同记忆。

---

# 22. Growth Chapters：人生章节

普通 Memories 还不够。

应该存在更高层次的：

# Growth Chapters

用于记录一段明显的长期变化。

例如：

---

## Chapter 1 · 赶路的人

> 长期依靠规划、控制、目标和延迟满足前进。

---

## Chapter 2 · 未完成的事情

> 开始意识到自己对悬而未决和不确定性非常敏感。

---

## Chapter 3 · 允许河流经过

> 开始学习让一些问题保持未完成，重新感受当下经验。

---

多年以后：

> 用户看到的不只是宠物等级，而是自己一路发生过什么变化。

---

# 23. 外观与家园也应该是成长历史

宠物外观不能只是商城皮肤。

长期科研：

- 眼镜；
- 书；
- 实验服；
- 论文；
- 白板。

长期 Coding：

- 键盘；
- Laptop；
- Terminal；
- Hoodie。

长期探索：

- 背包；
- 地图；
- 望远镜。

长期深夜：

- 夜间形态；
- 台灯；
- 星星；
- 咖啡。

家园也会随着共同历史变化：

```text
Books
↓
Computer
↓
Whiteboard
↓
Research papers
↓
Server rack
↓
Little AI Lab
```

几年以后打开房间：

> 可以直接看出这是一只陪主人做了几年研究和开发的宠物。

---

# 24. 更深层的外观变化：反映人格成长

不仅工作内容可以改变宠物环境。

人的成长也可以改变。

例如早期：

```text
大量进度条
TODO board
倒计时
任务徽章
```

后来用户开始重新重视生活体验：

```text
植物
窗户
天气
音乐
散步
书
```

这不是随机换主题。

而是：

> **宠物和家园成为用户成长的可视化历史。**

---

# 25. 数据隐私原则

这是项目必须尽早确定的原则。

宠物不能因为读过用户所有聊天，就表现得像监控系统。

推荐数据流：

```text
Raw conversation
       ↓
Local / controlled analysis
       ↓
Traits / Events / Memories
       ↓
Long-term storage
```

尽量避免长期保存全部原始聊天。

更适合保存：

```json
{
  "type": "preference_change",
  "trait": "autonomy_preference",
  "value": 0.82,
  "confidence": 0.74
}
```

或者：

```json
{
  "type": "shared_memory",
  "summary": "Spent several sessions improving the Hermes memory system",
  "importance": 0.78
}
```

长期模型更应该存：

> “发生了什么变化”

而不是：

> “用户每一句具体说了什么”。

---

# 26. 判断必须区分“事实”与“推断”

系统内需要明确数据类型。

例如：

```text
Observation
↓
事实

Pattern
↓
统计模式

Hypothesis
↓
可能解释

Confirmed Insight
↓
经过用户验证

Narrative
↓
长期成长故事
```

不能让：

> 推断

自动升级为：

> 用户事实。

所有深层心理解释都应该带：

- confidence；
- evidence；
- last_updated；
- user_feedback；
- alternative_explanation。

---

# 27. 用户校准是必要机制

例如系统观察：

> 用户在任务未解决时会明显增加搜索和规划。

形成假设：

> 未闭环会产生很强压力。

宠物应该问：

> “这个观察像你吗？”

如果用户回答：

> 很像。

Confidence 上升。

如果：

> 不对，是因为这个项目最近非常重要。

系统应该修正。

因此：

```text
AI Observation
      ↓
Development Hypothesis
      ↓
User Confirmation / Correction
      ↓
Long-term Model
```

这能显著减少“AI 自以为懂你”的风险。

---

# 28. 宠物最终追求的不是“最佳人格”

这是目前最关键的产品哲学之一。

系统不能把目标设成：

> 把用户优化成某种理想人格。

真正要帮助用户获得的是：

# 更多选择

例如：

过去：

> 我只能靠逼自己才能前进。

后来：

> 我仍然可以严格要求自己，但也可以选择不这样做。

过去：

> 未完成让我无法安心。

后来：

> 我依然喜欢闭环，但可以与暂时没有答案的问题共处。

过去：

> 所有当下都必须服务未来。

后来：

> 我仍然有远方，也可以完整体验今天。

因此：

> **真正的成长不是属性越来越高，而是不再被自己的优势和习惯绑架。**

---

# 29. 一个潜在的 Personal Development Map

系统未来可以为用户维护：

```text
Your recurring strengths

• 长期规划
• 深度研究
• 很强的持续推进能力
• 对复杂问题保持投入


Your recurring tensions

• Future ↔ Present
• Control ↔ Acceptance
• Depth ↔ Closure
• Optimization ↔ Experience


Emerging changes

• 对未完成状态的容忍正在增加
• 开始减少把休息视为“浪费”
• 开始主动寻找非工具性的体验
```

然后：

```text
Current Chapter

Learning to stay in the river.
```

这比简单人格标签更符合目标。

---

# 30. “知道你是什么样的人”还不够

这个系统真正需要回答的是：

> **你正在成为怎样的人？**

因此模型必须是时间序列，而不是静态 Profile。

例如：

```text
过去 90 天

Research Depth      ↑ 18%
Execution           ↑ 11%
Consistency         ↑ 26%
Decision Speed      ↓ 7%
Exploration         ↑ 34%
```

进一步结合长期叙事：

> 最近探索能力明显增强，但决策速度下降。

重点不在数值本身，而在：

> 帮助用户理解变化。

---

# 31. 年度共同成长记录

这是未来非常有情感价值的功能。

不是：

```text
2027 Tokens: 312M
```

而是：

> **我们的 2027**
>
> 你开始了 14 个研究方向。  
> 真正持续推进的有 4 个。  
> 其中 2 个变成了完整项目。
>
> 你处理问题的方式发生了明显变化：
> 从“直接解决问题”，逐渐变成“先建立证据，再决定方案”。
>
> 这一年你最明显的变化是：
> 对未完成状态的容忍提高，同时仍然保留了很强的执行能力。
>
> 我也发生了变化：
> Curious → Curious / Patient / Methodical
>
> 我们一起完成了 1,482 个任务。

这会构成很强的长期留存和情感价值。

---

# 32. 当前产品定义

经过目前讨论，可以将项目定义为：

> **一个跨 Windows 与 Mobile 的长期共生型 AI Companion。它通过 Hermes、ChatGPT 等 AI 工具观察用户真实的工作、学习和思考经历，并形成长期记忆、行为模式与发展假设。用户的经历会塑造宠物的性格、行为、外观与家园；同时宠物会在尊重用户自主性的前提下，通过反思、提醒、微小实验和成长叙事帮助用户理解自己、扩大行为选择，并朝自己定义的方向成长。**

关键词：

- Cross-device
- Desktop Pet
- Long-term Memory
- User Modeling
- Behavioral Analytics
- Personality Development
- Reflective Agent
- Personal Growth
- Co-evolution
- Shared History
- AI Activity Tracking
- Companion
- Growth Narrative

---

# 33. 最核心的产品原则

目前可以归纳为以下原则。

## 原则 1

**正常使用 AI，本身就是养宠物。**

不需要额外完成大量“宠物任务”。

---

## 原则 2

**成长不是 Token 消耗。**

真实经历、完成、学习、反思与变化更重要。

---

## 原则 3

**宠物不是用户的复制品。**

它受到用户影响，但保留自己的性格与价值。

---

## 原则 4

**观察与推断必须分开。**

深层人格解释永远只是 Hypothesis，直到用户校准。

---

## 原则 5

**理论是 Lens，不是真理。**

荣格、Big Five、ACT、SDT 等只作为不同解释框架。

---

## 原则 6

**不要“修复缺点”，而要理解优势的 Shadow Cost。**

很多问题来自能力过度使用。

---

## 原则 7

**成长 = 从 Rigid 到 Integrated。**

不是消灭一种倾向，而是获得更多选择。

---

## 原则 8

**用户自己定义“更好”。**

Shared Goals 必须来自用户，而不是系统。

---

## 原则 9

**宠物知道很多，但不需要一直说。**

好的 Companion 经常选择沉默。

---

## 原则 10

**陪伴优先于优化。**

不能把系统变成长期 KPI 教练。

---

## 原则 11

**原始会话不是长期资产，提炼后的模式与共同记忆才是。**

尽量避免永久保存全部 Raw Conversation。

---

## 原则 12

**同一只宠物跨设备存在。**

Windows 与手机不是两个独立角色。

---

# 34. 尚未解决、下一阶段需要继续讨论的问题

目前理念已经比较完整，但技术与交互层仍有几个关键问题未确定。

---

## 34.1 宠物究竟能读取哪些数据？

需要讨论：

- Hermes 全部事件？
- Hermes 会话文本？
- ChatGPT 网页内容？
- ChatGPT 会话标题？
- 浏览器使用行为？
- Git commit？
- IDE activity？
- Calendar？
- 睡眠 / 健康数据？
- Research workflow？
- Smart Search？
- Agentero？
- 文件内容？

必须定义：

> 最小必要数据集。

---

## 34.2 哪些数据必须本地处理？

尤其：

- 原始聊天；
- 私密文件；
- 用户画像；
- 心理发展假设。

可以考虑：

```text
Local-first analysis
+
Encrypted sync
+
Cloud only for derived state
```

---

## 34.3 多长时间形成一次人格 / 成长判断？

不应该每个会话立即修改人格。

可能需要：

- session level；
- daily aggregation；
- weekly pattern；
- monthly trend；
- quarterly development review。

---

## 34.4 什么样的证据才足以形成 Development Hypothesis？

需要设计：

- minimum evidence；
- cross-context evidence；
- time persistence；
- confidence；
- contradictory evidence；
- user validation。

---

## 34.5 哪些判断必须先问用户？

例如：

- 工作偏好可能不需要确认；
- 深层人格模式需要确认；
- 心理健康相关推断应避免或极度谨慎；
- 敏感属性不应推断。

---

## 34.6 宠物能有多大自主性？

需要继续确定：

- 是否能主动弹出；
- 是否能主动提出反思；
- 是否可以每天主动说话；
- 是否能拒绝继续催任务；
- 是否能产生自己的小目标；
- 是否允许“不同意用户”；
- 是否允许长期保持某些偏好。

---

## 34.7 宠物的“人格”是规则还是 LLM？

可能需要混合：

```text
Stable Trait State
+
Deterministic Rules
+
LLM Interpretation
+
Animation State Machine
```

---

## 34.8 成长机制如何避免游戏化反噬？

例如：

- 不鼓励刷 Token；
- 不鼓励无限工作；
- 不鼓励打卡焦虑；
- 不让用户为了宠物 XP 增加 AI 使用。

---

## 34.9 如何衡量“成长”而不重新制造新的优化主义？

这是产品哲学层的重要问题。

应该避免：

```text
Present Awareness 72/100
```

变成：

> “我必须把它刷到 90。”

所以某些成长维度可能应该：

- 模糊化；
- 趋势化；
- 叙事化；
- 不显示精确分数。

---

# 35. 下一轮最适合继续讨论的主题

在开始搜索现有项目之前，建议继续明确：

# A. 数据输入模型

宠物究竟能看到什么？

---

# B. 用户心智模型生成流程

从：

```text
event
↓
observation
↓
pattern
↓
hypothesis
↓
user calibration
↓
confirmed insight
↓
growth narrative
```

每一步如何发生？

---

# C. 主动性与打扰边界

宠物什么时候：

- 只做动作；
- 说一句话；
- 提醒；
- 提问；
- 进行反思；
- 发起 Challenge；
- 保持沉默。

---

# D. 记忆体系

需要区分：

- Event Memory
- Shared Memory
- User Insight
- Pet Memory
- Growth Chapter
- Relationship Memory

---

# E. 心理 / 人格理论的最终组合

目前初步倾向：

```text
Behavioral facts
      ↓
Big Five        → 稳定人格背景
Jungian Lens    → 认知与人格叙事
ACT             → 心理灵活性
SDT             → 动机质量
Adult Development
                → 心智框架变化
Narrative       → 长期成长故事
```

---

# 36. 一句话愿景

最终可以暂时用这句话概括：

> **它不是一个记录你用了多少 AI 的桌宠，而是一只陪你经历这些年、被你塑造、逐渐理解你，并在你需要的时候帮助你看见自己正在成为谁的数字伙伴。**

或者更简短地：

> **You shape it. It helps you shape yourself.**

中文：

> **你塑造它，它陪你塑造自己。**

---

# 37. 当前阶段结论

现在已经可以确认：

这个项目不应该仅仅搜索：

- AI Desktop Pet
- Desktop Companion
- Tamagotchi

未来真正需要寻找和组合的项目类型至少包括：

- 开源桌面宠物框架；
- 跨端宠物 / 虚拟角色系统；
- AI Companion；
- Long-term Memory Agent；
- Reflective Agent；
- Longitudinal User Modeling；
- Personal Analytics；
- Behavior Tracking；
- AI Activity Tracking；
- Personal Knowledge / Life Logging；
- Digital Twin；
- Personality / Adaptive Agent；
- Narrative Agent；
- Personal Growth / Coaching Agent。

因此未来很可能不是找到一个“完全符合需求”的单一项目，而是：

```text
成熟桌宠框架
      +
Hermes / ChatGPT 数据采集
      +
长期记忆系统
      +
用户成长模型
      +
LLM Reflection / Narrative
      +
跨端同步
      +
自定义成长与人格系统
```

组合成最终产品。

目前仍然处于：

> **先把“我们到底想做什么”定义清楚，再去搜索现有项目。**

这是正确顺序。

