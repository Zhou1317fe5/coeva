---
id: companion-phase-2.5-wp5-life-scheduler
type: module-design
title: Phase 2.5 WP-5 规范：Life Scheduler（轻量自主生命调度器）
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
  - companion-phase-2.5-wp1-pet-manifest
  - companion-phase-2.5-wp2-vasu-v2
  - companion-phase-2.5-wp3-activity-registry
  - companion-phase-2.5-wp4-behavior-arbiter
status: active
tags:
  - phase-2.5
  - wp-5
  - life-scheduler
  - silence-first
  - autonomous-life
  - invariants
---

# Phase 2.5 WP-5 — Life Scheduler (轻量自主生命调度器)

## 1. 目标与定位

WP-5 建立伴生体系统统一的 **Life Scheduler（轻量自主生命调度器）**。

核心定位：
> **负责在无人交互时，以“静默在场为主（Silence First）”的节律，偶尔产生通用的 `BehaviorIntent`，使桌宠自然具备自主生活感；同时彻底解耦宠物的具体动作名称与动画资源，消除 Vasu 历史上被 `_native_idle_frames` 完全阻断自主生命的既成缺陷。**

### 运行时调用链拓扑
```text
LifeScheduler.consider()
    ↓ (通用 BehaviorIntent 或 Silence / None)
ActivityRegistry.resolve(intent)
    ↓ (按当前宠物 Manifest 解析适配候选)
BehaviorRequest (P1_AUTONOMOUS, source=AUTONOMOUS)
    ↓
BehaviorArbiter.submit(request)
    ↓ (仲裁准入)
Body Execution Adapter / PetWindow (投影播放)
```

---

## 2. 核心原则与硬约束

1. **静默优先（Silence First）**：
   - “什么都不做（None / Silence）”是第一等合法决策，权重最高；
   - 每次动作执行完毕后，必须经过强制的静默窗口（`minimum_quiet_sec`），方可再次启动考虑；
2. **纯通用行为类别（Base Autonomous Categories Only）**：
   - 自主行为池严格限定在：`OBSERVE`, `WORK`, `REST`, `PLAY`, `MOVE`；
   - `IDLE` 是静息 Settle 状态，不作为主动调度事件；
   - 绝不主动产生 `GREET`（直接社交响应）、`REACT`（外部事件即时反馈）或随机 `SLEEP`（由 WP-6 昼夜节律专属负责）；
3. **零宠物名称与动作硬编码**：
   - Scheduler 源码中严禁包含任何特定宠物名字（`vasu`、`calico` 等）、特定 Activity ID（`review`、`typing`、`pondering` 等）或具体图像文件名；
4. **反重复机制（Anti-Repetition）**：
   - 避免连续两次选择相同类别（除非无其他可选类别）；
   - 限制短期窗口内 `MOVE` 频率；防止高能量 `PLAY` 密集扎堆；
5. **确定性测试与外部时钟/RNG 注入**：
   - 注入 `clock` 与 `rng`，支持相同随机种子产生 100% 相同且可预测的调度序列；
6. **纯离线 CPU 本地运行**：
   - 零网络调用、零 LLM 依赖、零内存数据库读写。

---

## 3. 调度配置模型 (`SchedulerConfig`)

```python
@dataclass(frozen=True)
class SchedulerConfig:
    """Configuration governing autonomous behavior cadence and weighting."""

    consideration_min_sec: float = 12.0
    consideration_max_sec: float = 35.0
    minimum_quiet_sec: float = 10.0
    autonomous_duration_min_sec: float = 6.0
    autonomous_duration_max_sec: float = 16.0
    silence_weight: float = 3.5
    category_weights: Mapping[BehaviorCategory, float] = field(
        default_factory=lambda: {
            BehaviorCategory.OBSERVE: 3.0,
            BehaviorCategory.WORK: 2.5,
            BehaviorCategory.REST: 2.0,
            BehaviorCategory.PLAY: 1.5,
            BehaviorCategory.MOVE: 1.0,
        }
    )
    max_consecutive_same_category: int = 1
    max_moves_in_history: int = 2
    history_capacity: int = 20
```

---

## 4. 内存运行历史 (`BehaviorHistory`)

在内存中维护轻量 `collections.deque`，不持久化、不落盘、不进入 Memory V2.1：
- 记录 `timestamp`、`category`、`direction`、`duration_sec`、`activity_id`；
- 供反重复与位移频次熔断评估。

---

## 5. 表现层改造与旧体系收口

在 `src/body/window.py` 内部：
1. **统一生命周期管理**：
   - 彻底删除过去硬编码在 `window.py` 内的 `work_activities` 动作名元组；
   - 彻底删除 `if self._native_idle_frames is not None: return` 阻断守卫；
   - 初始化 `self._scheduler = LifeScheduler(...)`；
2. **时序回环**：
   - `_autonomous_timer` 触发考虑；
   - 若返回 `None`（Silence）：继续维持静止并重新调度；
   - 若返回 `intent`：解析出候选，包装为 `BehaviorRequest(priority=P1_AUTONOMOUS)` 提交 Arbiter；
   - 若 Arbiter 接受：根据候选执行对应动画，并启动 `_autonomous_done_timer`；
   - 若被更高优先级（如用户正在拖拽、休眠或刚刚投喂）拒绝：干净退出，等待下一轮，**绝不发起循环重试风暴**；
   - `_autonomous_done_timer` 到期后通过 Arbiter 完成并平滑 Settle 回基线静止（Vasu 原画或像素呼吸）。

---

## 6. 显式非目标 (Explicit Non-goals)

- 不接入小时级昼夜作息或环境节律调制（WP-6）；
- 不接入 Agent 工具流或会话状态感知（WP-6）；
- 不接入 Sanctuary 模式（WP-6）；
- 不接入 RelationshipPolicy 或确认的人生章节（WP-6）；
- 不进行 80/15/5 长期仿真与遥测（WP-7）；
- 不制作新美术资产，不修改 Memory V2.1。

---

## 7. 验收标准

1. Vasu 在无人操作时不再永久定格在双帧眨眼，而是能偶发自发展现低频、优雅的自主动作；
2. 调度器在大部分时间返回“什么都不做”，保持静默陪伴哲学；
3. 源码零硬编码宠物名称或动作文件名；
4. 相同随机种子产生确定性的调度序列；
5. 全量回归测试与规范图谱校验 100% 通过。
