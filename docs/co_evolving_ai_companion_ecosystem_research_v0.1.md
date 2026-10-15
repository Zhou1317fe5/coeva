# Co-evolving AI Companion：开源生态、框架与相关研究调研
## ——桌宠、AI Companion、长期记忆、用户建模、反思与介入研究的系统梳理

> 项目：Co-evolving AI Companion / 共生型 AI 成长伙伴  
> 文档主题：开源生态、框架、项目与相关研究调研  
> 版本：v0.1  
> 日期：2026-10-15  
> 状态：外部生态与研究调研阶段  
> 说明：本文基于当前阶段公开项目、开源仓库、论文与产品方向进行整理。本文的目标是识别“哪些部分已经有成熟底座、哪些值得借鉴、哪些仍然是我们的核心差异化问题”，而不是在此阶段提前确定最终技术路线。

---

# 1. 调研目标

经过前期六份需求与理论文档，我们已经较完整地定义了：

- 产品愿景；
- Hermes 行为与用户行为的归因边界；
- Companion 介入与沉默策略；
- Companion Data Model；
- 人格 / 心智发展模型；
- 宠物自身成长、Relationship、Growth Chapters 与产品边界。

因此这一轮调研的重点不再是：

> “有没有一个会动的 AI 桌宠？”

而是：

> **现有开源生态里，哪些组件已经足够成熟，可以复用；哪些项目已经接近我们的目标；哪些能力目前仍然缺失，需要我们自己设计。**

调研主要覆盖六条线：

1. 桌面宠物 / 数字角色底座；
2. Web / Desktop / Mobile 跨端能力；
3. AI Companion / Avatar / Voice；
4. 长期记忆与 Stateful Agent；
5. 长期用户建模与 Personalization；
6. Reflection / Narrative / Intervention / Long-term relationship 相关研究。

---

# 2. 总体结论

当前没有发现一个开源项目能够完整实现我们定义的：

# Co-evolving AI Companion

也就是：

> 一个跨桌面与手机长期存在、能够被用户经历塑造，同时通过长期人格 / 心智发展模型理解用户、帮助用户成长，并形成共同记忆、关系与成长章节的数字伙伴。

但是：

> **现有生态已经能够解决大量“身体、角色、语音、跨端、插件、长期记忆”等基础问题。**

因此真正需要重点自研的并不是：

- 桌宠窗口；
- Live2D / VRM 渲染；
- 普通长期记忆；
- 基础语音；
- 基础 Agent runtime。

我们的核心差异化更集中在：

- User / Agent Attribution；
- Longitudinal Development Model；
- Evidence-grounded User Understanding；
- State + Development Intervention Policy；
- Growth Narrative / Growth Chapters；
- Pet Co-evolution；
- Relationship Development；
- “什么时候保持沉默”。

---

# 3. 最重要的项目发现：Project AIRI

## 3.1 AIRI 的定位

Project AIRI 是当前调研中与我们整体愿景最接近的开源项目。

它并不只是一个普通 VTuber 或聊天角色，而是在朝：

> **可以存在于 Browser / Desktop / Mobile 的长期数字生命 / AI Companion**

方向发展。

官方当前已经覆盖或正在推进：

- Web；
- PWA；
- Desktop；
- Desktop Tamagotchi；
- Mobile / Pocket；
- Live2D；
- VRM；
- Voice；
- Character；
- Game / Agent；
- Application Awareness；
- Plugin SDK；
- 多设备事件 / 插件架构；
- Memory；
- Dreaming Agent；
- Personality Update；
- Time Awareness。

项目地址：

https://github.com/moeru-ai/airi

文档：

https://airi.moeru.ai/

---

# 4. AIRI 与我们的需求高度重叠

可以把当前匹配情况概括为：

| 我们的需求 | AIRI 当前状态 |
|---|---|
| Windows / Desktop Companion | 支持 |
| Web | 支持 |
| 手机使用 | PWA 可用，Pocket 原生移动端持续开发 |
| 同一个角色跨端存在 | 架构方向明显支持 |
| Live2D | 支持 |
| VRM | 支持 |
| 语音 | 支持 |
| Agent / AI 角色 | 支持 |
| Application Awareness | 已在发展 |
| Plugin SDK | 重点发展方向 |
| Remote Plugin | 架构支持方向 |
| 多设备事件系统 | 明确设计 |
| 长期记忆 | 发展中 |
| Memory consolidation | roadmap / proposal 中 |
| Dreaming agent | roadmap 中 |
| Personality evolution | 已有 proposal / roadmap 方向 |
| 用户人格 / 心智发展模型 | 未见完整实现 |
| Attribution model | 未见完整实现 |
| Growth Chapters | 未见完整实现 |
| 用户成长 Intervention | 未见完整实现 |
| Hermes integration | 无现成实现 |

因此：

> **AIRI 不是我们的完整成品，但极有可能成为当前最值得重点研究的“身体 / Companion Runtime / 跨端生态底座”。**

---

# 5. AIRI 最值得关注的不是 Live2D，而是 Plugin Architecture

AIRI 真正改变我们技术判断的部分不是角色渲染。

而是它正在建立一套：

> **Desktop / Web / Mobile / Remote Plugin 可共享的统一事件与插件架构。**

其设计方向包括：

- Plugin Host；
- Plugin SDK；
- Control plane；
- Data plane；
- 本地插件；
- Remote plugin；
- 多设备节点；
- 浏览器 / IDE / Mobile bridge；
- 外部上下文输入。

这意味着我们的未来信息来源：

```text
Hermes
ChatGPT
Browser
Desktop
Mobile
Future agents
```

理论上都可能作为：

> Companion Event Source

接入，而不一定需要把所有逻辑直接写入 AIRI Core。

AIRI Plugin Architecture：

https://github.com/moeru-ai/airi/blob/main/packages/plugin-sdk/docs/design/architecture.md

---

# 6. AIRI 的 Memory / Dreaming / Personality 路线与我们部分重合

AIRI 的 roadmap 与讨论中已经出现：

```text
Memory
↓
Long-term consolidation
↓
Dreaming
↓
Personality update
```

并且已有公开 proposal 探讨：

> accumulated memories 如何逐渐塑造 AIRI personality / identity。

这与我们此前定义的：

> 用户经历会真正塑造宠物

存在明显重合。

相关讨论：

https://github.com/moeru-ai/airi/issues/2005

这意味着未来如果基于 AIRI：

> 不应该重复造一个完全独立的 Pet Identity / Pet Memory 体系。

我们真正应该保留差异化的部分更可能是：

- User Development；
- Attribution；
- Growth Narrative；
- Evidence Ledger；
- Intervention Policy；
- Relationship / Co-evolution。

---

# 7. AIRI 当前仍然没有解决我们的核心问题

即使 AIRI 已经非常接近数字生命 / Companion，其核心方向仍然更偏：

> 一个有身体、有语音、有记忆、能进入现实数字环境的 AI 角色。

而我们的目标进一步要求：

> 这个数字生命如何长期理解“用户正在成为怎样的人”。

这是非常不同的一层。

目前尚未看到 AIRI 完整解决：

- 用户行为与 Agent 行为归因；
- 长期人格 / 心智发展；
- Psychological Flexibility；
- Development Themes；
- State Intervention 与 Development Intervention；
- Evidence-grounded Reflection；
- Growth Chapters；
- 用户成长与宠物成长共同映射；
- 深层反思何时必须沉默。

因此：

> **AIRI 可以覆盖“身体和角色生态”，但不能取代我们的 Growth Core。**

---

# 8. VPet-Simulator：最值得借鉴“宠物感”的项目

项目：

https://github.com/LorisYounger/VPet

VPet-Simulator 与 AIRI 的方向不同。

它不是 AI Companion 优先，而是一个真正成熟的：

> **桌面宠物模拟器。**

已有大量传统桌宠能力，例如：

- 桌面行走；
- 摸头；
- 提起；
- 爬墙；
- 工作；
- 进食；
- 动画；
- 道具；
- 状态；
- Mod；
- Steam Workshop。

它非常值得我们参考的一点是：

> **怎样让一个角色真的像“宠物”，而不是一个悬浮在桌面的 AI 头像。**

---

# 9. VPet 的价值与局限

## 优势

- 桌宠行为成熟；
- 宠物感强；
- 大量互动；
- 动画丰富；
- 插件 / Mod 生态；
- 可以研究桌面空间交互；
- WPF Core Library 可复用。

## 局限

- Windows / WPF 导向；
- 不以跨端 Companion 为核心；
- 没有现成长时 User Model；
- 没有跨 Mobile 的统一角色体系；
- 没有我们需要的长期 Growth Core。

因此：

> **VPet 更适合作为桌宠体验与交互行为设计参考，而不是整个项目的唯一底座。**

---

# 10. Open-LLM-VTuber：成熟的 AI Body / Voice / Avatar 技术参考

项目：

https://github.com/Open-LLM-VTuber/Open-LLM-VTuber

当前已覆盖大量成熟能力：

- Windows；
- macOS；
- Linux；
- Web；
- Electron；
- Desktop Pet mode；
- 透明窗口；
- Live2D；
- Voice；
- ASR；
- TTS；
- 语音打断；
- Vision；
- 多种 LLM；
- MCP；
- Agent interface；
- Chat history。

这说明：

> **“让 AI 角色拥有语音、Live2D 身体、桌面存在感”本身已经不是难题。**

---

# 11. Open-LLM-VTuber 为什么不是当前第一底座候选

它更擅长：

> AI Avatar / VTuber / Voice Companion。

而不是：

> 长期跨端人格发展 Companion。

另外长期记忆部分仍处于调整和演进状态。

因此当前更适合作为：

- Voice architecture 参考；
- Live2D body 参考；
- Agent integration 参考；
- 桌面透明窗口参考。

而不是整体产品的第一优先级基础。

此外其不同组件许可证需要单独审查，尤其如果未来考虑产品化。

---

# 12. YUI：规模不大，但设计思想非常值得借鉴

项目：

https://github.com/yw0nam/YUI

YUI 最大的价值不是代码规模，而是它的一个核心理念：

# Body ≠ Brain

桌面客户端主要负责：

- sensing；
- user activity；
- idle；
- current app；
- desktop events。

然后把“发生了什么”交给 Agent。

Agent 决定：

> 要不要回应。

甚至：

> silence 可以直接成为有效输出。

这和我们此前独立设计出来的：

```text
Understanding Engine
↓
Intervention Policy
↓
Expression
```

高度一致。

尤其对应：

> **Silence is a valid and often optimal action.**

---

# 13. YUI 对我们的直接启发

它支持了一个非常重要的架构思想：

> **身体层和心智层应该分离。**

也就是说：

```text
Desktop Pet Body
≠
User Development Model
≠
Intervention Policy
```

如果后续基于 AIRI 或其他项目，这仍然是非常重要的设计原则。

YUI 当前许可为非商业导向，因此更适合作为：

> 理念与架构参考。

---

# 14. Liqu Desktop Companion 等项目：证明角色层技术已成熟

例如：

https://github.com/CameronCodesStuff/liqu-companion

这类项目已经展示：

- Electron；
- transparent window；
- three.js；
- VRM；
- 角色移动；
- 鼠标响应；
- AI；
- Voice。

因此：

> 我们没有必要把大量精力花在重新证明“桌面上放一个 3D AI 角色能不能做”。

答案已经非常明确：

> 可以。

真正的问题已经转向：

> **这个角色有没有长期意义。**

---

# 15. VRM 与 Live2D

## VRM

VRM 是开放的 3D Avatar 标准。

`@pixiv/three-vrm` 是 Three.js 生态中成熟的 VRM 实现：

https://github.com/pixiv/three-vrm

优点：

- 开放；
- Web 生态成熟；
- 3D 角色；
- 更适合跨端；
- 许可相对清晰。

## Live2D

Live2D 在 2D 角色表现方面非常成熟。

AIRI 和 Open-LLM-VTuber 都已支持。

但 Live2D Cubism SDK / Core 有单独商业许可与发布规则。

未来如果产品允许：

- 用户导入模型；
- 第三方扩展模型；
- 大规模分发；

需要额外关注许可证要求。

因此当前更合适的结论是：

> 不要过早把产品绑死在单一 Avatar 技术。

AIRI 同时支持 Live2D + VRM 本身是优势。

---

# 16. 长期记忆：这个领域已经足够成熟

长期记忆相关项目中，本轮重点调研：

- Hindsight；
- Memobase；
- Letta；
- Graphiti；
- Mem0；
- MemoryBank。

总体结论：

> **我们不应该从零实现通用长期记忆。**

真正应该做的是：

> 选择合适的 memory substrate，并在其上建立我们自己的 Attribution / Development / Growth 层。

---

# 17. Hindsight：最值得保留的长期记忆候选之一

项目：

https://github.com/vectorize-io/hindsight

Hindsight 当前的核心方向是：

> Agent memory that learns.

典型能力：

- retain；
- recall；
- reflect；
- observation；
- higher-order observations；
- memory consolidation；
- temporal conflict handling；
- long-term retrieval。

它尤其适合保存：

- Shared Memories；
- Episodes；
- 用户明确表达；
- 过去的重要事件；
- Relationship history；
- Growth evidence；
- Pet history。

---

# 18. Hindsight 在我们系统里的正确定位

它不应该直接承担：

> “判断用户是什么人格”。

因为我们的核心规则是：

```text
Event
≠
Observation
≠
Pattern
≠
Hypothesis
≠
Confirmed Insight
```

而且：

> Agent 行为不能直接代表用户。

因此更合理的定位是：

# Hindsight = Memory Substrate

而：

# Development Model = Our Layer

也就是说：

> Hindsight 负责记忆和检索证据，我们负责判断哪些证据可以进入用户发展模型。

这一边界非常重要。

---

# 19. Hindsight 对我们还有现实优势

用户已经长期使用并优化 Hindsight。

这意味着未来如果验证该路线：

- 学习成本更低；
- 部署经验已有；
- 对 retain / recall / reflect 有实际认识；
- 已经有独立 memory server 使用经验。

因此它不仅理论匹配度高，验证成本也低。

---

# 20. Memobase：非常值得重点比较的 User Memory 项目

项目：

https://github.com/memodb-io/memobase

Memobase 与 Hindsight 最大区别在于，它明确强调：

> **Memory for User, not Agent.**

核心关注：

- structured user profiles；
- event timeline；
- time-aware memory；
- user profile extraction；
- profile evolution。

这与我们的：

- User Action；
- Self-report；
- Longitudinal Pattern；
- Development Model；

存在很明显的概念接近。

---

# 21. Hindsight 与 Memobase 的初步角色差异

可以暂时概括为：

```text
Hindsight
更接近：
What happened?
What should the agent remember?
What did we learn?

Memobase
更接近：
What is changing about this user?
What profile has emerged over time?
```

但：

> 这只是当前生态判断，不是最终技术选型结论。

尤其 Memobase 的默认 Profile 机制不能直接照搬。

因为我们的产品已经明确要求：

- 不允许未经验证的人格推断；
- 不允许过度画像；
- 敏感心理解释必须谨慎；
- 长期 Profile 必须允许用户超越旧模型。

---

# 22. Letta：更适合“宠物自己的持续心智”

项目：

https://github.com/letta-ai/letta

Letta / MemGPT 系列重点解决：

> persistent stateful agent

也就是：

- Agent 自己持续存在；
- Agent 自己维护 memory；
- 长期状态；
- Agent identity；
- autonomous behavior。

这更像：

> **宠物的脑。**

而不是：

> 用户成长模型。

如果未来系统需要一个长期自主 Pet Mind Runtime，Letta 可能有价值。

但当前并不能替代我们的 User Development Core。

---

# 23. Graphiti：时间化知识与“用户已经改变”问题高度相关

项目：

https://github.com/getzep/graphiti

Graphiti 是 temporal knowledge graph。

它擅长处理：

> 某个事实不是静态永恒的，而是会随时间发生变化。

例如：

```text
以前喜欢 X
↓
现在不喜欢 X
```

或者：

```text
以前很难停止任务
↓
现在已经能够经常暂停
```

这与我们的重要原则：

> **用户必须能够超越宠物过去的理解。**

高度一致。

因此 Graphiti 的价值可能在于：

> 保存变化历史。

但：

> 它不提供“变化对人生意味着什么”。

所以它依然只是：

> evidence / temporal substrate。

---

# 24. Mem0：通用记忆很强，但默认思想不完全适合我们

项目：

https://github.com/mem0ai/mem0

Mem0 是成熟的通用 Agent Memory 项目。

但其一些设计倾向于：

> 把 Agent-generated facts 也作为 memory facts 使用。

对普通 Agent 场景这没有问题。

但对我们的 User Development Model 会存在风险。

因为我们的硬规则是：

> **Agent autonomous behavior must never become direct evidence of user personality.**

因此：

> 通用 Memory benchmark 强，不代表适合直接做人类发展模型。

Mem0 更适合：

- 对比；
- 通用记忆候选；
- 参考 memory architecture。

而不是直接作为用户人格建模器。

---

# 25. MemoryBank：研究思想值得借鉴

论文 / 项目：

MemoryBank: Enhancing Large Language Models with Long-Term Memory

核心关注：

- long-term companion；
- memory forgetting；
- memory reinforcement；
- user personality adaptation；
- Ebbinghaus-style forgetting。

它最值得我们的地方是：

> **长期系统不应该永远保留所有原始记忆。**

这支持了我们之前已经独立形成的：

# Raw Data Should Decay

也就是：

```text
Raw events
↓
episodes
↓
patterns
↓
insights
↓
growth chapters
```

越往上越长期。

---

# 26. Generative Agents：Reflection Pipeline 的经典前身

论文：

Generative Agents: Interactive Simulacra of Human Behavior

经典结构：

```text
Observation
↓
Memory
↓
Reflection
↓
Planning
↓
Behavior
```

这与我们的：

```text
Event
↓
Observation
↓
Pattern
↓
Hypothesis
↓
Insight
↓
Growth Narrative
```

非常接近。

Generative Agents 的最大启发不是：

> 全部照搬。

而是：

> **Memory consolidation + reflection 本身是形成高阶理解的有效架构思想。**

不过它强调完整 experience stream。

这一点不适合我们。

我们已经明确：

> 本产品不是 life logging。

---

# 27. PersonaMem：与长期用户理解高度相关

PersonaMem 系列专门研究：

> 长期对话中，系统能否真正理解用户。

关注：

- static preferences；
- dynamic preferences；
- preference evolution；
- implicit signals；
- cross-session personalization。

研究指出：

> 即使当前 frontier LLM，在长时间用户理解上仍然存在明显不足。

这说明：

> “把历史聊天直接扔给 LLM”并不会自然产生可靠的人格理解。

这是对我们 Evidence / Pattern / Calibration 设计的支持。

---

# 28. PersonaMem-v2：隐式偏好仍然很难

PersonaMem-v2 更关注：

> 用户很多真实偏好并不会直接说出来。

例如：

不是：

> “我喜欢详细答案。”

而是长期行为表现出：

> 用户总是在需要时要求更完整证据。

这种 implicit preference / behavior inference 很难。

这说明：

> 长期 Companion 必须非常谨慎地区分观察与推断。

---

# 29. PersonaMem-v3：与我们的“克制式个性化”高度相关

PersonaMem-v3 进一步研究：

- dynamic preference；
- cross-platform personalization；
- forgetting；
- sensitive information；
- proactive behavior；
- over-personalization；
- 什么时候不应该 personalize。

这与我们的：

> Silence is a valid action.

以及：

> 用户必须能够超越旧画像。

高度一致。

因此未来：

> PersonaMem-v3 可能非常适合作为 User Model evaluation 的思想来源。

---

# 30. LongMemEval：适合测“记住没有”，但不适合测“理解对不对”

LongMemEval 主要测试：

- 长时信息提取；
- multi-session reasoning；
- temporal reasoning；
- knowledge update；
- abstention。

它适合验证：

> Companion 有没有记错过去。

但不能直接验证：

> Companion 的人格 / 心智发展理解是否合理。

因此未来需要区分：

```text
Memory accuracy
vs
User understanding quality
```

前者可以借鉴 LongMemEval。

后者需要：

- PersonaMem；
- 自定义 Development evaluation；
- 用户校准。

---

# 31. JITAI：介入时机已有成熟研究基础

Just-in-Time Adaptive Interventions（JITAI）是行为科学 / HCI 中已经发展多年的相关方向。

核心问题就是：

> **在什么时候、根据什么状态、以什么剂量进行干预。**

常见概念：

- decision points；
- tailoring variables；
- intervention options；
- decision rules；
- vulnerability；
- opportunity；
- receptivity。

这与我们之前独立定义的：

```text
Evidence Gate
Permission Gate
Timing Gate
```

非常接近。

---

# 32. JITAI 对我们最重要的启发

一个非常重要的研究结论是：

> 用户最需要帮助的时候，不一定是最适合接受帮助的时候。

例如：

用户处于：

- 高压；
- deadline；
- 高认知负荷；
- 快速 debug；

即使系统判断：

> “你现在已经进入典型高压模式。”

也不代表应该立刻弹出深度反思。

这直接支持我们的：

> **Timing Gate**

和：

> **高认知负荷时优先沉默。**

---

# 33. MindScape：少量行为上下文可以提升反思质量

MindScape 将：

- behavioral sensing；
- contextual information；
- LLM journaling；

结合起来。

用户尤其认可：

> contextual prompts

相比 generic prompts，它们更容易引发有意义的反思。

这支持我们一个非常重要的判断：

> Companion 不需要知道用户所有事情。

只要知道少量真正关键的：

- 时间；
- 状态；
- 最近行为；
- 当前上下文；

就可能比通用问句产生更好的反思。

---

# 34. MindScape 也提醒我们不要走向过度 sensing

MindScape 使用了较丰富的 behavioral sensing。

但我们的产品目标不同。

我们已经明确：

> 不是 Life Logging。

因此我们更应该借鉴：

> contextual reflection

而不是照搬：

> 全量感知。

---

# 35. AuthScribe：与 Evidence Ledger 高度契合

AuthScribe 是近期非常值得关注的工作。

其核心概念：

# Autobiographical Citations

也就是：

> 当 AI 提出一个关于用户的反思时，应该能够说明这个判断来自用户过去哪些经历或表达。

这几乎直接对应我们已经设计的：

# Evidence Ledger

例如：

宠物说：

> “我觉得你最近越来越能接受暂时没有答案。”

用户可以进一步查看：

> 为什么你这么认为？

然后看到：

- 过去某次明确自我表达；
- 几次跨情境行为；
- 某个之前确认过的 Insight。

---

# 36. AuthScribe 对 Growth Narrative 还有另一个重要启发

它强调：

> AI 不应该替用户直接定义自传意义。

而应该允许用户：

- 重新表达；
- 修正；
- 认领；
- 拒绝。

这与我们的：

> Growth Chapter 最好由用户共同参与命名。

高度一致。

因此：

> Growth Narrative 应该是 co-authored，而不是 AI-authored。

---

# 37. 长期 AI Companion 研究：关系确实会形成

已有 longitudinal research 显示：

> 用户对 AI Companion 的认知和关系感会随着几周使用发生明显变化。

这支持：

> Relationship / Bond 不只是游戏机制。

长期关系本身确实是：

- 信任；
- 使用体验；
- companionship；

的重要组成部分。

---

# 38. 但长期 Companion 也存在依赖风险

CHI 等近期 Companion 研究反复提醒：

可能出现：

- emotional validation；
- social rehearsal；
- companionship；

同时也可能出现：

- dependency；
- withdrawal；
- isolation；
- loneliness language 增加；
- privacy boundary violation；
- relationship transgression。

这强化了我们此前已经确定的：

> **Bond 的目标不是让用户越来越离不开宠物。**

而是：

> **越来越懂彼此。**

---

# 39. Relational Agent 研究支持“关系建设”本身有价值

更早期的 relational agent research 已经发现：

相比纯 task-oriented agent，加入 relationship-building 的 agent：

- 更被喜欢；
- 更被信任；
- 用户更愿意长期使用。

这说明：

> Relationship 不应该只被看作 UI 装饰。

它本身就是：

> 长期 Companion 体验的一部分。

---

# 40. 但我们的 Bond 方向与 Engagement Maximization 不同

我们的目标不是：

> 最大化用户打开次数。

而是：

> Mutual Calibration。

也就是：

- 宠物越来越知道怎样与用户相处；
- 用户越来越理解宠物；
- 双方形成共同语言；
- 边界越来越自然。

这是一种：

> 关系质量优化。

而不是：

> engagement 最大化。

---

# 41. 当前生态可以划分成五层

综合调研，可以把当前生态分成五个层次：

| 层 | 当前成熟项目 / 研究 | 我们是否需要自研 |
|---|---|---|
| Body / Desktop / Mobile | AIRI、VPet、Open-LLM-VTuber、YUI | 大量可复用 |
| Voice / Avatar / Presence | AIRI、Open-LLM-VTuber、VRM | 大量可复用 |
| Long-term Memory | Hindsight、Memobase、Letta、Graphiti、Mem0 | 不建议从零造 |
| User Development Model | PersonaMem + 心理学研究 | 核心自研 |
| Growth / Intervention / Narrative | JITAI、AuthScribe、Generative Agents、Reflection research | 核心自研 |

---

# 42. 真正属于我们核心创新的部分

经过调研，可以更清晰地看到：

> **我们的核心并不是“桌宠”。**

也不是：

> “给 AI 加一个长期 memory。”

真正有差异性的部分更像：

## 42.1 Attribution-aware longitudinal user understanding

能够区分：

- User action；
- Agent action；
- Context；
- Interaction pattern。

不把 Agent autonomous loop 错误解释成用户人格。

## 42.2 Developmental rather than static personalization

不是只知道：

- 用户喜欢猫；
- 用户喜欢简洁；
- 用户喜欢 Python。

而是理解：

> **用户正在发生什么变化。**

## 42.3 Co-evolving pet personality

不是用户有 Profile，宠物有固定 Persona。

而是：

> 用户变化也会塑造宠物。

## 42.4 Evidence-grounded reflection

宠物的深层反思必须：

- 有证据；
- 可追溯；
- 可被用户校准；
- 可被推翻。

## 42.5 Intervention restraint

最重要的能力之一不是：

> 会说什么。

而是：

> **知道什么时候不说。**

## 42.6 Growth Narrative

把真正发生的结构性变化：

> 组织成长期 Growth Chapter。

而不是把普通经历强行文学化。

---

# 43. 候选项目优先级

当前初步优先级如下。

| 优先级 | 项目 / 研究 | 主要原因 |
|---|---|---|
| S | Project AIRI | 与整体 Companion 外壳高度重合 |
| S | Hindsight | 成熟长期记忆，且已有实际使用经验 |
| S | Memobase | User Profile / Timeline 与 User Model 接近 |
| A | VPet | 最值得学习真正的“宠物感” |
| A | YUI | Body/Brain 分离与 silence 思想 |
| A | PersonaMem v2/v3 | 动态用户理解与过度 personalization |
| A | JITAI | Intervention Policy 学术基础 |
| A | Generative Agents | Reflection / consolidation 思路 |
| A | AuthScribe | Evidence provenance + user agency |
| B | Open-LLM-VTuber | Avatar / Voice / Agent integration |
| B | Letta | Stateful Pet Mind 候选 |
| B | Graphiti | Temporal user-history 候选 |
| B | MemoryBank | Forgetting / companion memory 思想 |
| C | Mem0 | 通用 memory，可比较但不能直接照搬 |

---

# 44. 当前最重要的方向变化

项目最开始的思路更接近：

```text
找一个桌宠框架
+
接 Hermes
+
自己做成长系统
```

经过调研后，更值得进一步验证的方向是：

```text
Existing Companion Body / Runtime
         ↓
       AIRI
         ↓
Desktop / Web / Mobile / Avatar / Plugin
         ↓
Independent Co-evolving Growth Core
         ↓
Attribution
User Model
Development Model
Intervention
Narrative
Relationship
Pet Evolution
         ↓
Existing Memory Substrate
         ↓
Hindsight / Memobase / etc.
         ↓
Hermes / ChatGPT / future sources
```

注意：

> 这是当前调研后的候选方向，不是最终技术方案。

---

# 45. 为什么不建议现在直接 fork AIRI 并塞入全部逻辑

AIRI 自己正在快速发展：

- Plugin system；
- Multi-device；
- Memory；
- Dreaming；
- Personality evolution。

如果把全部 Growth Core 强耦合进 AIRI：

可能造成：

- 上游升级困难；
- 与 AIRI 自己未来 memory / personality 重复；
- Companion Body 和 User Development Core 被绑死；
- 将来难以支持其他宠物身体。

更值得进一步验证的概念是：

> **Growth Core 独立，AIRI 是第一个 Body。**

例如未来理论上可以：

```text
Growth Core
├── AIRI body
├── VPet-like pet body
├── Mobile-only body
└── future avatar
```

但是否真的采用这一结构，仍需下一阶段源码 / 架构深度调研后决定。

---

# 46. AIRI 后续需要重点回答的问题

下一轮如果进行 AIRI 深度调研，应重点回答：

1. Desktop / Web / Pocket 的状态到底如何共享；
2. Plugin SDK 当前成熟度；
3. Remote Plugin 实际能力；
4. Application Awareness 能获取什么；
5. 多设备事件总线是否足够稳定；
6. Alaya / Memory 当前已经实现到什么程度；
7. Dreaming agent 是 roadmap 还是已有代码；
8. Personality update 是否已有可用机制；
9. 外部 Agent 能否作为 AIRI Brain；
10. Hermes 是否可以以插件 / remote service 方式接入；
11. AIRI 是否允许只作为 body / expression layer；
12. 长期二开维护成本；
13. 许可是否适合未来分发；
14. 移动 Pocket 当前成熟度；
15. 是否已有 user profile / relationship state。

---

# 47. Memory 方向下一步应重点比较

建议单独做一轮：

# Hindsight vs Memobase vs AIRI Memory / Alaya

重点不是 benchmark 谁分数最高。

而是比较：

- 谁适合 Shared Memory；
- 谁适合 User Profile；
- 谁适合 Pet Identity；
- 谁支持时间变化；
- 谁支持 forgetting / update；
- 谁容易实现 Evidence Ledger；
- 谁能避免 Agent/User attribution 混淆；
- 谁适合长期成长模型。

---

# 48. 研究层面对前六份需求文档的验证

一个很重要的结论是：

> 前期需求讨论整体方向没有明显走偏。

很多我们独立提出的原则，在外部研究中都能找到对应支持。

| 我们的设计 | 外部对应 |
|---|---|
| Memory → Reflection | Generative Agents |
| Raw memory decay | MemoryBank |
| Dynamic profile | PersonaMem |
| Preference evolution | PersonaMem-v2 |
| 旧画像必须更新 | PersonaMem-v2/v3 |
| Over-personalization 要克制 | PersonaMem-v3 |
| Intervention timing | JITAI |
| Timing Gate | JITAI receptivity |
| 少量 context 触发反思 | MindScape |
| Evidence Ledger | AuthScribe autobiographical citations |
| Growth Narrative 需要用户参与 | AuthScribe |
| Long-term relationship 会形成 | AI companion longitudinal studies |
| Relationship 有价值 | Relational Agent research |
| Bond 不能制造依赖 | CHI companion harm studies |
| Memory 可能塑造 Pet Personality | AIRI roadmap / proposals |

---

# 49. 当前真正有研究价值的组合

目前最有意思的不是某一个独立模块。

而是：

> **把原本分散在多个研究领域的思想组合起来。**

这些领域包括：

- Desktop Pet；
- AI Companion；
- Long-term Memory；
- Personalization；
- User Modeling；
- Psychological Flexibility；
- Reflection；
- JITAI；
- Narrative Identity；
- Relational Agent；
- Digital Pet。

现有研究通常只解决其中一部分。

我们的产品目标是在一个具象宠物里把这些部分组合成：

> **长期共生关系。**

---

# 50. 产品创新核心的重新定义

现在可以更准确地说：

我们不是要发明：

> 一个会动的 AI 桌宠。

也不是要发明：

> 一个有 memory 的 AI。

真正想做的是：

> **一个具有身体与长期记忆的数字伙伴，通过高质量行为归因和长期心智发展模型理解用户的变化，在适当时机进行有证据、可校准、低打扰的反思，并让用户成长同时塑造宠物自身。**

这才是整个项目真正独特的部分。

---

# 51. 当前阶段不应该马上进入实现

虽然现在已经出现 AIRI 等非常强的候选，但不建议立刻：

- fork；
- 写插件；
- 定数据库；
- 定协议；
- 选最终 Memory；
- 确定具体模型。

原因是：

> AIRI 与我们的目标重合度已经足够高，可能显著改变整体方案。

因此应该先完成：

> **AIRI 深度源码 / 架构 / roadmap 调研。**

---

# 52. 推荐的下一阶段顺序

## Step 1：AIRI 深度调研

重点：

- Architecture；
- Plugin；
- Mobile；
- Memory；
- Personality；
- External Agent；
- App awareness；
- State sync；
- License；
- Extensibility。

## Step 2：Memory / User Model 对比

重点比较：

- Hindsight；
- Memobase；
- AIRI Alaya；
- Letta；
- Graphiti。

## Step 3：确认 Growth Core 的独立性

回答：

> Growth Core 应该：

- 作为 AIRI extension？
- 作为独立 service？
- 作为通用 Companion Core？
- 还是直接融入某个 memory framework？

## Step 4：再回头修正需求文档

只有看到真实项目能力后，再判断：

- 哪些我们原本计划自研，但其实已有；
- 哪些项目设计与我们冲突；
- 哪些需求需要降低；
- 哪些创新点值得保留。

---

# 53. 当前阶段最终判断

本轮调研最重要的三个发现是：

## 发现一

**Project AIRI 已经足够接近我们的“身体 / Companion Runtime”，值得优先深挖。**

## 发现二

**长期 Memory 已经有大量成熟基础设施，不应该重复造。**

Hindsight、Memobase、Letta、Graphiti 等都能承担不同部分。

## 发现三

**我们的真正核心仍然没有现成项目完整实现。**

也就是：

```text
Attribution
+
Development
+
Intervention restraint
+
Evidence-grounded reflection
+
Growth Narrative
+
Co-evolving Pet
+
Relationship
```

这些仍然是整个产品最值得投入设计的部分。

---

# 54. 关键项目与研究入口

## 开源项目

- Project AIRI  
  https://github.com/moeru-ai/airi

- AIRI Documentation  
  https://airi.moeru.ai/

- AIRI Plugin Architecture  
  https://github.com/moeru-ai/airi/blob/main/packages/plugin-sdk/docs/design/architecture.md

- AIRI personality / memory proposal  
  https://github.com/moeru-ai/airi/issues/2005

- VPet-Simulator  
  https://github.com/LorisYounger/VPet

- Open-LLM-VTuber  
  https://github.com/Open-LLM-VTuber/Open-LLM-VTuber

- YUI  
  https://github.com/yw0nam/YUI

- Liqu Desktop Companion  
  https://github.com/CameronCodesStuff/liqu-companion

- three-vrm  
  https://github.com/pixiv/three-vrm

- Hindsight  
  https://github.com/vectorize-io/hindsight

- Memobase  
  https://github.com/memodb-io/memobase

- Letta  
  https://github.com/letta-ai/letta

- Graphiti  
  https://github.com/getzep/graphiti

- Mem0  
  https://github.com/mem0ai/mem0

## 重点研究方向

- Generative Agents
- MemoryBank
- PersonaMem / PersonaMem-v2 / PersonaMem-v3
- LongMemEval
- Just-in-Time Adaptive Interventions（JITAI）
- MindScape
- AuthScribe / autobiographical citations
- Longitudinal AI Companion studies
- Relational Agent research

---

# 55. 一句话总结

如果用一句话概括这轮调研：

> **现有开源生态已经基本能够给我们的 Companion 一个“身体”、一套“感官”和一部分“记忆”；真正还缺的，是一个能够长期理解用户如何变化、知道什么时候介入，并和用户一起成长的“心智”。**

或者：

> **The ecosystem already has bodies and memories. What is still missing is a developmental mind.**
