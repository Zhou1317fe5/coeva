---
id: companion-phase-2.5-wp6-context-modulation
type: module-design
title: Phase 2.5 WP-6 规范：Circadian 与 Context Modulation（环境情境调制）
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
  - companion-phase-2.5-wp1-pet-manifest
  - companion-phase-2.5-wp2-vasu-v2
  - companion-phase-2.5-wp3-activity-registry
  - companion-phase-2.5-wp4-behavior-arbiter
  - companion-phase-2.5-wp5-life-scheduler
status: active
tags:
  - phase-2.5
  - wp-6
  - circadian
  - context-modulation
  - life-scheduler
  - invariants
---

# Phase 2.5 WP-6 — Circadian & Context Modulation（环境情境调制）

## 1. 目标与定位

WP-6 建立统一、轻量、确定性可测试的 **Context Modulation 层（上下文调制层）**。

核心定位：
> **负责收集外部运行环境（Circadian 昼夜节律、Agent 宏观活跃度、Sanctuary 避风港模式、Mini Mode 停靠、随手投喂/气泡输入状态以及已确认的人生洞察），并将其编译为针对 `LifeScheduler` 的只读倾向偏置（SchedulerModulation）；彻底切断任何外部环境直接向身体表现层发送 `set_state()` 命令的旁路架构隐患。**

### 运行时控制流拓扑
```text
Context Snapshot (Circadian, Agent, Sanctuary, Dock, UI, Confirmed Insights)
    ↓ (纯数据编译，绝不发送 Body 命令)
ContextModulator.modulate(base_config, context)
    ↓
SchedulerModulation (silence bias, category multipliers, sleep allowance)
    ↓
LifeScheduler.consider(registry, context=...)
    ↓ (通用 BehaviorIntent 或 None / Silence)
ActivityRegistry.resolve(intent)
    ↓
BehaviorRequest (P1_AUTONOMOUS)
    ↓
BehaviorArbiter.submit(request)
    ↓ (唯一准入仲裁)
Body Execution Adapter / PetWindow (投影播放)
```

---

## 2. 核心原则与硬约束

1. **Context ≠ Direct Body Command**：
   - 彻底废止 `circadian.py`、`state_watcher.py`、`sanctuary.py` 直接调用 `apply_state()` 或 `set_state()`；
   - Context 只能产出只读的偏好调制（Modulation），不能驱动 UI；
2. **Base Config 绝对不可变**：
   - `SchedulerConfig` 保持 frozen，调制只派生单次决策用的临时有效策略，绝不永久修改基准配置；
3. **确定性正交组合与安全限幅（Deterministic Clamped Composition）**：
   - 多个上下文并存时，乘数相乘并安全 clamp（`silence_multiplier: [0.3, 5.0]`, `category_multipliers: [0.0, 3.0]`），类别限制取保守交集，静默（Silence）永远合法；
4. **自主 SLEEP 的严格边界**：
   - 晚间自主睡眠属于 `P1_AUTONOMOUS`（`UNPROTECTED`），普通光标交互可自然打断；与用户显式设置的 `P4_EXPLICIT_USER`（`PROTECTED_SLEEP`）严格区分；
   - Calico 原生睡眠；Vasu 依据 WP-0 契约诚实降级为静止在场，绝不伪造虚假睡眠动画；
5. **已确认洞察（Confirmed-Only）防护**：
   - 仅已确认、当前有效的洞察（`status == "confirmed" | "active"`）允许产生微弱且有界的偏置（`[0.85, 1.2]`）；候选假说（Candidate Hypothesis）、拒绝/撤回的洞察绝对不影响行为；
6. **时序平滑过渡（Context Transition Semantics）**：
   - 环境发生改变（如时间进入深夜、Agent 开始工作、开启避风港）时，不强制中断正在执行的当前行为，而是在下一轮考虑（Consideration）时平滑应用新偏置。

---

## 3. 核心数据模型

### 3.1 运行时环境快照 (`LifeContext`)
```python
@dataclass(frozen=True)
class LifeContext:
    circadian_phase: CircadianPhase = CircadianPhase.MORNING_WORK
    hour: int = 10
    agent_active: bool = False
    sanctuary_active: bool = False
    mini_mode_docked: bool = False
    feeder_active: bool = False
    bubble_active: bool = False
    active_confirmed_insights: tuple[str, ...] = ()
```

### 3.2 调制报告模型 (`SchedulerModulation`)
```python
@dataclass(frozen=True)
class SchedulerModulation:
    silence_multiplier: float = 1.0
    quiet_window_multiplier: float = 1.0
    category_multipliers: Mapping[BehaviorCategory, float] = field(default_factory=dict)
    allowed_categories: frozenset[BehaviorCategory] | None = None
    allow_autonomous_sleep: bool = False
    reasons: tuple[str, ...] = ()
```

---

## 4. 环境规则矩阵

1. **Circadian 昼夜作息**：
   - `NIGHT_SLEEP`: silence ×2.5, REST ×1.8, MOVE ×0.0, PLAY ×0.0, `allow_autonomous_sleep=True`；
   - `MORNING_WAKE`: silence ×1.2, REST ×1.3, OBSERVE ×1.2, PLAY ×0.5；
   - `MORNING_WORK`: WORK ×1.4, OBSERVE ×1.2, PLAY ×0.6, MOVE ×0.9；
   - `MIDDAY_SIESTA`: silence ×1.5, REST ×1.6, PLAY ×0.3, MOVE ×0.3；
   - `AFTERNOON_FOCUS`: WORK ×1.4, OBSERVE ×1.2, PLAY ×0.6；
   - `EVENING_LEISURE`: PLAY ×1.4, REST ×1.3, WORK ×0.6；
2. **Agent Active 桌面高强度工作**：
   - silence ×1.6, PLAY ×0.2, MOVE ×0.2, quiet WORK ×1.2, quiet OBSERVE ×1.2（低扰动伴读，不做指示灯）；
3. **Sanctuary 避风港模式**：
   - silence ×3.0, PLAY ×0.0, MOVE ×0.0, 高能动作禁用，仅允许安静 REST/OBSERVE/SLEEP（深夜避风港时安静入睡仍属最合适的逃避性静息，且始终可被交互自然打断）；
4. **Mini Mode 边缘收纳**：
   - MOVE ×0.0（禁止自主移出屏幕边缘），仅允许静止 OBSERVE/WORK/REST；
5. **Feeder / Bubble 输入交互**：
   - silence ×2.5, MOVE ×0.0, PLAY ×0.0（用户编辑或气泡显示时不乱入打扰）；
6. **Confirmed Insights 关系反哺**：
   - 严格有界轻微调制（`[0.85, 1.2]`），严禁候选假说影响行为。

---

## 5. 显式非目标 (Explicit Non-goals)

- 不制作新动画或具体宠物动作；
- 不建立大型决策规划器（GOAP / 行为树）；
- 不侵入全局键鼠驱动级监听；
- 不进行 80/15/5 长期仿真与指标统计（WP-7）；
- 不修改 Memory V2.1 数据库结构与准入逻辑。

---

## 6. 验收标准

1. Circadian, StateWatcher, Sanctuary 不再包含任何直接控制 Body 状态机的代码；
2. 多重上下文能够正交、确定性组合且被安全限幅；
3. Vasu 与 Calico 晚间睡眠各安其职（Calico 真正入睡，Vasu 诚实降级为静息在场）；
4. 候选假说零行为影响；
5. 全量自动化测试与规范图谱校验 100% 通过。
