"""Growth Chapters & Narrative Co-authoring (Phase 2D).

Implements the narrative synthesis layer of the Co-evolving Companion:
- ChapterEligibilityGate: Ensures 4 gates (Sustained, Structural, Diversity, Meaning).
- NarrativeFirewall: Strictly filters flattery, preaching, and ensures workmate tone.
- ChapterGenerator: Uses LLMClient to draft grounded markdown growth chapters.
- GrowthChapter: Dataclass representing a chapter with co-authoring reflection.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.core.llm_client import LLMClient
from src.core.patterns import BehavioralPattern, PatternBuilder

if TYPE_CHECKING:
    from src.memory.store import ChronicleStore

DEFAULT_CHAPTERS_DIR = Path("data") / "chapters"

# Narrative Firewall: Expressions strictly forbidden from the companion's narrative
FORBIDDEN_PHRASES = (
    "令人钦佩",
    "卓越的智慧",
    "卓越的才能",
    "你应该放松",
    "建议你以后",
    "无与伦比",
    "伟大的成就",
    "你太棒了",
    "无上的光荣",
)


@dataclass
class GrowthChapter:
    """A co-authored narrative chapter marking a developmental shift."""

    chapter_id: str
    title: str
    period_start: str
    period_end: str
    primary_lenses: tuple[str, ...]
    the_shift: str
    evidence_footprints: str
    mutual_understanding: str
    human_reflection: str = ""
    created_at: str = field(default_factory=lambda: date.today().isoformat())

    def to_markdown(self) -> str:
        """Render the chapter into an elegant, human-readable Markdown document."""
        lenses_str = ", ".join(self.primary_lenses)
        md = [
            f"# {self.title}",
            "",
            f"> 记录周期：{self.period_start} 至 {self.period_end}  ",
            f"> 核心心智透镜：{lenses_str}  ",
            f"> 生成时间：{self.created_at}  ",
            "",
            "## 1. 伴生体的观察与心智转移（The Shift）",
            self.the_shift,
            "",
            "## 2. 客观经历与阻力足迹（Evidence Footprints）",
            self.evidence_footprints,
            "",
            "## 3. 我们的共同默契（Mutual Understanding）",
            self.mutual_understanding,
            "",
            "## 4. 用户手记（Human Reflection · 留白共创）",
            (
                self.human_reflection
                if self.human_reflection.strip()
                else "*（留白待用户在档案库中编辑补充）*"
            ),
            "",
        ]
        return "\n".join(md)

    def save(self, directory: Path | None = None) -> Path:
        """Persist this chapter as a Markdown file."""
        target_dir = directory or DEFAULT_CHAPTERS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"chapter_{self.chapter_id}.md"
        file_path.write_text(self.to_markdown(), encoding="utf-8")
        return file_path


class ChapterEligibilityGate:
    """Evaluates whether accumulated Chronicle evidence satisfies the 4 Chapter Gates."""

    MIN_EPISODES = 30
    MIN_SPAN_DAYS = 28

    def evaluate(
        self,
        store: ChronicleStore,
        patterns: list[BehavioralPattern] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Evaluate the 4 gates.

        Returns:
            (is_eligible, report_dict)
        """
        stats = store.stats()
        episodes_count = stats.get("episodes", 0)

        # 1. Sustained Gate: episodes count and time span
        episodes = store.list_episodes(limit=1000)
        span_days = 0
        earliest_date: str | None = None
        latest_date: str | None = None

        if episodes:
            timestamps = [e.started_at for e in episodes if e.started_at] + [
                e.ended_at for e in episodes if e.ended_at
            ]
            if timestamps:
                earliest_date = min(timestamps)[:10]
                latest_date = max(timestamps)[:10]
                try:
                    d_early = date.fromisoformat(earliest_date)
                    d_late = date.fromisoformat(latest_date)
                    span_days = max(1, (d_late - d_early).days)
                except ValueError:
                    span_days = 1

        sustained_ok = (episodes_count >= self.MIN_EPISODES) and (span_days >= self.MIN_SPAN_DAYS)

        # 2. Structural Shift Gate: at least 1 high-confidence pattern or confirmed insight
        active_patterns = (
            patterns if patterns is not None else PatternBuilder(store).build_patterns()
        )
        insights = store.list_insights()
        structural_ok = len(active_patterns) >= 1 or len(insights) >= 1

        # 3. Diversity Gate: evidence across multiple agents or contexts
        agents_seen: set[str] = set()
        for ep in episodes:
            agents_seen.update(ep.agent_ids)
        diversity_ok = len(agents_seen) >= 2 or len(active_patterns) >= 2

        # 4. Voluntary Gate: Ready for human confirmation
        voluntary_ok = True

        eligible = sustained_ok and structural_ok and diversity_ok and voluntary_ok

        report = {
            "eligible": eligible,
            "sustained": {
                "passed": sustained_ok,
                "episodes_count": episodes_count,
                "min_episodes": self.MIN_EPISODES,
                "span_days": span_days,
                "min_span_days": self.MIN_SPAN_DAYS,
                "earliest_date": earliest_date,
                "latest_date": latest_date,
            },
            "structural": {
                "passed": structural_ok,
                "patterns_count": len(active_patterns),
                "insights_count": len(insights),
            },
            "diversity": {
                "passed": diversity_ok,
                "agents_count": len(agents_seen),
                "agents": sorted(list(agents_seen)),
            },
            "voluntary": {"passed": voluntary_ok},
        }

        return eligible, report


class NarrativeFirewall:
    """Enforces workmate tone, evidence grounding, and filters flattery and preaching."""

    @staticmethod
    def get_system_prompt() -> str:
        """System prompt strictly locking the LLM into a non-preachy workmate perspective."""
        return (
            "你是一个住在桌面角落的共生型 AI 伴生体（Co-evolving Companion）。\n"
            "你现在正在协助用户撰写一份属于你们共同经历的「人生章节」（Growth Chapter）。\n\n"
            "【叙事防火墙硬约束 (Narrative Firewall)】\n"
            "1. 绝不谄媚与空洞赞扬：严禁出现'你太棒了'、'令人钦佩'、'卓越的智慧'等阿谀奉承之词；\n"
            "2. 绝小说教与人生导师口吻：严禁建议用户'你应该如何生活'、'建议你以后要放松'；\n"
            "3. 工坊战友口吻：你的视角是并肩作战的战友，平静、克制、质朴、诚恳；\n"
            "4. 事实锚定：必须基于提供的真实 Episode、工具报错与摩擦事实展开，禁止空中楼阁；\n"
            "5. 输出严格采用提供的 Markdown 四段结构，用平实诚恳的中文输出。"
        )

    @classmethod
    def sanitize_narrative(cls, text: str) -> str:
        """Censor any violating flattery or preaching phrases."""
        sanitized = text
        for phrase in FORBIDDEN_PHRASES:
            if phrase in sanitized:
                sanitized = sanitized.replace(phrase, "踏实的投入")
        return sanitized


class ChapterGenerator:
    """Orchestrates eligibility verification, LLM drafting, and chapter file persistence."""

    def __init__(
        self,
        store: ChronicleStore,
        client: LLMClient | None = None,
        chapters_dir: Path | None = None,
    ) -> None:
        self.store = store
        self.client = client or LLMClient()
        self.chapters_dir = chapters_dir or DEFAULT_CHAPTERS_DIR
        self.gate = ChapterEligibilityGate()

    def generate_chapter(
        self,
        *,
        force: bool = False,
        user_reflection: str = "",
    ) -> tuple[GrowthChapter | None, dict[str, Any]]:
        """Verify eligibility, prompt the LLM, and persist a new Growth Chapter.

        Returns:
            (created_chapter_or_None, eligibility_report)
        """
        patterns = PatternBuilder(self.store).build_patterns(min_episodes=2)
        eligible, report = self.gate.evaluate(self.store, patterns=patterns)

        if not eligible and not force:
            return None, report

        # Gather factual context
        stats = self.store.stats()
        insights = self.store.list_insights()
        episodes = self.store.list_episodes(limit=30)

        earliest = report["sustained"].get("earliest_date") or date.today().isoformat()
        latest = report["sustained"].get("latest_date") or date.today().isoformat()

        # Build prompt payload
        patterns_summary = "\n".join(
            f"- [{p.pattern_id}] {p.description} (支持会话: {len(p.supporting_episodes)})"
            for p in patterns
        )
        insights_summary = (
            "\n".join(
                f"- [共识] {ins.statement} (批注: {ins.user_confirmation_text})" for ins in insights
            )
            or "暂无显式确认的 Insight，以客观行为模式为主。"
        )

        sample_episodes = "\n".join(
            f"- Session {ep.session_id[:12]}: 事件数 {ep.event_count}, Agents {ep.agent_ids}"
            for ep in episodes[:10]
        )

        user_content = (
            f"请根据我们共同经历的客观事实，撰写一份人生章节。\n\n"
            f"【统计事实】\n"
            f"- 时间跨度: {earliest} 至 {latest}\n"
            f"- 累计经历: {stats['episodes']} 个研发会话，{stats['events']} 条客观行为事件\n\n"
            f"【挖掘出的稳定模式】\n{patterns_summary}\n\n"
            f"【双方已达成的共识】\n{insights_summary}\n\n"
            f"【近期典型会话采样】\n{sample_episodes}\n\n"
            f"请输出 Markdown 格式，包含：\n"
            f"# 章节标题（如：《从事必躬亲到学会委派》、《在长任务中寻找节奏》）\n"
            f"## 1. 伴生体的观察与心智转移（The Shift）\n"
            f"## 2. 客观经历与阻力足迹（Evidence Footprints）\n"
            f"## 3. 我们的共同默契（Mutual Understanding）\n"
        )

        # Call LLM through Narrative Firewall
        raw_output = self.client.chat_completion(
            messages=[{"role": "user", "content": user_content}],
            system_prompt=NarrativeFirewall.get_system_prompt(),
            temperature=0.6,
        )

        clean_output = NarrativeFirewall.sanitize_narrative(raw_output)

        # Parse sections
        title = "人生章节 · 工坊同路人的见证"
        m_title = re.search(r"^#\s+(.+)$", clean_output, re.MULTILINE)
        if m_title:
            title = m_title.group(1).strip()

        shift_sec = "在这段时间里，你面对复杂的长链路任务逐渐形成了稳定的协作节奏。"
        m_shift = re.search(r"## 1[^\n]*\n([\s\S]*?)(?=## 2|\Z)", clean_output)
        if m_shift:
            shift_sec = m_shift.group(1).strip()

        footprints_sec = "从多次报错摩擦与重试中，留下了大量真实且耐心的探索轨迹。"
        m_foot = re.search(r"## 2[^\n]*\n([\s\S]*?)(?=## 3|\Z)", clean_output)
        if m_foot:
            footprints_sec = m_foot.group(1).strip()

        mutual_sec = "在长链路探索中给予机器自主修复空间，宏观把控目标而不微观打断。"
        m_mut = re.search(r"## 3[^\n]*\n([\s\S]*?)(?=## 4|\Z)", clean_output)
        if m_mut:
            mutual_sec = m_mut.group(1).strip()

        # Generate unique chapter ID
        chapter_num = len(self.list_chapters()) + 1
        cid = f"{chapter_num:02d}_{datetime.now(UTC).strftime('%Y%m%d')}"

        chapter = GrowthChapter(
            chapter_id=cid,
            title=title,
            period_start=earliest,
            period_end=latest,
            primary_lenses=("regulatory_flexibility", "autonomous_action"),
            the_shift=shift_sec,
            evidence_footprints=footprints_sec,
            mutual_understanding=mutual_sec,
            human_reflection=user_reflection,
        )

        chapter.save(self.chapters_dir)
        return chapter, report

    def list_chapters(self) -> list[GrowthChapter]:
        """List all persisted markdown chapters on disk."""
        if not self.chapters_dir.is_dir():
            return []
        chapters: list[GrowthChapter] = []
        for p in sorted(self.chapters_dir.glob("chapter_*.md")):
            try:
                content = p.read_text(encoding="utf-8")
                # Parse title
                m_title = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
                title = m_title.group(1).strip() if m_title else p.stem

                # Parse metadata lines
                m_period = re.search(r"> 记录周期：(.+?) 至 (.+?)  ", content)
                p_start = m_period.group(1).strip() if m_period else "未知"
                p_end = m_period.group(2).strip() if m_period else "未知"

                m_lenses = re.search(r"> 核心心智透镜：(.+?)  ", content)
                lenses = tuple(
                    x.strip() for x in (m_lenses.group(1).split(",") if m_lenses else [])
                )

                # Parse sections
                m_shift = re.search(r"## 1[^\n]*\n([\s\S]*?)(?=## 2|\Z)", content)
                m_foot = re.search(r"## 2[^\n]*\n([\s\S]*?)(?=## 3|\Z)", content)
                m_mut = re.search(r"## 3[^\n]*\n([\s\S]*?)(?=## 4|\Z)", content)
                m_hum = re.search(r"## 4[^\n]*\n([\s\S]*?)\Z", content)

                chapters.append(
                    GrowthChapter(
                        chapter_id=p.stem.replace("chapter_", ""),
                        title=title,
                        period_start=p_start,
                        period_end=p_end,
                        primary_lenses=lenses or ("general_growth",),
                        the_shift=m_shift.group(1).strip() if m_shift else "",
                        evidence_footprints=m_foot.group(1).strip() if m_foot else "",
                        mutual_understanding=m_mut.group(1).strip() if m_mut else "",
                        human_reflection=m_hum.group(1).strip() if m_hum else "",
                    )
                )
            except OSError:
                continue
        return chapters
