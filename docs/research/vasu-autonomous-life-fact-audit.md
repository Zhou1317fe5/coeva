# Coeva / Vasu Autonomous Life & Native Idle 事实审计报告
## ——Phase 2.5 重构前桌面伴生体真实机制全景审计

> **审计基准与原则声明**：
> - 审计时间：2026-10-18
> - 代码库基线：Git main 分支最新稳定版（Memory V2.1 冻结态，全量 159 项测试持续通过）
> - 审计重点：**桌面伴生体 Vasu 真实物理与动画行为、Native Idle 机制、节律与交互仲裁事实**。
> - 审计准则：严格区分**代码事实（Code Fact）**、**运行时事实（Runtime Fact）**、**推断（Inference）**与**风险（Risk）**。无证据项显式标注为 `Unknown`，不修改任何代码、资产与数据库，不假设未来方案。

---

## 1. Executive Summary（执行摘要）

本轮审计系统回答了核心问题：**“Vasu 现在到底是怎么活着的？”**。核心事实结论如下：

1. **Vasu 在运行时的生命本质：双帧眨眼交替器（Two-Frame Blink Alternator）**：
   - 当 Vasu 作为当前桌宠加载时，`NativeIdleConfig.load()` 成功加载 `assets/pets/vasu/native_idle.json`。
   - 在 `PetState.IDLE` 状态下，`AnimationPlayer` 定时器被**完全停止**，系统常驻展示高精度静态原画 `neutral`（1024x1024）。
   - 唯一的自主行为是由 `_native_blink_timer` 每隔 8~18 秒触发一次持续 160ms 的 `blink` 帧切换。
   - **Vasu 资产图集（`spritesheet.webp`）第 0 行的 6 帧 `idle` 动画在常规运行时被 100% 旁路覆盖，从未播放**。

2. **自主生活例程与昼夜节律在 Vasu 身上被完全阻断（Circadian Completely Bypassed for Vasu）**：
   - 尽管 `src/core/circadian.py` 定义了精细的 6 大生活时间段（`night_sleep`、`morning_work` 等）并在 `window.py:_start_autonomous_routine()` 中设计了丰富的做工/闲暇行为；
   - **但在代码事实中，`_schedule_next_autonomous_routine` 与 `_start_autonomous_routine` 第一行均显式执行了 `if self._native_idle_frames is not None: return`**！
   - 自动化测试 `test_vasu_native_idle_and_core_interactions` 明确断言 `assert not window._autonomous_timer.isActive()`。
   - **结论：Vasu 此时此刻在静止状态下绝对不会自主走动、打字、扫地、发呆或随昼夜转换姿态。在用户不操作电脑的 30 分钟里，Vasu 只会孤立地眨眼约 120 次**。

3. **零行为调度器与零仲裁系统（No Behavior Scheduler / LWW Reality）**：
   - 架构中**完全不存在** `BehaviorScheduler`、`BehaviorArbiter`、`ActionQueue`、`PrioritySystem` 或统一的冷却管理器。
   - 所有状态变迁采用**纯粹的后发覆盖模式（Last-Write-Wins, LWW）**，并依赖散落在各处的单发 QTimer（`_wave_timer`、`_jump_settle_timer`、`_nap_timer` 等）在超时后暴力恢复 IDLE。
   - 存在多个状态踩踏与时序竞态 Bug：例如悬停打招呼触发的 1400ms 定时器会在用户提交切片后硬性重置开心姿态，鼠标轻掠桌面会彻底摧毁用户在托盘主动设置的免打扰休眠。

4. **数据面与控制面彻底隔离（Strict Data/Control Plane Decoupling）**：
   - 审计确认系统忠实执行了数据面铁律：Hermes / Pi / Codex 的工具调用、报错、推理遥测**绝无任何直接驱动 Vasu 身体动画的旁路代码**。
   - `StateWatcher` 仅维护工作时长与深夜布尔值供干预门（Intervention Policy）查询；`LocalEventBus` 的建议状态在生产运行时被解耦，未接入任何 UI 槽函数。

5. **80 / 15 / 5 比例属于完全不可测量的设计愿景（Zero Observability）**：
   - 运行时缺乏任何针对静默时长、主动发声次数、被动交互次数与用户操作频次的统计埋点，无数据能证明产品符合 80/15/5。

---

## 2. Current Body State Machine（当前身体状态机全景）

### 2.1 状态与图集资产映射事实

Vasu 拥有两套物理资产体系：
1. **高精度 Native Idle 资产**：`assets/vasu/reference/vasu-native-canonical-hires.png`（`neutral`）与 `assets/vasu/production/v2.1-native-desktop-idle/vasu-blink.png`（`blink`），尺寸均为 1024x1024；
2. **标准 Petdex 9 行精灵图集**：`assets/pets/vasu/spritesheet.webp`（1536x1872，每帧 192x208，共 9 行 8 列）。

各状态对应的候选资产及运行时触发事实全表如下：

| State (`PetState`) | 候选资产顺序（代码事实：`window.py:505`） | 触发源 (Trigger) | 权限拥有者 (Owner) | 优先级 | 动画时长 / 循环 | 结束后恢复路径 | 运行时真实使用事实 (Runtime Used) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`IDLE`** | `native_idle` (若存在)；回退 `["idle"]` (Row 0) | 启动初始化、交互超时归位、状态重置 | `PetWindow`, `BodyController` | 无 (0) | 常驻静止；每 8~18s 眨眼 160ms | 自身维持 | **✅ 核心常驻**。Vasu 下表现为 Native Idle，Atlas Row 0 被完全覆盖不播放。 |
| **`THINKING`** | `["review", "waiting", "idle"]` $\to$ Vasu 命中 Row 8 (`review`) | Feeder 开启语音监听 (`_on_voice_clicked`)；`/api/action` | `SliceFeederBar`, HTTP API | 无 (0) | 6 FPS, 循环播放 | 需外部显式重置为 IDLE | **🟡 极低频**。仅在点击 Feeder 麦克风图标时触发。Agent 推理不触发。 |
| **`WORKING`** | `["running", "running-right", "walk", "idle"]` $\to$ Vasu 命中 Row 7 (`running`) | `/api/action` (`"action": "work"`) | HTTP API 外部调用 | 无 (0) | 8 FPS, 循环播放 | 需外部显式重置为 IDLE | **❌ 孤立**。生产中 Agent 遥测不驱动该状态，仅作为保留接口。 |
| **`HAPPY`** | `["waving", "jumping", "idle"]` $\to$ Vasu 命中 Row 3 (`waving`) | 提交切片 (`_on_slice_submitted`)；鼠标悬停打招呼 (`_start_greeting`) | `SliceFeederBar`, `PetWindow` | 无 (0) | 6 FPS, 循环播放（悬停由 `_wave_timer` 截断为 1400ms） | `_wave_timer` (1400ms) 超时调用 `apply_state(IDLE)` | **✅ 高频**。投喂切片及鼠标进入窗体（且未触发跳跃）时展示。 |
| **`ERROR`** | `["failed", "idle"]` $\to$ Vasu 命中 Row 5 (`failed`) | `/api/action` (`"action": "error"`) | HTTP API 外部调用 | 无 (0) | 6 FPS, 循环播放 | 需外部显式重置为 IDLE | **❌ 孤立**。代码中 Agent `tool_failure` 不驱动该状态，正常体验不会出现。 |
| **`SLEEPING`**| `["sleep", "idle"]` $\to$ Vasu 无 sleep，回退 Row 0 (`idle` at 3fps) | 托盘菜单选择“休眠”；`/api/action` (`"sleep"`) | 托盘菜单, HTTP API | 无 (0) | 3 FPS, 循环播放；附带 45s 猫席定时器 (`_nap_timer`) | 45s 后 `_wake_up()` 自动唤醒，或鼠标 hover 强行打断唤醒 | **🟡 低频**。手动进入；因缺专用睡眠帧，表现为半速慢动作 IDLE。 |
| **`WAITING`** | `["waiting", "idle"]` $\to$ Vasu 命中 Row 6 (`waiting`) | 无运行时直接调用源 | - | 无 (0) | 6 FPS, 循环播放 | - | **❌ 彻底废弃**。虽然图集有第 6 行，但全工程没有一行代码调用 `apply_state(PetState.WAITING)`。 |
| *(Transient)* **Hover Jump** | 直接播放 Row 4 (`jumping`) | 鼠标移入窗体 (`enterEvent` $\to$ `_trigger_hover_jump`) | `PetWindow` | 隐式优先 | 8 FPS, 单次播放 (`loop=False`)，时长约 705ms | `_jump_settle_timer` (705ms) 超时调用 `apply_state(current_state)` | **✅ 核心高频**。悬停冷却 5s，游标掠过桌宠时的第一反应。 |
| *(Transient)* **Directional Drag** | 直接播放 Row 1 (`running-right`) 或 Row 2 (`running-left`) | 鼠标左键按住拖拽且水平位移 $> 1$ px | `PetWindow` (`mouseMoveEvent`) | 物理抢占 | 8 FPS, 循环播放 | 松开鼠标 (`mouseReleaseEvent`) 判定是否贴边，若非停靠则恢复 IDLE | **✅ 核心高频**。桌面拖拽时的奔跑搬家反馈。 |
| *(Transient)* **Body Poke** | 直接播放 Row 4 (`jumping`) | 鼠标左键点击桌宠未发生拖动 (`mouseReleaseEvent`) | `PetWindow` (`play_poke_reaction`) | 隐式优先 | 6 FPS, 单次播放，时长 1200ms | `_wave_timer` (1200ms) 超时恢复 IDLE | **✅ 核心高频**。轻戳伴生体交互动作。 |

---

## 3. Native Idle Runtime（Native Idle 真实机制审计）

### 3.1 资产与加载事实（代码事实：`src/body/animation.py:34-87`）
`assets/pets/vasu/native_idle.json` 完整内容：
```json
{
  "neutral": "../../vasu/reference/vasu-native-canonical-hires.png",
  "blink": "../../vasu/production/v2.1-native-desktop-idle/vasu-blink.png",
  "blink_interval_min_ms": 8000,
  "blink_interval_max_ms": 18000,
  "blink_duration_ms": 160
}
```
`NativeIdleConfig.load()` 读取并严格校验上述字段为正整数，随后在 `window.py:_load_native_idle_frames()` 中将两张 1024x1024 的 PNG 按当前窗口缩放比（`_scale`，默认 0.5）进行高质量缩放，缓存为 `_native_idle_frames = (neutral_pixmap, blink_pixmap)`。

### 3.2 运行机制分析
1. **单一两帧切换**：它不是动画池，不是状态序列，不是概率转移图，而纯粹是一个**稀疏双帧定时交替器**。
2. **算法实现**（`window.py:533-572`）：
   - 进入 IDLE 时，调用 `_activate_native_idle()`；
   - 立即将 Label 像素设置为 `neutral`（睁眼正常态）；
   - 启动 `_native_blink_timer`，时间设为 `random.randint(8000, 18000)` ms；
   - 定时器超时触发 `_start_native_blink()`：将 Label 像素设置为 `blink`（闭眼态），发射 `native_blink_started` 信号，并启动 `_native_blink_restore_timer`（160ms 单发）；
   - 160ms 后恢复 `neutral`，并重新随机调度下一次眨眼。
3. **上下文感知能力评估**：
   - **完全不感知**时间（Circadian）、用户键盘/鼠标活动、Agent 工作状态、Sanctuary 模式及历史共识。
   - **零记忆**：不维护任何行为历史栈，仅在两个 Pixmap 对象间来回切换。

### 3.3 结论判定：
**当前 Native Idle 本质上仅仅是一个“带随机间隔的眨眼定时器（Sparse Blink Timer）”，不具备任何“行为调度器（Behavior Scheduler）”的性质**。

---

## 4. Circadian Runtime（昼夜节律机制与在 Vasu 上的失效应证）

### 4.1 理论设计（代码事实：`src/core/circadian.py`）
模块设计了完善的 24 小时自然人类作息模型，划分为 6 大区间：
- `NIGHT_SLEEP` (23:00 - 07:30): 允许 `dozing`、`waking`，暂停间隔 10~25 分钟；
- `MORNING_WAKE` (07:30 - 09:00): 允许 `waking`、`yawning`、`thinking`，暂停间隔 1.5~3 分钟；
- `MORNING_WORK` (09:00 - 12:00): 工作期（`is_work_phase=True`），允许 `review`、`waiting`、`running` 等，暂停间隔 25~50 秒；
- `MIDDAY_SIESTA` (12:00 - 14:00): 允许 `yawning`、`dozing`、`waiting`，暂停间隔 2~4 分钟；
- `AFTERNOON_FOCUS` (14:00 - 18:30): 工作期，高频专注做工与审查；
- `EVENING_LEISURE` (18:30 - 23:00): 闲暇期，允许 `jumping`、`waving`、`running-right` 等。

### 4.2 运行时事实：Vasu 端 100% 旁路阻断
全局搜索确认 `get_schedule_for_time()` 仅在 `src/body/window.py` 内部被调用 4 次（行 477、706、725、782）。但在关键路径中：

```python
# src/body/window.py:455
if state == PetState.IDLE and self._native_idle_frames is not None:
    self._autonomous_timer.stop()
    self._autonomous_done_timer.stop()
    self._in_autonomous_routine = False
    self._activate_native_idle()
    return  # <--- 直接截断，后续调度完全不执行

# src/body/window.py:704
def _schedule_next_autonomous_routine(self, *, initial: bool = False) -> None:
    if self._native_idle_frames is not None:
        return  # <--- Vasu 直接返回

# src/body/window.py:716
def _start_autonomous_routine(self) -> None:
    if self._native_idle_frames is not None or ...:
        return  # <--- Vasu 直接返回
```

### 4.3 事实定性：
1. **对于非 Vasu 伴生体（如 Calico）**：Circadian 是一个静态的“时间段 $\to$ 允许动作列表”映射表，通过 `_autonomous_timer` 周期性随机挑选动作播放。其依然缺乏主动时钟轮询（时间跨越整点不会主动切换姿态，必须等上一个例程自然结束才重查）。
2. **对于官方默认的 Vasu**：**Circadian 逻辑代码存在，但在运行时执行率为 0%**。所有设计好的晨间伸懒腰、午休打盹、黄昏玩耍全部被 `_native_idle_frames is not None` 的防御守卫扼杀在入口处。

---

## 5. Human Interaction Overrides（用户交互与覆盖链路）

| 用户交互动作 | 触发函数及入口 | 产生 Body State / 动画 | 冷却时间 (Cooldown) | 结束后恢复路径 | 潜在问题与竞争风险 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Cursor Hover** (悬停) | `window.py:enterEvent` | 若非停靠且非睡眠，优先触发 `jumping` (Row 4)；冷却未到触发 `waving` (Row 3) | Jump: 5,000ms；Wave: 120,000ms | Jump: 705ms 超时恢复原状态；Wave: 1400ms 超时恢复 IDLE | **打断休眠**：无论用户是否主动设置免打扰，鼠标滑过窗口会强行唤醒伴生体 (`_wake_up`)。 |
| **Hover Jump** (悬停轻跳) | `window.py:_trigger_hover_jump` | 独立播放 `jumping` (Row 4, 8 FPS, 单次) | 5,000ms | `_jump_settle_timer` (705ms) $\to$ `apply_state(current_state, force=True)` | 动画播放期间若发生拖拽，检查 `_has_moved` 虽防住归位，但未重置计时器。 |
| **Body Poke / Click** (轻戳) | `window.py:mouseReleaseEvent` $\to$ `play_poke_reaction` | 播放 `jumping` (Row 4, loop=False) | 无冷却 | `_wave_timer` (1200ms) 超时恢复 IDLE | 若伴生体已在说话，连续点击会导致动画重播，同时派发多次 AI 对话请求。 |
| **Mouse Drag** (拖拽) | `window.py:mouseMoveEvent` | 位移 $\ge 4$px：右移 `running-right` (Row 1)，左移 `running-left` (Row 2) | 无 | 松开鼠标 (`mouseReleaseEvent`)：吸附停靠则进入停靠，否则 `apply_state(current_state)` | 拖拽速度过快跨屏时可能触发系统边界光标丢失。 |
| **Speech Bubble** (气泡发声) | `window.py:say` | 身体动画不变；若睡眠则唤醒，若停靠则滑动展开并设置回弹定时器 | 无 | 气泡自身 TTL 超时隐藏；若展开则 `_retract_timer` 超时缩回 | 气泡展开时若发生快速鼠标进出，可能导致 `_retract_timer` 竞态。 |
| **Feeder Bar** (投喂栏打开) | `window.py:open_feeder_input` | 唤醒伴生体，展开停靠，在身下锚定弹出输入条；身体动画不变 | 无 | 输入完成或 Esc 退出隐藏 | Vasu 不知道输入栏何时聚焦，无“低头注视输入”的协同姿态。 |
| **Feeder Slice Submit** | `window.py:_on_slice_submitted` | `apply_state(PetState.HAPPY)` (播放 `waving`) | 无 | `run_companion.py` 判断情绪后下发 `perform_action("rest")` 或 `"jump"` | **定时器覆盖 Bug**：若在此前 500ms 触发过悬停打招呼，`_wave_timer` 会在 900ms 后强制恢复 IDLE。 |
| **Edge Snapping** (边缘停靠) | `window.py:mouseReleaseEvent` | 水平贴边 $<30$px：`_docked_edge = "right" / "left"`，缩进屏幕仅留 24px | 800ms 缩回延迟 | 鼠标移入展开，离开 800ms 缩回 | Vasu 无专属 miniMode 贴边帧，缩进后直接硬生生裁剪原画，视觉截断生硬。 |

---

## 6. Agent / StateWatcher Boundary（Agent 与数据面物理边界）

针对系统是否存在隐式旁路驱动桌宠动作的代码审计事实：

1. **Telemetry 绝不驱动 Body（100% 遵从隔离规范）**：
   - 检查 `src/connectors/http_server.py:364-375`（`_handle_event_on_main_thread`）：所有来自 Hermes / Pi / Codex 的 HTTP 事件仅被转发至 `self.bus.dispatch_json(data)`，进入数据面与持久化。
   - `LocalEventBus`（`src/connectors/event_bus.py:59`）内部虽有 `_EVENT_TO_STATE` 映射，但 `run_companion.py:257` 实例化 Bus 时**根本没有传入 `on_state_suggested` 回调**。
   - 历史版本中存在的“Agent 调工具桌宠高频手抖切换 700 次”的 Bug 已被彻底根治，数据面驱动身体的旁路通道已被彻底切断。
2. **StateWatcher 的实际角色**：
   - `src/core/state_watcher.py` 仅在内存中维护两个时间戳（`_session_start` 与 `_last_active`）；
   - 它仅提供两个查询函数：`is_overworking()`（是否连续工作超 3 小时）与 `is_late_night()`（当前时间是否在 00:00~05:00）；
   - 它**不主动发出任何信号，不调用任何 UI 控制器，不影响 Native Idle 的节奏，也不改变桌宠动画**。
3. **唯一的跨界通道：StateCare 主动关怀定时器**：
   - 在 `run_companion.py:349-370` 中，存在一个每 5 分钟轮询一次的 `care_timer`；
   - 只有当连续工作超 3 小时或深夜依然有活动、且任务不在进行中（`is_task_in_flight == False`）、且避风港未激活、且今日发言配额有剩余时，才会调用：
     `self.controller.perform_action("rest")`（重置为 IDLE）并由 AI 发送一句文字气泡（如“今天这个任务折腾挺久了，先歇口气？”）。

---

## 7. Autonomous Trigger Inventory（自主行为触发源盘点与 30 分钟无操作模拟）

### 7.1 全部非用户操作触发源总览

| 触发源标识 | 调度周期 / 频率 | 触发前置条件 | 身体影响 (Body Effect) | 语言影响 (Speech Effect) | 冷却时间 | 控制归属 (Owner) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **`_native_blink_timer`** | 随机 8,000 ~ 18,000 ms | 当前处于 Native Idle 激活态 | 切换到 `blink.png` 160ms，随后恢复 `neutral.png` | 无 | 无 | `PetWindow` |
| **`_nap_timer`** | 45,000 ms (单发) | 伴生体进入 `SLEEPING` 状态 | 倒计时结束触发 `_wake_up()`，恢复 IDLE | 无 | 45s | `PetWindow` |
| **`care_timer`** | 固定每 300,000 ms (5分钟) | 连续工作 $\ge 3$h 或处于 00:00-05:00，且任务空闲，且配额可用 | 下发 `perform_action("rest")` $\to$ IDLE | 弹出关怀文本气泡，持续 4.5s | 每日 3 次发言配额限制 | `run_companion.py` |
| **`_retract_timer`** | 游标离开后 800 ms (单发) | 处于停靠且已展开，且光标不在桌宠/气泡/Feeder 内部 | 平移回缩进停靠坐标 | 无 | 800ms | `PetWindow` |
| *(Disabled on Vasu)* **`_autonomous_timer`** | 25s ~ 25min (依节律) | **对于 Vasu 永久失效**（`_native_idle_frames is not None` 守卫阻断） | 原设计为播放随机做工/玩耍动画 12~75s | 无 | 依节律 | `PetWindow` |

### 7.2 真实代码时间线模拟（用户完全不操作电脑 30 分钟）

基于当前代码逻辑，当用户启动 Vasu 后完全不移动鼠标、不触碰键盘、后台无 Agent 高负载运行，持续静置 30 分钟：

- **00:00**：Vasu 处于 `IDLE` 状态，屏幕上展示静态高清原画 `neutral`。`_native_blink_timer` 启动（例如随机命中 11,400ms）。
- **00:11**：`_native_blink_timer` 超时，Label 切换为 `blink.png`（闭眼），启动 160ms 恢复定时器。
- **00:11.160**：恢复为 `neutral.png`（睁眼）。调度下一次眨眼（例如随机命中 14,200ms）。
- **00:25**：再次眨眼 160ms，随后恢复静态原画。
- **05:00**：`care_timer`（5分钟巡检）触发 `_check_state_care()`。由于用户没有任何操作，`StateWatcher` 未记录持续高频活动，门控检查不通过，静默返回。
- **05:00 ~ 10:00**：仅每隔 8~18 秒单调眨眼一次（期间发生约 20~25 次眨眼）。
- **10:00**：`care_timer` 再次静默返回。
- **...**
- **30:00**：**整个 30 分钟内，Vasu 没有发生过任何一次转身、张望、打哈欠、伸懒腰、走动或发呆。Vasu 仅仅像一张悬浮在桌面的静态贴纸，累计进行了约 120 次机械闭眼！**

---

## 8. Behavior Arbitration Reality（行为仲裁现状与典型冲突判定）

经过全局代码排查，当前系统**没有任何统一的行为仲裁系统或动作队列**。状态与动作切换完全基于 **Last-Write-Wins（最后写入者胜出）**。

针对 8 组典型冲突场景的静态代码推演结果如下：

### 场景 1：Circadian 想要 Rest，Native Idle 正在眨眼
- **代码推演**：由于 `_schedule_next_autonomous_routine` 中第一行即拦截 `if self._native_idle_frames is not None: return`，Circadian 的 Rest 请求根本无法产生。
- **胜出方**：**Native Idle（无条件绝对压制）**。

### 场景 2：Mouse Hover 触发跳跃，用户同时立即拖动伴生体
- **代码推演**：悬停触发 `_trigger_hover_jump()`，启动 `_jump_settle_timer` (705ms) 并播放 `jumping`；用户在 100ms 内按下并拖动，`mouseMoveEvent` 判定位移 $\ge 4$px，置 `_has_moved = True` 并强行播放 `running-right`。705ms 后跳跃定时器超时执行 `_finish_hover_jump()`，因包含 `if not self._has_moved` 守卫，跳跃归位逻辑被主动放弃。
- **胜出方**：**User Drag（用户拖拽正确抢占）**。

### 场景 3：悬停打招呼动画未结束，用户立即在 Feeder 提交切片
- **代码推演**：悬停触发 `_start_greeting()`，启动 `_wave_timer` (1400ms) 并将状态设为 `HAPPY`（挥手）；300ms 后用户提交切片，`_on_slice_submitted()` 调用 `apply_state(PetState.HAPPY)` 试图维持开心并弹出反馈；但在 1100ms 后，此前的 `_wave_timer` 超时触发 `_finish_greeting()`，其源码无条件执行了 `self.apply_state(PetState.IDLE)`。
- **胜出方**：**陈旧悬停定时器（Bug：切片反馈动画被提前粗暴打断回 IDLE）**。

### 场景 4：用户通过托盘主动设置“休眠”，鼠标不小心划过桌宠窗体
- **代码推演**：托盘动作调用 `controller.set_state(PetState.SLEEPING)`，伴生体进入睡眠并启动 45s 猫席定时器；用户的光标从屏幕另一侧移向任务栏，无意中扫过了伴生体窗体边缘；Qt 抛出 `enterEvent`，该事件第一行即无条件调用了 `self._wake_up()`，强制将状态恢复为 IDLE。
- **胜出方**：**偶然的光标悬停（Bug：用户的显式免打扰意图被瞬间破坏）**。

### 场景 5：StateCare 关怀定时器超时，同时避风港（Sanctuary）处于激活态
- **代码推演**：`care_timer` 触发 `_check_state_care()`，进入 `intervention.evaluate_intervention()`。Gate 1 明确检查 `if self.sanctuary.is_active: return None`，直接拦截返回。
- **胜出方**：**Sanctuary Guard（避风港成功守卫）**。

### 场景 6：气泡正在发声，Native Idle 到达眨眼间隔
- **代码推演**：`say()` 将文字送入独立的 `SpeechBubble` 控件渲染，并不更改 `PetWindow` 的内部状态；`_native_blink_timer` 正常工作，通过直接更改主窗口 Label 的 Pixmap 呈现眨眼。
- **胜出方**：**二者和平共存（Coexistence）**。

### 场景 7：停靠缩回定时器运行中，用户光标移入底部的 Feeder 输入条
- **代码推演**：游标离开桌宠主体触发 `leaveEvent`，启动 `_retract_timer` (800ms)；但系统启动了 150ms 间隔的轮询监测 `_check_cursor_outside_polling()`，内部检查包含 `in_feeder = self._feeder_bar.geometry().contains(cursor_pos)`。当检测到游标位于 Feeder 条时，显式执行 `self._retract_timer.stop()`。
- **胜出方**：**Feeder Bar（停靠回缩被正确挂起）**。

### 场景 8：外部通过 HTTP `/api/action` 强设思考状态，用户鼠标移入窗体
- **代码推演**：`/api/action` 将状态设置为 `THINKING`（播放 `review`）；用户光标移入窗体触发 `_trigger_hover_jump()`，跳跃播放 705ms；705ms 后 `_finish_hover_jump()` 执行 `apply_state(self._current_state, force=True)`。由于 `_current_state` 仍为 `THINKING`，跳跃结束后自动切回 `review` 动画。
- **胜出方**：**悬停跳跃临时插队，结束后忠实恢复外部设定动作**。

---

## 9. Available Runtime Context（伴生体生命感上下文现状盘点）

| 上下文信息项 | 可用状态 | 代码位置 / 审计依据 |
| :--- | :---: | :--- |
| **当前物理时间** | **✅ 已有且可靠** | `datetime.now()`, `time.time()`, `time.monotonic()` 随处可用。 |
| **上次用户交互时间戳** | **🟡 可以推导** | 窗体各自记录了 `_last_hover_jump_timestamp` 与 `_last_greet_timestamp`，但缺乏统管全局交互（点击/投喂/移动）的单一时钟。 |
| **上次 Vasu 动作状态** | **✅ 已有且可靠** | `self._current_state`（枚举）及当前加载的 SpriteSheet 引用。 |
| **操作系统级键鼠活动** | **❌ 当前没有** | 项目仅在 `GlobalHotkeyListener` 中使用了 `pynput` 监听热键，没有安装全局键鼠空闲监视器（Idle Hook），不知道用户是否正在敲代码。 |
| **当前 Agent 是否繁忙** | **🟡 可以推导** | `run_companion.py:_is_task_in_flight()` 可判定过去 60 秒内是否有来自 Agent 的活跃工具调用或思考。 |
| **最近任务结束时间** | **❌ 当前没有** | 数据库 events 表存有历史 `task_complete`，但内存运行时中无最近一次任务完成的时间戳记录。 |
| **气泡当前是否可见** | **✅ 已有且可靠** | `self._bubble.isVisible()`。 |
| **Feeder 当前是否处于输入态**| **✅ 已有且可靠** | `self._feeder_bar.isVisible()` 且 `self._feeder_bar.current_mode == "input"`。 |
| **伴生体当前是否被拖动** | **✅ 已有且可靠** | `self._drag_offset is not None` 且 `self._has_moved == True`。 |
| **当前是否处于边缘停靠态** | **✅ 已有且可靠** | `self._docked_edge in ("left", "right")`。 |
| **避风港（Sanctuary）激活状态** | **✅ 已有且可靠** | `self.guard.is_active`（布尔值）。 |
| **当前确认的关系/认知策略** | **❌ 当前没有** | 尽管数据库存在 `insights` 表，但如 Phase 2 审计所示，运行时**没有任何组件**将其加载到内存中转换为行为决策策略。 |
| **今日用户交互次数** | **🟡 可以推导** | `ColdStartPolicy` 在内存中记录了 `speech_count_today`，但这仅统计伴生体主动发声，不包含用户点击和投喂的统计。 |
| **当前连续静止（Idle）时长** | **❌ 当前没有** | 没有计时器或时间戳记录伴生体已经连续在 IDLE 保持了多少秒。 |
| **近期动作历史回溯队列** | **❌ 当前没有** | 没有维护过往动作的 RingBuffer 或栈结构，无法做出“连续跳跃两次后不再跳跃”的决策。 |

---

## 10. 80 / 15 / 5 Observability（80/15/5 律可观测性现状）

在产品架构理念（`DESIGN.md` 与 `SPEC.md`）中，明确提出了伴生体的发声比例律：
- **80% 静默陪伴（Silent Presence）**
- **15% 事实镜像 / 随手回声（Factual Mirror / Echo）**
- **5% 深度反思共创（Reflection）**

### 可观测性审计事实：
- **伴生体主动发声次数**：**🟡 弱可测**。仅由 `ColdStartPolicy.speech_count_today` 记录当日主动关怀气泡次数（每日上限 3 次），进程重启清零。
- **用户主动发起交互次数**：**❌ 完全不可测**。无计数器累加用户点击、悬停或投喂总数。
- **反思（Reflection）次数**：**❌ 完全不可测**。自模型与人生章节生成未接入运行时监控。
- **Sanctuary 抑制发声次数**：**❌ 完全不可测**。被避风港静默拦截的事件直接静默 `return None`，未产生指标记录。
- **每小时动作频次与静止时长**：**❌ 完全不可测**。
- **结论判定**：**当前系统完全不存在衡量 80/15/5 比例的运行时遥测或统计基础设施。80/15/5 目前仅是存在于设计文档中的规范主张，产品真实表现是否达标无法被客观证实**。

---

## 11. Animation ↔ Semantic Mapping（动画资产与行为语义匹配审计）

对 Vasu 当前生产图集中的动作视觉语义与代码运行语义进行对照分析：

| 动画标识 (Row / Asset) | 视觉呈现语义 (Visual Meaning) | 代码运行时赋予语义 (Runtime Meaning) | 匹配度 (Match?) | 审计定性与改进建议 |
| :--- | :--- | :--- | :---: | :--- |
| **Row 0: `idle`** (6帧) | 身体自然呼吸起伏，尾巴轻摇，微眨眼 | 原设计为常规待机；**实际被 Native Idle 彻底旁路** | **Partial (被闲置)** | 美术资产制作优良，但当前完全不可见，属于被白白浪费的资产。 |
| **Row 1: `running-right`** (8帧) | 面向右侧欢快奔跑 | 鼠标向右拖拽时的搬家搬移状态 | **✅ MATCH** | 视觉动作与鼠标右向拖动物理方向高度吻合。 |
| **Row 2: `running-left`** (8帧) | 面向左侧欢快奔跑 | 鼠标向左拖拽时的搬家搬移状态 | **✅ MATCH** | 视觉动作与鼠标左向拖动物理方向高度吻合。 |
| **Row 3: `waving`** (4帧) | 双脚站立，单爪大幅度热情挥手 | 投喂切片成功时的开心庆祝；悬停打招呼 | **✅ MATCH** | 友好的社交互动肢体语言，表意准确。 |
| **Row 4: `jumping`** (5帧) | 原地轻巧欢快纵身一跃 | 鼠标移入时的 Codex Hop 弹跳；鼠标轻戳伴生体身体反馈 | **✅ MATCH** | 极具灵动感与生命感的小跳，反馈及时。 |
| **Row 5: `failed`** (8帧) | 啪嗒摔倒扑街在地上，晕头转向 | `PetState.ERROR` 故障报错 | **🟡 Mismatch (语境失配)** | Agent 报错在现代多代理中往往是自愈过程中的常规摩擦，若让桌宠当场扑街倒地，会制造强烈的惊悚感和挫败感。当前被物理隔离不触发是合理的。 |
| **Row 6: `waiting`** (6帧) | 乖巧端坐，小脑袋微歪，静静注视 | `PetState.WAITING` 等待指令；**代码中零调用** | **❌ Orphaned (废弃)** | 极其优雅的伴读/等待姿态，但代码中没有任何路径切入该动作。 |
| **Row 7: `running`** (6帧) | 纯正向奔跑 | `PetState.WORKING` 工作状态 | **🟡 Mismatch (语境失配)** | 用户在敲代码或 Agent 在搜索时，小动物在原地无休止冲刺奔跑并不符合“平静陪伴”的心理学原则。目前已被隔离不触发。 |
| **Row 8: `review`** (6帧) | 挠头思考，歪头托腮，若有所思 | `PetState.THINKING` 思考中（点击语音输入时触发） | **✅ MATCH** | 形象生动地表达出“我在认真听你说话、在琢磨你的意思”。 |

---

## 12. Long-running Risks（连续运行稳定性与退化风险）

静态代码分析结合长时间运行场景（1h / 8h / 24h）识别出的工程风险：

1. **睡眠唤醒逻辑缺陷（Broken Sleep Persistence）**：
   - 伴生体设计了 `_nap_timer`（45秒猫打盹），45秒后自动唤醒；
   - 导致如果用户晚上睡觉前从托盘点击“休眠（免打扰）”，45秒后伴生体会**自动睁眼唤醒自己**；且期间任何鼠标掠过都会将其唤醒。真正的 DND（免打扰）状态在当前代码中无法长时间维持。
2. **多显示器分辨率与 DPI 缩放漂移（Multi-DPI Coordinate Creep）**：
   - `window.py:_restore_position` 仅针对主屏幕可用空间计算坐标限制；
   - 当用户在多显示器环境下将伴生体拖至副屏，系统休眠唤醒或副屏热插拔后，`availableGeometry()` 变化会导致坐标越界或贴边计算异常。
3. **QTimer 链条脆弱性（Timer Chain Vulnerability）**：
   - 整个伴生体生命活动完全系于单发定时器的闭环重启（例如 `_native_blink_timer` 超时启动 `_native_blink_restore_timer`，后者超时再启动前者）；
   - 一旦在某次特定系统事件（如全屏游戏独占、操作系统锁屏或休眠）中丢弃了单次超时信号，**眨眼循环将永久停摆，伴生体将彻底石化**。

---

## 13. Test Coverage Inventory（现有生命与表现层测试盘点）

当前工程针对 Body 与动画表现相关的测试主要位于 `tests/test_body.py`（23 项）与 `tests/test_circadian.py`（2 项）：

- **已充分覆盖的单点契约**：
  - 图集切片与帧宽校验（`test_spritesheet_load_and_slice`）；
  - `AnimationPlayer` 帧派发逻辑（`test_animation_player_logic`）；
  - 控制器状态与气泡派发（`test_body_controller_state_and_say`）；
  - 越界紧急重置居中（`test_pet_window_clamping_and_reset`）；
  - 边缘吸附缩进与透明边距度量（`test_art_padding_and_peek_offset`）；
  - Vasu Native Idle 激活与跳跃/拖拽覆盖（`test_vasu_native_idle_and_core_interactions`）；
  - 昼夜节律的时间段枚举划分（`test_get_circadian_phase_distribution`）。
- **完全缺失的测试领域**：
  - **无长时间运行稳定性测试**：没有 10 分钟或 1 小时的生命循环推进模拟；
  - **无随机性确定测试（Deterministic Seed Test）**：眨眼与例程间隔纯用系统随机数，未打桩验证；
  - **无动作仲裁与冲突测试**：没有针对“悬停未归位时立刻拖动”、“拖动中遇到气泡”等并发场景的自动化断言；
  - **无动作频率安全上限测试**：缺乏对快速连续事件下帧率与 CPU 占用尖峰的保护测试。

---

## 14. Missing Capabilities（核心缺失能力清单）

为迈向真正的 Phase 2.5 Autonomous Life，当前系统确凿缺失的底层能力：

1. **统一行为仲裁器（Behavior Arbiter）**：缺乏按“物理拖拽 > 用户互动 > 深度睡眠 > 自主闲逛 > 呼吸待机”分层的动作优先级管线。
2. **真正的动作池与状态机（Action Pool & State Graph）**：Vasu 的 `waiting`、`review`、`running` 等优秀动作被生硬割裂，缺乏从“待机 $\to$ 歪头注视 $\to$ 打瞌睡”的自然姿态转移概率图。
3. **自适应环境节律调制器（Active Circadian Modulator）**：节律不应仅是静态列表，而应真正具备时钟感知，能根据深夜或上午动态调节眨眼间隔、动作活跃度与休息概率。
4. **动作防重与冷却管理器（Cadence & Cooldown Manager）**：防止同一个动作连续重复执行，维护全局互动冷却。
5. **行为可观测性管道（Behavior Metrics Pipeline）**：打通针对动作触发、发声比例与静默时长的内部打点统计。

---

## 15. Facts Phase 2.5 Must Respect（V2.5 重构设计必须尊重的既成事实）

在设计下一步 Autonomous Life / Living Companion SPEC 时，必须严格遵循以下铁律：

1. **必须承认“Vasu 资产只有 9 行图集 + 高清眨眼”，不能幻想不存在的复杂骨骼或 3D 动画**。
   重构生命感必须立足于把现有的 9 行动作（特别是被闲置的 `waiting`、`idle` 呼吸帧与 `review`）通过合理的时序串联盘活，而不是假定有无穷无尽的动作库。
2. **必须保持数据面绝对隔离原则**。
   无论未来希望伴生体如何“感知”Agent 工作，Agent 遥测绝不可直接越权调用 `set_state`，必须经由行为仲裁器在宏观节奏上温和表达。
3. **Native Idle 高清原画是 Vasu 的视觉辨识度核心，不可粗暴舍弃**。
   Vasu 之所以受到喜爱，正是因为高清原画的静谧质感。Phase 2.5 的目标不是让桌宠变成躁动不安的多动症患儿，而是在保持高度静谧的前提下，赋予其微小而生动的自主生命律动。
4. **免打扰睡眠（DND）的主权必须高于一切自动逻辑**。
   当用户在托盘选择休眠时，系统必须保持绝对的深睡，绝不可因为光标掠过或猫打盹倒计时结束而擅自唤醒。

---

## 16. Proposed Capability Support Matrix（能力现状支撑对照表）

| Capability (能力项) | Exists (已具备) | Partial (部分具备) | Missing (缺失) | Current Owner (当前归属模块) | Main Limitation (核心局限 / 现状事实) |
| :--- | :---: | :---: | :---: | :--- | :--- |
| **Native Idle** | **✓** | | | `src/body/window.py` | 仅支持单调的双帧眨眼（8~18s 一次），缺乏微动作池与呼吸循环；Atlas 原始 `idle` 被完全覆盖废弃。 |
| **Circadian modulation** | | **✓** | | `src/core/circadian.py` | 代码中存在静态映射表；但在 Vasu 身上被 Native Idle 守卫 100% 旁路阻断，实际未参与运行时调节。 |
| **Autonomous behavior scheduler**| | | **✓** | *(None)* | 完全没有自主行为调度器。非 Vasu 伴生体只有简陋的随机挑选，Vasu 身上则完全冻结。 |
| **Behavior arbitration** | | | **✓** | *(None)* | 零仲裁器。完全由各个单发定时器与后发事件执行 Last-Write-Wins 暴力覆盖，存在倒计时截断 Bug。 |
| **Interaction interruption policy**| | **✓** | | `src/body/window.py` | 仅对拖拽做了针对跳跃的布尔值保护，缺乏通用的交互抢占与中断保护协议（如悬停可粗暴破坏休眠）。 |
| **Behavior memory** | | | **✓** | *(None)* | 无历史动作队列或 RingBuffer，记不住上一个动作，无法避免连续动作重复或产生因果关联行为。 |
| **User activity awareness** | | | **✓** | *(None)* | 没有操作系统级键鼠活动监测，不知道用户正在深思、狂敲键盘还是已经离开工位。 |
| **Agent activity awareness** | | **✓** | | `src/core/state_watcher.py` | 能通过事件感知 Agent 是否正在执行工具；但目前该信息仅用于关怀气泡拦截，未进入身体语言体系。 |
| **Relationship-policy influence**| | | **✓** | *(None)* | 双方确认的 Insight 仍为死数据，尚未能对桌宠的亲密度、互动宽容度或待机姿态产生任何反哺。 |
| **80/15/5 observability** | | | **✓** | *(None)* | 没有任何运行时刻度与统计埋点，无法客观证实产品是否符合静默发声比例律。 |
| **Long-horizon simulation** | | | **✓** | *(None)* | 缺乏 10 分钟或 1 小时以上的确定性仿真测试套件，无法在 CI 中防御偶发死锁或状态停滞。 |

---
*(报告结束 · 本轮事实审计未对项目代码、配置与数据执行任何修改)*
