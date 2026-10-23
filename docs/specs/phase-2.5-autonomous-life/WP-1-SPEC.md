---
id: companion-phase-2.5-wp1-pet-manifest
type: module-design
title: Phase 2.5 WP-1 规范：Pet Manifest 与 Capability 契约 (Pet Manifest & Capability Contract)
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
status: active
tags:
  - phase-2.5
  - wp-1
  - pet-manifest
  - capability-contract
  - behavior-semantics
  - invariants
---

# Phase 2.5 WP-1 — Pet Manifest & Capability Contract

## 1. 目标与职责定位

WP-1 基于 WP-0 冻结的通用“行为语义层”（`companion-phase-2.5-wp0-behavior-semantics`），建立 Coeva 官方统一的 **Pet Manifest / Capability Contract**。

核心职责：
> **使每只宠物通过其声明式的 Manifest，明确声明“自己能如何表达通用 BehaviorIntent”，从而保证生命系统 / Scheduler 与具体宠物、具体资产彻底解耦。**

### 核心分层拓扑
```text
BehaviorIntent (WHAT / WHY, Coeva Runtime / Growth Core)
    ↓ (解耦边界：Scheduler 零宠物专属词汇)
PetActivity (HOW, Pet Manifest 声明能力与表达方式)
    ↓ (表现边界：只记录视觉引用，不直接解析二进制)
Animation / Asset (VISUAL EXECUTION, Desktop Body 表现层)
```

---

## 2. 核心原则与硬约束

1. **INV-B1 ~ INV-B6 必须继续严格成立**：
   - 行为语义不得由动画文件名决定；
   - Scheduler 不得知道具体宠物 Activity ID 或资产路径；
   - 宠物能力必须由 Manifest 显式声明；
   - Intent 表达 WHAT，Activity 表达 HOW，Animation 负责视觉执行；
   - 缺少可选能力属于合法常态；
   - IDLE 本身即为合法 Quiet Presence 行为。
2. **纯声明式数据（Pure Declarative Data）**：
   - Manifest 必须是纯 JSON 静态数据，严禁嵌入 Python 脚本、条件表达式或动态调度逻辑；
3. **宠物局部标识符（Pet-local Activity ID）**：
   - Activity ID（如 `reviewing`, `typing`, `sorting`）仅具有宠物局部作用域，仅由 Pet Runtime / Registry 消费，严禁暴露至 Scheduler 领域。

---

## 3. Canonical Manifest (`pet.json` V2)

系统继续采用 `pet.json` 作为唯一官方 Canonical Manifest，不引入运行时的 `pet.yaml`。
通过显式 `schema_version: 2` 标识 V2 格式。

### 结构范式
```json
{
  "schema_version": 2,
  "id": "vasu",
  "name": "Vasu",
  "description": "A calm, curious, independent river-otter companion.",
  "format": "atlas",
  "spritesheet_path": "spritesheet.webp",
  "native_idle_path": "native_idle.json",
  "capabilities": [
    "idle",
    "sleep",
    "move",
    "work",
    "observe",
    "play",
    "greet",
    "react"
  ],
  "activities": [
    {
      "id": "idle_breathe",
      "category": "idle",
      "traits": ["quiet", "stationary", "solitary", "low_energy"],
      "direction": "none",
      "visual": {
        "ref": "idle",
        "format": "spritesheet"
      },
      "loop": "loop",
      "interruptible": true,
      "duration_ms": null,
      "weight": 1.0
    },
    {
      "id": "reviewing",
      "category": "work",
      "traits": ["quiet", "stationary", "solitary", "focused", "low_energy"],
      "direction": "none",
      "visual": {
        "ref": "review",
        "format": "spritesheet"
      },
      "loop": "loop",
      "interruptible": true,
      "weight": 1.0
    }
  ]
}
```

---

## 4. PetActivity 领域模型与元数据契约

在 `src/core/behavior/` 建立不可变（frozen）强类型领域模型，包含以下元数据：

1. **`id: str`**：宠物内部唯一的 Activity 标识符；
2. **`category: BehaviorCategory`**：必须为 WP-0 冻结的 9 大顶层行为类别之一；
3. **`traits: frozenset[ActivityTrait]`**：必须来自 WP-0 冻结的 11 项原子特征标签；
4. **`direction: BehaviorDirection`**：`NONE`, `LEFT`, `RIGHT`；
5. **`visual: VisualBinding`**：绑定表现层资产标识（如状态名、行号或资源键名）；
6. **`loop: LoopMode`**：有限循环枚举（`once`, `loop`, `hold_last`）；
7. **`interruptible: bool`**：是否允许打断（默认为 True，打断策略由后续 WP-4 Arbiter 决定）；
8. **`duration_ms: int | None`**：Activity 自身的固有预期时长元数据，正整数或 None；
9. **`weight: float`**：同类 Activity 的相对偏好权重（必须 `> 0.0`，默认为 1.0；WP-1 不实现随机选择）；
10. **`tags: tuple[str, ...]`**：不可包含任何图像文件扩展名（`.gif`, `.png` 等），捍卫 INV-B1。

---

## 5. Capability 契约与双向一致性法则

Manifest 必须通过 `capabilities: frozenset[BehaviorCategory]` 显式声明其支持的行为大类。

### 5.1 Required Baseline 与 Optional Capabilities
- **Required Baseline**：`IDLE`, `SLEEP`, `MOVE`；
  - 宠物必须支持 `IDLE`（必须有原生 Activity 实现，不可降级为空）；
  - `SLEEP` 若未原生声明，可根据 WP-0 Fallback 链降级到 `IDLE`；
  - `MOVE` 若未原生声明，按 WP-0 语义保持原地，不回退到假移动；
- **Optional Capabilities**：`REST`, `WORK`, `OBSERVE`, `PLAY`, `GREET`, `REACT`；
  - 缺失任何 Optional 能力均属于合法常态，运行时依据 WP-0 链式降级。

### 5.2 双向一致性法则
1. **完整覆盖**：`capabilities` 中声明的每一个行为类别，必须在 `activities` 列表中至少拥有 1 个有效的 Activity 实现；
2. **闭环约束**：`activities` 中出现的每一个 Activity，其 `category` 必须存在于已声明的 `capabilities` 中；
3. **唯一性约束**：同一 Manifest 中的 `activity.id` 严禁重复。

---

## 6. Visual Binding 边界规范

`PetActivity` 仅记录对表现层资产的间接引用，不越权直接加载或解析图像：
```text
PetActivity.visual
    ↓
VisualBinding(ref="review", format="spritesheet", mirror=False)
    ↓
Body AnimationPlayer / Asset Loader
```
- **职责划分**：Manifest Validator 仅静态检查引用的视觉资产或动画标识在宠物包中是否真实有效（例如存在 `spritesheet.webp` 或 `theme.json`），绝不由资产文件名反推行为语义。

---

## 7. Loop 语义规范

为避免模糊布尔值造成歧义，WP-1 明确定义有限的 `LoopMode`：
- **`ONCE ("once")`**：单次播放，播完后恢复基线状态；
- **`LOOP ("loop")`**：循环播放，直至收到新的行为指令或被打断；
- **`HOLD_LAST ("hold_last")`**：单次播放，并在最后一帧保持静止，直至被后续动作替代。

---

## 8. Direction 与镜像契约

1. Activity 明确声明 `direction`: `NONE`, `LEFT`, `RIGHT`；
2. **镜像适配**：若宠物仅有一侧移动资产（如仅有向右奔跑），则在向左移动时通过 `VisualBinding(mirror=True)` 声明由渲染层水平翻转执行，Scheduler 绝不需要知道 `running-left` 与 `running-right` 的存在。

---

## 9. Fallback 静态兼容性校验

Manifest Validator 依据 WP-0 `SEMANTIC_FALLBACK_CHAINS` 校验静态兼容性：
- 确保宠物的 capabilities 能够覆盖系统的最小运行需求；
- 对任意可能派发的 BehaviorCategory，确保其在当前宠物身上要么有直接支持，要么能通过链条安全落在一个已声明的类别上。

---

## 10. V1 向后兼容策略

为不破坏已有 `vasu` 与 `calico` 生产加载，采用双轨透明适配：
1. **自动版本识别**：若 `pet.json` 缺少 `schema_version` 或 `schema_version == 1`，透明路由至 `V1PetManifestAdapter`；
2. **Vasu (Atlas + Native Idle)**：根据 9 行 Atlas 映射原生 `idle`, `running`, `jumping`, `waiting`, `review`, `waving`, `failed` 等 Activity，自动映射为满足契约的 V2 Manifest；
3. **Calico (Theme APNG)**：解析 `theme.json` 中的动画状态，自动生成符合规范的 V2 Manifest；
4. **现有 Loader 零退化**：`src/body/window.py` 与 `test_body.py` 现有测试 100% 保持正常运行。

---

## 11. 严格校验器 (Validator Rules & Diagnostics)

提供统一的 `validate_pet_manifest` 与 `validate_pet_directory` 接口，提供清晰可读的诊断输出：
- 格式良好，指明具体宠物 ID 与出错字段（例如 `Pet 'foo': declared capability 'work' has no activities`）；
- 杜绝隐式 `KeyError` 或裸异常。

---

## 12. 核心不变量表

- **INV-M1 (Declarative Integrity)**：Manifest 是纯数据，禁止可执行脚本。
- **INV-M2 (Local Identifier Seclusion)**：Activity ID 仅在宠物内部有效，严禁进入 Scheduler。
- **INV-M3 (Capability-Activity Parity)**：声明能力与 Activity 集合必须双向一致闭环。
- **INV-M4 (Required Baseline Safety)**：无论能力多寡，宠物必须具备安全的 IDLE 基线与降级路径。
- **INV-M5 (Visual Indirection)**：Activity 仅保存对视觉资产的逻辑绑定，不耦合物理渲染格式。

---

## 13. 显式非目标 (Explicit Non-goals)

以下内容严格留存后续工作包：
- **WP-2**：Vasu 资产制作与规范重整；
- **WP-3**：`ActivityRegistry` 动态运行时与 `select_activity()` 降级选择器；
- **WP-4**：抢占打断策略（Behavior Arbiter）；
- **WP-5**：Life Scheduler 与行为概率分布；
- **WP-6**：昼夜节律联动与 Sanctuary 偏置；
- **WP-7**：80/15/5 律可观测性指标。

---

## 14. 验收标准

1. `PetManifest`、`PetActivity`、`VisualBinding` 均被定义为强类型不可变对象；
2. `pet.json` V2 规范正式确立，并通过双轨适配器 100% 兼容既有 Vasu 与 Calico；
3. 校验器能够准确拦截缺失 Required、双向不一致、非法 Traits/Direction/Loop 等错误并提供友好日志；
4. 架构扫描测试确凿证明 LifeScheduler 领域不包含任何特定宠物名称与图像资产文件；
5. Spec 挂入规范图谱并通过 `spec_validate`；全量自动化测试通过。
