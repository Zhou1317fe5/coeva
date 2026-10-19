# Co-evolving Companion：跨会话长期记忆 V2.1 检索架构决策记录 (Retrieval Decision Record · RDR)

> **决策状态与元数据**：
> - **决策编号**：RDR-2026-01 (Technical Retrieval Architecture Decision)
> - **决策状态**：`ACCEPTED & FROZEN`
> - **上位规范**：
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-architecture-frozen.md` (Architecture V2.1 Frozen)
>   - `docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md` (Data Model V2.1 Frozen)
> - **实证支持**：
>   - `docs/memory-v2/retrieval/retrieval-benchmark-cases.json` (DEV 29 用例 + HOLDOUT 15 用例)
>   - `docs/memory-v2/retrieval/retrieval-benchmark-results.csv` (全量 44 用例实测明细)
>   - `docs/memory-v2/retrieval/retrieval-ablation-report.md` (消融与量化评测报告 · Freeze Patch 版)

---

## 1. 核心上下文与问题陈述 (Context)

Coeva 作为轻量常驻 Windows 桌面伴生体，必须在 Python 3.11 + SQLite 环境下实现低内存、零卡顿、高静谧的跨会话长期记忆检索。上一阶段审计发现：
- 现有基于 `LIKE %kw%` 的检索器 Recall@3 仅为 28.57%；
- 面对“刺眼浅色”等口语同义改写时完全漏召；
- 缺乏工程作用域隔离，跨项目污染率达 24%~31%；
- 面对通用编程常识或负面情绪抱怨时盲目返回无关历史（False Recall Rate > 10%）。

在 Freeze Patch 审查中，进一步排查并解决了三大方法学与语义缺陷：
1. **Sanctuary 粗暴截断缺陷**：修正为熔断反思性自模型回忆（Reflective Recall），但放行最小任务连续性（Minimum Task Continuity）；
2. **快筛优先级冲突**：显式历史意图（“之前是怎么解决的”）优先于通用 QA 快筛（“怎么”）；
3. **数据方法学纠偏**：引入三级金标（`must` / `acceptable` / `must_not`），彻底分离查询通过率与候选精确率，并通过未参与调参的独立 HOLDOUT 集（15 用例）验证泛化性。

---

## 2. 核心架构决议汇总 (Decisions)

### 决议 1：确定采用“优先级意图快筛、目标选择、四重硬过滤、双通道融合打分、终置信门控”的五阶流水线
- **技术流水线拓扑**：
  ```text
  Query ──► [Stage 1: 优先级意图与避风港快筛门]
                 ├── 隐私阻断检查 (IMPL-3)
                 ├── 任务连续性检查 (放行基础错误经历)
                 ├── 避风港熔断检查 (阻断反思自模型与历史受挫)
                 ├── 显式历史/规则/偏好优先通行
                 └── 通用QA快筛门 (怎么/天气/常识 -> 早期返回 [])
                 │
                 ▼
            [Stage 2: 目标数据面选择] (Fact / Preference / Rule / Episode / Narrative)
                 │
                 ▼
            [Stage 3: 四重强类型硬过滤器] (IMPL-3 隐私阻断 / 作用域隔离 / 时态更替 / 时序截断)
                 │
                 ▼
            [Stage 4: 双通道融合打分] (0.6 FTS5 字符词法 + 0.4 表层相似度空间 + 意图加权)
                 │
                 ▼
            [Stage 5: 确定性置信度门控] (Threshold >= 0.16; 低于则触发 NO_RELEVANT_MEMORY)
                 │
                 ▼
            Recall Gate (结构化候选输出，携带强类型 ProvenanceRef)
  ```
- **实证依据**：DEV 调优集达成 **93.10% 查询通过率**；独立 HOLDOUT 验证集达成 **100.0% 查询通过率**、**100.0% 必须召回率** 与 **0.00% 误召回率**。

### 决议 2：词法通道选型 SQLite FTS5 (Unigram + Bigram 分词表征)
- **决议**：采用 SQLite 3.53 原生 FTS5 虚拟表，并在入库/查询时由应用层分词器对中文生成字符 1-gram 与相邻 2-gram，英文保留完整小写词条。
- **依据**：SQLite FTS5 原生 trigram 无法自然匹配 2 字符的常用中文词组（如“桌宠”）；而应用层 Bigram 方案能够 100% 匹配中英混合标识符与短语，零外部 C 库依赖，性能达到亚毫秒级（0.36ms）。

### 决议 3：通道定性与语义模型引入裁决 (Surface Similarity vs Dense Embedding)
- **决议**：
  - 正式将基于 N-gram TF-IDF 的余弦相似度通道定性为 **Surface Similarity Channel（表层统计相似度通道）**；
  - **Coeva V2.1 正式检索架构不强制引入外部深度 Embedding 模型**；
  - 维持 `FTS5 + Surface Similarity` 为核心组合，足以闭环当前全部业务场景；30MB 级轻量 ONNX 运行时方案降级为未来超大规模（>10k slices）可选扩展插件。
  - **彻底否决**：严禁引入 PyTorch、Sentence-Transformers、Milvus/Qdrant、Docker 等重型依赖。

### 决议 4：否决引入重排序器 (Reject Heavy Cross-Encoder Reranker)
- **决议**：检索层**不引入 Reranker 模型**。
- **依据**：在三级金标下，HOLDOUT 查询通过率达 100%，Forbidden 召回率为 0.00%，Top-3 列表中候选质量充分满足 Recall Gate 过滤需求。引入 Cross-Encoder 徒增 50~150ms 延迟与上百兆内存开销，属于典型过度工程化。

### 决议 5：贯彻执行三大实施不变量 (Strict Invariants Enforcement)
- **IMPL-1 (Retention Pinning)**：外部工具遥测骨架受 30 天 TTL 管辖，仅当被 `observation_event_links` 明确作为长期信念锚点时才触发 Retention Pin；被 Episode 引用不触发持久 Pin；
- **IMPL-2 (Multi-Source FK-safe Provenance)**：`semantic_memories` 通过强类型外键关联表与底层证据绑定（支持切片、遥测与经历），检索候选携带强类型 `ProvenanceRef(kind, id, role)`；
- **IMPL-3 (Privacy Redaction Block)**：任何处于 `needs_privacy_redaction == 1` 的章节制品在检索与上下文生成中**物理阻断、立即可读屏蔽**，绝无异步等待隐私敞口。

### 决议 6：检索融合参数正式冻结 (Parameters Frozen)
- **融合权重**：`0.6 Lexical + 0.4 Surface Similarity`；
- **置信度门限**：`0.15 ~ 0.16`；
- **意图偏置**：`Rule Boost: +0.3`, `Past Episode Boost: +0.25`；
- **依据**：参数在未参与调优的 15 个 HOLDOUT 独立样本上达成 100% 通过率，无过拟合风险，**正式冻结**。

---

## 3. 结果与影响 (Consequences)

### 正向收益 (Positive)
1. **彻底解决事实源分裂与旧事实倒灌**：时态置更替与作用域隔离保证伴生体绝不拿明朝的剑斩清朝的官；
2. **极高静谧与防翻车能力**：通用常识与负面心境下 100% 保持安静，不炫耀记忆力，践行 Silence Is Valid；
3. **极低资源开销**：单次检索耗时 ~1.88ms，常驻内存增量 < 5MB，完全嵌入当前 WAL 事务循环，桌宠常驻 CPU/内存近乎零感知。

### 明确合规边界 (Compliance Boundary)
- 检索层绝不直接将未经验证的候选文本塞入 LLM 回复；
- 检索结果必须封装为强类型 `RetrievedCandidate` 交付给 Recall Gate 处理。

---

## 4. INTERFACE CHANGE REQUEST (WP-8 Recall Gate & Sanctuary Integration)

- **Change Scope**: `src/memory/v2/retrieval/models.py` (`RetrievedCandidate`)
- **Motivation**: WP-8 Recall Gate acts as an authoritative second policy boundary (Prompt §3 & §8) performing defense-in-depth verification (IMPL-3 privacy-pending unreadability, Sanctuary expression policy, category isolation) without re-executing storage lookups.
- **Specification**:
  - Add optional fields to `RetrievedCandidate` with backwards-compatible defaults:
    - `needs_privacy_redaction: int = 0`
    - `expression_policy: str = "normal"`
    - `category: str = "fact"`
- **Backwards Compatibility**:
  - 100% backwards-compatible: existing positional/keyword construction in WP-7 continues to function identically.
  - Passes all 89 retrieval tests and maintains zero benchmark degradation.
