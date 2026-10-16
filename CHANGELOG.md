# Changelog（项目变更与交接日志）

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - Architecture: 彻底切断 Agent 执行与桌宠身体姿态的直连（物理隔离）

### 🚀 Architecture & Philosophy（架构哲学回归）
- **控制面与数据面物理分离（AGENTS.md §4 硬约束落地）**：
  - **根因复盘**：此前系统残留了将每个微观工具调用（`Read` / `Bash` 耗时 30ms）直连桌宠动画的玩具式逻辑。实测一段 2 分钟对话中，事件 1129 条导致了 **734 次状态毫秒级震荡**（`running 30ms` -> `idle 50ms` -> `running 60ms`）。这不仅造成小猫像抽搐般频繁狂奔，而且在多 Agent（Pi + Hermes + Codex）并发时，会导致毫秒级覆盖踩踏；
  - **彻底解绑**：移除 `run_companion.py` 中 `LocalEventBus` 对 `controller.set_state` 的回调直连，移除 `http_server.py` 中 Agent 事件对桌宠姿态的强行篡改；
  - **各归其位**：
    - **数据面（Data Plane）**：所有 Agent 发来的高频微观工具事件，**100% 只作为只读证据静默存入 Chronicle 档案库与 StateWatcher 心智节律中，对桌面表现层零干扰**；
    - **桌面表现层（Desktop Body）**：桌宠姿态主权彻底回归**人类与自然节律**（正常工作时静默微呼吸 Idle、投喂切片时轻快确认 Jump、离开 60 秒自然打瞌睡 Sleep、鼠标触碰或点击自然唤醒），不再沦为任何 Agent CLI 的低级进度条外壳。

---
### 🔧 Changed（行为调整）
- **默认尺寸改为 50%**：`DEFAULT_SCALE` 由 `1.0` 改为 `0.5`，并移除 `run_companion.py` /
  `src/body/main.py` 中显式传入的 `scale=1`（它覆盖了默认值，导致改常量无效）。
  首次启动的伴生体更小巧、更不打扰；用户仍可通过设置面板、托盘菜单或 `Ctrl + 滚轮` 放大。
  已保存过尺寸的用户不受影响——`data/body_position.json` 中的偏好会覆盖该默认值。

### 🐛 Fixed（缺陷修复）
- **摩擦归因时间序因果缺陷（P1 · 认知偏差）**：原 `PatternBuilder._detect_friction_response` 仅判断
  会话内是否存在 `tool_failure` 和 `user_prompt`，未检查二者发生的前后时间顺序。由于大多数会话
  均以用户 Prompt 启动（`timestamp` 早于报错），当 Agent 遭遇报错并自主修复时，用户的起始指令被错误
  识别为“报错后的纠偏介入”，导致模式挖掘将 Agent 自主修复错误归因为 `pat_friction_recovery`（用户主动干预）。
  现引入严格时间序因果约束：仅当 `user_prompt` 的时间戳严格晚于 `tool_failure` 时才归为用户干预；
  若 Agent 自主修复未被打断，则如实归因为 `pat_agent_autonomous_recovery`（充分自主修复空间 / 信任委派），
  并映射至“接纳不确定性”与“调节灵活性”心智透镜。同时优化 `_detect_delegation_ratio`，支持双向对流判定。
- **拖拽贴边后不再自动收纳（P0 · 用户报告）**：`_has_moved` 仅在鼠标按下时重置，拖动结束
  (`mouseReleaseEvent`) 后从未复位；而 `leaveEvent` 与 150ms 游标轮询两条自动收纳路径都要求
  `not self._has_moved`。因此**只要用拖拽把宠物贴到边缘，收纳逻辑就被永久关闭** ——
  鼠标悬停时弹出，移开后却一直杵在原地，看起来像"忘了自己贴边"。
  仅从磁盘恢复贴边的路径（不设该标志）正常，所以这个 bug 一直被掩盖。
  现于释放时清除该标志（它本就只用于"拖动过程中"抑制收纳）。
  回归测试 `test_docked_pet_retracts_again_after_being_dragged_to_the_edge` 完整走
  按下 → 拖到边缘 → 释放 → 悬停 → 移开 → 收纳，并断言窗位移回贴边位置；
  已用"还原修复 → 测试失败并指出 `_has_moved` 未清除 → 恢复后通过"验证有效。
- **大尺寸贴边后整体消失（P0 · 用户报告）**：贴边收纳时只保留固定 `PEEK_REVEAL_WIDTH_PX = 24px`，
  而 Petdex 图集自带**透明留白**且留白随缩放放大（实测 tiko 32px、wangcai 19px、debug-duck 15px）。
  一旦 `留白 × 缩放 ≥ 24`，留着的那 24px 全是透明像素，宠物即不可见 —— tiko 在 0.92 倍以上、
  wangcai 在 1.85 倍以上必然"消失"，与"变大后贴边就没了"完全对应。
  现新增 `measure_art_padding()`（列向 max 扫描 Qt alpha 缓冲，整张图集约 40ms）在装载与缩放时
  测量**最坏帧**的左右留白，贴边露出量改为 `留白 + PEEK_VISIBLE_ART_PX`（按边计算），
  6 处固定常量用法全部改走 `_peek_reveal_px()`。回归验证覆盖 3 宠物 × 8 缩放 × 左右两侧
  共 48 组合，真实美术像素全部 > 0；旧逻辑在同等组合下多处为 0（不可见）。
- **面板动作按钮 3/4 失效（P1）**：PI-Desktop 控制台发送 `thinking` / `working` / `celebrating`，
  而 `BodyController` 只认 `think` / `work` / `jump`，三者在 `action_map.get()` 中全部回落 IDLE，
  点了没反应。现将动作表提为模块级 `ACTION_STATES` 并补齐这些别名；
  新增契约测试**直接解析面板 HTML**，任何按钮 id 与动作表漂移即测试失败
  （已用"注入漂移 → 测试报出三个缺失 id → 还原后通过"验证）。
- **设置页第 3 页为纯静态文案（P1）**：避风港与冷启动两张卡片写着固定说明，看着像配置项却不可配、
  也不反映真实状态。现改为**实时状态显示**：避风港显示"已激活 / 未激活"，
  冷启动显示"第 N 天 · 当前阶段 · 今日配额与剩余次数 · 深度心理分析是否允许"，
  每次切换到该页刷新（`refresh_core_status()`）；未接入实例时明确显示"未接入"而非假装可用。

### ✨ Added（新增功能）
- **闲置 60 秒自动入睡（P2）**：DESIGN §2.1 早有要求，但全仓无任何闲置定时器，入睡只能由
  `session_end` 或托盘菜单触发，等于桌宠作息被 Agent 生命周期绑架。现实现
  `IDLE_SLEEP_AFTER_MS = 60_000` 单次定时器：任何状态变化重置计时；入睡后仅"真活动"
  （鼠标悬停、点击、收到气泡）唤醒。顺带修正 `assets/pets/claw/pet.yaml` 中矛盾的
  `sleep_after_idle_sec: 120`（该文件从未被代码读取）与 DESIGN 的 60 秒对齐。
- **探头招手（P2）**：DESIGN §2.1 的"悬停时探出头向用户招手"此前只做了位移、没有动作。
  现鼠标进入时播放一次招手（HAPPY 帧，1.4s 后自动归于 IDLE），且不会覆盖入睡状态与进行中的招手。

### 📝 Docs（规范与决策）
- **DESIGN §2.1** 标注眼球跟随（Eye-tracking）**延后原因**：现有 Petdex 素材是扁平烘焙图
  （单张 atlas，192×208/帧，无独立眼睛图层），瞳孔与身体烤在一起无法单独平移，
  强做会露出透明空洞；需美术提供独立眼睛图层或瞳孔偏移变体后才能实现。
- **Phase 2 SPEC 新增 §4.5 切片双写契约**：明确 Chronicle 为唯一事实源、
  `data/raw_slices.jsonl` 为可重建的人类可读导出/手机同步通道；新读取路径只准读 Chronicle。
  对应待做项由"待确认"改为"已决定保留双写"。

### 🧪 Tests（新增测试，80 项全绿）
- `tests/test_body.py`：贴边可见性（3 宠物 × 6 缩放 × 两侧真实像素断言）、
  动作按钮契约（解析面板 HTML）、设置页实时状态（含未接入分支）、闲置入睡与招手。

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

### 🧪 Tests（新增测试，当时全库 75 项全绿）
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
