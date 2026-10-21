"""Long-term memory retriever for cross-session companion recall.

Extracts relevant past slices based on temporal intent (e.g. 昨天、前天),
open-ended memory queries (e.g. 还记得什么、聊过什么), and semantic topic keywords.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta

from src.core.personality import format_memory_snippet
from src.memory.store import ChronicleStore, SliceRecord

# Common non-informative conversational stop words in Chinese and English
DEFAULT_STOP_WORDS: frozenset[str] = frozenset(
    {
        "你",
        "我",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "自己",
        "的",
        "了",
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "哦",
        "嗯",
        "啦",
        "在",
        "有",
        "是",
        "和",
        "就",
        "还",
        "这",
        "那",
        "个",
        "说",
        "想",
        "做",
        "去",
        "吃",
        "看",
        "听",
        "到",
        "着",
        "过",
        "得",
        "什么",
        "怎么",
        "怎样",
        "如何",
        "为什么",
        "哪里",
        "哪个",
        "之前",
        "前天",
        "昨天",
        "今天",
        "明天",
        "后天",
        "大前天",
        "聊了",
        "聊过",
        "讨论",
        "谈到",
        "提过",
        "说过",
        "关于",
        "一下",
        "问你",
        "知道",
        "记得",
        "还记得",
        "了解",
        "认识",
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "to",
        "for",
        "in",
        "on",
    }
)

# Low-entropy greetings and acknowledgments to skip when selecting memorable history
DEFAULT_TRIVIAL_SLICES: frozenset[str] = frozenset(
    {
        "hi",
        "hello",
        "hey",
        "你好",
        "您好",
        "嗨",
        "早",
        "早安",
        "晚安",
        "测试",
        "测试气泡",
        "测试发消息",
        "你是谁",
        "你是？",
        "你是",
        "嗯",
        "嗯嗯",
        "好的",
        "嗯嗯好的",
        "行",
        "收到",
        "好嘞",
    }
)

# Markers indicating the user is explicitly inquiring about companion's memory
DEFAULT_MEMORY_INTENT_MARKERS: tuple[str, ...] = (
    "还记得",
    "记得什么",
    "记得我",
    "你记得",
    "还记不记得",
    "聊了什么",
    "聊过什么",
    "说了什么",
    "提过什么",
    "讨论了什么",
    "了解我",
    "认识我",
    "关于我",
    "有什么记忆",
    "记忆库",
    "记得不",
)


class MemoryRetriever:
    """Intelligent cross-session memory retrieval engine backed by ChronicleStore."""

    def __init__(
        self,
        store: ChronicleStore,
        *,
        stop_words: frozenset[str] = DEFAULT_STOP_WORDS,
        trivial_slices: frozenset[str] = DEFAULT_TRIVIAL_SLICES,
        memory_intent_markers: tuple[str, ...] = DEFAULT_MEMORY_INTENT_MARKERS,
    ) -> None:
        self.store = store
        self.stop_words = stop_words
        self.trivial_slices = trivial_slices
        self.memory_intent_markers = memory_intent_markers

    def _is_meaningful_slice(self, content: str) -> bool:
        """Check if slice contains substantial context worthy of long-term memory."""
        c = content.strip().lower()
        if not c or len(c) < 2:
            return False
        if c in self.trivial_slices:
            return False
        # Do not recall meta-questions themselves as historical memories
        if any(marker in c for marker in self.memory_intent_markers):
            return False
        return True

    def _detect_temporal_target(self, text: str, local_date: date) -> date | None:
        """Parse natural language relative dates into specific target calendar date."""
        if "昨天" in text or "昨日" in text:
            return local_date - timedelta(days=1)
        if "前天" in text:
            return local_date - timedelta(days=2)
        if "大前天" in text:
            return local_date - timedelta(days=3)
        if "今天" in text or "今日" in text:
            return local_date

        days_ago_match = re.search(r"(\d+)\s*(?:天|日)前", text)
        if days_ago_match:
            try:
                days = int(days_ago_match.group(1))
                if 0 <= days <= 365:
                    return local_date - timedelta(days=days)
            except ValueError:
                pass

        return None

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract multi-character search keywords and n-grams from query."""
        keywords: list[str] = []

        # 1. Alphanumeric / English words (e.g. "python", "bug", "gui")
        en_words = re.findall(r"[a-zA-Z0-9_\-\.]{2,}", text)
        for w in en_words:
            w_lower = w.lower()
            if w_lower not in self.stop_words and w not in keywords:
                keywords.append(w)

        # 2. Chinese text cleanup
        cleaned = re.sub(r"[\s，。！？、；：“”\"'（）\(\)\[\]]", "", text)
        for sw in sorted(self.stop_words, key=len, reverse=True):
            cleaned = cleaned.replace(sw, " ")

        for part in cleaned.split():
            part = part.strip()
            if len(part) >= 2:
                if part not in keywords:
                    keywords.append(part)
                # Generate sub-grams (2-char and 3-char) for fuzzy substring matching
                if len(part) > 2:
                    for n in (2, 3):
                        for i in range(len(part) - n + 1):
                            sub = part[i : i + n]
                            if sub not in keywords and sub not in self.stop_words:
                                keywords.append(sub)

        return keywords

    def recall_records(
        self,
        query: str,
        *,
        limit: int = 3,
        exclude_ids: set[str] | None = None,
        now: datetime | None = None,
    ) -> list[SliceRecord]:
        """Retrieve relevant past SliceRecords matching temporal intent, keywords, or open query."""
        clean_q = query.strip()
        if not clean_q:
            return []

        exclude = set(exclude_ids or ())
        current_time = now or datetime.now()
        local_date = current_time.date()

        recalled_slices: list[SliceRecord] = []
        seen_ids: set[str] = set(exclude)
        seen_contents: set[str] = {clean_q}

        # ── 1. Temporal Intent Recall ──
        target_date = self._detect_temporal_target(clean_q, local_date)
        if target_date is not None:
            start_local = datetime.combine(target_date, time.min).astimezone()
            end_local = datetime.combine(target_date, time.max).astimezone()
            start_utc_iso = start_local.astimezone(UTC).isoformat()
            end_utc_iso = end_local.astimezone(UTC).isoformat()

            # Query database by exact UTC timestamp range
            date_slices = self.store.get_slices_in_timerange(start_utc_iso, end_utc_iso, limit=50)

            # Fallback for slices recorded with date prefix if any
            if not date_slices:
                date_prefix = target_date.strftime("%Y-%m-%d")
                date_slices = self.store.search_slices(date_prefix, limit=30)

            for s in date_slices:
                s_content = s.content.strip()
                if s.id not in seen_ids and s_content not in seen_contents:
                    if not self._is_meaningful_slice(s_content):
                        continue
                    seen_ids.add(s.id)
                    seen_contents.add(s_content)
                    recalled_slices.append(s)
                    if len(recalled_slices) >= limit:
                        break

        # If an explicit date was requested, we strictly honor the temporal target
        # and do not backfill with unrelated dates.
        if target_date is not None:
            return recalled_slices[:limit]

        # ── 2. Topic / Keyword Substring Search ──
        keywords = self._extract_keywords(clean_q)
        if keywords and len(recalled_slices) < limit:
            for kw in keywords:
                matches = self.store.search_slices(kw, limit=10)
                for m in matches:
                    m_content = m.content.strip()
                    if m.id not in seen_ids and m_content not in seen_contents:
                        if not self._is_meaningful_slice(m_content):
                            continue
                        seen_ids.add(m.id)
                        seen_contents.add(m_content)
                        recalled_slices.append(m)
                        if len(recalled_slices) >= limit:
                            break
                if len(recalled_slices) >= limit:
                    break

        # ── 3. Open-ended Memory Intent Recall ──
        is_memory_intent = any(marker in clean_q for marker in self.memory_intent_markers)
        if is_memory_intent and len(recalled_slices) < limit:
            recent_slices = self.store.list_slices(limit=30)
            for s in recent_slices:
                s_content = s.content.strip()
                if s.id not in seen_ids and s_content not in seen_contents:
                    if not self._is_meaningful_slice(s_content):
                        continue
                    seen_ids.add(s.id)
                    seen_contents.add(s_content)
                    recalled_slices.append(s)
                    if len(recalled_slices) >= limit:
                        break

        return recalled_slices[:limit]

    def recall(
        self,
        query: str,
        *,
        limit: int = 3,
        exclude_ids: set[str] | None = None,
        now: datetime | None = None,
    ) -> tuple[str, ...]:
        """Format recalled memories into ready-to-inject LLM system prompt snippets."""
        records = self.recall_records(
            query,
            limit=limit,
            exclude_ids=exclude_ids,
            now=now,
        )
        return tuple(format_memory_snippet(r.timestamp, r.content) for r in records)
