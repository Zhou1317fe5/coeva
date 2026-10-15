---
id: companion-architecture-design
type: architecture-design
title: 共生型 AI 成长伙伴：总体系统架构设计规范
parent: co-evolving-companion-root
status: active
tags:
  - architecture
  - body-mind-separation
  - system-disciplines
  - growth-core
  - connectors
  - airi-disciplines
---

# 共生型 AI 成长伙伴：总体系统架构设计规范

## 1. 架构核心定理：Body ≠ Brain ≠ Memory（终极收敛拓扑）

经过对开源候选底座的真实源码审计与架构论证，系统确立**“极简小身体 + 独立大心智”**架构：

```text
┌─────────────────────────────────────────────────────────────┐
│ 1. 独立成长心智层 (Growth Core - 永续核心资产)               │
│    Python 本地服务 (Our Core Proprietary System)             │
│    - 归因引擎 (Attribution Filter: 过滤 Agent 循环，提取选择)│
│    - 节律感知器 (State Watcher: 连续工作/深夜作息检测)       │
│    - 介入决策器 (Intervention Policy: 80%沉默 / 避风港熔断) │
│    - 心理灵活性六大透镜 (ACT / 时间整合 / 未知开放周期性反思) │
│    - 随手投喂切片输入处理器 (Slice Receiver)                │
│    - 人生章节档案库 (Chronicle / Growth Chapters)            │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               │ Normalized Events             │ Companion Contract
               │ (客观事件推流)                │ set_state() / say()
               ▼                               ▼
┌─────────────────────────────┐ ┌─────────────────────────────┐
│ 2. 多 Agent 感知连接层      │ │ 3. 独立桌面身体 (Desktop Body)│
│ (Connector Hub)             │ │ (以 openclaw-tamagotchi 为基准)
│ 借鉴 Clawd 的成熟 Hook 逻辑: │ │ - 纯 Python 3.11+ / PySide6 │
│ - Hermes Companion Hook     │ │ - 1,700 行精炼代码，MIT 协议│
│ - Pi Global Extension       │ │ - 透明通道、置顶、点击穿透  │
│ - Codex CLI Session Watcher │ │ - 像素 Sprite、动画状态机   │
└─────────────────────────────┘ └─────────────────────────────┘
```

**关键控制流反转：**
> **Agent 不直接控制宠物。**  
> Agent 的操作仅作为客观事件输入给 Growth Core；由 Growth Core 结合用户的长期状态、当前负荷与避风港规则，统筹决策宠物表现（例如：连续工作 4 小时后，Hermes 的跑任务事件不会让宠物兴奋跳跃，而是安静坐在桌角陪伴）。

---

## 2. 核心架构决议（Decisions & Trade-offs）

### 决议 1：以 `openclaw-tamagotchi`（MIT）为 Desktop Body 代码起点
- **原因**：源码仅 1,724 行纯 Python，代码质量极高（通过 strict mypy / Ruff / 89 个测试），纯逻辑与 Qt 视图天然解耦。无任何第三方臃肿依赖，100% 自主可控。
- **契约封装**：仅继承其透明窗口和 Sprite 动画层，对其上层封装标准的 `Pet Body Contract`（`set_state`, `say`, `perform_action`），确保未来若更换身体底座，心智层零改动。

### 决议 2：借鉴 `Clawd on Desk` 的 Connector 逻辑，拒绝其代码膨胀
- **原因**：Clawd on Desk 的 16.8 万行代码深度耦合了 Coding Agent 会话仲裁，不适合做伴生底座；但其为 Hermes、Pi 编写的 Hook 逻辑是现成的宝库，直接借鉴移植为轻量 Connector。

### 决议 3：借鉴 `OpenPet` 的纯粹 Body API 思想
- **原因**：OpenPet 证明了桌宠身体应当是“纯粹不干预业务的受控体”，心智完全外置。

### 决议 4：控制面与数据面物理分离，兼顾伴生体 Stage 空间保护
- **原因**：将高频感知数据与低频控制决策物理隔离开，同时在交互上严格保护角色的圣域空间，杜绝桌面杂乱。

---

## 3. 伴生体核心架构与交互规范（Core System Disciplines）

本项目的核心架构与交互设计规范包括：

### 3.1 控制平面与数据平面分离（Planes Separation）
- **数据平面（Data Plane）**：Hermes/Pi 的高频工具调用日志、会话行更新、实时状态流。这些数据属于只读高频流，仅流向 Growth Core 的归因队列，不直接触发 UI 频繁重绘。
- **控制平面（Control Plane）**：伴生体状态机变更（Idle/Thinking/Resting）、气泡话术（Say）、避风港熔断切换、前 14 天冷启动限频仲裁。控制指令经过三道门（Evidence/Permission/Timing）过滤后低频下发，确保桌面极度静谧。

### 3.2 伴生体空间圣域准则（Clean Stage Principle）
- **屏幕空间归属于伴生体**：桌宠常驻区域严禁堆砌长篇报表、状态栏、密集图标或常驻控件。
- **瞬态交互即用即走**：随手投喂切片输入框采用半透明、极简设计，快捷键呼出后输入即存，回车秒隐，不侵占工作主视线。
- **深度配置与档案分离**：深层心智配置与人生章节阅读收拢在独立的二级设置或本地 Markdown 档案（Chronicle）中，绝不直接贴在桌宠头顶。

### 3.3 严格依赖注入与边界纪律（Boundary Discipline）
- 依赖注入（DI）仅用于外部 I/O 边界（本地 SQLite 数据库、大模型 API 网关、全局快捷键系统钩子）。
- 内部纯函数与逻辑规则（如 ACT 六大透镜评估、避风港关键词判定、冷启动限频计数）保持无副作用与纯粹性，杜绝滥用全局状态。

---

## 4. 系统核心硬约束（System Invariants）

1. **Invariant 1 (Host Inversion)**: Companion Body 是唯一常驻桌面宿主，任何 Agent 的启动或退出不影响桌宠的生存与待机状态。
2. **Invariant 2 (Attribution First)**: 严禁将 Agent 的自主重试或长链路循环直接推断为用户人格。进入心智模型的必须是 `User Choice`。
3. **Invariant 3 (Observe by Default)**: 默认观察，90% 的检测信号静默吞掉。不得频繁弹窗说教。
4. **Invariant 4 (Sanctuary Guard)**: 检测到负面情绪或心烦意乱时，自动熔断一切反思和引导逻辑，100% 保持安静。
5. **Invariant 5 (Minimal & Decaying Data)**: 原始切片与事件必须随时间衰减，长期档案只沉淀提炼后的高阶章节（Growth Chapters）。
6. **Invariant 6 (Control & Data Plane Decoupling)**: 外部 Agent 数据流只进心智归因层，桌宠动作由心智控制面低频派发，严禁外部事件直通 UI 造成状态抽搐。
7. **Invariant 7 (Clean Stage)**: 桌面常驻形态必须保持纯粹像素伴生状态，所有交互输入框必须满足“快捷键呼出、输入后即隐、无界面残留”的瞬态约束。
