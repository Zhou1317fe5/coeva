---
id: companion-phase-1-runtime-and-bridge
type: module-design
title: 第一阶段规范：独立常驻桌宠 Runtime、多 Agent 桥接与随手投喂 MVP
parent: co-evolving-companion-root
depends-on:
  - companion-architecture-design
status: active
tags:
  - phase-1
  - mvp
  - openclaw-tamagotchi
  - growth-core
  - slice-feeding
  - python-native
---

# 第一阶段规范：独立常驻桌宠 Runtime、多 Agent 桥接与随手投喂 MVP

## 1. 源码深度剖析与候选底座定调（Codebase Analysis & Selection）

在实际 clone 并检视 `openclaw-tamagotchi`、`OpenPet`、`Clawd on Desk`、`Project AIRI` 四大源码库后，第一阶段的技术栈与项目分工正式定音：

| 项目 | 源码行数与语言 | 许可证 | 架构定位与分工 |
| :--- | :--- | :--- | :--- |
| **openclaw-tamagotchi (首选底座)** | **1,724 行纯 Python 3.11+ (PySide6)** | **MIT** | **Desktop Body 代码起点**：极其轻量、结构规整，自带透明置顶窗口与 Sprite 动画；修改半径最小，100% 自主可控。 |
| **Clawd on Desk** | 16.8 万行 JavaScript (Electron) | AGPL-3.0 | **Connector 宝库**：不作为底座，直接借鉴/移植其为 Hermes、Pi 编写的成熟 Hook 逻辑。 |
| **OpenPet** | 7,717 行 Rust + TS | GPL-3.0 | **接口思想借鉴**：借鉴其标准的 Body 控制接口设计（`set_state`, `say`, `perform_action`）。 |
| **Project AIRI** | 38 万行巨石 Monorepo (51 pkgs) | MIT | **长期跨端架构参考**：作为中长期的架构理念与移动端参考，当前阶段不引入其庞大依赖。 |

---

## 2. 模块职责与边界（Responsibility & Boundary）

### 本阶段必须交付（In Scope）：
1. **独立桌面身体底座（Desktop Body）**：
   - 基于 `openclaw-tamagotchi` 建立 Windows 11 下的完全独立常驻（开机自启、置顶、透明通道、点击穿透、闲置入睡）；
   - 在其外部抽象出统一的 `Body Control API`，供 Growth Core 驱动动画与气泡。
2. **多 Agent 状态桥接（Connector Hub）**：
   - **Hermes 桥接**：利用 Hermes 生命周期 Hook（`pre_tool_call`, `post_tool_call`, `on_session_start`, `on_session_end`），向 Growth Core 汇报客观事件；
   - **Pi 桥接**：利用 Pi 的全局 extension 机制，向 Growth Core 汇报任务起止。
3. **随手投喂切片输入（Slice Feeding MVP）**：
   - 建立 Python 全局快捷键监听（如双击 `Alt` 或 `Win+Shift+P`）；
   - 呼出极简半透明输入框，输入文字后敲击回车追加写入 `data/raw_slices.jsonl`；
   - 自动驱动桌宠做轻微点头动作或 3 秒气泡确认。
4. **轻量心智与守卫（Growth Core v0.1）**：
   - 统筹决策：Agent 事件先经过 Growth Core 决策，再下发给桌宠 Body；
   - 注入前 14 天冷启动限频状态机（Day 1~3、Day 4~7、Day 8~14 渐进式破冰）；
   - 注入避风港模式（Sanctuary Mode）：检测到负面/抱怨情绪时，100% 保持安静，严禁说教；
   - 监测连续工作时长与夜间客观节律。

---

## 3. 核心接口与数据契约（Contracts）

### 3.1 Companion Body 控制契约（Body Control Contract）
Growth Core 与桌宠 Body 的内部通信协议（支持直接调用或本地 socket）：
- `set_state(state: str)`: `idle | thinking | working | happy | error | sleeping`
- `say(text: str, ttl_ms: int = 4000)`: 在桌宠头顶弹出质朴气泡，ttl 后自动淡出
- `perform_action(action_id: str)`: 播放特定动作动画（如 `wave`, `jump`, `nod`）

### 3.2 随手投喂切片存储契约（`data/raw_slices.jsonl`）
```json
{
  "id": "slice_20261015_001",
  "timestamp": "2026-10-15T15:30:00+08:00",
  "actor": "user",
  "source": "manual_feed",
  "content": "读到《悉达多》关于河流的段落，突然意识到不必每次都赶路...",
  "mood_flag": "neutral | frustrated | reflective"
}
```

---

## 4. 验收标准（Acceptance Criteria）

- [ ] **AC-1 (完全独立常驻)**：关闭所有 Agent 终端，桌面宠物依然在桌角自然呼吸、点击穿透、闲置入睡，内存维持在 60MB 左右（PySide6 进程）。
- [ ] **AC-2 (Hermes / Pi 联动)**：启动 Hermes 或 Pi 跑任务，Growth Core 接收到事件并在 1 秒内驱动桌宠展示对应动作。
- [ ] **AC-3 (随手投喂体验)**：按全局快捷键，200ms 内唤起半透明输入框，输入文字回车后窗口秒隐，`data/raw_slices.jsonl` 成功增加一条有效记录，桌宠点头确认。
- [ ] **AC-4 (避风港熔断)**：在投喂中输入带有“烦死了”、“全搞砸了”等负面情绪切片，系统静默存盘，严禁触发任何说教气泡。
