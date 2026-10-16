# Changelog（项目变更与交接日志）

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - Fix: Agent 事件直连桌宠（静默陪伴回归）

### 🐛 Fixed（缺陷修复）
- **Agent 气泡绕过 Growth Core 三道门（P0）**：`/api/event` 曾把每条带 `message` 的事件无条件
  交给 `controller.say`，而 `InterventionPolicy.evaluate_intervention` 在生产代码中零调用方，
  文案硬编码在桥接侧。一次 27 回合的编码会话实测会弹 ≈111 条气泡（每次工具调用一条），
  气泡 TTL 3s 且新消息重置计时，导致气泡常驻不消失，桌宠退化为 Agent 日志直播机。
  现新增 `InterventionPolicy.allow_agent_bubble(event_type)`：常规遥测（prompt / tool call /
  turn end / session end）一律**只动状态不发声**，仅 `tool_failure` 这类值得注意的事件可发声，
  且受 60s 冷却 + 每日主动配额双重约束，同时满足 DESIGN §2.3 的 80/15/5 比例与
  SPEC §2.6「沉默是有效的成功状态」。**状态动画保持直通，反应速度不变。**
- **Sanctuary 不覆盖 Agent 事件路径（P0）**：`guard.is_active` 原先只在切片投喂与桌宠点击两条
  路径被检查，用户处于情绪熔断状态时 Agent 仍会弹气泡。现 `allow_agent_bubble` 第一道门即
  Sanctuary 检查，熔断期间 Agent 事件 100% 静默（仅动画）。
- **`apply_state` 同状态重播导致动画抖动（P1）**：`apply_state` 原先无条件 `play()`，把帧索引
  重置为 0；Agent 每回合重复下发同一状态（每次工具调用一次），使跑动/工作动画反复抽回首帧。
  现同状态为 no-op，仅在 `force=True`（首次绘制、换装、换缩放）时重播。
- **Petdex `idle` 被误映射为「回合完成」（P1）**：`POST /state` 曾把 `idle` 与 `completed` 合并为
  `task_complete`，Agent 一空闲就触发庆祝动画与气泡。现 `idle → session_end`（安静休息），
  `needs_input` 映射到新增的 `AgentEventType.NEEDS_INPUT`（`waiting` 动画）。
- **`/bubble` 与 `/state` 绕过权限门控（P1）**：两处端点原先不检查 Agent 开关与气泡开关。
  现共用 `_agent_may_speak()`，与 `/api/event` 走同一套 enable / instance / allow_bubble 判定。
- **未知事件类型会让 Qt 槽抛异常（P1）**：`dispatch_json` 现对未知 `event_type` 保守降级为
  `pre_tool_use`（agent_context），不再让外部进程传入的脏值在渲染槽中抛错。
- **`/state` 未知状态劫持用户归因（P1）**：原先默认 `user_prompt`（唯一 `user_action`/`durable`
  事件类型），会让 Agent 遥测冒充用户主动决策；现默认降级为 `pre_tool_use`。

### 🧪 Tests（新增测试，70 项全绿）
- `tests/test_core.py`：`allow_agent_bubble` 的 3 道门（常规遥测静默、冷却到期、Sanctuary 与
  配额熔断）；
- `tests/test_http_server.py`：端到端回归——模拟完整回合（prompt → tool call → turn end）
  断言「状态照常流转、气泡零输出」；Petdex `idle` 不庆祝、Agent 静音后 `/bubble` 被过滤。

---

## [Unreleased] - Phase 2A (Chronicle Foundation)

### 🚀 Added（新增）
- **本地记忆与证据档案库（Chronicle Store, `src/memory/store.py`）**：
  - Python 原生 SQLite（WAL 模式），`data/companion_chronicle.db`；
  - 两张表 `slices` / `events` + 一个 `evidence` **视图**（视图而非实体表，避免证据双写导致事实源分裂）；
  - `import_slices_jsonl()`：对 `data/raw_slices.jsonl` 幂等导入（`INSERT OR IGNORE`），损坏行跳过不中断；
  - 查询层：`list_slices` / `search_slices` / `list_evidence` / `list_episodes` / `stats`；
  - `prune()`：按 `retention_class` 删除超期 `transient` 事件（默认 30 天），`durable` 行永不触碰。
- **行为归因门（Attribution Gate, `src/core/attribution.py`）**：
  - 纯函数 `classify(event_type) -> (provenance, retention_class)`，无状态、无 I/O、无 LLM；
  - 只有 `user_prompt` 具备用户归因（`user_action`），其余（含未知事件类型）一律降级为 `agent_context`；
  - 这是架构规范 Invariant 2「Agent 行为 ≠ 用户行为」在代码中的唯一落点。
- **Agent 事件持久化**：`LocalEventBus` 新增可选 `store` 依赖；Phase 1 的事件流原先仅存内存、进程重启即清零，现已落盘（保持控制面/数据面分离，写库不触发 UI）。
- **只读 Chronicle HTTP 端点**：`/api/chronicle/{stats,slices,evidence,episodes}` 与 `POST /api/chronicle/slices/search`；
  按 `client_address` 做回环判定，**非回环来源一律 403**（WSL 跨网 Agent 路径不受影响）。
- **规范图谱**：`docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md`（2A MVP 范围）与对应 task-spec。
- **随手投喂快捷键可自定义（Slice Feeder Hotkey, `src/feeder/hotkey.py`）**：
  - 设置「桌面身体偏好 → 随手投喂切片」新增**录制式**录入框（点击后直接按下组合键即捕获，Esc 放弃）与「↺ 恢复默认」按钮；
  - 持久化于 `data/agent_settings.json` 的 `feeder_hotkey`，存 pynput canonical 串（如 `"<ctrl>+<alt>+f"`），默认 `"<alt>+<space>"`；
  - 校验不变量：必须含 Ctrl/Alt/Shift/Win 修饰键且恰有一个主键，**非法值永不落盘**（抛 `ValueError`），磁盘值非法或缺失时启动回退默认；
  - 保存后**立即重挂监听器，无需重启**；托盘菜单项与桌宠点击气泡文案跟随当前值；
  - Qt→pynput 键名映射表由两库自身枚举派生，不手写硬编码表。
  - 顺带修复热键重挂的旧监听线程竞态（旧组合可能残留为双重绑定），详见 phase-1 规范 §5.9。

### 🧪 Tests（新增测试，当前全库 69 项全绿）
- `tests/test_memory.py`：AC-1~AC-6、AC-9 及事件幂等键、Episode 分组；
- `tests/test_chronicle_http.py`：AC-7 回环限定与端到端只读接口；
- `tests/test_feeder.py`：快捷键归一化/幂等、拒绝裸键与未知键、Qt 组合键映射、监听器非法组合拒绝、旧监听线程释放回归；
- `tests/test_connectors.py`：`feeder_hotkey` 默认值、写入-重载往返、非法值拒绝、磁盘非法值回退；
- `tests/test_body.py`：设置窗口显示已存快捷键、录制落盘与信号、无修饰键拒绝、恢复默认。

### 📌 Known Limitations（如实记录）
- **检索未用 FTS5**：实测（SQLite 3.53.1）`unicode61` 与 `trigram` 分词器对 **2 字中文词均 0 命中**，
  FTS5 在中文场景默认不可用。MVP 采用 `LIKE`，切片 > 10k 时再引入中文分词器。
- **事件幂等键覆盖范围有限**：hook 载荷不带时间戳，服务端打戳，同一条 hook 重投会得到两个不同 id；
  §4.3 的幂等只覆盖"同对象重复写入"。端到端去重需 connector 侧提供稳定 id。
- **2A 无用户可见新功能**：桌宠行为与 Phase 1 一致，本阶段只建立证据输入流与档案库。
- **Pattern / Hypothesis / Chapter 等推理与叙事层全部延后**，逐项启动条件见规范 §8 待做表。

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
  - Hermes 生命周期连接器 (`src/connectors/hermes_connector.py`)；
  - 本地伴生体 HTTP 服务 (`src/connectors/http_server.py`)，暴露 `127.0.0.1:17321` 标准端点；
- **实装 Clawd 风格多 Agent 设置与介入管理 (Multi-Agent Settings)**：
  - 建立 Agent 持久化过滤规则层 (`src/connectors/settings.py`，存储至 `data/agent_settings.json`)；
  - 在 HTTP 服务与事件总线注入多 Agent 开关逻辑，支持物理拦截未勾选 Agent 的遥测事件；
  - 实现原生深色风格多 Agent 设置面板 (`src/body/settings_window.py`)，支持在托盘菜单直接呼出，自由开启/屏蔽 PI-Desktop、Hermes、Codex CLI、Claude Code 等；
  - PI-Desktop 伴生体面板 (`renderer/index.html`) 同步增加实时多 Agent 遥测列表与开关卡片；
  - **实装多环境实例细分隔离 (Windows vs WSL)**：支持同一 Agent（如 Hermes、Pi CLI、Codex）在 Windows 本地与 WSL (Ubuntu-24.04) 独立识别心跳并分别控制开关，实现精细化环境隔离；
  - **独立区分 PI-Desktop 与 Pi CLI**：卡片上保留 PI-Desktop（桌面工作区扩展）的同时，新增 Pi CLI（终端命令行智能体）独立卡片与双端实例控制；
  - **迁移 Clawd 风格 Hook 自动管理 (AgentHookManager)**：实现跨 Windows 与 WSL 的 Hook 物理就绪检测 (`check_hook_status`)、一键自动部署 (`install_hook`) 与干净卸载 (`uninstall_hook`)，消除用户手动找路径配置的认知负担，并在设置界面展示实时 HOOK 徽章与操作按钮。
  - **吸纳 Petdex 协议与资产生态 (Petdex Interop)**：
    - 经过对 `crafter-station/petdex`（2.3 万行 Zig 源码）的深入审计，确立“坚守 Python 心智基座，但吞噬 Petdex 生态”决议；
    - 原生兼容 Petdex 9 状态 SpriteSheet 规范 (`src/body/animation.py` 中的 `PetdexAtlasLoader`)，可直接无缝挂载社区海量宠物图谱；
    - 在 HTTP 服务原生兼容 Petdex 协议端点 (`POST /state`、`POST /bubble`、`GET /health`、`GET /whoami`)，无缝接纳社区开源 Agent 桥接。
  - **实装 Petdex/SpriteYard 完整标准资产图谱与内置宠物 (Builtin Pets)**：
    - 增强 `PetdexAtlasLoader`：支持透明空帧自动探测与剔除 (`trim_empty_frames`)，避免行末空帧引起透明闪烁；
    - 增强 `PetWindow`：自动感知并加载 Petdex `pet.json` 与 `spritesheet.webp` 规范，全面打通 `PetState`（IDLE, SLEEPING, THINKING, WORKING, HAPPY, ERROR, WAITING）到 Petdex 9 状态动作切片的完整映射；
    - 支持动态无缝切宠 (`PetWindow.load_pet`) 与托盘动态图标响应；
    - 内置三大精选开源宠物：**Tiko**（好奇单眼小机器人 · 默认）、**Debug Duck**（调试小黄鸭）、**Wangcai**（布偶猫），均已放置于 `assets/pets/` 并通过标准包格式校验；
    - 托盘菜单新增「🔄 切换伴生体」子菜单，支持随时一键在三大内置宠物间平滑切换。
    - **新增全方位大小缩放调节 (Pet Scale Adjustment)**：
      - 增强 `SpriteSheet.scaled()`：突破整数倍限制，支持 `float` 连续任意缩放（平滑插值与最近邻保持清晰）；
      - 支持 **Ctrl + 鼠标滚轮** 在桌面上无级缩放桌宠（伴随 `🔍 伴生体大小: X%` 瞬态气泡反馈）；
      - 设置面板「桌面身体偏好」新增「🔍 伴生体缩放与尺寸调节」卡片，提供 50%、75%、100%、125%、150% 快捷档位；
      - 系统托盘新增「🔍 伴生体大小」子菜单；
      - 缩放比例持久化至 `data/body_position.json`，重启自动恢复。
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
- **修复 HTTP 服务阻塞风险**：`http_server.py` 从单线程 `HTTPServer` 升级为并发 `ThreadingHTTPServer`，增加 5s 超时与 `Connection: close` 保护，杜绝异常连接挂起整个服务。
- **修复 PI-Desktop 扩展不可见**：将伴生体桥接插件部署为标准安装插件 `pi.companion-bridge`，并在 `~/.pi-desktop/plugins/registry.json` 中配置注册项，确保在 PI-Desktop「设置 -> 插件」中直接可见并生效。
- **规范 Windows PowerShell 调用方式**：排查并记录 PowerShell 下 curl 转义剥离双引号导致 Bad Hostname 和 Invalid JSON 根因，明确推荐采用 PowerShell 原生 `Invoke-RestMethod`。

### 📋 Handover Notes（团队交接与开发须知）
1. **测试运行**：本地执行 `.venv\Scripts\pytest -v` 必须保证 19 个测试全绿。
2. **规范校验**：任何修改如果改变了接口或边界，必须同步更新 `docs/specs/` 并执行 `spec_validate`。
3. **代码规范**：提交代码前必须通过 `ruff check .` 与 `mypy src --strict`。
