# Project Companion Agent Guide (AGENTS.md)
## ——开发规范与工程行为守则

本文件规定在 `co-evolving-companion` 项目中工作时必须遵守的核心工程纪律与开发规范。在开始任何编码或架构任务前，必须通读并严格遵守本规范。

---

## 1. Project Map（项目工程拓扑）

本项目采用 **Python 3.11+ 原生轻量架构**，结合 PySide6 表现层与独立心智服务。

| 目录 / 路径 | 核心职责与归属 |
| :--- | :--- |
| `src/body/` | **桌面表现投影层（Desktop Body）**：基于 PySide6 实现的透明置顶挂件、Sprite 动效状态机、光标追踪与极简气泡渲染。纯粹作为“受控终端”，只响应 `Body Control Contract`。 |
| `src/core/` | **独立成长心智层（Growth Core）**：系统的长盛心智。包括归因引擎（Attribution Filter）、节律感知器（State Watcher）、介入决策器（Intervention Policy）、心理灵活性六大透镜评估与避风港熔断守卫（Sanctuary Guard）。 |
| `src/connectors/` | **多 Agent 状态桥接层（Connector Hub）**：连接外部工具（Hermes 生命周期钩子、Pi 全局扩展、Codex CLI 观察者）。负责将外部异构信息归一化为只读数据流推送给 Core。 |
| `src/feeder/` | **随手投喂切片输入器（Slice Feeder）**：全局热键（如双击 `Alt` 或 `Win+Shift+P`）监听、半透明磨砂即用即走输入框及存盘管道。 |
| `src/memory/` | **本地记忆与生命档案（Chronicle Store）**：管理 `data/raw_slices.jsonl`（切片流）、本地 SQLite（结构化事件）及 Markdown 格式的长期成长章节（Growth Chapters）。 |
| `docs/specs/` | **ThinkRail 规范图谱（Durable Spec Graph）**：项目真实性事实源（Source of Truth）。包含总体目标、系统架构及各阶段模块规范。 |
| `docs/concepts/` | **产品哲学与心智设计理论**：立项愿景、ACT 心理灵活性框架、介入三道门、归因与记忆衰减理论总纲。 |
| `docs/research/` | **开源生态与选型调研**：Clawd 等桌宠底座调研、主从反转架构定调报告及历史演进归档。 |
| `DESIGN.md` | **伴生体空间圣域与交互哲学规范**：定义 Stage 空间保护、点击穿透、输入框瞬态退出与质朴气泡风格。 |
| `tests/` | **自动化测试套件**：涵盖单元测试、状态机流转测试与归因过滤测试。 |

---

## 2. Commands（标准工具链指令）

所有开发命令均在项目根目录下执行：

- **环境激活与管理**：使用 `uv` 管理虚拟环境（`.venv/Scripts/activate`）。
- **静态类型检查（Typecheck）**：`mypy src --strict`
- **代码规范与格式化（Lint & Format）**：
  - 检查代码：`ruff check .`
  - 自动修复：`ruff check --fix .`
  - 代码格式化：`ruff format .`
- **运行自动化测试（Test）**：
  - 执行所有测试：`pytest`
  - 单文件测试：`pytest tests/test_xxx.py`
- **规范图谱校验（Spec Validation）**：
  - 执行 `spec_validate` 确保图谱无悬空链接、重复 ID 或环路。
- **启动桌宠本体（Run Body）**：`python -m src.body.main`
- **启动投喂守护器（Run Feeder）**：`python -m src.feeder.main`

---

## 3. Scope and Checks（任务范围与自检纪律）

- **严格控制任务范围（Strict Scope Boundary）**：改动严格限制在当前任务范围之内。在改动某个函数、类或测试时，纠正其不符合规则的地方；**严禁因为“顺手可以优化”而修改无关代码或大范围重写无关模块**。
- **严禁私造一次性轮子（No One-Off Patterns）**：编写任何新工具函数或辅助类前，必须先检索项目内已有实现；如果新逻辑可抽象为通用工具，应在明确设计后置于通用模块，严禁随意引入仅使用一次的胶水逻辑。
- **重构逐步推进（Step-by-step Refactor）**：重构必须有明确收益，禁止在没有测试保护的情况下进行大范围重构。
- **交付前必须自检**：在宣布任务完成前，必须在本地运行并确认：
  1. `ruff check .` 无任何警告或错误；
  2. `mypy src --strict` 类型完全通过；
  3. 相关单元测试 100% 通过；
  4. 若涉及系统边界或契约改变，`docs/specs/` 对应 Spec 已经同步更新且 `spec_validate` 通过。
- **诚实汇报**：只汇报实际执行过的命令和真实结果，严禁捏造未执行的测试输出。

---

## 4. Code Rules（代码与架构准则）

- **模块职责边界分明**：各子模块必须职责单一，严禁跨模块隐式共享全局可变状态。
- **严格类型约束（Strict Typing Discipline）**：
  - Python 必须使用类型注解（typing），彻底禁止未经声明的裸 `Any` 或隐式字典传递；
  - 结构化业务数据契约必须采用 `@dataclass(frozen=True)` 或 Pydantic 强结构定义；
  - 针对通用容器使用泛型（TypeVar / Generic）。
- **控制平面与数据平面物理分离（Planes Separation Discipline）**：
  - **Data Plane（数据面）**：Hermes/Pi 高频工具执行日志、会话更新、原始切片流。属于只读数据流，只能推入心智归因队列，严禁直接绑定或触发 UI 重绘；
  - **Control Plane（控制面）**：伴生体状态机切换、气泡输出、避风港熔断控制。必须经过决策审批后低频下发，确保桌面极度静谧。
- **依赖注入仅限外部边界（Dependency Injection Only at External Boundaries）**：
  - 仅在数据库访问、大模型网络 API、文件持久化、操作系统全局热键等外部 I/O 边界使用依赖注入；
  - 内部纯业务规则（如心理灵活性六大透镜评估、避风港关键词判定、冷启动限频计数）保持纯函数直接调用，严禁过度工程化。
- **拒绝无休止的向下兼容包袱（No Premature Backward-Compatibility Bloat）**：
  - 严禁在未经过需求评审的情况下堆砌向前兼容胶水代码；
  - 若有临时过渡代码，必须标注严格规范注释：
    ```python
    # NOTICE:
    # 临时过渡原因: <原因描述>
    # 依赖上下文: <关联文件或任务ID>
    # 移除条件: <何时可安全删除>
    ```
- **纯函数优先**：纯数据转换与无状态计算必须采用纯函数；拥有长程生命周期、状态机或明确外部边界的模块使用 Class 封装。
- **错误处理规范**：统一捕获明确异常，严禁无差别的 `except Exception: pass`。

---

## 5. Documentation & Specs as Source of Truth（文档与规范管理）

- **Spec 是第一事实源**：
  - `SPEC.md`（根目录）定义项目总体目标与范围（`goal-and-requirements`）；
  - `docs/specs/SPEC.md` 定义系统总体架构拓扑与硬约束（`architecture-design`）；
  - `docs/specs/<module>/SPEC.md` 定义各阶段具体模块规范（`module-design`）；
  - `.thinkrail/context/` 存放临时施工任务（`task-spec`）。
- **代码与 Spec 强一致性**：
  - 禁止出现 `Code says one thing, Spec says another`；
  - 代码变更改变了产品行为、数据结构、接口契约或系统约束时，必须在同一个变更中同步更新对应 Spec，并运行 `spec_validate` 确认。
- **缺陷排查与工程复盘（Bug Post-mortems & Handover）**：
  - 在联调测试中发现的任何非浅层缺陷（如跨线程死锁、坐标裁剪、事件截获失效等），必须在解决后立即将**“现象、根因、修复方案”**记录到对应模块 `SPEC.md` 的 `Bug Post-mortems` 章节；
  - 版本功能里程碑与缺陷修复必须实时同步记录到 `CHANGELOG.md`，确保团队交接与维护时有据可查、不重复踩坑。
---

## 6. Git & Commits（版本控制纪律）

- **Conventional Commits 规范**：
  提交信息格式必须为 `<type>(<scope>): <description>`，严禁无意义的提交说明。
  - `feat:` 新增功能（如添加快捷键投喂、Hermes Connector）
  - `fix:` 修复缺陷
  - `spec:` 规范图谱更新与架构设计
  - `docs:` 纯文档或设计说明更新
  - `refactor:` 代码结构重构（无行为变化）
  - `test:` 补充或修复自动化测试
- **逻辑独立提交**：一个 Commit 尽量只对应一个完整的逻辑单元，避免将多个无关功能混合在一次提交中。
