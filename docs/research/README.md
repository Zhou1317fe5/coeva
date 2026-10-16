# 开源生态与底座架构调研报告 (Research Index)

本目录记录了 Co-evolving AI Companion 项目在架构路线决策与开源底座选型过程中的研究成果与演化脉络。

---

## 1. 核心与最新调研结论 (Latest & Active)

- **[`ecosystem_research_v2.0.md`](./ecosystem_research_v2.0.md)** — **共生型 AI 成长伙伴：开源生态与独立常驻底座调研报告 (v2.0)**
  - **核心转折**：明确“Host Inversion（主从反转）”最高架构原则——桌宠是独立常驻的桌面宿主，AI Agents 只是其感官天线，彻底摒弃“寄生于某一 Agent 内部”的路线；
  - **底座选型**：深度剖析 Clawd on Desk 等候选底座，确立“极简小身体（PySide6）+ 独立大心智（Python Growth Core）”的分离式拓扑；
  - **研发指引**：明确第一阶段（Phase 1）任务边界与契约划分。

---

## 2. 调研演进历史归档 (Historical Archive)

以下两篇为前期探索性调研过程记录，已在 v2.0 中完全收敛，保留供追溯决策背景：

- **[`archive/ecosystem_research_v1.0.md`](./archive/ecosystem_research_v1.0.md)** — **开源生态与相关研究最终调研报告 (v1.0)**
  - 基于两轮生态调研、项目核验与需求框架交叉分析后的收敛版；
  - 覆盖桌宠底座、长期记忆框架（Mem0、Hindsight）、用户建模与主动反思机制的横向对比。
- **[`archive/ecosystem_research_v0.1.md`](./archive/ecosystem_research_v0.1.md)** — **开源生态、框架与相关研究初版调研 (v0.1)**
  - 初期全景地毯式调研，涵盖 Desktop Mate、Airi、各类桌宠项目的源码级特性初筛。
