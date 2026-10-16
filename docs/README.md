# Co-evolving AI Companion 文档中心

欢迎查阅共生型 AI 成长伙伴（Co-evolving AI Companion）项目文档体系。

本项目将文档分为三个不同效力与层次的区域：
1. **现行执行规范图谱 (`specs/`)**：项目的**第一事实源（Source of Truth）**，受 ThinkRail 强一致性校验保护；
2. **产品哲学与心智设计理论 (`concepts/`)**：奠定产品灵魂与心理学基石的七篇核心概念设计；
3. **开源生态与技术选型调研 (`research/`)**：技术路线探索与底座选型分析报告。

---

## 1. 现行执行规范图谱 (Durable Spec Graph)

> **位置**：[`specs/`](./specs/)  
> **地位**：当前代码实现、接口契约与阶段范围的唯一有效事实源。任何代码变更必须与规范图谱保持一致，并通过 `spec_validate` 校验。

- **总体目标与需求规范**：[`/SPEC.md`](../SPEC.md)（项目根规范，`co-evolving-companion-root`）
- **总体架构设计规范**：[`specs/SPEC.md`](./specs/SPEC.md)（`companion-architecture-design`）
- **Phase 1 规范**：[`specs/phase-1-runtime-and-bridge/SPEC.md`](./specs/phase-1-runtime-and-bridge/SPEC.md) — 独立常驻桌面 Runtime、PySide6 极简身体与单 Agent 桥接
- **Phase 2 规范**：[`specs/phase-2-chronicle-and-growth-chapters/SPEC.md`](./specs/phase-2-chronicle-and-growth-chapters/SPEC.md) — 人生章节（Growth Chapters）与生命档案库（Chronicle）

---

## 2. 产品哲学与心智设计理论 (Concepts & Philosophy)

> **位置**：[`concepts/`](./concepts/)  
> **说明**：成文于立项需求研讨阶段。深入阐述了共生伙伴的核心理念、心理灵活性框架与相处边界。建议按编号顺序阅读：

| 序号与文档 | 主题与核心洞见 |
| :--- | :--- |
| **[`01_concept_and_vision_v0.1.md`](./concepts/01_concept_and_vision_v0.1.md)** | **概念设计与产品愿景总纲**<br>定义“伴生伙伴”而非玩具、平级伙伴关系、反对刷数值、共同经历沉淀。 |
| **[`02_mind_development_framework_v0.1.md`](./concepts/02_mind_development_framework_v0.1.md)** | **六大心智发展域与心理灵活性框架**<br>基于接纳承诺疗法（ACT）与自我决定理论，关注从“僵化”到“整合”的成长。 |
| **[`03_intervention_policy_v0.1.md`](./concepts/03_intervention_policy_v0.1.md)** | **介入策略、沉默原则与决策三道门**<br>确立 80% 沉默 / 15% 镜像 / 5% 临界介入，以及极端情况下的避风港（Sanctuary）熔断机制。 |
| **[`04_attribution_design_v0.1.md`](./concepts/04_attribution_design_v0.1.md)** | **Hermes 行为归因与防误判设计**<br>严格区分 Agent 机器自主循环与用户真实意志，避免把工具死循环误判为用户行为。 |
| **[`05_data_model_requirements_v0.1.md`](./concepts/05_data_model_requirements_v0.1.md)** | **数据最小化与衰减生命周期**<br>定义记忆采集边界、隐私保护、分级衰减与遗忘机制。 |
| **[`06_relationship_and_growth_chapters_v0.1.md`](./concepts/06_relationship_and_growth_chapters_v0.1.md)** | **关系演化、人生章节与十项 Non-goals**<br>双向成长叙事、阶段性人生章节沉淀，以及明确绝不做的事情（Non-goals）。 |
| **[`07_cold_start_and_slice_feeder_v0.1.md`](./concepts/07_cold_start_and_slice_feeder_v0.1.md)** | **单工具聚焦、随手投喂切片与破冰策略**<br>单工具深度聚焦、全局轻量投喂切片交互及前 14 天破冰策略。 |

---

## 3. 开源生态与技术选型调研 (Research & Evolution)

> **位置**：[`research/`](./research/)  
> **说明**：技术路线调研、候选底座对比与演化决策记录。详见 [`research/README.md`](./research/README.md)。

- **最新决策报告**：[`research/ecosystem_research_v2.0.md`](./research/ecosystem_research_v2.0.md) — 确立“桌宠独立常驻宿主（Host Inversion）”与 Clawd on Desk 剖析；
- **历史调研演化归档**：[`research/archive/`](./research/archive/) — 保留 v0.1 全景扫描与 v1.0 双轮核验收敛版。
