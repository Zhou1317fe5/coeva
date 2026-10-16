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
  - bugfix-postmortem
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
   - 在其外部抽象出统一的 `Body Control API`，供 Growth Core 驱动动画与气泡；
   - 具备屏幕边界硬裁剪、30px 边缘磁吸收纳（Peek Docking）、光标悬停探头展开与离开自动缩回。
2. **多 Agent 状态桥接（Connector Hub）**：
   - **Hermes 桥接**：利用 Hermes 生命周期 Hook（`pre_tool_call`, `post_tool_call`, `on_session_start`, `on_session_end`），向 Growth Core 汇报客观事件；
   - **Pi 桥接**：利用 Pi 的全局 extension 机制，向 Growth Core 汇报任务起止。
3. **随手投喂切片输入（Slice Feeding MVP）**：
   - 建立 Python 全局快捷键监听，默认 `Alt + Space`，**用户可在设置「桌面身体偏好 → 随手投喂切片」中自定义**（录制式录入，必须含 Ctrl/Alt/Shift/Win 修饰键；保存后立即重挂监听，无需重启）；
   - 呼出可自由拖动与记忆位置的极简半透明输入框，输入文字后敲击回车追加写入 `data/raw_slices.jsonl`；
   - 自动驱动桌宠做动作确认与温和气泡反馈。
4. **轻量心智与守卫（Growth Core v0.1）**：
   - 统筹决策：Agent 事件先经过 Growth Core 决策，再下发给桌宠 Body；
   - 注入前 14 天冷启动限频状态机（Day 1~3、Day 4~7、Day 8~14 渐进式破冰）；
   - 注入避风港模式（Sanctuary Mode）：检测到负面/抱怨情绪时，100% 保持安静，严禁说教；提供“🍃 收到。先放一放，我陪着你...”的温和接纳气泡；
   - 监测连续工作时长与夜间客观节律。

---

## 3. 核心接口与数据契约（Contracts）

### 3.1 Companion Body 控制契约（Body Control Contract）
Growth Core 与桌宠 Body 的内部通信协议（支持直接调用或本地 socket）：
- `set_state(state: str)`: `idle | thinking | working | happy | error | sleeping`
  **调用约束（硬·控制面与数据面彻底解绑）**：
  Agent 发送的任何高频微观工具事件（`Read` / `Bash` 耗时数十毫秒）、提示轮次变化均属于**只读数据面（Data Plane）**，
  100% 只静默落库（Chronicle）并供心智感知（StateWatcher），**严禁直接调用 `set_state` 驱动桌宠变幻姿态**。
  桌宠身体姿态的控制权（Control Plane）彻底归还人类交互（投喂切片、点击、闲置 60s 打瞌睡），
  从架构上根治了多 Agent 姿态踩踏与每分钟数百次高频抽搐奔跑。
- `say(text: str, ttl_ms: int = 4000)`: 在桌宠头顶弹出质朴气泡，ttl 后自动淡出（气泡自动做屏幕内安全边缘吸附，防止截断）。
  **调用约束（硬）**：气泡属控制面，任何来源（含 Agent 事件）都必须先经 Growth Core 审批。
  常规 Agent 遥测绝不发声；仅值得注意的极端事件（如 `tool_failure`）可发声，且受 Sanctuary / 每日配额 / 冷却三道门约束。
- `perform_action(action_id: str)`: 播放特定动作动画（如 `wave`, `jump`, `nod`, `rest`）

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

### 3.3 投喂快捷键配置契约（`data/agent_settings.json`）
```json
{
  "version": 2,
  "selected_pet": "tiko",
  "feeder_hotkey": "<alt>+<space>",
  "agents": {}
}
```
- **磁盘形式**：pynput canonical 组合串（修饰键顺序固定为 `ctrl → alt → shift → cmd`，保证同一组合只有唯一写法）；默认 `"<alt>+<space>"`。
- **展示形式**：`"Alt + Space"`、`"Ctrl + Alt + F"`，由 `hotkey_display()` 派生，磁盘值不参与展示。
- **校验不变量**：必须包含至少一个修饰键（Ctrl / Alt / Shift / Win）且恰有一个主键；非法输入**永不落盘**（`set_feeder_hotkey()` 抛 `ValueError`），磁盘值非法或缺失时载入回退默认。
- **生效方式**：变更后立即重建监听器（无需重启），托盘菜单项与桌宠点击气泡文案同步更新。
- **模块归属**：`src/feeder/hotkey.py` 独占热键域（`HotkeySpec` / `parse_hotkey` / `hotkey_from_qt` / `hotkey_display` / `GlobalHotkeyListener`）；Qt→pynput 键名表由两库自身枚举派生，不手写。

---

## 4. 验收标准（Acceptance Criteria）

- [x] **AC-1 (完全独立常驻)**：关闭所有 Agent 终端，桌面宠物依然在桌角自然呼吸、点击穿透、闲置入睡，内存维持在 60MB 左右（PySide6 进程）。
- [x] **AC-2 (多 Agent 数据面静默解绑)**：启动 Hermes、Pi、Codex 执行多步高频工具任务，所有事件 100% 完整、静默存盘进本地数据库（Chronicle）并供客观节律感知（StateWatcher），表现层桌宠身体姿态保持静止微呼吸（零 UI 频繁重绘与抽搐扰动），多 Agent 并发时不发生姿态踩踏。
- [x] **AC-3 (随手投喂体验)**：按全局快捷键，200ms 内唤起半透明输入框，输入文字回车后窗口秒隐，`data/raw_slices.jsonl` 成功增加一条有效记录，桌宠点头确认。
- [x] **AC-4 (避风港熔断)**：在投喂中输入带有“烦死了”、“全搞砸了”等负面情绪切片，系统静默存盘，严禁触发任何说教气泡，提供温和接纳反馈。
- [x] **AC-5 (快捷键可自定义)**：设置「桌面身体偏好 → 随手投喂切片」以录制式录入新组合键；保存后 `data/agent_settings.json` 的 `feeder_hotkey` 写入 canonical 串并**立即生效无需重启**；无修饰键的组合被拒绝且磁盘值不变；「↺ 恢复默认」回到 `Alt + Space`；托盘菜单与气泡文案跟随当前值；磁盘值非法或缺失时启动回退默认且不崩溃。

---

## 5. 缺陷排查与工程修复复盘（Bug Post-mortems）

为便于团队开发、后续交接与架构审查，记录在实际桌面联调中排查的关键缺陷及根治方案：

### 5.1 缺陷 1：全局热键与 GUI 线程死锁（Thread-safe Hotkey Bridge）
- **现象**：按 `Alt + Space` 弹出输入框后，窗口卡死、未响应，无法输入文字。
- **根因**：`pynput` 热键在 Windows 底层钩子工作线程触发，直接跨线程操作 Qt GUI 窗口方法，导致 Windows 消息泵与 Qt 事件循环死锁。
- **修复方案**：引入 `_QtSignalBridge(QObject)`，热键线程仅触发 Qt Signal，由 Qt 内部调度机制安全排队至 GUI 主线程执行，彻底根治卡死。

### 5.2 缺陷 2：窗口越界迷路与边缘探头收纳（Peek Docking & 30px Snap）
- **现象**：小猫拖拽没有屏幕边界限制，拖到屏幕外后彻底丢失；贴边缺乏半身隐藏的探头收纳感。
- **根因**：位移计算缺少 `screen.availableGeometry()` 裁剪；且全量包含在屏幕内，无法实现半身隐藏。
- **修复方案**：
  1. 增加屏幕可用区边界硬裁剪，严格保留至少 24px 在屏内，物理上不可能再被拖丢；
  2. 确立 30px 贴边吸附阈值（`EDGE_SNAP_DISTANCE_PX = 30`），贴近边缘时自动向外收纳，仅露半身；
  3. 托盘增加“📍 唤回伴生体 (居中重置)”应急菜单。

### 5.3 缺陷 3：屏幕边缘气泡文字截断（Speech Bubble Edge Clamping）
- **现象**：小猫靠右侧贴边时，头顶气泡依然按中心对称定位，导致气泡右半截被 Windows 屏幕右边界切断。
- **根因**：气泡坐标计算未做屏幕边界判定。
- **修复方案**：在 `SpeechBubble.anchor_to_pet` 中注入智能屏幕裁剪算法，右侧溢出时自动将气泡左推，保留 12px 安全边距；同时动态计算指示尾巴的相对横坐标（`_tail_relative_x`），使气泡文字完整居中的同时，尾巴依然精准指向小猫头部。

### 5.4 缺陷 4：子控件截获导致 Hover 离开事件失效（Cursor Polling Watcher）
- **现象**：小猫在边缘探头出来后，鼠标移开，小猫不会自动缩回。
- **根因**：Qt 内部 `QLabel` 截获了鼠标进入，导致父窗体没有稳定接收到 `leaveEvent`。
- **修复方案**：开启父子控件 `setMouseTracking(True)`，并引入 150ms 游标探针（`QCursor.pos()` 巡检），一旦鼠标脱离小猫与气泡包围盒，800ms 后必触发自动收纳。

### 5.5 缺陷 5：避风港无反馈误解（Empathic Acknowledgment Bubble）
- **现象**：输入心烦吐槽内容后，桌宠没有任何界面动作，用户无法确认系统是否响应。
- **根因**：过早采取了 100% 绝对静默，缺少最起码的“情绪被接纳”确认。
- **修复方案**：避风港状态下严禁任何说教或行动建议，但弹出非干预性温和气泡（`🍃 收到。先放一放，我陪着你...`），既守住底线，又消除了未响应的疑惑。

### 5.6 缺陷 6：HTTP 单线程阻塞与连接挂起（ThreadingHTTPServer & Connection Close）
- **现象**：外部调用一次格式错误或未正常关闭的 HTTP 请求后，后续所有请求（包括 `/api/status`）均发生超时挂起。
- **根因**：原 `CompanionHttpServer` 使用了标准库单线程阻塞式的 `HTTPServer`，当一个连接半开或被客户端中断时，单线程主循环被阻塞在当前 socket 读写中。
- **修复方案**：全面升级为并发 `ThreadingHTTPServer`，每个连接由独立工作线程处理；响应中显式增加 `Connection: close` 标头并置 `close_connection = True`，同时设置 `timeout = 5.0s`，彻底杜绝单次异常请求卡死整个服务。

### 5.7 缺陷 7：PI-Desktop 扩展未在注册表登记导致不可见（Registry Registration）
- **现象**：虽然将插件代码拷贝到了扩展目录，但在 PI-Desktop「设置 -> 插件」面板中完全找不到扩展。
- **根因**：PI-Desktop 插件管理严格依赖 `~/.pi-desktop/plugins/registry.json`，未在注册表中配置的插件不会被宿主加载和展示在 UI 中。
- **修复方案**：将插件规范化为标准已安装插件 `pi.companion-bridge`（桌面伴生体心跳桥接），通过 `PluginCheck` 格式校验，并在 `registry.json` 中完整写入其元数据、权限（`agent.extension`）与配置信息，实现在 PI-Desktop 界面中立即可见且生效。

### 5.8 缺陷 8：Windows PowerShell 双引号剥离与参数截断（PowerShell Invoke-RestMethod）
- **现象**：在 PowerShell 中执行包含转义双引号 `\"` 的 `curl -d "{\"key\":\"value\"}"` 时报错 `Invalid JSON`、`Port number not between 0 and 65535` 及 `Could not resolve host`。
- **根因**：PowerShell 的命令行解析引擎会预处理并剥离双引号中的反斜杠双引号，导致传给底层程序的不是合法 JSON，且包含空格的 message 文本被误切分为独立的主机名/端口参数。
- **修复方案**：规范在 Windows PowerShell 下的交互调用，推荐使用 PowerShell 原生 `Invoke-RestMethod`，或在 `curl` 中使用单引号包裹 JSON（在 PowerShell 中单引号是逐字字符串，内部无需反斜杠转义）。

### 5.9 缺陷 9：热键重挂时旧监听线程残留导致双重绑定（Listener Handoff Race）
- **现象**：在设置中自定义投喂快捷键并保存后，理论上旧组合应失效；但若热键在监听线程尚未完成启动时被替换，旧组合仍可能保持注册状态，出现新旧两个热键同时可用。
- **根因**：`GlobalHotkeyListener` 的监听器对象由工作线程在 `_run()` 内赋值。当 `stop()` 早于该赋值执行时，`stop()` 看到 `_listener is None` 便直接返回，而工作线程随后仍会创建并进入 `listener.join()`，使这个「已被替换」的监听器长期存活。
- **修复方案**：在 `_run()` 内创建监听器后检查 `self._running`——若已被停止，立即退出 `with` 块（触发 `GlobalHotKeys` 上下文清理），确保被替换的热键绝不残留；`stop()` 改为等待工作线程收尾（`join(timeout=2.0)`）并统一清空 `_listener` / `_thread` 引用，使「停止即完全释放」成为确定行为。回归测试 `test_listener_stop_releases_a_worker_that_has_not_started_yet` 锁定该顺序；已验证旧逻辑下该断言失败（监听器确实泄漏），新逻辑通过。

### 5.10 缺陷 10：Agent 事件直连气泡导致桌宠退化为日志直播（Intervention Gate on Agent Events）
- **现象**：接入 PI-Desktop 后，桌宠在编码会话中持续弹出气泡（约每次工具调用一条），密集时气泡几乎常驻不消失，
  状态动画也出现反复抽回首帧的抖动。
- **根因**：
  1. `/api/event` 与 Petdex `/state` 路径把每条带 `message` 的事件**无条件**交给 `controller.say`，
     完全绕过 `Body Control Contract` 规定的「气泡须经 Growth Core 审批」；
  2. `InterventionPolicy.evaluate_intervention()` 在生产代码中**没有调用方**（仅测试引用），
     桥接侧文案（`🤔 思考中` / `⚙️ 正在执行: <工具>` / `🎉 回合完成`）为硬编码，`SanctuaryGuard`
     也只覆盖切片投喂与桌宠点击两条路径；
  3. `SpeechBubble.show_message` 每条新消息重置 TTL，短于 TTL 的连续事件使气泡无法淡出；
  4. `PetWindow.apply_state` 在状态未变时同样调用 `player.play()`，把帧索引重置为 0。
- **修复方案**：
  1. 新增 `InterventionPolicy.allow_agent_bubble(event_type)`，作为 Agent 事件进入气泡的**唯一闸门**：
     常规遥测（`user_prompt` / `pre_tool_use` / `post_tool_use` / `task_complete` / `session_end`）
     一律只驱动状态动画、**绝不发声**；仅 `NOTABLE_AGENT_EVENTS`（当前为 `tool_failure`）可发声，
     并受 Sanctuary → 每日主动配额 → 冷却窗口（默认 60s）三道门约束；
     `_handle_event_on_main_thread` 与 `run_companion` 完成接线，状态动画保持直通；
  2. `apply_state(state, *, force=False)` 对同状态变为 no-op，仅在首次绘制、`load_pet`、`set_scale`
     重切图集时显式 `force=True`；
  3. Petdex `/state` 的 `idle` 改为映射 `session_end`（安静休息，不再庆祝），`needs_input` 映射到
     新增的 `AgentEventType.NEEDS_INPUT`；未知状态默认降级为 `pre_tool_use`（`agent_context`），
     避免 Agent 遥测冒充 `user_action`；
  4. `/state` 与 `/bubble` 共用 `_agent_may_speak()`，与 `/api/event` 采用同一套 enable / instance /
     allow_bubble 判定；`dispatch_json` 对未知 `event_type` 保守降级，杜绝 Qt 槽抛错。
- **回归测试**：`tests/test_core.py` 覆盖三道门；`tests/test_http_server.py` 端到端断言
  「完整回合状态照常流转、气泡零输出」，并锁定 `idle` 不庆祝与静音后 `/bubble` 被过滤。
  另以临时 harness 做变异验证：关闭闸门时同一回合产出 3 条气泡，开启后为 0，状态序列一致。

### 5.11 缺陷 11：Agent 微观工具事件绑定桌宠姿态导致高频抽搐与多 Agent 冲突（数据面与控制面彻底物理解绑）
- **现象**：Agent 在执行任务时，小猫在桌角极度频繁地乱动抽搐。实测一段 2 分钟对话中，1129 条事件引发了高达 **734 次状态切换**（`10:46:05.342` `pre_tool_use` WORKING -> 仅过 23ms `turn_end` IDLE -> 几秒后下一个工具 `pre_tool_use` WORKING）。
- **根因**：
  1. **微观工具粒度失配**：PI-Desktop 每执行完一个底层工具调用（如 `Read` 耗时 30ms），就会触发一次微观的 `turn_end`。系统把 `turn_end` 映射到 `IDLE`、把 `tool_call` 映射到 `WORKING`，导致小猫每调用一个工具就疯狂奔跑几十毫秒，接着立刻闪回待机，如此往复循环；
  2. **多 Agent 状态踩踏**：当后台有 Hermes 执行长任务、前台有 Pi 处于对话空闲、IDE 侧有其它代码补全 Agent 时，多个 Agent 的微观数据包毫秒级交替到达，桌宠姿态被强行覆盖，沦为混乱的数据包指示灯；
  3. **违背立项哲学**：系统违背了 `AGENTS.md §4` 规定的“控制面与数据面物理分离”硬约束，把 Agent 的只读工作遥测当成了驱动桌面实体表演的开关，严重干扰用户心流。
- **修复方案**：
  1. **彻底解绑**：移除 `run_companion.py` 中 `LocalEventBus` 对 `controller.set_state` 的直连回调，移除 `http_server.py` 中 `_handle_event_on_main_thread` 对桌宠姿态的篡改调用；
  2. **数据面与控制面归位**：
     - **Data Plane（数据面）**：所有 Agent 发来的高频微观工具调用、思考、报错或轮次结束，**100% 只作为只读证据静默存入 Chronicle 档案库与 StateWatcher 中，对桌面表现层零干扰**；
     - **Control Plane（表现层）**：桌宠姿态主权彻底回归**人类与桌面自然节律**（正常工作时静默微呼吸 Idle、投喂切片时跳跃确认 Jump、离开 60 秒自然打瞌睡 Sleep、鼠标触碰或点击自然唤醒），不再沦为任何 Agent CLI 的低级进度条外壳。
- **回归测试**：`tests/test_http_server.py::test_agent_events_do_not_override_pet_posture_nor_print_bubbles` 完整模拟 Agent 包含 prompt -> 多个 tool calls -> turn end 的多步任务流，断言控制面 `controller.states == []`（姿态保持安宁，不产生任何抽搐乱动），且数据面 `len(bus.history) == 3` 完整无漏静默落盘。
