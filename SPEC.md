---
id: co-evolving-companion-root
type: goal-and-requirements
title: 共生型 AI 成长伙伴：总体目标与需求规范
status: active
tags:
  - companion
  - desktop-pet
  - growth-core
---

# 共生型 AI 成长伙伴：总体目标与需求规范

## 1. 核心定位与终极愿景

本项目构建一个**以用户心智发展与存在体验为核心的“共生型数字伙伴”（Co-evolving AI Companion）**。

它坚决不是一个简单的“AI 聊天框套桌面皮”，也不是一个“刷 Token / 挂机换经验的玩具”，而是一个具有独立生命感、与用户平级相处、由真实经历塑造、并反向协助用户看清自身生活轨迹的**自适应思想镜像与智识同路人**。

核心原则：
> **You shape it. It helps you shape yourself.**  
> （你塑造它，它陪你塑造自己。）

---

## 2. 核心价值与边界规则

### 2.1 关系哲学（The Relational Stance）
- **平级伙伴，严禁主仆**：严禁主人/仆人、导师/学生或上下级称呼。口吻平实质朴、克制真诚，像工坊里并肩作战的战友，绝不写无病呻吟的文青小作文。
- **80 / 15 / 5 相处比例**：
  - 80% 沉默陪伴（静默在场，绝不打扰心流）；
  - 15% 事实镜像（适时反映客观节律与投喂切片回响）；
  - 5% 临界介入（仅在极少数关键节点提供微小反思与阻力）。
- **避风港模式（Sanctuary Mode）**：当检测到用户极度心烦、情绪受挫或抱怨时，自动熔断一切反思和引导逻辑，100% 保持安静倾听或退至一旁。

### 2.2 成长模型（Rigid → Integrated）
- **成长非数值堆砌**：成长的核心不是把属性刷到 100 分，而是从“僵化使用优势”走向“灵活整合选择”（例如：从“只有达成目标才允许生活”走向“既有远方，也允许事情暂时没有答案”）。
- **六大心理灵活性发展域**：
  1. *Temporal Integration*（时间整合：当下与未来的平衡）
  2. *Openness to Uncertainty*（对未知的开放：允许未闭环）
  3. *Regulatory Flexibility*（调节与行动灵活性：坚持与放下的切换）
  4. *Autonomous & Values-Aligned Action*（自主行动：因热爱而非因“必须”）
  5. *Experiential & Emotional Openness*（体验开放：感知情绪且保留选择）
  6. *Reflective & Narrative Integration*（叙事整合：沉淀人生章节）

### 2.3 宿主拓扑定理（Host Inversion）
- **桌宠是独立常驻宿主，Agent 是感官天线**：桌宠是一个独立常驻的桌面运行时，不寄生在任何单一 AI 工具内部。无论 Hermes、Pi、Codex 开启还是关闭，桌宠本体始终常驻桌角，陪伴用户生活。

---

## 3. 总体需求范围（Scope）

1. **桌面独立实体**：Windows 透明通道无边框置顶小宠物，支持待机动效、光标眼球追踪、闲置睡眠、极简贴边。
2. **多 Agent 状态感知**：实时接收 Hermes、Pi、Codex 等外部工具的工作状态（思考/打字/报错/完成）。
3. **随手投喂切片（Slice Feeding）**：用户在任何界面（包括 ChatGPT 网页版、IDE）按快捷键弹出半透明输入框，一键喂给桌宠，桌宠动作确认并存盘。
4. **长程心智沉淀与章节（Growth Chapters）**：本地持久化档案（Chronicle），以时间线记录重大结构性改变，支持用户共同命名。
5. **轻量移动端同步**：通过 S3/WebDAV 同步状态与 Markdown 档案，供手机端只读翻阅。
