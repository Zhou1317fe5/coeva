---
id: companion-phase-2d-growth-chapters
type: submodule-design
title: 第二阶段 2D 规范：大模型接入、叙事防火墙与人生章节共创
parent: companion-phase-2-growth-core-and-chronicle
status: active
version: 0.1
tags: [phase-2d, llm-service, growth-chapters, narrative-firewall, co-authoring, markdown-export]
---

# 第二阶段 2D 规范：大模型接入、叙事防火墙与人生章节共创

## 1. 目标与定位

在 Phase 2A/2B/2C 完成了证据库、行为模式挖掘和假说校准，并通过历史会话收割沉淀了 200+ Episodes 与 12 万条客观事件后，系统已具备深厚的事实底座。
Phase 2D 的目标是**将底层离散的行为模式与心理透镜，升华形成具有生命传记感的“人生章节”（Growth Chapters）**。

> **核心哲学**：  
> 它不是千篇一律的大模型总结，也不是鸡汤小作文；  
> 它是用户与伴生体共同经历的客观见证，是一份“工坊同路人”视角的并肩作战回忆录。

---

## 2. LLM 客户端与安全接入契约（OpenAI-Compatible Standard）

### 2.1 零重型 SDK 依赖（Zero Bloat Invariant）
依据 AGENTS.md 与架构原则，系统坚决不引入 LangChain、LlamaIndex 等臃肿框架。
使用 Python 标准库（`urllib.request` / `json`）实现极简、高容错、轻量级的标准 OpenAI 兼容客户端：
- **通信协议**：`POST {base_url}/chat/completions`
- **请求头**：`Authorization: Bearer {api_key}`
- **配置持久化**：存储于 `data/llm_config.json`（已在 `.gitignore` 中，绝不泄露到 Git 仓库）。

### 2.2 配置模型与预设
- `base_url`: 支持官方 OpenAI、DeepSeek、本地 Ollama (`http://localhost:11434/v1`)、vLLM、OneAPI 等；
- `api_key`: 密码掩码保存；
- `model`: 模型名称（如 `gpt-4o`, `deepseek-chat`, `qwen2.5:7b`）；
- `temperature`: 默认 `0.7`；
- `max_tokens`: 默认 `2048`。

---

## 3. 章节生成四大资格门（Chapter Eligibility Gate）

生成人生章节绝不能是轻率、频繁的自动化任务。触发章节生成前，必须由确定性规则校验通过四道资格门：

1. **持续性门（Sustained Gate）**：
   - 历史跨度 $\ge$ 4 周（28 天），且持久化 Episode 累计 $\ge$ 30 个（当前环境已满 215 个，跨度 7 个月，完全达标）；
2. **结构性转变门（Structural Shift Gate）**：
   - 系统中至少存在 1 个高置信度行为模式，或已形成至少 1 条双方校准的共识洞察（Confirmed Insight）；
3. **多样性门（Diversity Gate）**：
   - 证据来源涵盖至少 2 种不同场景（例如：工具报错调试 + 长链路自主委派，或切片投喂 + 节律数据）；
4. **自愿性与防打扰门（Meaning & Voluntary Gate）**：
   - 章节生成必须由用户在 UI 界面显式发起，或伴生体在满足前三门后、且当日发言配额有剩余时轻柔提议。

---

## 4. 叙事防火墙硬约束（Narrative Firewall · Hard Invariants）

调用大模型撰写章节草稿时，必须通过系统级 Prompt 防火墙进行严格过滤，彻底杜绝劣质 AI 的常见通病：

1. **绝对禁止谄媚与空洞赞扬（Anti-Flattery）**：
   - 严禁出现“你太棒了”、“令人钦佩的坚持”、“展现了卓越的智慧”等虚伪阿谀；
2. **绝对禁止心理说教与人生导师口吻（Anti-Preach）**：
   - 严禁指导用户“你应该如何生活”、“建议你以后更放松”；
3. **工坊同路人视角（Workmate Stance）**：
   - 视角必须是“坐在桌角的安静伙伴”，语言平实、质朴、克制、诚恳；
4. **事实锚定（Evidence-Grounded）**：
   - 章节中的每一次转变，必须引用具体的真实 Episode、真实工具摩擦（如 Bash 报错、长任务执行）或具体的随手切片内容。

---

## 5. 章节结构与双人共写（Co-Authoring Contract）

生成的章节保存为本地 Markdown 文件（`data/chapters/chapter_01_xxx.md`），结构如下：

```markdown
# 章节名称（用户与伴生体共同命名）

> 记录周期：YYYY-MM-DD 至 YYYY-MM-DD  
> 核心透镜：[如：接纳不确定性 / 行动灵活性]  
> 伴生体：Tiko / Claw / Wangcai / Debug Duck  

## 1. 伴生体的观察（The Shift）
[从当初的事必躬亲，到后来的充分委派……]

## 2. 客观经历与阻力足迹（Evidence Footprints）
[列举具体代表性的 Episode 与摩擦场景]

## 3. 我们的共同默契（Mutual Understanding）
[记录双方校准认同的思维与相处共识]

## 4. 用户手记（Human Reflection · 留白由用户填写）
[用户在软件中编辑并保存的真实个人感悟]
```

---

## 6. 验收标准（Acceptance Criteria）

- **AC-1 客户端兼容性**：支持主流 OpenAI 兼容接口（含本地 Ollama 与 DeepSeek），提供快捷测试连通性；
- **AC-2 安全隔离**：API Key 与 Base URL 仅落盘于 `data/llm_config.json`，严禁上传代码仓库；
- **AC-3 资格门校验**：当数据不足时明确阻断生成并给出差距提示；数据充足时放行；
- **AC-4 叙事防火墙达标**：生成的章节草稿无谄媚阿谀，通篇保持工坊同路人平静视角，并锚定真实 Episode；
- **AC-5 本地持久化与渲染**：章节以标准 Markdown 存储于 `data/chapters/`，在 Viewer 中可实时阅读、共同命名与导出。
