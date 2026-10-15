# Changelog（项目变更与交接日志）

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.1.0] - 2026-10-15 (Sprint 1 Milestone)

### 🚀 Added（新增功能与架构）
- **独立常驻桌面伴生体（Desktop Body）**：
  - 基于 PySide6 实现无边框、透明背景、置顶悬浮、点击穿透的桌面挂件窗口 (`src/body/window.py`)；
  - 内置 Sprite 像素帧动画播放器 (`src/body/animation.py`)，支持 2x 像素最近邻插值；
  - 封装 `BodyController` 遵循 `Body Control Contract` 规范；
  - 头顶质朴气泡 (`src/body/speech_bubble.py`)，支持动态居中与淡出。
- **随手投喂切片输入器（Slice Feeder）**：
  - 全局快捷键呼出半透明输入弹窗 (`src/feeder/overlay.py`)，按回车瞬时存盘，失焦秒隐；
  - 本地追加流存储管道 (`src/feeder/storage.py`)，持久化至 `data/raw_slices.jsonl`；
  - 线程安全全局热键监听 (`src/feeder/hotkey.py`)。
- **独立成长心智与守卫（Growth Core）**：
  - 避风港模式 (`src/core/sanctuary.py`)：负面情绪关键词自动熔断说教逻辑；
  - 前 14 天冷启动限频状态机 (`src/core/cold_start.py`)：Day 1~3 / Day 4~7 / Day 8~14 渐进式破冰配额；
  - 节律感知器 (`src/core/state_watcher.py`)：监测连续工作 3h+ 与凌晨 00:00~05:00 作息；
  - 介入决策器 (`src/core/intervention.py`)：执行证据门、权限门、时机门过滤。
- **多 Agent 状态桥接层（Connector Hub）**：
  - 归一化事件流 (`src/connectors/contracts.py`)；
  - 本地事件总线 (`src/connectors/event_bus.py`)；
  - Hermes 生命周期连接器 (`src/connectors/hermes_connector.py`)。
- **规范与文档图谱**：
  - `SPEC.md`、`docs/specs/SPEC.md`、`docs/specs/phase-1-runtime-and-bridge/SPEC.md`；
  - `DESIGN.md`（伴生体空间圣域准则）；
  - `AGENTS.md`（代码与工程行为规范）。

### 🐛 Fixed（实测缺陷排查与根治）
- **修复全局热键卡死**：采用 `_QtSignalBridge` 解决 `pynput` 钩子线程跨线程调用 Qt GUI 引发的消息泵死锁。
- **修复窗口拖拽越界丢失**：增加屏幕可用几何区域硬边界裁剪，严格保留至少 24px 在屏内，杜绝拖丢。
- **修复边缘气泡文字截断**：在 `SpeechBubble` 引入屏幕边缘自动左推算法（保持 12px 边距），并动态微调指示小尾巴指向。
- **实装边缘探头与半身收纳（Peek Mode）**：支持将桌宠贴近屏幕左/右边缘 30px 时自动收纳入墙边仅露半身；鼠标悬停自动探头展开，离开 800ms 自动缩回。
- **修复 Hover 离开事件偶发失效**：开启父子控件鼠标追踪，并注入高频光标探针巡检。
- **修复避风港无反馈误解**：触发避风港时弹出温和接纳气泡（`🍃 收到。先放一放，我陪着你...`），守住不批评、不说教底线的同时给予视觉确认。
- **修复输入框固定不可动**：`SliceFeederOverlay` 升级为可自由拖拽，并持久化记忆位置 (`data/feeder_position.json`)。

### 📋 Handover Notes（团队交接与开发须知）
1. **测试运行**：本地执行 `.venv\Scripts\pytest -v` 必须保证 19 个测试全绿。
2. **规范校验**：任何修改如果改变了接口或边界，必须同步更新 `docs/specs/` 并执行 `spec_validate`。
3. **代码规范**：提交代码前必须通过 `ruff check .` 与 `mypy src --strict`。
