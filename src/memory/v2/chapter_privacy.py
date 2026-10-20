"""Privacy Redaction and Regeneration Lifecycle for Growth Chapters (WP-9).

Part of Coeva Long-Term Memory V2.1 Stage 7 (WP-9).
Implements IMPL-3 P0 privacy safety:
- Immediate fail-closed unreadability upon privacy deletion marking
- Surviving source bundle reconstruction excluding retracted/deleted evidence
- Safe asynchronous redaction/regeneration with atomic file replacement
- Flag clearing ONLY after successful rewrite validation and link updating
- Fail-closed error handling (failure leaves flag=1, unreadable, no old text fallback)
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from src.core.llm_client import LLMClient
from src.memory.v2.chapter import (
    ChapterGeneratorV2,
    ChapterRepository,
    ChapterSourceBundle,
    NarrativeFirewallV2,
    NarrativeFirewallViolationError,
)
from src.memory.v2.entities import (
    ChapterEpisodeLinkEntity,
    ChapterInsightLinkEntity,
    ChapterSliceLinkEntity,
    ConfirmedInsightEntity,
    EpisodeEntity,
    RawSliceEntity,
)
from src.memory.v2.store import ChronicleStoreV2


@dataclass(frozen=True)
class ChapterRedactionResult:
    """Outcome of a privacy redaction or regeneration cycle."""

    success: bool
    chapter_id: str
    cleared_redaction: bool
    surviving_sources_count: int
    error: str | None = None
    actions_performed: list[str] = field(default_factory=list)


class ChapterPrivacyService:
    """Orchestrates immediate unreadability and safe privacy redaction/regeneration."""

    def __init__(
        self,
        store: ChronicleStoreV2,
        repo: ChapterRepository | None = None,
        client: LLMClient | None = None,
    ) -> None:
        self.store = store
        self.repo = repo or ChapterRepository(store)
        self.client = client
        self.generator = ChapterGeneratorV2(store, repo=self.repo, client=client)

    def mark_privacy_pending(self, chapter_id: str) -> None:
        """Mark a chapter as immediately needing privacy redaction (P0 Invariant).

        Once marked:
        - Chapter becomes immediately unreadable to normal readers.
        - Reader returns fail-closed placeholder or None.
        - Stale markdown is never returned.
        """
        self.store.update_chapter_privacy_redaction(chapter_id, 1)

    def is_unreadable(self, chapter_id: str) -> bool:
        """Check whether a chapter is currently blocked due to privacy pending."""
        meta = self.store.get_chapter_metadata(chapter_id)
        if not meta:
            return True
        return meta.needs_privacy_redaction == 1

    def redact_or_regenerate_chapter(
        self,
        chapter_id: str,
        *,
        simulate_failure: bool = False,
    ) -> ChapterRedactionResult:
        """Safely execute privacy redaction or narrative regeneration.

        Sequence:
        1. Ensure needs_privacy_redaction = 1 (fails closed immediately).
        2. Inspect linked sources and filter for surviving, valid evidence.
        3. If simulate_failure or rewrite fails:
           - Flag remains 1.
           - Stale text remains unreadable.
           - Returns failure result.
        4. If no safe sources remain:
           - Write minimal safe redacted archive markdown.
           - Atomically replace file.
           - In DB transaction: clear old links, clear redaction flag.
        5. If safe sources remain:
           - Build surviving ChapterSourceBundle.
           - Regenerate narrative grounded ONLY on surviving sources.
           - Validate with NarrativeFirewallV2.
           - Atomically replace file.
           - In DB transaction: clear old links, insert surviving links, clear redaction flag.
        """
        actions: list[str] = []

        # 1. Ensure chapter exists
        meta = self.store.get_chapter_metadata(chapter_id)
        if not meta:
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=0,
                error=f"Chapter '{chapter_id}' not found in metadata store.",
            )

        # Ensure marked privacy pending immediately
        if meta.needs_privacy_redaction != 1:
            self.mark_privacy_pending(chapter_id)
            actions.append("marked_privacy_pending")

        # Check for simulated failure before any replacement
        if simulate_failure:
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=0,
                error="Simulated redaction worker failure; chapter remains unreadable.",
                actions_performed=actions,
            )

        # 2. Inspect currently linked sources
        slice_links = self.store.get_chapter_slice_links(chapter_id)
        ep_links = self.store.get_chapter_episode_links(chapter_id)
        ins_links = self.store.get_chapter_insight_links(chapter_id)

        # Filter surviving sources
        surviving_slices: list[RawSliceEntity] = []
        for sl in slice_links:
            s = self.store.get_raw_slice(sl.slice_id)
            if s is not None:
                surviving_slices.append(s)

        surviving_episodes: list[EpisodeEntity] = []
        for el in ep_links:
            ep = self.store.get_episode(el.episode_id)
            if ep is not None:
                surviving_episodes.append(ep)

        surviving_insights: list[ConfirmedInsightEntity] = []
        for il in ins_links:
            ins = self.store.get_confirmed_insight(il.insight_id)
            # Only active, confirmed insights count as surviving legal sources
            if ins is not None and ins.status == "confirmed":
                surviving_insights.append(ins)

        surviving_count = len(surviving_slices) + len(surviving_episodes) + len(surviving_insights)
        final_file = Path(meta.file_path)

        # Case A: No safe sources remain
        if surviving_count == 0:
            redacted_content = (
                f"# {meta.title} (已脱敏归档)\n\n"
                "> 记录状态：隐私脱敏归档  \n"
                f"> 原记录周期：{meta.time_span_start} 至 {meta.time_span_end}  \n\n"
                "[由于用户隐私擦除请求，本章节引用的所有底层事件与共识已全部脱敏删除。]\n"
            )
            # Validate redacted content
            is_valid, violations = NarrativeFirewallV2.validate_narrative(redacted_content)
            if not is_valid:
                return ChapterRedactionResult(
                    success=False,
                    chapter_id=chapter_id,
                    cleared_redaction=False,
                    surviving_sources_count=0,
                    error=f"Redacted archive violates firewall: {violations}",
                    actions_performed=actions,
                )

            # Atomic file replacement
            tmp_file = final_file.parent / f"{final_file.name}.tmp_{uuid.uuid4().hex}"
            try:
                tmp_file.write_text(redacted_content, encoding="utf-8")
                os.replace(tmp_file, final_file)
                actions.append("replaced_file_with_redacted_archive")
            except Exception as e:
                if tmp_file.exists():
                    tmp_file.unlink(missing_ok=True)
                return ChapterRedactionResult(
                    success=False,
                    chapter_id=chapter_id,
                    cleared_redaction=False,
                    surviving_sources_count=0,
                    error=f"Failed to replace chapter file: {e}",
                    actions_performed=actions,
                )

            # Atomic DB transaction: clear old links, clear redaction flag
            try:
                with self.store.transaction():
                    self.store.clear_chapter_links(chapter_id)
                    self.store.update_chapter_privacy_redaction(chapter_id, 0)
                actions.append("cleared_links_and_redaction_flag")
            except Exception as e:
                # If DB fails, mark flag back to 1 to fail closed
                self.store.update_chapter_privacy_redaction(chapter_id, 1)
                return ChapterRedactionResult(
                    success=False,
                    chapter_id=chapter_id,
                    cleared_redaction=False,
                    surviving_sources_count=0,
                    error=f"DB link update failed: {e}",
                    actions_performed=actions,
                )

            return ChapterRedactionResult(
                success=True,
                chapter_id=chapter_id,
                cleared_redaction=True,
                surviving_sources_count=0,
                actions_performed=actions,
            )

        # Case B: Surviving sources exist -> Regenerate grounded on surviving sources
        bundle = ChapterSourceBundle(
            time_span_start=meta.time_span_start,
            time_span_end=meta.time_span_end,
            confirmed_insights=tuple(surviving_insights),
            episodes=tuple(surviving_episodes),
            raw_slices=tuple(surviving_slices),
        )

        try:
            gen_result = self.generator.generate(
                bundle,
                title=meta.title,
                created_at=meta.created_at,
            )
        except NarrativeFirewallViolationError as e:
            # Firewall violation: fail closed, flag remains 1
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=surviving_count,
                error=f"Rewritten narrative failed firewall: {e}",
                actions_performed=actions,
            )
        except Exception as e:
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=surviving_count,
                error=f"Regeneration failed: {e}",
                actions_performed=actions,
            )

        # Atomic replacement of disk artifact
        tmp_file = final_file.parent / f"{final_file.name}.tmp_{uuid.uuid4().hex}"
        try:
            tmp_file.write_text(gen_result.markdown_content, encoding="utf-8")
            os.replace(tmp_file, final_file)
            actions.append("atomically_replaced_file")
        except Exception as e:
            if tmp_file.exists():
                tmp_file.unlink(missing_ok=True)
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=surviving_count,
                error=f"Atomic file replacement failed: {e}",
                actions_performed=actions,
            )

        # Atomic DB transaction: update typed links and clear flag
        now_ts = datetime.now(UTC).isoformat()
        try:
            with self.store.transaction():
                self.store.clear_chapter_links(chapter_id)
                for s_id in bundle.slice_ids:
                    self.store.insert_chapter_slice_link(
                        ChapterSliceLinkEntity(
                            chapter_id=chapter_id,
                            slice_id=s_id,
                            linked_at=now_ts,
                        )
                    )
                for e_id in bundle.episode_ids:
                    self.store.insert_chapter_episode_link(
                        ChapterEpisodeLinkEntity(
                            chapter_id=chapter_id,
                            episode_id=e_id,
                            linked_at=now_ts,
                        )
                    )
                for i_id in bundle.insight_ids:
                    self.store.insert_chapter_insight_link(
                        ChapterInsightLinkEntity(
                            chapter_id=chapter_id,
                            insight_id=i_id,
                            linked_at=now_ts,
                        )
                    )
                self.store.update_chapter_privacy_redaction(chapter_id, 0)
            actions.append("updated_links_and_cleared_redaction_flag")
        except Exception as e:
            # Rollback to unreadable flag
            self.store.update_chapter_privacy_redaction(chapter_id, 1)
            return ChapterRedactionResult(
                success=False,
                chapter_id=chapter_id,
                cleared_redaction=False,
                surviving_sources_count=surviving_count,
                error=f"Failed to update chapter links in DB: {e}",
                actions_performed=actions,
            )

        return ChapterRedactionResult(
            success=True,
            chapter_id=chapter_id,
            cleared_redaction=True,
            surviving_sources_count=surviving_count,
            actions_performed=actions,
        )
