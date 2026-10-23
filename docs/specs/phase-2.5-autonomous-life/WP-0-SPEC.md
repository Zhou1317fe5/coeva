---
id: companion-phase-2.5-wp0-behavior-semantics
type: module-design
title: Phase 2.5 WP-0 规范：宠物行为语义层契约 (Pet Behavior Semantics)
parent: companion-architecture-design
status: active
tags:
  - phase-2.5
  - wp-0
  - behavior-semantics
  - autonomous-life
  - invariants
---

# Phase 2.5 WP-0 — Pet Behavior Semantics（宠物行为语义层契约）

## 1. 目标

WP-0 定义 Coeva 所有宠物共同遵循的“行为语义层”。

本阶段解决的问题不是：
- Vasu 有哪些 GIF；
- 某个动作文件叫什么；
- 动画具体多少帧；
- Scheduler 什么时候播放哪个动画。

而是先回答：
> **当 Coeva 说“宠物现在想工作 / 休息 / 观察 / 睡觉”时，这些概念在系统中究竟意味着什么？**

行为语义必须独立于任何具体宠物和任何具体资产。

---

## 2. 核心分层

Coeva 中必须严格区分三个概念：

```text
BehaviorIntent (WHAT / WHY, Runtime / Growth Core)
    ↓
PetActivity (HOW, Pet Capability / Manifest)
    ↓
Animation / Asset (VISUAL EXECUTION, Desktop Body 表现层)
```

### 2.1 BehaviorIntent
- **描述**：当前生命系统希望宠物“做什么 / 为什么做”。
- **范围**：例如 `IDLE`, `REST`, `SLEEP`, `WORK`, `OBSERVE`, `PLAY`, `MOVE`, `GREET`, `REACT`。
- **归属**：`BehaviorIntent` 属于 Coeva Runtime / Growth Core。它不属于 Vasu，也不属于任何特定宠物。

### 2.2 PetActivity
- **描述**：当前宠物如何表达某个 `BehaviorIntent`。
- **例如**：针对 `BehaviorIntent.WORK`：
  - Vasu 可以表达为：`typing`, `reviewing`, `sorting_stone`；
  - 另一只猫可以表达为：`paperwork`, `watching_screen`, `pawing_notebook`。
- **硬约束**：Scheduler 不得知道这些 Activity 名称。

### 2.3 Animation / Asset
- **描述**：`PetActivity` 最终使用什么视觉资产播放。
- **例如**：
  - `vasu_reviewing` → spritesheet row 8 frames 0..5；
  - `vasu_blink` → assets/vasu-blink.png。
- **归属**：资产属于表现层。**资产文件名与图集行号不得承担行为语义**。

---

## 3. 核心不变量 (Core Invariants)

### INV-B1 — Behavior != Asset
行为语义不得由动画文件名、GIF 名称或 spritesheet row 名称决定。
- **禁止**：
  ```python
  if animation == "typing":
      behavior = WORK
  ```
- **必须**：由 PetActivity Manifest 显式声明语义。

### INV-B2 — Scheduler Knows No Pet-specific Activity
LifeScheduler 不得引用特定宠物的动作标识：
- **禁止**：引用 `vasu_typing`, `vasu_review`, `calico_paperwork` 等特定字符串。
- **必须**：Scheduler 只能产生通用 `BehaviorIntent(category=WORK)`。

### INV-B3 — Pet Declares Capabilities
Runtime 不得假设某只宠物拥有某个可选动作（如 `WORK`, `PLAY`, `OBSERVE`, `GREET` 都可能不存在）。当前宠物能够做什么，必须由 Pet Capability 声明。

### INV-B4 — Intent Describes WHAT, Activity Describes HOW
- `BehaviorIntent` = WHAT / WHY
- `PetActivity` = HOW
- `Animation` = VISUAL EXECUTION
三层职责边界严明，不得混用。

### INV-B5 — Missing Optional Behavior Is Normal
宠物缺少某个可选行为不是异常，Runtime 必须能够安全 fallback（例如 `WORK` → `OBSERVE` → `IDLE`），而不是抛错或强求每只宠物拥有完全相同的动画集。

### INV-B6 — Silence Is a Behavior
`IDLE` 不是“没有行为”。Quiet presence（平静在场）本身就是合法行为状态。因此 Scheduler 不得因为“没有别的动作”就不断寻找动画播放。

---

## 4. 第一版 Behavior Category

WP-0 冻结为九个顶层行为类别，不继续发散：

1. `IDLE`
2. `REST`
3. `SLEEP`
4. `WORK`
5. `OBSERVE`
6. `PLAY`
7. `MOVE`
8. `GREET`
9. `REACT`

---

## 5. 各行为语义定义

### 5.1 IDLE
- **含义**：宠物没有明确目标，安静存在于桌面空间中。
- **典型表现**：静止、微呼吸、眨眼、微小姿态变化、极偶发的小动作。
- **边界**：IDLE 不等于发呆动画必须循环，不等于不断播放 6 帧动画，不等于每隔几秒必须产生动作。IDLE 是 80% quiet presence 的主要承载状态。

### 5.2 REST
- **含义**：宠物主动降低活动水平，但仍然处于清醒状态。
- **典型表现**：趴下、坐着休息、靠着、安静整理身体、放松。
- **边界**：REST 与 SLEEP 必须区分。REST 默认允许轻度互动中断。

### 5.3 SLEEP
- **含义**：宠物进入明确睡眠 / 免打扰状态。
- **来源**：circadian tendency, autonomous nap, explicit user sleep。
- **边界**：SLEEP 是持续性、低响应行为。

### 5.4 WORK
- **含义**：宠物正在进行具有目的性的、自我导向的小活动。
- **边界**：WORK 不代表“映射用户正在 Coding”，也不映射 Agent 工具循环。它表达的是“伴生体自己也有自己的事情”。具体表现完全由宠物自主决定。

### 5.5 OBSERVE
- **含义**：宠物短暂关注周围环境，而不主动发起强交互。
- **典型表现**：看向一边、抬头、探头、看屏幕、看用户方向。
- **边界**：OBSERVE（我注意到了什么）与 GREET（我主动回应你）不同，是极其重要的低强度生命感行为。

### 5.6 PLAY
- **含义**：非生产目的、自发的轻松活动。
- **典型表现**：玩石头、摆弄尾巴、玩小物件、自娱。
- **边界**：PLAY 不意味着一定高能量，也不意味着必须响应用户。

### 5.7 MOVE
- **含义**：从一个桌面位置向另一个位置产生实际位移。
- **边界**：MOVE 是行为语义，不等于 `running.gif`。具体宠物可以走、跑、跳、滑、飞。Direction 属于 Activity metadata，不是新的顶层 BehaviorCategory。

### 5.8 GREET
- **含义**：针对用户明确出现或主动互动做出的轻度社交回应。
- **典型表现**：挥手、探头、点头、短暂看向用户。
- **边界**：GREET 必须保持低频，绝非鼠标移入就必须触发，触发由后续 Interaction Policy 仲裁。

### 5.9 REACT
- **含义**：对一个明确事件进行短暂、即时的身体反馈。
- **边界**：REACT 是顶层类别。具体情绪和语义使用 tags（如 `positive`, `negative`, `surprised`, `acknowledge`）描述，严禁在顶层无限新增 HAPPY/SAD 等状态。

---

## 6. Activity Traits

Activity 支持声明 Traits 描述其风格，第一版冻结为 5 对 11 个原子标签：
- `quiet` / `active`
- `stationary` / `locomotive`
- `social` / `solitary`
- `focused` / `casual`
- `low_energy` / `medium_energy` / `high_energy`

Scheduler 将来可以请求 preferred_traits（例如请求 `WORK` 且期望 `[quiet, stationary]`），但 Scheduler 绝不请求具体的 activity id（例如 `reviewing`）。

---

## 7. Direction 语义规范

禁止将 `MOVE_LEFT`、`MOVE_RIGHT` 作为独立 BehaviorCategory。方向统一作为 `BehaviorIntent` 的参数：
- `NONE`
- `LEFT`
- `RIGHT`

---

## 8. BehaviorIntent 契约约束

`BehaviorIntent` 数据结构包含：
- `category: BehaviorCategory`
- `source: str`（如 `life_scheduler`, `interaction`, `circadian`）
- `preferred_traits: tuple[ActivityTrait, ...]`
- `direction: BehaviorDirection`
- `intensity: float`（取值 `[0.0, 1.0]`）
- `tags: tuple[str, ...]`

**硬约束**：严禁包含 `gif filename`、`spritesheet row`、`animation id` 或任何特定宠物的 activity id。

---

## 9. Required 与 Optional 语义边界

- **Required（最低运行能力基线）**：
  - `IDLE`
  - `SLEEP`
  - `MOVE`（MOVE 可以只有单向资产，由渲染层水平翻转提供另一方向）
- **Optional（扩展能力）**：
  - `REST`
  - `WORK`
  - `OBSERVE`
  - `PLAY`
  - `GREET`
  - `REACT`

---

## 10. Behavior Fallback 原则与语义矩阵

第一版语义 Fallback 链路规定：
- `WORK` → `OBSERVE` → `IDLE`
- `PLAY` → `OBSERVE` → `IDLE`
- `REST` → `IDLE`
- `OBSERVE` → `IDLE`
- `GREET` → `REACT` → `IDLE`
- `REACT` → `IDLE`
- `SLEEP` → `IDLE`
- `MOVE` → `()`（若不支持 MOVE，则保持当前位置，绝不回退到原地踏步的假动作）

---

## 11. 不进入 WP-0 的工作包划分

以下内容严格留存后续 Work Package：
- **WP-1**: `pet.json` / `pet.yaml` schema、Activity metadata schema、资产路径、fps、循环、打断控制与校验器。
- **WP-2**: Vasu 实际制作动画清单、具体帧数、美术规范与图集排布。
- **WP-3**: `ActivityRegistry`、`select_activity()`、动态 fallback 解析器。
- **WP-4**: 行为优先级、打断恢复（interrupt & resume）、冷却时间与 Behavior Arbiter。
- **WP-5**: Life Scheduler、概率分布、行为频次控制。
- **WP-6**: 昼夜节律联动、用户/Agent 活跃度感知、Sanctuary 抑制与偏置。
- **WP-7**: 80/15/5 律可观测性指标、FakeClock、确定性仿真测试。

---

## 12. 验收标准

WP-0 达成必须满足：
1. Scheduler 的行为语言不引用任何 Vasu 专属名称；
2. 行为类别与动画文件完全解耦；
3. 能够解释同一个 WORK 在不同宠物身上拥有完全不同表现；
4. 缺少 WORK / PLAY / OBSERVE 等动作时 Runtime 仍可安全 Fallback 运行；
5. IDLE 被正式定义为 quiet presence，而不是动画循环；
6. `BehaviorIntent`、`PetActivity`、`Animation` 三层职责严格物理隔离；
7. 供后续 Vasu v2 制作与第三方新增宠物无缝遵循。
