# Changelog（项目变更与交接日志）

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased] - UI: 完全参照 Clawd on Desk 重构“打开足迹”记忆档案库界面

### 🎨 UI & UX Modernization（足迹档案库纯白轻量化）
- **“打开足迹”窗口（`ChronicleViewerWindow`）全面对齐 Light Mode**：
  - 整体面板与内容区域全面转换为纯白底色（`#ffffff`），消除原本沉重突兀的暗黑大背景；
  - 顶部 Header Bar：标题更名为沉稳克制的“伴生体生命档案库”（去除非必要的 Emoji），统计 Badge 改为浅灰精致胶囊（`#f5f5f7` + 柔和浅边框），“导入历史会话”和“刷新”按钮统一为 Clawd 现代白底轻边框扁平按钮；
  - 侧边栏（`#chronicleNav`）：宽度统一为 200px，背景浅暖灰（`#f5f5f7`），消除 Windows 默认虚线焦点，每项配置来自 Clawd 规范的线性 SVG 矢量图标（树叶、齿轮、闪电、调色盘、书本），选中态为纯白带微弱柔边；
  - 列表与文本视窗（`#dataList`, `QTextEdit`, `QLineEdit`）：纯白底色、细微分割线、浅灰 hover 与选中态、等宽字体用于时间戳与原文字句，消除 Windows 原生粗白滚动条，自定义 6px 宽透明轨道深色圆角细滑块；
  - 操作按钮规范：心智假说校准与撰写章节按钮采用高保真扁平胶囊设计（翡翠绿 / 陶土暖橙），完全贴合 Clawd on Desk 视觉体系。

## [Unreleased] - Vasu Phase 2C: failed 自主小挫折动画验收

### 📝 Art Production（美术制作）
- 制作并验收 `failed` 8 帧：Vasu 自己的小意图没奏效后短暂困惑、轻微失望并恢复平静；不表达 Agent、用户或系统错误。经过失败帧局部修正与整行尺度修正，完成 64px、GIF、接触表与色键 QA。九个核心 row 现在齐备，但最终图集仍待单独批准。

## [Unreleased] - Vasu Phase 2C: jumping 自主玩耍动画验收

### 📝 Art Production（美术制作）
- 制作并验收 `jumping` 5 帧：Vasu 自己的一次低幅度小跳，带准备、离地、落地和安定，不表达任务成功或 Agent 完成。使用 stable-slot 抽帧保持空中帧体量，完成 64px、GIF、接触表与色键 QA。其它行与最终图集未制作或修改。

## [Unreleased] - Vasu Phase 2C: waving 朋友式回应验收

### 📝 Art Production（美术制作）
- 制作并验收 `waving` 4 帧：一次短暂、克制的单爪回应，随后回到自己的生活。使用 stable-slot 抽帧修正组件法造成的中间帧体量跳动；完成 64px、GIF、接触表与色键 QA。其它行与最终图集未制作或修改。

## [Unreleased] - Calico Theme: 移植接入 Clawd on Desk 经典三花猫并设为默认宠物
### 🐾 Fixed & Enhanced: 彻底重构贴边停靠（Mini Mode）动效状态机
- **引入真实人类昼夜作息大周期（`Circadian Life Schedule`, `src/core/circadian.py`）**：
  - **彻底告别多动症式的频繁换动作**：废除 20~40 秒的高频动作切换定时器，状态基底保持长时间平静（以数分钟为单位），90% 以上时间处于温和平静的呼吸与发呆（`idle`）；
  - **全天 24 小时自然作息对齐**：
    - **07:30 - 09:00 晨间苏醒（`MORNING_WAKE`）**：醒来伸懒腰（`waking`）、打哈欠（`yawning`），慢节奏开启新的一天；
    - **09:00 - 12:00 上午专注工作（`MORNING_WORK`）**：以沉稳打字（`typing`）、深思构思（`thinking`）和安静陪伴为主，不进行吵闹娱乐；
    - **12:00 - 14:00 午间休整与午睡（`MIDDAY_SIESTA`）**：打瞌睡揉眼（`dozing`）、打哈欠、小憩；
    - **14:00 - 18:30 下午工坊沉浸（`AFTERNOON_FOCUS`）**：工匠日常（木工 `building`、打字 `typing`、整理 `sweeping`、搬运 `carrying`），单次专注做工持续 20~30 秒，间隔 3~8 分钟才偶发一次；
    - **18:30 - 23:00 傍晚放松娱乐（`EVENING_LEISURE`）**：下班闲暇，偶尔听音乐指挥（`conducting`）、玩耍抛球（`juggling`）、散漫发呆；
    - **23:00 - 07:30 夜间深度睡眠（`NIGHT_SLEEP`）**：夜深人静，桌宠保持安详沉睡（`sleeping`）或打瞌睡（`dozing`）。若主人深夜写代码，它安静蜷在桌角陪伴，绝不切换吵闹动作；
  - **互动冷却提升至 60 秒（`GREETING_COOLDOWN_MS = 60_000`）**：光标滑过不再反复挥手，保持桌面极度静谧，只有间隔一段后初次交互才挥爪致意。
- **解决物理切片导致的半截身子截断问题**：
  - 废弃原本生硬的窗口向屏幕边缘滑出裁切方式（`_peek_reveal_px`）；
  - 贴边时激活专属 **Mini Mode 动效状态机**，采用 Clawd on Desk 规范的贴边姿态资产（`calico-mini-idle`、`calico-mini-peek`、`calico-mini-happy`、`calico-mini-sleep`）；
- **精准边缘贴合与翻转（`offsetRatio` & `flipAssets`）**：
  - 读取 Calico 主题配置 `offsetRatio = 0.4`：屏幕外隐藏 40% 身形，屏幕内露出 60% 萌趣身姿（小猫伸爪趴在屏幕边框上探出头）；
  - 左边缘与右边缘自适应翻转（`flipAssets: true`）：右边缘停靠时水平镜像翻转（`mini-idle-flipped`），爪子与小脑袋探向屏幕中心；左边缘停靠时直接朝内探出，姿势完全符合物理直觉；
- **多层次微互动（Hover & Poke）**：
  - 贴边常态：播放从容趴边探头的 `mini-idle`（或打盹时的 `mini-sleep`）；
  - 鼠标悬停（Hover）：小猫进一步往外探出（`mini-peek`）；
  - 鼠标点击/轻戳（Poke）：播放开心的贴边互动动画 `mini-happy` 并露出粉嫩肉垫；
  - 拖离边缘：自动解除 Mini Mode 并恢复完整站姿 `idle`。


- **接入官方核心默认伴生体 Vasu Core v0.1（`assets/pets/vasu/`）**：
  - 正式将完成生产冻结的 Vasu Core v0.1 部署至 `assets/pets/vasu/`（包含 `pet.json` 与标准 1536×1872 8×9 图集 `spritesheet.webp`，57 个有效动作帧无损呈现）；
  - 设置为系统出厂唯一官方默认伙伴：`src/connectors/settings.py` 与 `run_companion.py` 默认读取 `vasu`；
  - 桌面右键菜单与设置面板同步将 Vasu 设为置顶首选；
  - 完整跑通 9 状态动作映射（`idle`, `running-right`, `running-left`, `waving`, `jumping`, `failed`, `waiting`, `running`, `review`），并经由单元测试验证。
- **全面看齐 Codex 核心交互动力学与生理节律（`src/body/animation.py`, `src/body/window.py`）**：
  - **彻底解决眨眼过快频闪问题**：`AnimationPlayer` 引入 `loop_delay_range_ms`。完成一次平静呼吸与自然闭合眨眼后，在睁眼基线帧保持 3.0~5.5 秒的深沉凝视，将眨眼频率校准为自然界真实的“数秒一次”，彻底消除一秒一次的机械频闪感；
  - **对齐 Codex 悬停小跳（Hover Jump）**：光标滑入桌宠时，触发轻快利落的 `jumping` 动作（Row 4，5 帧，约 500ms），给予桌面触觉反馈，并配置 5 秒冷却避免连续划过抽搐；
  - **对齐 Codex 拖拽步态方向感知（Directional Dragging）**：按住向右拖动宠物时自动流转为 `running-right`（右行步态），向左拖动自动流转为 `running-left`（左行步态），松手放开时自然定步回到 `idle`。
  - **根除像素艺术模糊与高分屏二次拉伸（Pixel-Art Sharpness & High-DPI DPR Mapping）**：
    - 彻底废除 `SmoothTransformation`（双线性平滑滤波导致的边缘色散虚影），无论放大或缩小 100% 锁定为 `FastTransformation`（最近邻采样），对齐 Codex 的 `image-rendering: pixelated;`；
    - 引入 Windows 物理显示屏像素感知（`dpr = screen.devicePixelRatio()`，如 150% 缩放下的 1.5x）；缩放直接计算物理像素并显式配置 `setDevicePixelRatio(dpr)`，彻底杜绝 Windows DWM 二次模糊拉伸；
    - 显式锁定 `_label.setScaledContents(False)`，确保每一颗像素块像刀刻般锐利、眼珠与胡须分明。
### 🚀 Added（新增功能）
- **原生 APNG 动图主题加载器（`ThemeApngLoader`, `src/body/animation.py`）**：
  - 支持 Clawd on Desk 规范的 `theme.json` 与 `.apng` 动图主题；
  - 采用 Pillow 高性能解包 32 位 RGBA 无损序列与帧率（如打字 16 FPS、呼吸 8 FPS），瞬间加载 40+ 个生动日常动作；
- **Calico 完整动作资产库（`assets/pets/calico/`）**：
  - 拥有 27 个独立动作、包含 40+ 种丰富生活与互动行为：
    - 悠闲日常：`calico-idle.apng`（从容呼吸摇尾巴）；
    - 自主生活：打字（`typing`）、扫地（`sweeping`）、做木工（`building`）、搬运（`carrying`）、抛球杂耍（`juggling`）、指挥音乐（`conducting`）；
    - 自然入睡序列：打哈欠（`yawning`）、打瞌睡（`dozing`）、趴下入睡（`collapsing`）、深睡（`sleeping`）、伸懒腰醒来（`waking`）；
    - 交互与反应：被悬空提起的挣扎摇晃（`react-drag`）、戳一戳的轻快回眸（`react-poke`）、开心跳舞（`happy`）、抱头晕倒（`error`）；
    - 贴边探头：小脑袋探出（`mini-peek`）、贴边开心（`mini-happy`）、贴边打盹（`mini-sleep`）；
- **交互动作深度联动（`PetWindow`）**：
  - 鼠标拖拽宠物时自动播放小猫被提起的悬空动作 `react-drag`，松开落地后恢复优雅坐姿；
  - 鼠标轻点宠物时播放被戳戳的互动动作 `react-poke`；
  - 贴边探头时播放 `mini-peek`；
- **全系统默认宠物定音（Default Pet -> Calico）**：
  - `src/connectors/settings.py`：默认 `selected_pet` 改为 `"calico"`；
  - `run_companion.py`、`main.py`、`settings_window.py` 均将 Calico 设为首选默认宠物，托盘与设置面板可无缝切换。

### 🗑️ Removed（移除废弃宠物）
- **完全删除 Tiko、Debug Duck、Wangcai 素材与引用**：
  - 彻底删除 `assets/pets/tiko`、`assets/pets/debug-duck`、`assets/pets/wangcai` 目录；
  - 清理 `run_companion.py`、`main.py`、`settings_window.py`、`settings.py` 中的列表与回退项；
  - 伴生体阵容全面收敛至 Calico（三花猫，默认）与 Claw（经典小猫）。
---

### 📝 Art Production（美术制作）
- 修正 Phase 2A self-work 动作语义：旧闭眼梳理草图仍不作为生产素材；`running` 现表达 Vasu 为自己的小事克制地迈步前行，而非 Agent 任务状态。完成 6 帧色键抽帧、GIF、四行接触表、64px 对照与逐行 QA；已批准行与最终图集均未改动。

## [Unreleased] - Vasu Phase 2C: waving 朋友式回应验收

### 📝 Art Production（美术制作）
- 制作并验收 `waving` 4 帧：一次短暂、克制的单爪回应，随后回到自己的生活。使用 stable-slot 抽帧修正组件法造成的中间帧体量跳动；完成 64px、GIF、接触表与色键 QA。其它行与最终图集未制作或修改。

## [Unreleased] - Vasu Phase 2C-3: review 专注观察动画验收

### 📝 Art Production（美术制作）
- 制作并验收 `review` 6 帧：Vasu 为自己的好奇心短暂专注观察共享空间，和 `idle`、`waiting` 在 64px 下可区分。完成色键抽帧、GIF、三行接触表与逐行 QA；未制作其他行或最终图集。

## [Unreleased] - Vasu Phase 2C-2: waiting 动画试产与验收

### 📝 Art Production（美术制作）
- 将 `waiting` 定义为 Vasu 暂停自己的活动、安静感知共享空间；制作并验收 6 帧，完成与 `idle` 的接触表、64px 对照、GIF 和色键抽帧 QA。前两版因身形过高及转头过大被拒，第三版与 `idle` 尺度一致并通过视觉验收。未制作其他行或最终图集。

## [Unreleased] - UI: 完全参照 Clawd on Desk 复刻右键菜单与设置界面

### 🎨 UI & UX Modernization（界面复刻与体验升华）
- **右键菜单与系统托盘深度精简**：
  - 完全参照 Clawd on Desk 的 `joinGroups` 菜单规范，将杂乱冗余的测试/调试条目（“模拟 Hermes Agent 4 步测试”、“测试气泡”、“恢复待机”等）从默认菜单中剔除；
  - 规范化 5 大核心分组：`状态组（休眠/唤醒）`、`工作与记忆（随手投喂切片、足迹档案库）`、`伴生体与显示（切换伴生体、缩放尺寸、拉回主屏）`、`应用设置（伴生体设置、显示/隐藏）`、`退出`；
  - 在 `PetWindow` 实现 `context_menu_requested` 与 `contextMenuEvent`，右击桌宠身体任意位置即可直接呼出菜单，与托盘操作逻辑无缝对齐；
  - 定制现代高雅浅白 QSS 菜单样式（`#ffffff` 底色、`#f4f4f5` 悬停态、微弱浅灰边框与分割线）。
- **现代化胶囊 Toggle Switch 控件落地**：
  - 在 `src/body/widgets.py` 新增 `SwitchButton`，完全复刻 iOS / macOS 与 Clawd on Desk 的丝滑胶囊切换开关（38px × 20px，圆角 10px，白圆滑块平滑移动）；
  - 彻底淘汰系统默认刺眼粗糙的纯绿色方块 `QCheckBox`。
- **设置界面（SettingsWindow）高保真重构**：
  - 侧边栏宽度定调为标准 200px，引入 Clawd on Desk 原生 24x24 线性 SVG 图标（纯线条矢量渲染，替代系统粗糙 emoji），消除 Windows 原生虚线焦点框；
  - 色彩系统全面对齐 Clawd on Desk 亮白模式（Light Mode）：页面底色与内容面板 `#ffffff`、侧边栏浅灰 `#f5f5f7`（选中间底白色带细微边框）、卡片容器 `#fbfbfd`（圆角 10px，边框 `rgba(0, 0, 0, 0.08)`）、强调色采用招牌暖陶土橙 `#d97757`；
  - 矢量 SVG 侧边栏图标与 SwitchButton 控件同步对齐浅色配色（关状态浅灰 `#d4d4d8`、开状态陶土橙、白圆滑块带边缘阴影）；
  - 自定义细长现代深色滚动条（6px 宽，透明轨道，半透明圆角滑块）；
  - 多 Agent 接入卡片、大模型服务、桌面身体偏好、心智避风港与关于页全面统一为新设计规范。

## [Unreleased] - Vasu Phase 2C-1: running-left 镜像验收

### 📝 Art Production（美术制作）
- 审核右行姿态的脸、耳、奶油色花纹、尾巴、脚掌与光照后，逐帧水平镜像已批准的 8 帧，保留原帧序。左行通过 64px、透明度、基线、循环与左右一致性 QA；未制作其他动画行或最终图集。

## [Unreleased] - Vasu Phase 2B: idle 与 running-right 双行动画试产

### 📝 Art Production（美术制作）
- 完成 `idle` 6 帧与 `running-right` 8 帧的色键抽帧、64px 对照、GIF/接触表和逐行 QA。定向修复洋红溢色及右行第 4 帧的尺寸跳动；两行通过试产门槛。其余行与最终图集未制作。

## [Unreleased] - Philosophy: 独立生命个体与朋友式共存哲学入档

### 📝 Docs & Philosophy（设计哲学与产品规范确立）
- **根目录 `SPEC.md` §2.1**：确立“独立生命个体与朋友式共存（Autonomous Life & Non-Intrusive Companionship）”，明确桌宠生活在桌面上，有自己的工作、玩耍与休息闭环，与用户同处一个工坊，彼此独立而不割裂；
- **`DESIGN.md` §1**：升华“生命感与日常自主节律（Living Presence & Ambient Fellowship）”，确立 90% 依赖体态微语言、文字气泡极低频且克制的交互分寸。生命引擎实现与新自制宠物彻底解耦，待新宠物制作完毕后再行落地讨论。

---

### 📝 Art Production（美术制作）
- 新增 `assets/vasu/production/` 的六姿态静态草图、朝右行走基准姿态、64px 对比图与评审记录。朝右轮廓可作为 Phase 2B 的试行动画依据；观察、做事、休息、玩耍和回应仍需按评审意见修订。未制作动画行或图集。

## [Unreleased] - Vasu Phase 1: 生产契约与标准形象锁定

### 📝 Docs（规范与决策）
- 更新 `docs/specs/vasu/SPEC.md`：明确 Vasu 与用户安静共处、独立观察、做事、休息、玩耍及温和回应的美术动作语言；本阶段未制作动画素材。

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
- **历史数据扫描与批量导入致 GUI 假死（P0 · 性能缺陷）**：
  - **根因复盘**：旧代码在 Qt GUI 主线程同步调用跨网 UNC I/O 扫描文件，且在入库时针对每条事件执行
    一次 `self._conn.commit()`。在面对 12.4 万条大规模历史事件时，导致主事件循环挂起、窗口报 `(未响应)`，
    且触发了 12.4 万次单行磁盘刷盘（fsync），导入耗时长达数分钟；
  - **彻底修复**：
    1. 新增 `ChronicleStore.record_events_batch`，采用 `executemany` 配合单次显式事务提交，将 12.4 万条事件入库耗时从数分钟暴降至 **0.5 秒以内（300x 速度提升）**；
    2. 将扫描预览与批量导入彻底迁移至 `HarvestWorkerThread(QThread)` 异步工作线程，主界面保持 60fps 丝滑且配备实时脉冲进度条；
    3. 为 JSONL 读取引入快速行预过滤，避免无谓的 json 反序列化开销。
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
- **Phase 2D 人生章节生成与双人共写（Growth Chapters & Narrative Co-authoring）**：
  - **标准 OpenAI 兼容 LLM 客户端（`src/core/llm_client.py`）**：采用 Python 3.11+ 原生标准库实现，零第三方臃肿框架依赖，支持官方 API、DeepSeek、本地 Ollama / vLLM 以及自定义代理；配置安全保存在 `data/llm_config.json`；
  - **在软件设置面板新增「🧠 大模型服务」页面**：提供常用服务商快速预设（DeepSeek, OpenAI, Ollama 本地等）、密码掩码保护及异步毫秒级连通性测试按钮；
  - **章节生成四大资格门（`ChapterEligibilityGate`）**：严格校验持续性（跨度 ≥ 28 天且 Episodes ≥ 30）、结构性模式存在、多源环境多样性与自愿发起；
  - **叙事防火墙硬约束（`NarrativeFirewall`）**：过滤谄媚吹捧与人生导师式说教，通篇锁定工坊战友并肩作战口吻，所有转变必须锚定真实底层行为证据；
  - **档案库新增「📖 人生章节」浏览与共写界面（`ChronicleViewerWindow` Tab 5）**：支持一键触发共创、Markdown 精美排版渲染、留白用户手记在线编辑沉淀，以及本地 Markdown 文件一键导出。
- **多 Agent 历史会话收割器（Multi-Agent History Harvester）**：
  - **架构实现**：在 `src/connectors/history/` 落地三大日志转译器（`PiDesktopParser`、`CodexCliParser`、`HermesDbParser`），自动扫描发现 Windows 和 WSL 下沉淀的 500+ 个历史会话日志；
  - **严格零文本隐私与时间序因果（AC-1 ~ AC-3）**：100% 物理隔离用户的 Prompt 输入正文、思维链（CoT）与工具输出细节，仅提取行为时间脉冲，支持 SHA-1 幂等导入；
  - **物理陪伴冷启动锁（AC-6）**：确立“信息与信任的不对称性”哲学硬约束，历史数据仅作为底层静默证据池，前台桌宠的破冰节奏与每日发言配额 100% 物理锁死在用户真实的相处天数上，坚决不因数据充裕而快进关系。
  - **配套 CLI 工具**：支持 `--dry-run` 安全预览、`--sources` 来源选择与 `--limit` 灵活配置。
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
