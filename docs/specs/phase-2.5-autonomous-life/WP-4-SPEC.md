---
id: companion-phase-2.5-wp4-behavior-arbiter
type: module-design
title: Phase 2.5 WP-4 规范：Behavior Arbiter（统一行为仲裁器与时序保护）
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
  - companion-phase-2.5-wp1-pet-manifest
  - companion-phase-2.5-wp2-vasu-v2
  - companion-phase-2.5-wp3-activity-registry
status: active
tags:
  - phase-2.5
  - wp-4
  - behavior-arbiter
  - priority
  - stale-timer-safety
  - invariants
---

# Phase 2.5 WP-4 — Behavior Arbiter（统一行为仲裁器与时序保护）

## 1. 目标与定位

WP-4 建立伴生体系统统一的 **Behavior Arbiter（行为仲裁器）**，彻底终结历史遗留的 `timer -> set_state()` 与后发覆盖（Last-Write-Wins, LWW）混乱模型。

核心定位：
> **作为控制平面（Control Plane）唯一的行为执行准入中枢；所有意图改变宠物身体行为的动作请求在被表现层（Body Runtime）执行前，都必须经过 Arbiter 进行优先级、打断权限、保护态、冷却期与完成时序判定。**

### 运行时分层拓扑
```text
BehaviorIntent (WHAT / WHY, Runtime / Scheduler)
    ↓
ActivityRegistry (HOW, Pet Capability Index)
    ↓
ActivityResolution (Candidate Activities & Adaptation)
    ↓
BehaviorRequest (Priority, Source, Protection, Resumable)
    ↓
BehaviorArbiter (Priority, Interruption, Protection, Cooldown, Stale Timer Guard)
    ↓ (唯一权威准入裁决)
BehaviorDecision (START / INTERRUPT_AND_START / REJECT / RESUME / NO_OP)
    ↓
Body Execution Adapter / PetWindow (视觉表现与物理投影)
```

---

## 2. 核心原则与硬约束

1. **结束 Last-Write-Wins 混乱**：表现层状态机必须成为 Arbiter 决策结果的受控投影，严禁任何零散定时器或外部事件直接越权强刷 `apply_state(IDLE)`；
2. **过期定时器防护（Stale Timer Safety）**：每个行为结束时必须携带其唯一的 `request_id` 进行完成登记；若活跃请求已被更高优先级或更新行为替代，过期定时器触发安全空转（`NO_OP`）；
3. **免打扰休眠保护（DND Protection）**：用户显式设置的休眠处于 `PROTECTED_SLEEP` 保护态，光标掠过（hover）、身体轻戳（poke）或猫打盹定时器严禁擅自唤醒；
4. **确定性优先级裁决**：严格按照清晰的语义优先级层级判定抢占，禁止使用魔法数值；
5. **绝对零宠物专属代码**：Arbiter 源码中严禁出现任何特定宠物名称（`vasu`、`calico` 等）或具体图像文件名；
6. **纯仲裁器定位**：Arbiter 本身不主动产生自主行为（自主行为发生器属于 WP-5 LifeScheduler）。

---

## 3. 优先级契约 (Priority Contract)

WP-4 冻结为五级语义优先级：

| 优先级 (`BehaviorPriority`) | 语义级别 | 典型来源与场景 | 抢占规则 |
| :--- | :---: | :--- | :--- |
| **`P4_EXPLICIT_USER`** (40) | 最高用户主权 | 用户鼠标拖拽、托盘显式休眠/唤醒、强点击 | 绝对优先，可抢占所有低优先级；可打断保护态 |
| **`P3_SAFETY`** (30) | 系统与安全保护 | 避风港 Sanctuary 模式、UI 关键保护态 | 优先于交互与自主行为；仅可被 P4 显式用户行为改变 |
| **`P2_DIRECT_INTERACTION`** (20) | 直接短互动 | 光标悬停打招呼、轻戳反馈、切片投喂成功反馈 | 优先于自主行为；受冷却限制；不可打断保护态 |
| **`P1_AUTONOMOUS`** (10) | 自主日常行为 | 未来 LifeScheduler 自发小动作（工作/观察/玩耍） | 可被交互与用户操作随时抢占 |
| **`P0_AMBIENT`** (0) | 环境背景基线 | 静止待机（IDLE）、微呼吸、稀疏眨眼微动 | 最低基线，仅在无更高指令时维持运行 |

---

## 4. 保护与打断契约 (Interruption & Protection)

### 4.1 保护等级 (`ProtectionLevel`)
- **`UNPROTECTED`**：常规行为，允许被高优先级请求中断；
- **`PROTECTED_SLEEP`**：用户显式休眠（DND），仅允许 `P4_EXPLICIT_USER`（显式唤醒）或 `P3_SAFETY` 打断，普通 hover、poke 或 nap timer 直接拒绝（`REJECT`）；
- **`PROTECTED_INTERACTION`**：进行中的关键交互（如正在物理拖拽），非显式行为无法抢占。

### 4.2 抢占与挂起恢复 (`Resume`)
- 若活跃行为声明 `resumable=True` 且被更高优先级行为抢占：Arbiter 将其保存至单层 `_suspended_request`；
- 抢占行为完成时（`complete(request_id)`），自动触发挂起行为的恢复（`action=RESUME`）；
- 若活跃行为不可恢复（`resumable=False`，如环境小动作或拖拽释放），完成后平滑 settle 到默认基线 IDLE。

---

## 5. 完成契约与过期定时器消除 (Stale Timer Guard)

1. 行为结束时调用 `arbiter.complete(request_id)`；
2. **时序验证**：
   - 若 `request_id == _active_request.request_id`：有效完成，检查挂起栈或 settle；
   - 若 `request_id != _active_request.request_id`：**确认为过期定时器（Stale Timer），静默返回 `NO_OP`，绝不修改当前活动状态！**
3. 彻底根治“悬停打喷嚏定时器在投喂切片后把开心的桌宠强行刷回静止”的历史竞态缺陷。

---

## 6. 集中式冷却契约 (Cooldown Management)

- Arbiter 统一维护 `_cooldowns: dict[str, float]`；
- 短交互（如 `hover_greet`, `poke_reaction`）携带 `cooldown_key`；
- 在冷却期内到来的同类请求直接由 Arbiter 拦截拒绝（`action=REJECT, reason="cooldown_active"`），不再在表现层散落布尔变量。

---

## 7. 表现层适配与旧路径接管

在 `src/body/window.py` 内部接入 Arbiter：
- **拖拽行为**：按下且产生位移时提交 `P4_EXPLICIT_USER`（`PROTECTED_INTERACTION`），松开鼠标时完成；
- **显式休眠**：提交 `P4_EXPLICIT_USER`（`PROTECTED_SLEEP`），彻底封死 hover 自动唤醒；
- **光标悬停**：`enterEvent` 提交 `P2_DIRECT_INTERACTION`，在休眠或拖拽期间由 Arbiter 优雅拒绝；
- **切片投喂**：提交 `P2_DIRECT_INTERACTION`，具备高于悬停的优先级；
- **定时器**：全部迁移为携带 `request_id` 的 `arbiter.complete(request_id)` 闭环。

---

## 8. 验收标准

1. 12 项核心时序与冲突回归测试 100% 通过；
2. 现有桌宠窗口正常启动，拖拽、悬停、显式休眠/唤醒、切片交互全部正常；
3. 过期定时器踩踏与休眠被毁现象被确凿根除；
4. Arbiter 纯领域实现，零宠物专属名称侵入；
5. spec-graph 与全量测试套件持续通过。
