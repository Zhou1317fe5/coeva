---
id: companion-phase-2.5-wp3-activity-registry
type: module-design
title: Phase 2.5 WP-3 规范：Activity Registry 与动态 Fallback 解析契约 (Activity Registry & Fallback Resolution)
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
  - companion-phase-2.5-wp1-pet-manifest
  - companion-phase-2.5-wp2-vasu-v2
status: active
tags:
  - phase-2.5
  - wp-3
  - activity-registry
  - semantic-fallback
  - resolver
  - invariants
---

# Phase 2.5 WP-3 — Activity Registry & Fallback Resolution

## 1. 目标与定位

WP-3 基于已完成的 WP-0（行为语义层）、WP-1（Pet Manifest / Capability 契约）以及 WP-2（Vasu v2 Reference Pet），构建 Coeva 的通用 **Activity Registry 与动态 Fallback 解析契约**。

核心职责：
> **提供纯领域、无副作用、无任何具体宠物硬编码分支的索引与查询解析层；输入通用的 `BehaviorIntent`，结合当前宠物的 `PetManifest`，高效且确定性地解析出结构化的 `ActivityResolution`（包含适配候选集、语义降级路径、镜像适配与保持原地标识）。**

---

## 2. 核心原则与硬约束

1. **绝对零宠物专属代码污染（Zero Pet-specific Logic）**：
   - Resolver 与 Registry 模块源码内严禁出现任何特定宠物名称（`vasu`、`calico` 等）、特定 Activity ID（`pondering`、`wave` 等）或具体图像文件名；
2. **复用唯一 Fallback 事实源**：
   - 降级链条严格由 WP-0 的 `SEMANTIC_FALLBACK_CHAINS` 驱动，严禁在解析器内另立降级分支；
3. **MOVE 守则（No Fake Locomotion）**：
   - 若当前宠物无可用 MOVE 动作，直接解析为 `no_op=True`（保持原地），绝不降级为原地踏步的假动作；
4. **确定性候选排序（Deterministic Candidate Ranking）**：
   - 相同输入必须返回 100% 确定性的候选排序（按匹配分、权重与 ID 字典序稳定排序），禁止引入随机加权选择（随机决策属于 WP-5 LifeScheduler）；
5. **纯领域隔离（Pure Domain Isolation）**：
   - Registry 仅负责“查找并评估宠物如何表达”，绝不调用动画播放器、绝不直接操作窗口状态机、绝不读取节律（Circadian）或调用 LLM。

---

## 3. 结构化解析结果 (`ActivityResolution`)

```python
@dataclass(frozen=True)
class ResolvedCandidate:
    """A matched activity adapted with execution metadata."""

    activity: PetActivity
    mirror_required: bool = False
    match_score: float = 1.0


@dataclass(frozen=True)
class ActivityResolution:
    """Complete structural report of resolving a BehaviorIntent against a pet's registry."""

    requested_category: BehaviorCategory
    resolved_category: BehaviorCategory | None
    candidates: tuple[ResolvedCandidate, ...] = ()
    fallback_path: tuple[BehaviorCategory, ...] = ()
    degraded: bool = False
    no_op: bool = False
    reason: str = ""
```

---

## 4. 注册与索引结构 (`ActivityRegistry`)

```python
class ActivityRegistry:
    """Immutable, indexed activity catalog for a single pet manifest."""

    def __init__(self, manifest: PetManifest) -> None:
        ...

    def resolve(self, intent: BehaviorIntent) -> ActivityResolution:
        """Resolve a generic BehaviorIntent into structured candidates with fallback."""
        ...

    def activities_for(self, category: BehaviorCategory) -> tuple[PetActivity, ...]:
        """Directly query activities registered for a category."""
        ...

    def supports_category(self, category: BehaviorCategory) -> bool:
        """Check if pet natively has activities for category."""
        ...
```

---

## 5. 动态解析与匹配算法

### 5.1 类别解析与降级探测
1. **优先原生探测**：若宠物有对应 `intent.category` 的 activities，直接命中，`degraded = False`；
2. **链式降级**：若无，按 `SEMANTIC_FALLBACK_CHAINS[intent.category]` 逐级探测；命中第一个有动作的类别即止，`degraded = True`，并记录完整 `fallback_path`；
3. **MOVE 缺位**：若请求 `MOVE` 且无可用动作，直接返回 `no_op=True, resolved_category=None, reason="move_not_supported_hold_position"`；
4. **全链路缺位**：若回退到底仍无可用动作，返回 `no_op=True`。

### 5.2 方向与镜像匹配 (Direction & Mirroring)
- **NONE**：所有方向候选均合法，`mirror_required = False`；
- **RIGHT**：原生 `RIGHT` 或 `NONE` 优先；若仅有 `LEFT` 且 `visual.mirror=True`，允许作为镜像候选（`mirror_required = True`）；
- **LEFT**：原生 `LEFT` 或 `NONE` 优先；若仅有 `RIGHT` 且 `visual.mirror=True`，允许作为镜像候选（`mirror_required = True`）。

### 5.3 候选评分与确定性排序 (Deterministic Ranking)
每个候选计算匹配分 `match_score`：
- 方向匹配：精确匹配（+10.0 分），无方向兼容（+5.0 分），镜像匹配（+3.0 分）；
- Trait 偏好：每命中一个 `intent.preferred_traits`，加 +2.0 分；
- 权重调节：`+ 0.01 * activity.weight`（次级微调）；
- 排序法则：严格按 `match_score` 降序排列，平局按 `activity.id` 字典序升序稳定平局，确保无隐藏随机性。

---

## 6. 跨宠物天然多态验证 (Cross-Pet Verification)

证明同一套解析器在不同宠物上的行为：
1. **Vasu**：
   - `BehaviorIntent(category=WORK)` $\to$ 解析出 Vasu 的 `pondering`；
   - `BehaviorIntent(category=SLEEP)` $\to$ 降级到 Vasu 的 IDLE 动作（`idle_native`, `idle_breathing`），`degraded = True`；
2. **Calico**：
   - 同一个 `BehaviorIntent(category=WORK)` $\to$ 解析出 Calico 的 `calico_working`, `calico_typing`, `calico_sweeping`；
   - 同一个 `BehaviorIntent(category=SLEEP)` $\to$ 解析出 Calico 原生的 `calico_sleeping`，`degraded = False`。
整个解析过程**零 `if pet_id` 显式分支**，纯粹由声明式 Manifest 驱动多态。

---

## 7. 显式非目标 (Explicit Non-goals)

WP-3 严禁实现：
- 行为优先级管理（Behavior Arbiter，属于 WP-4）；
- 打断抢占与恢复（属于 WP-4）；
- 随机加权行为选择（属于 WP-5）；
- 节律偏置、Agent 数据流注入或 80/15/5 指标；
- 操作实际窗口或播放器。

---

## 8. 验收标准

1. `ActivityRegistry` 与 `ActivityResolution` 模型强类型不可变；
2. 完整复用 WP-0 降级规则并支持方向镜像；
3. Vasu 与 Calico 跨宠物交叉验证 100% 通过；
4. 源码中绝对无宠物专属标识符污染；
5. 全量自动化测试通过，spec-graph 校验有效。
