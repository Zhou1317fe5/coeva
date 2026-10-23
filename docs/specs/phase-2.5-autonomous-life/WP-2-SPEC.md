---
id: companion-phase-2.5-wp2-vasu-v2
type: module-design
title: Phase 2.5 WP-2 规范：Vasu v2 Reference Pet 契约迁移与资产语义整编
parent: companion-architecture-design
depends-on:
  - companion-phase-2.5-wp0-behavior-semantics
  - companion-phase-2.5-wp1-pet-manifest
status: active
tags:
  - phase-2.5
  - wp-2
  - vasu-v2
  - reference-pet
  - pet-manifest
  - invariants
---

# Phase 2.5 WP-2 — Vasu v2 Reference Pet 契约迁移与资产语义整编

## 1. 目标与定位

WP-2 以 Coeva 第一主角 Vasu 为落地对象，实施 **Vasu v2 Reference Pet** 契约整编与规范迁移。

核心定位：
> **验证 WP-0（行为语义层）与 WP-1（Pet Manifest / Capability 契约）在真实生产宠物身上的表达力与严谨性；通过对现有 9 行 Atlas 与 Native Idle 资产的视觉语义重整，将被孤立废弃的资产盘活，使 Vasu 成为第一只原生遵循 `pet.json` (schema_version=2) 的标准参考宠物。**

---

## 2. 资产全景审计与语义映射 (Asset Semantic Mapping)

经过对 Vasu 物理图集（`spritesheet.webp`，8 列 × 9 行）与 Native Idle（`neutral` + `blink`）的逐项审计，确立真实视觉语义映射表：

| Asset / Row | 真实视觉表现 (Visual Meaning) | 过去运行时用途 | WP-0 行为类别 | 契约 Activity ID | 原子特征 (Traits) | 方向 | 契约判定 |
| :--- | :--- | :--- | :--- | :--- | :--- | :---: | :--- |
| **Native Idle** | 1024px 高精正视、温和端坐、稀疏眨眼 | 常驻桌面静止待机 | `IDLE` | `idle_native` | `quiet`, `stationary`, `solitary`, `low_energy` | `none` | **保留为 Ambient IDLE baseline** |
| **Row 0: `idle`** | 6 帧像素呼吸起伏、尾巴微摇 | 曾被 Native Idle 完全旁路 | `IDLE` | `idle_breathing` | `quiet`, `stationary`, `solitary`, `low_energy` | `none` | **保留为微动态 IDLE 备选序列** |
| **Row 1: `running-right`**| 8 帧向右自然步态快跑 | 鼠标向右拖拽 | `MOVE` | `run_right` | `active`, `locomotive`, `solitary`, `medium_energy` | `right` | **保留为原生向右位移** |
| **Row 2: `running-left`** | 8 帧向左自然步态快跑 | 鼠标向左拖拽 | `MOVE` | `run_left` | `active`, `locomotive`, `solitary`, `medium_energy` | `left` | **保留为原生向左位移** |
| **Row 3: `waving`** | 4 帧站立、单前爪友好挥手 | 投喂切片庆祝、鼠标悬停打招呼 | `GREET` | `wave` | `social`, `stationary`, `casual`, `medium_energy` | `none` | **保留为温和社交问候** |
| **Row 4: `jumping`** | 5 帧原地纵身轻跃、落定 | 移入跳跃、轻戳反馈 | `PLAY` | `hop` | `active`, `stationary`, `casual`, `medium_energy` | `none` | **保留为自发玩耍轻跳** |
| **Row 5: `failed`** | 8 帧倒地趴下、眩晕后爬起 | `PetState.ERROR` 故障（未用） | `REACT` | `stumble` | `stationary`, `casual`, `low_energy` | `none` | **保留为小挫折即时反应** |
| **Row 6: `waiting`** | 6 帧乖巧端坐、歪头打量注视 | 零调用（被彻底废弃孤立） | `OBSERVE` | `look_around` | `quiet`, `stationary`, `casual`, `low_energy` | `none` | **解除废弃，盘活为清醒注视** |
| **Row 7: `running`** | 6 帧正向奔走迈步 | 曾绑至 `WORKING` | `MOVE` | `trot` | `active`, `locomotive`, `casual`, `medium_energy` | `none` | **保留为正向小跑步态** |
| **Row 8: `review`** | 6 帧挠耳朵、托腮琢磨若有所思 | 麦克风语音输入状态 | `WORK` | `pondering` | `quiet`, `stationary`, `focused`, `low_energy` | `none` | **确立为做自己的小事（WORK）** |

---

## 3. Vasu v2 Capability 集合与缺口策略

Vasu 诚实声明当前物理资产真实支持的能力集合，不搞“将呼吸待机假冒成休眠”的虚假适配：

```text
Vasu v2 Declared Capabilities:
├── IDLE    (原生支持: idle_native, idle_breathing)
├── MOVE    (原生支持: run_right, run_left, trot)
├── WORK    (原生支持: pondering)
├── OBSERVE (原生支持: look_around)
├── PLAY    (原生支持: hop)
├── GREET   (原生支持: wave)
└── REACT   (原生支持: stumble)
```

### 缺口与降级规范
- **`SLEEP`（缺少专用蜷睡动画）**：依据 WP-0 标准降级链 `SLEEP` $\to$ `IDLE` 安全降级到静态在场，由 Validator 产生结构化 Diagnostic Warning；未来在专有美术轮次制作真正闭眼蜷睡资产后再行接入；
- **`REST`（缺少专用趴卧动画）**：依据 WP-0 标准降级链 `REST` $\to$ `IDLE` 安全降级。

---

## 4. Native Idle 重新定位 (Ambient IDLE Resource)

彻底解耦过去代码中“Native Idle = Vasu 整个生命”的生硬判断：
1. **职责下沉**：Native Idle（`vasu-native-canonical-hires.png` 与 `vasu-blink.png`）被规范为 Vasu 表达 `IDLE` 类别的一种表现层资源（`VisualBinding(ref="idle", format="native_idle")`）；
2. **多态共存**：与 Row 0 像素呼吸（`idle_breathing`）共同隶属于 Vasu 的 IDLE 动作池，为未来 WP-3 / WP-5 调度微动留出清晰契约结构。

---

## 5. Canonical `pet.json` (schema_version=2) 规范

`assets/pets/vasu/pet.json` 正式升级为 V2，内容包含：
- `schema_version: 2`
- `id: "vasu"`, `name: "Vasu"`
- `capabilities`: 7 大原生行为类别；
- `activities`: 10 个显式绑定的 `PetActivity`（均包含局部 ID、WP-0 标准类别、Traits、方向、Loop 与权重）；
- 同时保留 `spritesheetPath` 与 `spritesheet_path`，确保既有表现层 Loader 物理零破坏。

---

## 6. 契约反馈（Contract Feedback）

在将 Vasu 作为首个 Reference Pet 实施迁入的过程中，确认：
1. **WP-0 9 大类别与 11 项 Traits 表现力充足**：能自然涵盖端坐待机、微呼吸、左右奔跑、挥手问候、思考琢磨、好奇打量与自娱小跳；
2. **WP-1 VisualBinding 设计良好**：成功支持单一宠物内同时并存 `native_idle` 原画与 `spritesheet` 图集切片，未产生资产格式硬编码冲突；
3. **Fallback 降级验证有效**：诚实声明 7 类支持，在测试与 CLI 校验中精准提示 `sleep -> idle` 降级警告，契约闭环运行良好。

---

## 7. 显式非目标 (Explicit Non-goals)

WP-2 严格遵守边界约束，明确禁止：
- 实现 LifeScheduler 或自主随机轮播逻辑；
- 实现 BehaviorArbiter 打断抢占策略；
- 制作或引入未经评审的大量新动画资产；
- 修改 Memory V2.1 代码或数据；
- 破坏现有陪伴桌宠窗口启动与拖拽交互行为。

---

## 8. 验收标准

1. `assets/pets/vasu/pet.json` 正式成为 schema_version=2 的 Canonical Manifest；
2. 通过 `validate_pet_manifest` 与 `validate_pet_directory` 严格校验；
3. 单元测试与现有桌面 Smoke 测试全量通过；
4. spec-graph 校验有效。
