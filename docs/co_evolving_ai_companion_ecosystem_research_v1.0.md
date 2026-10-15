# 共生型 AI 成长伙伴：开源生态与相关研究最终调研报告
## ——基于两轮生态调研、项目核验与需求框架交叉分析后的收敛版

> 项目：Co-evolving AI Companion / 共生型 AI 成长伙伴  
> 文档版本：v1.0 Final Research Synthesis  
> 日期：2026-10-15  
> 状态：生态调研阶段收敛版  
> 适用阶段：进入源码级架构调研与候选路线对比之前  
>   
> 说明：本文整合此前的生态全景调研与后续补充调研，并对关键项目、Hermes 本地能力、长期记忆框架与相关研究进行了二次交叉核验。本文仍属于“调研结论与候选路线判断”，不提前固定数据库字段、算法、技术栈、最终系统架构或工程实施细节。

---

# 1. 调研背景

前期已经形成六份核心需求 / 理论文档，分别讨论：

1. 共生型 AI Companion 的产品愿景；
2. Hermes / Agent 行为与用户行为的归因边界；
3. 宠物何时介入、何时观察、何时保持沉默；
4. Companion Data Model；
5. 通用人格发展 / 心智发展维度；
6. 宠物自身成长、Relationship、Growth Chapters 与产品边界。

这些文档已经比较清楚地回答：

> **我们到底想做什么。**

因此当前调研不再围绕：

> “有没有一个现成 AI 桌宠？”

而是围绕：

> **哪些开源项目已经解决身体、跨端、记忆、用户模型、插件与关系层问题；哪些可以复用；哪些只能借鉴；哪些真正属于我们的核心创新。**

---

# 2. 最终总判断

经过两轮调研与交叉核验，目前可以比较明确地得出：

> **没有任何一个现成开源项目完整实现我们定义的“共生型 AI 成长伙伴”。**

但另一方面：

> **身体、桌面驻留、动画、跨端、插件、语音、长期记忆、用户画像等基础能力已经有大量成熟或快速发展的开源方案。**

因此真正值得投入自研的，不是：

- 透明桌宠窗口；
- Live2D / VRM 渲染；
- 普通长期记忆；
- 普通聊天机器人；
- 基础向量检索；
- 单纯 User Preference Profile。

而是：

```text
Attribution-aware User Understanding
+
Longitudinal Development Model
+
State / Development Intervention Policy
+
Evidence-grounded Reflection
+
Growth Narrative / Growth Chapters
+
Pet Co-evolution
+
Relationship Development
+
Silence / Restraint
```

这组能力仍然没有看到哪个开源 Companion 项目完整实现。

---

# 3. 最重要的宏观结论：Body ≠ Brain ≠ Memory

整个生态最值得保留的架构认知是：

```text
Body
桌面 / Web / Mobile / Avatar / 动画

≠

Memory
事件 / 经历 / 长程上下文 / 检索

≠

Developmental Mind
用户发展理解 / 归因 / 介入 / 叙事 / 共演化
```

现有生态已经能够较好地提供：

- Body；
- Presence；
- Voice；
- Agent Runtime；
- Memory。

真正稀缺的是：

> **Developmental Mind。**

这与前六份需求文档的方向完全一致。

---

# 4. 第一项关键修正：Hermes 原生 Pet 比最初认为的成熟很多

后续核验发现，Hermes Agent 当前已经拥有一套明显成熟于早期认知的 Petdex 宠物系统。

官方代码与文档确认：

- Hermes 原生支持 Petdex；
- CLI / TUI / Desktop 使用统一宠物状态；
- 宠物会响应 Agent activity；
- 支持状态包括：
  - `idle`
  - `review`
  - `run`
  - `wave`
  - `jump`
  - `failed`
  - `waiting`（新 sheet 支持，旧 sheet 可 fallback）
- 支持 Petdex gallery；
- 支持 `/pet`；
- 支持 `/hatch` 直接 AI 生成新宠物；
- Desktop 中支持 roaming；
- 支持透明弹出的 always-on-top Pet overlay；
- overlay 可拖动并记忆位置；
- overlay 已有 speech bubble；
- single-click 可打开 mini composer，直接向最近 Hermes Session 发送 prompt；
- Hermes Desktop 已经存在独立 Pet Bubble / Pet Overlay 相关模块。

因此过去那种：

> “Hermes Pet 主要还是 TUI / App 内展示，如要独立桌面宠物需自己额外写 GUI 壳”

的判断已经过时。

更准确的结论是：

> **如果第一阶段明确以 Hermes 为主，Hermes 原生 Pet 本身已经是一个非常强的 MVP Body 候选。**

---

# 5. Hermes 原生 Pet 的价值

它有几个特殊优势：

## 5.1 状态来源天然正确

Hermes 自己已经知道：

- 正在 thinking；
- 正在 tool run；
- turn finished；
- failed；
- waiting user；
- plan completed。

因此：

> 不需要外部系统重新猜测 Hermes 当前处于什么状态。

---

## 5.2 不需要重新解决 Petdex

Hermes 已经：

- 读取 Petdex；
- 管理宠物资产；
- 解析标准精灵图；
- 统一状态映射；
- 支持生成新宠物。

因此如果第一版主要服务 Hermes：

> 重写一个 Petdex Runtime 的价值明显下降。

---

## 5.3 已经有独立桌面 Overlay

Hermes Desktop 当前已经支持：

> Pet 从主 App 中 pop-out 成透明、always-on-top 的独立桌面窗口。

并且：

- 可移动；
- 可持久化位置；
- 有 bubble；
- 有 composer；
- 可恢复主 App。

这已经非常接近我们早期设想的：

> “桌面上有一只会动的小宠物，并可以进行极轻量交互。”

---

# 6. Hermes Plugin / Hook 能力也比早期认知更成熟

进一步核验确认，Hermes 已经存在多种扩展面：

- General Plugin；
- Plugin Hooks；
- Shell Hooks；
- Gateway Hooks；
- Outbound Webhooks；
- Desktop Plugin SDK；
- Dashboard extensions。

可监听生命周期事件包括：

- `pre_tool_call`
- `post_tool_call`
- `pre_llm_call`
- `post_llm_call`
- `on_session_start`
- `on_session_end`
- `on_session_finalize`
- `subagent_stop`
- 以及 Gateway 的：
  - `agent:start`
  - `agent:step`
  - `agent:end`

Desktop Plugin SDK 甚至已经暴露：

> `ctx.pet.say(...)`

允许插件直接往原生 Pet Bubble 中显示短消息。

因此：

> **Hermes-first 版本并不需要通过修改 Hermes Core 才能获得状态与宠物交互。**

这显著改变了第一阶段候选路径的复杂度判断。

---

# 7. 第二项关键修正：state.db 不应作为首选实时事件总线

补充报告提出：

> 只读监听 `%LOCALAPPDATA%\hermes\state.db` / WAL，实时获取 Hermes 状态。

经过进一步核验：

Hermes 确实使用：

> `state.db`

作为 canonical session store。

并且：

- Windows 默认位于 `%LOCALAPPDATA%\hermes\state.db`；
- Linux / macOS 默认位于 `~/.hermes/state.db`；
- Profile 拥有独立 state.db；
- SQLite 使用 WAL 模式；
- 其中包含 session metadata、messages、tool calls 等信息。

所以：

> **state.db 是一个真实、重要的数据源。**

但不建议把：

> “实时监听 state.db / WAL”

直接定为正式主事件桥。

---

# 8. 为什么 state.db 更适合“历史证据源”，而不是唯一实时事件源

Hermes 官方已经存在：

- lifecycle hooks；
- plugin hooks；
- shell hooks；
- outbound webhook；
- Gateway events。

这些机制天然表达：

> “某个事件刚刚发生。”

而 state.db 主要解决：

> “发生过什么，并将其持久化下来。”

此外 Hermes 的 WAL 并发与多进程读写本身有明确的恢复、防冲突与锁保护逻辑。

因此更稳妥的调研结论是：

```text
实时事件 / 状态
优先：
Hermes Hook / Plugin / Event

历史证据 / 会话回溯
可以：
Read-only state.db
```

而不是：

```text
所有实时状态
都从 WAL 推断
```

这也更符合我们的 Attribution 原则：

> 事件应该尽量从最接近原始语义的位置获得。

---

# 9. OpenPet 已确认存在，并且确实是高质量轻量候选

项目：

https://github.com/X-T-E-R/OpenPet

经过核验，OpenPet 当前确实提供：

- Tauri；
- TypeScript / Rust；
- 透明无边框；
- always-on-top；
- 可拖动；
- Tray；
- Pet import；
- Windows 主开发平台；
- macOS / Linux CI build；
- 本地 HTTP API；
- CLI；
- MCP；
- Agent event control；
- Companion event：
  - `thinking`
  - `tool-running`
  - `reviewing`
  - `success`
  - `failure`
  - `attention`

License：

> GPL-3.0-or-later

因此补充报告中：

> “OpenPet 是一个极轻量、Agent-friendly 的本地桌宠 Runtime”

这个判断基本成立。

---

# 10. OpenPet 的正确定位

OpenPet 最大优势不是：

> 比 Hermes Pet 更强。

而是：

> **它天然与具体 Agent 解耦。**

如果未来希望：

```text
Hermes
Codex
Pi
Claude Code
其他 Agent
        ↓
同一个桌宠 Body
```

那么 OpenPet 的：

- HTTP；
- CLI；
- MCP；
- Agent event API；

非常有价值。

所以：

### Hermes Native Pet

适合：

> **Hermes-first MVP。**

### OpenPet

适合：

> **Agent-agnostic Desktop Body。**

这两个方向不应该简单互相淘汰。

---

# 11. openclaw-tamagotchi 已确认存在

项目：

https://github.com/katolikov/openclaw-tamagotchi

当前特征：

- Python 3.11+；
- PySide6；
- frameless desktop pet；
- sprite-sheet animation；
- speech bubble；
- pet YAML；
- asset importer；
- Windows / Linux / macOS；
- 结构较小；
- 项目仍较新。

它最大的价值是：

> **简单、透明、容易修改。**

因此它特别适合：

- 快速验证桌宠行为；
- 快速加自定义输入；
- 快速实验动作和 Bubble；
- Python 环境下快速修改。

---

# 12. 但 openclaw-tamagotchi 更适合“实验底座”而不是长期战略底座

相对 AIRI、Hermes、VPet：

它的：

- 社区规模；
- 长期稳定性；
- 插件生态；
- 跨端能力；

都还很弱。

因此更准确的定位是：

> **优秀的轻量实验体。**

而不是：

> 目前可以直接押注几年的平台。

---

# 13. Project AIRI：长期跨端 Companion 最强候选仍然成立

项目：

https://github.com/moeru-ai/airi

AIRI 当前已明确覆盖：

- Web；
- Desktop；
- Mobile Pocket；
- Electron Tamagotchi；
- Live2D；
- VRM；
- Spine；
- MMD；
- Voice；
- Computer Use；
- Application awareness；
- Plugin；
- Remote Plugin；
- Multi-device orchestration；
- Stage Pocket；
- Avatar / Character runtime。

其 Plugin Platform 明确提出：

> Desktop / Web / Mobile 使用统一插件 API，支持 local / remote plugin，并通过 control plane 与 data plane 处理多设备能力。

这一点仍然是所有当前候选中最接近：

> **长期跨设备 Companion Runtime**

的方案。

---

# 14. AIRI 的 Mobile / Cross-device 路线是真实存在的

当前源码结构已经明确存在：

```text
apps/stage-web
apps/stage-tamagotchi
apps/stage-pocket
```

Pocket 使用：

- Capacitor；
- Kotlin；
- Swift。

因此：

> “未来同一个 Companion 在 Desktop + Web + Mobile 存在”

并不是纯 roadmap 想象，而是已经进入代码结构的方向。

---

# 15. AIRI 的 Memory / Personality 方向也确实存在

AIRI roadmap 与 issue 中明确存在：

- Alaya memory layer；
- Dreaming agent；
- memory management；
- long-term consolidation；
- personality update；
- time awareness。

并且已有 proposal：

> memory accumulated over time → personality / identity changes.

因此：

> AIRI 本身也在向“记忆塑造角色人格”的方向前进。

这与我们的：

> Pet Co-evolution

部分重叠。

---

# 16. AIRI 与我们的差异仍然非常明确

AIRI 当前的核心愿景更偏：

> 数字生命 / Cyber Companion / Waifu / VTuber / embodied agent。

我们的核心则是：

> **用户长期人格 / 心智发展的理解与双向共演化。**

当前没有看到 AIRI 已经完整具备：

- User / Agent Attribution；
- Psychological Development Model；
- Evidence Ledger；
- User Calibration；
- State / Development Intervention；
- Growth Narrative；
- Growth Chapters；
- 用户变化与 Pet 变化之间的稳定映射。

因此：

> **AIRI 仍然不能替代 Growth Core。**

---

# 17. AIRI 的“重载”问题应该如何理解

补充报告提出：

> AIRI 对第一版 MVP 可能太重，而且容易把精力带到二次元 / Live2D 视觉细节。

这个判断有合理性，但需要更准确地表达。

AIRI 的问题不是：

> “它不能做我们的项目。”

而是：

> **它解决的问题比第一阶段要多得多。**

对于只想先验证：

```text
Hermes activity
↓
pet reaction
↓
simple feeding
↓
initial memory / reflection
```

AIRI 的：

- Monorepo；
- Multi-device；
- Voice；
- Avatar；
- Plugin platform；
- Computer Use；

可能带来不必要的认知与维护负担。

所以更准确的结论：

> **AIRI 是终局级 / 中长期 Body Runtime 高优先级候选，但未必是 Hermes-first MVP 的最小路径。**

---

# 18. 因此 Body 方向不应是一条路线，而应分成三档

## 18.1 Hermes Native Pet

适合：

> Hermes-first 最小验证。

特点：

- 已经安装；
- 已经知道 Hermes 状态；
- 已经有 overlay；
- 已经有 mini composer；
- 已经有 bubble；
- 已经有 roaming；
- 已经有 Petdex；
- 可以通过 Hermes plugin / desktop plugin 扩展。

---

## 18.2 OpenPet / openclaw-tamagotchi

适合：

> 独立桌宠 Body 或快速实验。

其中：

### OpenPet

更适合：

> Agent-agnostic、长期作为独立 Body。

### openclaw-tamagotchi

更适合：

> 低成本 Python 快速实验。

---

## 18.3 AIRI

适合：

> 中长期跨端、Avatar、Mobile、Plugin ecosystem。

因此并不是：

```text
AIRI vs OpenPet
```

而更像：

```text
Hermes Native
→ 最快验证

OpenPet
→ 独立轻量 Body

AIRI
→ 长期跨端 Companion Runtime
```

---

# 19. VPet 仍然值得保留，但主要用于学习“宠物感”

项目：

https://github.com/LorisYounger/VPet

VPet 仍然是：

> 桌宠体验设计的重要参考。

最值得学习：

- 宠物在桌面的空间行为；
- 自主移动；
- 拖拽；
- 动画丰富度；
- 非语言存在感；
- 游戏化宠物互动。

但：

- Windows / WPF；
- 游戏养成逻辑较重；
- 不以 AI Companion 为中心；
- 不提供我们的长期心智系统。

所以更适合：

> **体验参考，而非 Growth Core 基础。**

---

# 20. Open-LLM-VTuber 继续作为 Voice / Avatar 参考

它仍然适合用于学习：

- Voice pipeline；
- Live2D；
- Web / Desktop；
- AI Avatar；
- Agent interface；
- MCP；
- 语音打断。

但当前没有足够理由把它提升为整体第一底座。

---

# 21. 记忆 / 用户建模方向：补充调研发现非常有价值

第二轮调研补充了几个此前遗漏的重要项目：

1. build-your-users-mind
2. O-Mem
3. FERNme
4. Syke

这四个项目对我们的影响非常大。

---

# 22. build-your-users-mind：与 Attribution / Evidence Ledger 高度契合

项目：

https://github.com/ellmos-ai/build-your-users-mind

它不是：

> 一个通用 AI Memory Server。

而是一个：

> **从用户授权的 Agent 交互日志中建立可检查、可修正的 User Decision / Preference Model 的方法与工具集。**

核心思想包括：

- local-first；
- 从 Claude / Codex / Gemini 等日志提取；
- 只提取用户真正表达 / 决定的内容；
- hypothesis with citation；
- 不声称“读心”；
- 不允许心理诊断；
- 不允许 covert profiling；
- 高风险行动仍需确认；
- 对预测结果进行后续反馈验证。

这些思想与我们的：

- Attribution；
- Evidence Ledger；
- User Calibration；
- “Hypothesis 不是事实”；
- “不做心理诊断”；

几乎完全一致。

---

# 23. build-your-users-mind 最适合借鉴什么

它最值得直接研究的不是：

> 最终 Memory Database。

而是：

> **证据纪律。**

尤其：

```text
User explicit decision
↓
Evidence-backed hypothesis
↓
Prediction
↓
Real feedback
↓
Correction
```

这是我们 Development Hypothesis 非常需要的一种验证思想。

因此其定位更适合：

> **Attribution / Calibration methodological reference。**

---

# 24. O-Mem：Active User Modeling 的强参考

项目：

https://github.com/OPPO-PersonalAI/O-Mem

论文：

> O-Mem: Omni Memory System for Personalized, Long Horizon, Self-Evolving Agents

核心思想：

> Memory 不应该只是 passive storage / retrieval，而应该主动维护用户模型。

其层次包括：

- User Persona Attributes；
- Event Records；
- Topic-indexed Messages。

这与我们的：

```text
Long-term understanding
↓
Events
↓
User model
↓
Context grounding
```

高度契合。

---

# 25. O-Mem 与 Growth Chapters 不能直接画等号

补充报告将 O-Mem 三层与我们的：

> 事实模式 → 发展假设 → 人生章节

直接对应。

这一点需要修正。

O-Mem 更准确的结构是：

```text
Persona
Event
Message
```

它解决的是：

> Personalization / Long-horizon User Modeling。

而不是直接解决：

> Developmental Hypothesis / Growth Chapter。

所以：

> **O-Mem 是 User Model / Memory 分层参考，不是 Growth Narrative 的现成实现。**

Growth Chapters 仍然需要我们自己的 Development Layer。

---

# 26. FERNme：极值得关注的“用户模型而非聊天记录”路线

项目：

https://github.com/mirkofr/FERNme

FERNme 的理念非常接近我们的 Data Model：

> **models the user, not the transcript**

特点：

- Local / user-owned；
- deterministic core；
- zero-LLM write core；
- optional LLM enrichment；
- fuzzy graph；
- Hebbian update；
- decay；
- user-editable；
- user-deletable；
- bounded prompt card；
- token cost 基本保持平坦；
- outcome feedback loop；
- 不主张隐藏式 profiling。

这与我们的：

- Raw data decay；
- Long-term model should become smaller；
- 用户可以修正模型；
- Profile 不应该无限膨胀；

非常一致。

---

# 27. FERNme 不应被理解成“零 LLM 就能解决人格发展”

它解决的是：

> 用户偏好、习惯、风格、约束等个性化记忆。

而我们真正要解决：

> Development Hypothesis / Narrative / Psychological Flexibility。

这仍然需要高层推理与用户共同校准。

所以 FERNme 更适合：

> **bounded personalization memory 参考。**

不是：

> 完整 Development Engine。

---

# 28. Syke：这一轮调研中非常值得新增的强候选

项目：

https://github.com/saxenauts/syke

Syke 是：

> 一个 local ambient memory agent。

支持读取：

- Claude Code；
- Codex；
- OpenCode；
- Cursor；
- GitHub Copilot；
- Antigravity；
- Hermes；
- Gemini CLI。

这对我们非常值得注意。

因为它不是：

> 单一 Agent Memory。

而是：

> **跨多个 Agent Harness 形成用户自己的长期记忆空间。**

---

# 29. Syke 的几条原则与我们高度一致

其官方架构明确提出：

### Evidence ≠ Inference

原始 harness 数据：

> 留在数据源。

Memory：

> 是基于证据形成的可变推断。

这和我们的 Attribution Layer 高度一致。

---

### Memory is identity, not retrieval

Syke 认为：

> Memory 不是“搜索以前说过什么”，而是逐步形成用户的 computational identity。

这与我们的长期 Companion 理念非常接近。

---

### SQLite + FTS5

Syke 当前明确使用：

- `syke.db`
- SQLite
- FTS5
- sparse graph links
- MEMEX.md

并明确解释为什么：

> 不需要独立 Graph Database。

---

# 30. 对补充报告中 Syke / Persona 描述的修正

旧 `saxenauts/persona` 本身曾采用：

- Neo4j；
- graph-vector；
- HNSW。

但项目已经继续演化为：

> Syke。

Syke 当前架构确实已经转向：

- local SQLite；
- FTS5；
- sparse graph over SQLite；
- agent synthesis；
- MEMEX；
- direct harness reading。

因此：

> “Persona 最终证明 SQLite + FTS5 一定比任何图数据库都准”

这种表达过强。

更准确的是：

> **Syke 团队当前的架构判断是：对于它自己的稀疏、agent-maintained memory workload，SQLite + FTS5 + sparse links 已经足够，而且比独立图数据库更符合可移植性和复杂度目标。**

这是重要工程参考，但不能当成通用定理。

---

# 31. Hindsight 的定位仍然成立

Hindsight 依然是高优先级候选。

它更适合：

- Episode；
- Reflection；
- Shared Memory；
- Higher-order observation；
- Long-term recall；
- Consolidation。

而我们的 Growth Core 仍然应该位于它之上。

特别要坚持：

> Hindsight 中存了什么，不代表这些东西自动有资格成为 User Personality Evidence。

---

# 32. Attribution Filter 必须位于任何 Memory 系统之前或之上

无论最终使用：

- Hindsight；
- O-Mem；
- FERNme；
- Syke；
- Memobase；
- Graphiti；

都不能跳过：

```text
Actor Attribution
↓
Context
↓
User Evidence
↓
Pattern
↓
Hypothesis
```

不能：

```text
Raw Hermes history
↓
Memory system
↓
User personality
```

因为：

> Agent autonomous behavior 仍然不是 User behavior。

这一点属于整个项目最重要的系统 invariant。

---

# 33. Memobase 仍然值得保留在对比名单

Memobase 的：

> User Profile + Event Timeline

仍然和我们非常相关。

它适合比较：

- structured user profile；
- profile evolution；
- time-aware user memory；
- event timeline。

但默认 Profile Schema 同样不能直接照搬为我们的心理发展模型。

---

# 34. Graphiti 仍然适合处理“用户已经改变”

Graphiti 的 temporal knowledge graph 能够很好表达：

```text
以前
↓
现在
```

这非常适合：

> 旧画像不应该永久绑定用户。

因此它仍然是：

> Temporal Evidence / Change History

方向的重要候选。

---

# 35. Letta 更像 Pet Mind，而不是 User Development Model

Letta / MemGPT 的优势仍然在：

> Stateful Agent。

因此更适合：

- Pet identity；
- Agent state；
- autonomous companion mind。

而不是直接承担：

> 用户人格发展。

---

# 36. Memory 项目的最终分类

经过补充调研后，更适合按“用途”而不是“排行榜”来看。

## A. Episode / Reflective Memory

代表：

- Hindsight

解决：

> 我们经历过什么？

---

## B. User Profile / Personalization Memory

代表：

- Memobase
- O-Mem
- FERNme

解决：

> 用户有哪些逐渐稳定或变化中的偏好、习惯、特征？

---

## C. Ambient Cross-Harness Memory

代表：

- Syke

解决：

> 用户跨多个 Agent / Harness 的工作上下文如何长期沉淀？

---

## D. Temporal Relation / Change History

代表：

- Graphiti

解决：

> 一个事实什么时候成立、什么时候已经改变？

---

## E. Stateful Agent Mind

代表：

- Letta

解决：

> Agent / Pet 自己如何长期保持状态与身份？

---

## F. Attribution / User Model Methodology

代表：

- build-your-users-mind

解决：

> 什么才有资格成为对用户的推断？推断怎样带证据、怎样被反馈修正？

---

# 37. 这说明没有必要寻找一个“万能 Memory”

我们的产品天然包含多个不同问题：

```text
Shared Experience Memory
User Development Evidence
User Profile
Pet Identity
Relationship History
Growth Narrative
```

这些未必应该全部由同一个系统承担。

所以后续比较的重点不应该是：

> “Hindsight、O-Mem、Syke 谁最好？”

而应该是：

> **哪个系统最适合哪一种记忆职责，以及哪些职责根本不应该交给通用 Memory 框架。**

---

# 38. 学术研究部分的原判断仍然成立

此前调研中的以下研究线仍然非常重要：

- Generative Agents；
- PersonaMem；
- PersonaMem-v2 / v3；
- LongMemEval；
- JITAI；
- MindScape；
- AuthScribe；
- Relational Agents；
- Longitudinal AI Companion studies。

这些研究共同支持了我们很多前期设计。

---

# 39. Generative Agents 对应 Reflection Pipeline

其：

```text
Observation
↓
Memory
↓
Reflection
↓
Planning
```

仍然是：

> 从经验形成高层理解

的重要参考。

但我们不继承：

> 全量 experience stream。

---

# 40. PersonaMem 对应动态用户理解

它证明：

- 用户偏好会变化；
- 隐式偏好难以提取；
- 长期历史不是简单 stuffing；
- personalization 很容易过度。

这支持：

> User Model 必须独立、有证据、允许更新。

---

# 41. JITAI 对应 Intervention Policy

它仍然是：

> “什么时候介入”

最值得借鉴的研究方向。

尤其：

> Need ≠ Receptivity。

用户最需要帮助的时刻：

> 不一定适合被打扰。

这支持：

- Timing Gate；
- Cooldown；
- high cognitive load → silence。

---

# 42. AuthScribe 对应 Evidence Ledger

深层反思最好具有：

> autobiographical provenance。

也就是用户可以知道：

> 你为什么这么认为？

并看到：

- 自己过去的表达；
- 过去的选择；
- 已经确认的 insight。

这非常适合我们的 Companion。

---

# 43. Long-term Companion 研究继续支持“关系要有，但不能制造依赖”

已有 longitudinal / HCI 研究表明：

- AI Companion 关系会形成；
- Relationship 会影响信任与持续使用；
- 但可能产生 dependency、withdrawal、privacy boundary 风险。

因此我们的：

> Bond = Mutual Calibration

而不是：

> Engagement Maximization

仍然是正确方向。

---

# 44. 经过二次调研后的 Body 候选优先级

这里不做单一排行榜，而是按用途排序。

| 候选 | 最适合的角色 | 当前判断 |
|---|---|---|
| **Hermes Native Pet** | Hermes-first MVP | **最短路径** |
| **OpenPet** | Agent-agnostic lightweight desktop body | **高优先级** |
| **openclaw-tamagotchi** | Python 快速实验 | **实验优先** |
| **AIRI** | 长期跨端 Companion Runtime | **长期最高优先级** |
| **VPet** | 宠物感 / 动画 / 空间交互参考 | 体验参考 |
| Open-LLM-VTuber | Voice / Avatar / Live2D 参考 | 技术参考 |
| YUI | Body-Brain separation / Silence 参考 | 架构参考 |

---

# 45. 最重要的 Body 路线变化

原先比较像：

```text
选一个桌宠框架
↓
以后一直使用
```

现在更合理的认识是：

```text
Growth Core
      │
      ├─ Hermes Native Pet
      ├─ OpenPet
      └─ AIRI
```

也就是说：

> **Body 可以被替换，而 Growth Core 不应该依赖某一个具体 Body。**

这是二次调研后非常重要的结构性结论。

---

# 46. “敏捷 MVP vs 长期终局”的双轨思想值得保留

补充报告提出的：

> Bimodal Strategy

非常有价值。

但最终版不把它写成已经确定的技术实施方案，而是写成：

> **候选产品验证战略。**

---

# 47. Track A：Hermes-first Minimal Validation

目标不是：

> 建成最终产品。

而是验证：

```text
Agent activity
↓
Pet presence
↓
User feeding / interaction
↓
Memory
↓
Reflection
↓
Early relationship value
```

这一阶段最有优势的候选：

- Hermes Native Pet；
- Hermes Hook / Plugin；
- 或 OpenPet 作为独立 Body。

重点应该验证：

> 用户到底会不会因为“宠物理解自己的经历”而产生长期使用价值。

不是：

> Avatar 做得多精美。

---

# 48. Track B：Long-term Cross-device Companion

当核心价值被验证以后，再重点考虑：

- AIRI；
- Stage Pocket；
- Web / Desktop / Mobile；
- Avatar / Home；
- Cross-device state；
- 更丰富的 Pet Co-evolution；
- ChatGPT / Browser / IDE 等多来源。

AIRI 在这个阶段依然是目前最值得深挖的候选。

---

# 49. 为什么两个 Track 可以共享同一个核心

因为真正需要长期保留的不是：

> GUI 代码。

而是：

```text
Attribution Rules
Development Model
Evidence Ledger
User Calibration
Intervention Policy
Relationship Model
Growth Narrative
Pet Evolution State
```

只要这些保持独立：

> 早期使用 Hermes Native Pet，未来迁移 AIRI 并不会推翻核心产品逻辑。

---

# 50. “随手投喂切片”仍然是值得保留的产品想法

补充报告中的：

> 随手投喂 Slice

非常符合我们的产品理念。

因为自动观察永远有盲区。

用户应该拥有一种非常低摩擦的方式主动告诉宠物：

- 今天发生了什么；
- 我突然意识到了什么；
- 这件事很重要；
- 这个细节值得记住；
- 我对刚才那件事的真实感受是什么。

这可以弥补：

> 自动 telemetry 对“意义”的捕捉不足。

---

# 51. 但 Slice 不应该被理解成“额外记日志任务”

设计原则应该是：

> **可投喂，但不要求投喂。**

否则产品会退化成：

> 另一个 journaling / quantified-self 工具。

Slice 的价值是：

> 用户主动补充“机器看不到的意义”。

---

# 52. Mobile 方向也需要从两阶段看

补充报告提出：

> Markdown + WebDAV / S3 作为第一阶段手机查看。

这个想法可以作为：

> 极轻量验证候选。

但目前不建议直接写成最终产品架构。

因为：

- AIRI 已经有 Stage Pocket；
- 最终同一只宠物应该是实时共享状态，而不只是读 Markdown；
- Relationship / Pet State 不完全等于文档同步。

所以：

### Early validation

Markdown / simple web viewer 可以成立。

### Long-term

需要真正：

> Shared Companion State。

---

# 53. Chronicle / Markdown 的价值仍然很高

即使未来不是用 Markdown 做最终同步：

> “档案室可读、可编辑、用户可掌控”

仍然是很好的原则。

特别适合：

- Growth Chapters；
- Confirmed Insights；
- Relationship History；
- User editable narratives；
- Export / portability。

所以：

> Markdown 更适合作为“透明档案格式”概念，而不是现在就锁死成唯一存储技术。

---

# 54. 对“本地 SQLite / Markdown 即可”的最终判断

补充报告中存在一种倾向：

> “SQLite + Markdown 已经足够，因此不用复杂系统。”

目前更合适的判断是：

> **SQLite + Markdown 是一个非常有吸引力的 local-first baseline，但不能在调研阶段提前证明它就是终局。**

Syke 的实践证明：

> 对它的 workload，这条路线非常有效。

但我们的系统未来还可能涉及：

- Mobile；
- Cross-device；
- Shared Pet State；
- Temporal history；
- Multi-source memory；
- encrypted sync。

所以现在应该保留：

> 简单优先。

而不是：

> 简单路线已经被证明是唯一正确答案。

---

# 55. 最终建议的生态分层

经过两轮调研后，当前最合理的生态地图是：

```text
┌──────────────────────────────────────┐
│             BODY LAYER               │
│ Hermes Pet / OpenPet / AIRI / VPet   │
└─────────────────┬────────────────────┘
                  │
┌─────────────────▼────────────────────┐
│         SOURCE / SENSING LAYER       │
│ Hermes Hooks / ChatGPT / Browser ... │
└─────────────────┬────────────────────┘
                  │
┌─────────────────▼────────────────────┐
│        ATTRIBUTION / EVIDENCE        │
│ Our rules + build-your-users-mind    │
└─────────────────┬────────────────────┘
                  │
┌─────────────────▼────────────────────┐
│          MEMORY SUBSTRATES           │
│ Hindsight / O-Mem / FERNme / Syke    │
│ Memobase / Graphiti / Letta          │
└─────────────────┬────────────────────┘
                  │
┌─────────────────▼────────────────────┐
│        DEVELOPMENTAL MIND CORE       │
│ Psychological Flexibility            │
│ Pattern / Hypothesis / Calibration   │
│ Intervention / Narrative / Relation  │
└─────────────────┬────────────────────┘
                  │
┌─────────────────▼────────────────────┐
│           EXPRESSION LAYER           │
│ Pet behavior / Bubble / Mobile / UI  │
└──────────────────────────────────────┘
```

其中：

> **Developmental Mind Core 仍然是我们真正的核心。**

---

# 56. 最终候选优先级：不再用一个总排行榜

更合理的是分赛道。

## Body / Presence

### S
- Hermes Native Pet —— Hermes-first
- AIRI —— long-term cross-device

### A
- OpenPet —— agent-agnostic desktop body
- VPet —— pet UX reference

### B
- openclaw-tamagotchi —— rapid prototype
- Open-LLM-VTuber —— avatar / voice
- YUI —— architecture reference

---

## Attribution / User Modeling

### S
- build-your-users-mind
- O-Mem
- PersonaMem research

### A
- FERNme
- Memobase

---

## Memory

### S
- Hindsight
- Syke

### A
- O-Mem
- Graphiti
- Memobase
- FERNme

### B
- Letta
- Mem0
- MemoryBank

注意：

> 这里不是“质量排名”，而是与本项目问题的相关度排序。

---

# 57. 下一阶段真正值得深挖的项目

现在不再需要继续广泛搜索几十个同类项目。

更值得进入源码级调研的是：

## 1. Hermes Native Pet / Plugin / Hook

回答：

- 是否能直接成为 MVP Body；
- 是否能完全不 fork core；
- 当前 Pet state / bubble / overlay API 到什么程度；
- User decision event 能否通过 official hooks 获得。

---

## 2. Project AIRI

回答：

- Plugin SDK 实际成熟度；
- Desktop / Web / Pocket state sharing；
- Alaya；
- Memory；
- Dreaming；
- Personality；
- External remote plugin；
- Body-only 使用模式；
- 长期维护成本。

---

## 3. Hindsight vs O-Mem vs FERNme vs Syke vs Memobase

重点不是 benchmark。

而是：

> 谁分别适合什么职责。

---

## 4. build-your-users-mind

重点研究：

- evidence discipline；
- user decision extraction；
- prediction feedback；
- inspectable hypothesis；
- 如何避免 covert profile。

---

# 58. 当前不需要继续深入的方向

暂时不必继续大量搜索：

- 普通 Electron 桌宠；
- 普通 PyQt 桌宠；
- 普通 Live2D Chatbot；
- 普通 RAG Memory；
- 普通 Avatar 项目。

这些问题已经得到足够证明：

> 有大量现成方案。

继续增加 repo 数量对决策价值不大。

---

# 59. 当前应保持未决的技术问题

尽管生态路线已经清晰，以下仍然不应现在锁死：

- 最终数据库；
- 是否使用向量库；
- 是否使用 graph；
- 是否采用 O-Mem schema；
- 是否直接使用 Hindsight；
- 是否使用 Syke；
- 是否长期使用 Hermes Native Pet；
- AIRI 是否 fork；
- Growth Core 是 service / plugin / library；
- Mobile 同步协议；
- ChatGPT browser capture 方法；
- 是否需要 cloud backend。

这些应该在下一阶段：

> 源码级验证

之后再决定。

---

# 60. 最终修正版路线判断

当前最合理的总体战略不是：

> “现在选一个大框架，然后所有东西塞进去。”

而是：

# Keep the Mind Independent.

中文：

> **保持“成长心智”独立。**

Body 可以换：

```text
Hermes Pet
→ OpenPet
→ AIRI
```

Memory 可以换：

```text
Hindsight
→ O-Mem
→ Syke
→ Hybrid
```

但是以下核心逻辑不能绑定某个外部框架：

```text
Attribution
Development
Calibration
Intervention
Narrative
Relationship
Co-evolution
```

这才是长期最稳健的产品资产。

---

# 61. 经过二次核验后的三条最重要结论

## 结论一

> **Hermes 自带的 Pet / Plugin / Hook 已经足够成熟，Hermes-first MVP 不一定需要另外造桌宠。**

这是补充调研带来的最大现实捷径。

---

## 结论二

> **AIRI 仍然是长期跨端 Companion Runtime 的最强候选，但没有必要用它承担第一阶段所有验证。**

AIRI 与 Hermes Native Pet 不冲突：

- 一个适合最短验证；
- 一个适合长期终局。

---

## 结论三

> **新的 Memory / User Modeling 项目进一步证明：真正重要的不是存更多对话，而是形成可检查、可修正、有时间变化的用户理解。**

build-your-users-mind、O-Mem、FERNme、Syke 都从不同角度支持了这一点。

---

# 62. 对整个项目创新点的最终确认

目前没有发现开源项目完整实现：

```text
Agent/User Attribution
+
Longitudinal Development
+
Psychological Flexibility
+
Evidence-grounded Hypothesis
+
User Calibration
+
State Intervention
+
Development Intervention
+
Growth Narrative
+
Pet Co-evolution
+
Relationship Calibration
+
Silence
```

因此项目真正值得继续推进的部分依然成立。

---

# 63. 与前六份需求文档的一致性

调研并没有推翻前六份文档。

反而进一步验证了：

### Attribution

build-your-users-mind、Syke 都强调：

> Evidence 与 inference 必须分开。

---

### Data Minimalism

FERNme、Syke 支持：

> 长期记忆不应该等于无限 transcript。

---

### Dynamic User Model

O-Mem、PersonaMem 支持：

> User profile 会变化。

---

### Raw Data Decay

FERNme / MemoryBank 等支持：

> 旧信息不应永远保持同等权重。

---

### Intervention Restraint

JITAI、PersonaMem-v3 支持：

> 个性化和介入应该考虑时机与是否需要。

---

### Evidence Ledger

build-your-users-mind、AuthScribe 都支持：

> 推断应该有来源。

---

### Relationship / Bond

Relational Agent 与 Companion studies 支持：

> 关系会真实影响长期体验。

---

# 64. 最终生态判断

如果用一句话总结目前开源世界的状态：

> **我们已经不缺一个“会动的宠物”，也不缺一个“会记忆的 Agent”；真正缺少的是一个能够长期、克制、可验证地理解用户如何变化，并让这种变化同时塑造数字伙伴自身的成长心智层。**

---

# 65. 推荐的下一阶段

生态广度调研到这里已经足够。

下一阶段不再继续扩大项目列表。

推荐进入三个窄而深的专项调研：

## A. Hermes Native Companion 深挖

聚焦：

> MVP 能否直接站在 Hermes 原生 Pet / Plugin / Hook 上。

---

## B. AIRI Deep Dive

聚焦：

> 长期跨端 Body 是否可以直接基于 AIRI，并保持 Growth Core 独立。

---

## C. Memory / User Model Comparative Study

重点对比：

- Hindsight
- O-Mem
- FERNme
- Syke
- Memobase
- Graphiti
- build-your-users-mind

最终回答：

> 哪些直接复用，哪些借鉴思想，哪些职责必须由 Growth Core 自己承担。

---

# 66. 最终一句话

> **短期，我们已经拥有足够轻的身体；长期，我们也已经找到足够强的跨端身体。现在真正需要认真设计的，是那个会陪用户一起成长的“心”。**

英文：

> **We already have enough bodies and memories. The real product is the developmental mind that connects them.**
