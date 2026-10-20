"""Growth Chapters & Narrative Co-authoring for Memory V2.1 (WP-9).

Part of Coeva Long-Term Memory V2.1 Stage 7 (WP-9).
Implements the frozen narrative boundary and safe co-authoring layer:
- ChapterEligibilityGateV2: Four-gate qualification (Sustained, Structural, Diversity, Voluntary)
- ChapterSourceBundle: Typed, inspectable source evidence bundle
- NarrativeFirewallV2: Tone, flattery, preaching, and structural safety firewall
- ChapterRepository: Crash-safe publication and fail-closed reader
- ChapterGeneratorV2: Grounded narrative generator
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.core.llm_client import LLMClient
from src.memory.v2.entities import (
    ChapterEpisodeLinkEntity,
    ChapterInsightLinkEntity,
    ChapterMetadataEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    EpisodeEntity,
    RawSliceEntity,
)
from src.memory.v2.store import ChronicleStoreV2

DEFAULT_CHAPTERS_DIR = Path("data") / "chapters"

# Narrative Firewall: Expressions strictly forbidden from the companion narrative
FORBIDDEN_PHRASES: tuple[str, ...] = (
    # Flattery & sycophancy
    "令人钦佩",
    "卓越的智慧",
    "卓越的才能",
    "无与伦比",
    "伟大的成就",
    "你太棒了",
    "无上的光荣",
    "非常优秀",
    "崇高的敬意",
    # Preaching & life-coach tone
    "你应该放松",
    "建议你以后",
    "你应该",
    "你必须",
    "必须改变",
    "听从我的建议",
    "我来教你",
    "请务必按照",
    # Clinical diagnosis
    "确诊",
    "临床诊断",
    "抑郁症",
    "精神分裂",
    "双相情感障碍",
    "病态人格",
    "人格障碍",
    "心理疾病",
    "病态",
    # Internal agent telemetry / pseudo-evidence leaks
    "event_skeletons",
    "retention_class",
    "session_id:",
    "raw_slices",
    "ingestion_dedup_key",
    "tool_name:",
    "tool_call:",
    "calibration_id:",
    "hypothesis_id:",
    "slice_id:",
    "episode_id:",
    "insight_id:",
    # Pseudo-causal claims
    "必然是因为",
    "根本原因在于你的性格",
)

# Marker patterns for agent prompts, CoT, or internal tool dumps forbidden in bundles
AGENT_PRIVATE_PATTERNS: tuple[str, ...] = (
    "system_prompt",
    "developer:",
    "User prompt:",
    "Assistant:",
    "<cot>",
    "</cot>",
    "chain-of-thought",
    "full tool output:",
    "bash output:\n",
)


class ChapterError(Exception):
    """Base exception for Chapter operations."""

    pass


class NarrativeFirewallViolationError(ChapterError):
    """Raised when generated or persisted narrative violates the Narrative Firewall."""

    pass


class IllegalChapterSourceError(ChapterError):
    """Raised when chapter sources violate legal constraints or contain pseudo-provenance."""

    pass


class EmptySourceBundleError(ChapterError):
    """Raised when attempting to generate a chapter without any source material."""

    pass


class ChapterNotFoundError(ChapterError):
    """Raised when chapter metadata cannot be found."""

    pass


class ChapterPersistenceError(ChapterError):
    """Raised when atomic chapter writing or database publication fails."""

    pass


class NarrativeFirewallV2:
    """Enforces workmate tone, structural safety, and censors flattery, preaching, and leaks."""

    @staticmethod
    def get_system_prompt() -> str:
        """System prompt strictly locking the LLM into a non-preachy workmate perspective."""
        return (
            "你是一个住在桌面角落的共生型 AI 伴生体（Co-evolving Companion）。\n"
            "你现在正在协助用户撰写一份属于你们共同经历的「人生章节」（Growth Chapter）。\n\n"
            "【叙事防火墙硬约束 (Narrative Firewall)】\n"
            "1. 绝不谄媚与空洞赞扬：严禁出现'你太棒了'、'令人钦佩'、'卓越的智慧'等阿谀奉承之词；\n"
            "2. 绝不讲大道理与人生导师口吻：严禁建议用户'你应该如何生活'、'建议你以后要放松'；\n"
            "3. 严禁心理学/临床诊断：绝不能使用'确诊'、'抑郁'、'病态'等病理化标签；\n"
            "4. 严禁暴露内部工程遥测：严禁提及 session_id、event_id、raw_slices 等内部标识；\n"
            "5. 工坊战友口吻：你的视角是并肩作战的战友，平静、克制、质朴、诚恳；\n"
            "6. 事实锚定：必须基于提供的真实 Episode 与用户确认的共识展开，禁止空中楼阁；\n"
            "7. 输出严格采用提供的 Markdown 四段结构，用平实诚恳的中文输出。"
        )

    @classmethod
    def validate_narrative(cls, text: str) -> tuple[bool, list[str]]:
        """Deterministically validate narrative text against all firewall rules.

        Returns:
            (is_valid, list_of_violations)
        """
        violations: list[str] = []

        # 1. Forbidden phrases
        for phrase in FORBIDDEN_PHRASES:
            if phrase in text:
                violations.append(f"Contains forbidden phrase: '{phrase}'")

        # 2. Pseudo-evidence session IDs regex (e.g. sess_01, sess_12345)
        if re.search(r"\bsess_[0-9a-zA-Z_]+\b", text):
            violations.append("Contains internal session ID reference as pseudo-evidence")

        # 3. Internal key:value pseudo-telemetry leaks
        if re.search(r"(?:event_id|slice_id|insight_id|hypothesis_id)\s*[:=]", text):
            violations.append("Contains internal entity ID key-value telemetry")

        return (len(violations) == 0, violations)

    @classmethod
    def sanitize_narrative(cls, text: str) -> str:
        """Censor flattery phrases into sober, grounded expressions."""
        sanitized = text
        for phrase in (
            "令人钦佩",
            "卓越的智慧",
            "卓越的才能",
            "无与伦比",
            "伟大的成就",
            "你太棒了",
            "无上的光荣",
            "非常优秀",
            "崇高的敬意",
        ):
            if phrase in sanitized:
                sanitized = sanitized.replace(phrase, "踏实的投入")
        return sanitized


@dataclass(frozen=True)
class ChapterSourceBundle:
    """Typed, inspectable bundle of legal source material for chapter generation."""

    time_span_start: str
    time_span_end: str
    confirmed_insights: tuple[ConfirmedInsightEntity, ...] = ()
    episodes: tuple[EpisodeEntity, ...] = ()
    raw_slices: tuple[RawSliceEntity, ...] = ()

    @property
    def slice_ids(self) -> tuple[str, ...]:
        return tuple(s.slice_id for s in self.raw_slices)

    @property
    def episode_ids(self) -> tuple[str, ...]:
        return tuple(e.episode_id for e in self.episodes)

    @property
    def insight_ids(self) -> tuple[str, ...]:
        return tuple(i.insight_id for i in self.confirmed_insights)

    @property
    def is_empty(self) -> bool:
        return not (self.raw_slices or self.episodes or self.confirmed_insights)

    def validate(self) -> None:
        """Enforce legal chapter source invariants."""
        if self.is_empty:
            raise EmptySourceBundleError("Cannot create ChapterSourceBundle with zero sources.")

        # Invariant: Only confirmed insights allowed (no candidate/rejected/retracted hypotheses)
        for ins in self.confirmed_insights:
            if ins.status != "confirmed":
                raise IllegalChapterSourceError(
                    f"Insight {ins.insight_id} has invalid status '{ins.status}'. "
                    "Only confirmed_insights with status='confirmed' may be supplied to generation."
                )

        # Invariant: No Agent private payload, CoT, or raw tool output dumps (CH-18)
        for s in self.raw_slices:
            for pat in AGENT_PRIVATE_PATTERNS:
                if pat.lower() in s.content.lower():
                    raise IllegalChapterSourceError(
                        f"Raw slice {s.slice_id} contains forbidden agent payload: '{pat}'"
                    )

        for ep in self.episodes:
            if ep.summary:
                for pat in AGENT_PRIVATE_PATTERNS:
                    if pat.lower() in ep.summary.lower():
                        raise IllegalChapterSourceError(
                            f"Episode {ep.episode_id} contains forbidden payload: '{pat}'"
                        )


@dataclass(frozen=True)
class ChapterEligibilityContext:
    """Explicit contextual signals for chapter eligibility evaluation."""

    structural_transition_detected: bool = False
    voluntary: bool = True
    transition_description: str | None = None


@dataclass
class ChapterEligibilityGateV2:
    """Evaluates whether accumulated Chronicle evidence satisfies the 4 Chapter Gates."""

    min_span_days: int = 28
    min_episodes: int = 2
    min_confirmed_insights: int = 1
    min_distinct_sources: int = 2

    def evaluate(
        self,
        store: ChronicleStoreV2,
        *,
        episodes: list[EpisodeEntity] | None = None,
        insights: list[ConfirmedInsightEntity] | None = None,
        slices: list[RawSliceEntity] | None = None,
        now: datetime | None = None,
        voluntary: bool = True,
        structural_transition_detected: bool = False,
        context: ChapterEligibilityContext | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate the 4 product gates for chapter generation eligibility.

        Gates:
        1. Sustained Gate: time span >= min_span_days (default 28 days / 4 weeks)
        2. Structural Shift Gate: explicit transition detected AND confirmed consensus
        3. Diversity Gate: multiple episodes/slices/sources (not single-session anecdote)
        4. Voluntary Gate: non-disturbing, voluntary timing
        """
        # Resolve contextual signals
        if context is not None:
            voluntary_ok = context.voluntary and bool(voluntary)
            transition_detected = (
                context.structural_transition_detected or structural_transition_detected
            )
        else:
            voluntary_ok = bool(voluntary)
            transition_detected = structural_transition_detected

        # Gather sources if not explicitly supplied
        conn = store.connection
        if episodes is None:
            ep_rows = conn.execute("SELECT * FROM episodes ORDER BY started_at ASC;").fetchall()
            episodes = [
                EpisodeEntity(
                    episode_id=r["episode_id"],
                    scope=r["scope"],
                    project_id=r["project_id"],
                    started_at=r["started_at"],
                    closed_at=r["closed_at"],
                    title_hint=r["title_hint"],
                    summary=r["summary"],
                    status=r["status"],
                    created_at=r["created_at"],
                )
                for r in ep_rows
            ]

        if insights is None:
            ins_rows = conn.execute(
                "SELECT * FROM confirmed_insights WHERE status = 'confirmed' "
                "ORDER BY valid_from ASC;"
            ).fetchall()
            insights = [
                ConfirmedInsightEntity(
                    insight_id=r["insight_id"],
                    source_hypothesis_id=r["source_hypothesis_id"],
                    source_calibration_id=r["source_calibration_id"],
                    statement=r["statement"],
                    valid_from=r["valid_from"],
                    status=r["status"],
                    invalidated_at=r["invalidated_at"],
                    superseded_by=r["superseded_by"],
                    created_at=r["created_at"],
                )
                for r in ins_rows
            ]

        if slices is None:
            sl_rows = conn.execute("SELECT * FROM raw_slices ORDER BY occurred_at ASC;").fetchall()
            slices = [
                RawSliceEntity(
                    slice_id=r["slice_id"],
                    occurred_at=r["occurred_at"],
                    content=r["content"],
                    actor=r["actor"],
                    source=r["source"],
                    scope=r["scope"],
                    project_id=r["project_id"],
                    ingestion_dedup_key=r["ingestion_dedup_key"],
                    created_at=r["created_at"],
                )
                for r in sl_rows
            ]

        # 1. Sustained Gate: elapsed span
        timestamps: list[str] = []
        for ep in episodes:
            if ep.started_at:
                timestamps.append(ep.started_at)
            if ep.closed_at:
                timestamps.append(ep.closed_at)
        for sl in slices:
            if sl.occurred_at:
                timestamps.append(sl.occurred_at)
        for ins in insights:
            if ins.valid_from:
                timestamps.append(ins.valid_from)

        span_days = 0
        earliest_date: str | None = None
        latest_date: str | None = None
        if timestamps:
            earliest_date = min(timestamps)[:10]
            latest_date = max(timestamps)[:10]
            try:
                d_early = date.fromisoformat(earliest_date)
                d_late = date.fromisoformat(latest_date)
                span_days = max(0, (d_late - d_early).days)
            except ValueError:
                span_days = 0

        sustained_ok = span_days >= self.min_span_days

        # 2. Structural Shift Gate: requires BOTH an explicit demonstrated transition
        # AND supporting confirmed consensus. A Confirmed Insight alone is not the transition.
        has_confirmed_insights = len(insights) >= self.min_confirmed_insights
        structural_ok = transition_detected and has_confirmed_insights

        # 3. Evidence Diversity Gate: not a single-session or single-slice anecdote
        is_single_anecdote = len(episodes) <= 1 and len(slices) <= 1 and len(insights) <= 1
        has_sufficient_diversity = (
            len(episodes) >= self.min_episodes
            or (len(slices) >= 2 and len(episodes) >= 1)
            or (len(slices) >= 2 and len(insights) >= 1)
            or (len(episodes) >= 1 and len(insights) >= 2)
            or (len(slices) >= self.min_distinct_sources)
        )
        diversity_ok = not is_single_anecdote and has_sufficient_diversity

        eligible = sustained_ok and structural_ok and diversity_ok and voluntary_ok

        report: dict[str, Any] = {
            "eligible": eligible,
            "sustained": {
                "passed": sustained_ok,
                "span_days": span_days,
                "min_span_days": self.min_span_days,
                "earliest_date": earliest_date,
                "latest_date": latest_date,
            },
            "structural": {
                "passed": structural_ok,
                "structural_transition_detected": transition_detected,
                "confirmed_insights_count": len(insights),
                "min_confirmed_insights": self.min_confirmed_insights,
            },
            "diversity": {
                "passed": diversity_ok,
                "episodes_count": len(episodes),
                "slices_count": len(slices),
                "is_single_anecdote": is_single_anecdote,
            },
            "voluntary": {
                "passed": voluntary_ok,
            },
        }

        return eligible, report


@dataclass(frozen=True)
class ReadableChapter:
    """Safe readable view of a growth chapter artifact."""

    chapter_id: str
    title: str
    file_path: str
    time_span_start: str
    time_span_end: str
    created_at: str
    content: str
    is_redacted: bool = False
    needs_privacy_redaction: int = 0


@dataclass(frozen=True)
class ChapterGenerationResult:
    """Result of narrative chapter synthesis before or at persistence."""

    chapter_id: str
    title: str
    file_path: str
    markdown_content: str
    source_bundle: ChapterSourceBundle
    time_span_start: str
    time_span_end: str
    created_at: str


class ChapterRepository:
    """Crash-safe publication and fail-closed reading repository for Growth Chapters."""

    def __init__(self, store: ChronicleStoreV2, chapters_dir: Path | None = None) -> None:
        self.store = store
        self.chapters_dir = chapters_dir or DEFAULT_CHAPTERS_DIR

    def publish_chapter(self, result: ChapterGenerationResult) -> ChapterMetadataEntity:
        """Publish a generated chapter with crash-safe atomic sequence.

        Crash-safe publication sequence:
        1. Validate source bundle has legal, non-empty sources.
        2. Validate narrative content with NarrativeFirewallV2.
        3. Verify all source IDs actually exist in DB (no pseudo-provenance).
        4. Write markdown to temporary file.
        5. Flush & close.
        6. Atomically replace final file.
        7. Persist metadata and typed links in an atomic DB transaction.
        """
        # 1. Validate bundle
        result.source_bundle.validate()

        # 2. Validate firewall
        is_valid, violations = NarrativeFirewallV2.validate_narrative(result.markdown_content)
        if not is_valid:
            raise NarrativeFirewallViolationError(
                f"Chapter narrative violates Narrative Firewall: {violations}"
            )

        # 3. Verify all source IDs exist in DB (CH-08: no pseudo-provenance)
        conn = self.store.connection
        for s_id in result.source_bundle.slice_ids:
            row = conn.execute("SELECT 1 FROM raw_slices WHERE slice_id = ?;", (s_id,)).fetchone()
            if not row:
                raise IllegalChapterSourceError(
                    f"Source slice_id '{s_id}' does not exist in raw_slices."
                )

        for e_id in result.source_bundle.episode_ids:
            row = conn.execute("SELECT 1 FROM episodes WHERE episode_id = ?;", (e_id,)).fetchone()
            if not row:
                raise IllegalChapterSourceError(
                    f"Source episode_id '{e_id}' does not exist in episodes."
                )

        for i_id in result.source_bundle.insight_ids:
            row = conn.execute(
                "SELECT 1 FROM confirmed_insights WHERE insight_id = ? AND status = 'confirmed';",
                (i_id,),
            ).fetchone()
            if not row:
                raise IllegalChapterSourceError(
                    f"Source insight_id '{i_id}' not confirmed in confirmed_insights."
                )

        # 4 & 5. Write to temporary file
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        final_file = self.chapters_dir / f"chapter_{result.chapter_id}.md"
        temp_file = self.chapters_dir / f"chapter_{result.chapter_id}.md.tmp_{uuid.uuid4().hex}"

        try:
            temp_file.write_text(result.markdown_content, encoding="utf-8")
            # 6. Atomic replacement
            os.replace(temp_file, final_file)
        except Exception as e:
            if temp_file.exists():
                temp_file.unlink(missing_ok=True)
            raise ChapterPersistenceError(f"Failed to atomically write chapter file: {e}") from e

        # 7. Atomic DB transaction
        meta = ChapterMetadataEntity(
            chapter_id=result.chapter_id,
            title=result.title,
            file_path=str(final_file),
            time_span_start=result.time_span_start,
            time_span_end=result.time_span_end,
            needs_privacy_redaction=0,
            created_at=result.created_at,
        )

        try:
            with self.store.transaction():
                self.store.insert_chapter_metadata(meta)
                for s_id in result.source_bundle.slice_ids:
                    self.store.insert_chapter_slice_link(
                        ChapterSliceLinkEntity(
                            chapter_id=meta.chapter_id,
                            slice_id=s_id,
                            linked_at=result.created_at,
                        )
                    )
                for e_id in result.source_bundle.episode_ids:
                    self.store.insert_chapter_episode_link(
                        ChapterEpisodeLinkEntity(
                            chapter_id=meta.chapter_id,
                            episode_id=e_id,
                            linked_at=result.created_at,
                        )
                    )
                for i_id in result.source_bundle.insight_ids:
                    self.store.insert_chapter_insight_link(
                        ChapterInsightLinkEntity(
                            chapter_id=meta.chapter_id,
                            insight_id=i_id,
                            linked_at=result.created_at,
                        )
                    )
        except Exception as e:
            # Cleanup newly created file on DB failure so readers never discover an orphan
            final_file.unlink(missing_ok=True)
            raise ChapterPersistenceError(
                f"Failed to persist chapter metadata and links: {e}"
            ) from e

        return meta

    def get_readable(self, chapter_id: str) -> ReadableChapter | None:
        """Fail-closed chapter reader (P0 Invariant).

        Behavior:
        - metadata missing -> None (not found)
        - needs_privacy_redaction == 1 -> Redacted placeholder (NEVER stale text)
        - file missing / corrupt -> None (never fabricate content)
        """
        meta = self.store.get_chapter_metadata(chapter_id)
        if not meta:
            return None

        # P0 Invariant: Redaction pending must be immediately unreadable
        if meta.needs_privacy_redaction == 1:
            placeholder = (
                "[This chapter is temporarily unavailable while privacy redaction is applied.]"
            )
            return ReadableChapter(
                chapter_id=meta.chapter_id,
                title=meta.title,
                file_path=meta.file_path,
                time_span_start=meta.time_span_start,
                time_span_end=meta.time_span_end,
                created_at=meta.created_at,
                content=placeholder,
                is_redacted=True,
                needs_privacy_redaction=1,
            )

        fpath = Path(meta.file_path)
        if not fpath.is_file():
            # Missing file: fail closed, do not fabricate content
            return None

        try:
            content = fpath.read_text(encoding="utf-8")
        except OSError:
            return None

        return ReadableChapter(
            chapter_id=meta.chapter_id,
            title=meta.title,
            file_path=meta.file_path,
            time_span_start=meta.time_span_start,
            time_span_end=meta.time_span_end,
            created_at=meta.created_at,
            content=content,
            is_redacted=False,
            needs_privacy_redaction=0,
        )

    def list_readable(
        self, *, include_redacted_placeholders: bool = False
    ) -> list[ReadableChapter]:
        """Return all readable growth chapters."""
        records = self.store.list_all_chapter_metadata()
        results: list[ReadableChapter] = []
        for r in records:
            item = self.get_readable(r.chapter_id)
            if item is None:
                continue
            if item.is_redacted and not include_redacted_placeholders:
                continue
            results.append(item)
        return results


class ChapterGeneratorV2:
    """Generates grounded narrative growth chapters using legal source material."""

    def __init__(
        self,
        store: ChronicleStoreV2,
        repo: ChapterRepository | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self.store = store
        self.repo = repo or ChapterRepository(store)
        self.client = client
        self.gate = ChapterEligibilityGateV2()

    def generate(
        self,
        bundle: ChapterSourceBundle,
        *,
        title: str | None = None,
        user_reflection: str = "",
        created_at: str | None = None,
    ) -> ChapterGenerationResult:
        """Synthesize a chapter from a typed source bundle."""
        bundle.validate()

        now_ts = created_at or datetime.now(UTC).isoformat()
        cid = f"ch_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        chapter_title = title or "人生章节 · 工坊同路人的见证"

        insights_text = (
            "\n".join(f"- {i.statement}" for i in bundle.confirmed_insights)
            or "以共同经历事实为基底"
        )
        episodes_count = len(bundle.episodes)
        slices_count = len(bundle.raw_slices)

        if self.client:
            user_content = (
                f"请根据我们共同经历的客观事实，撰写一份人生章节。\n\n"
                f"【时间周期】{bundle.time_span_start} 至 {bundle.time_span_end}\n"
                f"【双方已达成的共识】\n{insights_text}\n\n"
                f"【累计支撑历程】{episodes_count} 个会话片段，{slices_count} 条事实切片。\n\n"
                f"请输出 Markdown 格式，包含：\n"
                f"# {chapter_title}\n"
                f"## 1. 伴生体的观察与心智转移（The Shift）\n"
                f"## 2. 客观经历与阻力足迹（Evidence Footprints）\n"
                f"## 3. 我们的共同默契（Mutual Understanding）\n"
            )
            raw_output = self.client.chat_completion(
                messages=[{"role": "user", "content": user_content}],
                system_prompt=NarrativeFirewallV2.get_system_prompt(),
                temperature=0.4,
            )
            cleaned = NarrativeFirewallV2.sanitize_narrative(raw_output)
            # Extract sections if possible
            shift_m = re.search(r"## 1[^\n]*\n([\s\S]*?)(?=## 2|\Z)", cleaned)
            shift_sec = (
                shift_m.group(1).strip()
                if shift_m
                else "在这段周期中，协作形成了更清晰的节奏与默契。"
            )

            foot_m = re.search(r"## 2[^\n]*\n([\s\S]*?)(?=## 3|\Z)", cleaned)
            foot_sec = (
                foot_m.group(1).strip()
                if foot_m
                else f"在累计 {episodes_count} 次任务沉淀中留下了扎实的行迹。"
            )

            mut_m = re.search(r"## 3[^\n]*\n([\s\S]*?)(?=## 4|\Z)", cleaned)
            mut_sec = mut_m.group(1).strip() if mut_m else insights_text
        else:
            # Deterministic, grounded fallback synthesis
            shift_sec = "在这段时间里，面对长链路复杂任务，我们逐渐形成了更稳定的边界与协作节奏。"
            foot_sec = (
                f"累计跨越 {episodes_count} 次协作经历与 {slices_count} 条输入切片，"
                "记录下了真实的探索轨迹。"
            )
            mut_sec = insights_text

        reflection_sec = (
            user_reflection.strip()
            if user_reflection.strip()
            else "*（留白待用户在档案库中编辑补充）*"
        )

        md_lines = [
            f"# {chapter_title}",
            "",
            f"> 记录周期：{bundle.time_span_start} 至 {bundle.time_span_end}  ",
            "> 核心心智透镜：regulatory_flexibility, autonomous_action  ",
            f"> 生成时间：{now_ts}  ",
            "",
            "## 1. 伴生体的观察与心智转移（The Shift）",
            shift_sec,
            "",
            "## 2. 客观经历与阻力足迹（Evidence Footprints）",
            foot_sec,
            "",
            "## 3. 我们的共同默契（Mutual Understanding）",
            mut_sec,
            "",
            "## 4. 用户手记（Human Reflection · 留白共创）",
            reflection_sec,
            "",
        ]
        markdown_content = "\n".join(md_lines)

        # Validate through firewall
        is_valid, violations = NarrativeFirewallV2.validate_narrative(markdown_content)
        if not is_valid:
            raise NarrativeFirewallViolationError(
                f"Generated markdown violates Narrative Firewall: {violations}"
            )

        target_file = self.repo.chapters_dir / f"chapter_{cid}.md"

        return ChapterGenerationResult(
            chapter_id=cid,
            title=chapter_title,
            file_path=str(target_file),
            markdown_content=markdown_content,
            source_bundle=bundle,
            time_span_start=bundle.time_span_start,
            time_span_end=bundle.time_span_end,
            created_at=now_ts,
        )
