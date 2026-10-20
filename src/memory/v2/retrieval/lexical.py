"""Lexical channel and application-level dual-track tokenization (FTS5 compatible).

Authoritative mapping to:
- docs/memory-v2/retrieval/technical-retrieval-design.md (§11 Lexical Channel Design)
- docs/memory-v2/retrieval/retrieval-decision-record.md (Decision 2)

Dual-Track Tokenization:
- English alphanumeric and technical identifiers: regex [a-zA-Z0-9_\-\.]{2,}, lowercased.
- Chinese characters: unigrams and adjacent bigrams.
- Non-informative stopwords removed.
- Weighted overlap: bigrams/words len >= 2 weight 2.0, unigrams weight 0.5.
"""

from __future__ import annotations

import re

# Standard Chinese & English conversational non-informative stopwords
STOP_WORDS: frozenset[str] = frozenset(
    {
        "的",
        "了",
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "在",
        "有",
        "是",
        "和",
        "就",
        "还",
        "这",
        "那",
        "个",
        "什么",
        "怎么",
        "哪个",
        "关于",
        "一下",
        "问你",
        "知道",
        "记得",
        "说",
        "想",
        "做",
        "看",
        "写",
        "帮我",
        "看看",
        "告诉",
        "我们",
        "你们",
        "他们",
        "我",
        "你",
        "他",
        "她",
        "它",
        "是不是",
        "有没有",
    }
)


def tokenize_text(text: str) -> list[str]:
    """Extract ordered unique unigram/bigram tokens from mixed Chinese-English text."""
    tokens: list[str] = []

    # 1. English words, numbers, and technical identifiers
    en_words = re.findall(r"[a-zA-Z0-9_\-\.]{2,}", text)
    for w in en_words:
        w_lower = w.lower()
        if w_lower not in STOP_WORDS and w_lower not in tokens:
            tokens.append(w_lower)

    # 2. Chinese unigrams and bigrams
    cleaned = re.sub(r"[\s，。！？、；：“”\"\'（）\(\)\[\]]", "", text)
    chars = [c for c in cleaned if "\u4e00" <= c <= "\u9fff"]
    for i, c in enumerate(chars):
        if c not in STOP_WORDS and c not in tokens:
            tokens.append(c)
        if i + 1 < len(chars):
            bg = c + chars[i + 1]
            if bg not in STOP_WORDS and bg not in tokens:
                tokens.append(bg)

    return tokens


def compute_lexical_score(
    q_tokens: list[str],
    d_tokens: list[str],
    *,
    bigram_weight: float = 2.0,
    unigram_weight: float = 0.5,
) -> float:
    """Compute weighted lexical overlap score in [0.0, 1.0]."""
    if not q_tokens or not d_tokens:
        return 0.0

    d_set = set(d_tokens)
    score = 0.0
    total_w = 0.0

    for q in q_tokens:
        w = bigram_weight if len(q) >= 2 else unigram_weight
        total_w += w
        if q in d_set:
            score += w

    return score / total_w if total_w > 0 else 0.0
