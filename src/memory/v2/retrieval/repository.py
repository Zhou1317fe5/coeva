"""Read-only Retrieval Repository and Rebuildable Derived Index.

Authoritative mapping to:
- Prompt §6: Data Access / File Ownership (self-contained read-only SQLite repository)
- Prompt §7: FTS5 / Derived Index (derived materialized view, rebuildable, canonical rows intact)
- docs/memory-v2/retrieval/technical-retrieval-design.md (§11, §18)

Invariants:
- Read-only connection: Never modifies production or canonical memory tables.
- Derived index: FTS5 virtual table is a rebuildable materialized view.
- Typed provenance: Extract canonical candidates with complete ProvenanceRef tuples.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from pathlib import Path

from src.memory.v2.retrieval.lexical import tokenize_text
from src.memory.v2.retrieval.models import CanonicalCandidateRecord, ProvenanceRef


class RetrievalRepository:
    """Read-only data access layer and rebuildable FTS5 index manager."""

    def __init__(
        self,
        db_path: Path | str,
        *,
        rebuild_index: bool = False,
        readonly: bool = False,
    ) -> None:
        self.db_path = str(db_path)
        self.readonly = readonly
        if self.readonly:
            resolved = Path(db_path).resolve().as_posix()
            self._conn = sqlite3.connect(
                f"file:{resolved}?mode=ro", uri=True, check_same_thread=True
            )
        else:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=True)
        self._conn.row_factory = sqlite3.Row
        if not self.readonly:
            self._ensure_fts5_index(rebuild=rebuild_index)

    def close(self) -> None:
        """Close SQLite connection."""
        self._conn.close()

    def _ensure_fts5_index(self, rebuild: bool = False) -> None:
        """Create or rebuild derived FTS5 virtual index over canonical tables."""
        if rebuild:
            self._conn.execute("DROP TABLE IF EXISTS fts_memory_statements")

        self._conn.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS fts_memory_statements USING fts5(
                candidate_id UNINDEXED,
                candidate_type UNINDEXED,
                scope UNINDEXED,
                project_id UNINDEXED,
                tokenized_statement
            )
            """
        )
        self._conn.commit()

    def rebuild_derived_index(self) -> int:
        """Drop and rebuild FTS5 derived index entirely from canonical tables.

        Returns total indexed count.
        """
        self._conn.execute("DROP TABLE IF EXISTS fts_memory_statements")
        self._ensure_fts5_index(rebuild=False)

        candidates = self.load_all_canonical_candidates()
        for cand in candidates:
            toks = " ".join(tokenize_text(cand.statement))
            self._conn.execute(
                """
                INSERT INTO fts_memory_statements(
                    candidate_id, candidate_type, scope, project_id, tokenized_statement
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (cand.candidate_id, cand.candidate_type, cand.scope, cand.project_id, toks),
            )
        self._conn.commit()
        return len(candidates)

    def _has_table(self, table_name: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?;", (table_name,)
        )
        return cur.fetchone() is not None

    def load_all_canonical_candidates(self) -> list[CanonicalCandidateRecord]:
        """Load all candidate memory entities from canonical 20-entity tables."""
        candidates: list[CanonicalCandidateRecord] = []

        # 1. semantic_memories
        if self._has_table("semantic_memories"):
            cur = self._conn.execute(
                """
                SELECT memory_id, category, statement, authority_class, scope,
                       project_id, valid_from, validity_status, expression_policy,
                       source_slice_id, source_event_id, source_episode_id
                FROM semantic_memories
                """
            )
            for row in cur.fetchall():
                mem_id = str(row["memory_id"])
                prov: list[ProvenanceRef] = []
                if row["source_slice_id"]:
                    prov.append(
                        ProvenanceRef(
                            kind="slice", id=str(row["source_slice_id"]), role="supporting"
                        )
                    )
                if row["source_event_id"]:
                    prov.append(
                        ProvenanceRef(
                            kind="event", id=str(row["source_event_id"]), role="supporting"
                        )
                    )
                if row["source_episode_id"]:
                    prov.append(
                        ProvenanceRef(
                            kind="episode", id=str(row["source_episode_id"]), role="contextual"
                        )
                    )

                proof_count = 1
                if self._has_table("evidence_reinforcements"):
                    r_cur = self._conn.execute(
                        "SELECT count(*) as c FROM evidence_reinforcements WHERE memory_id = ?",
                        (mem_id,),
                    )
                    r_count = int(r_cur.fetchone()["c"])
                    proof_count = 1 + r_count

                candidates.append(
                    CanonicalCandidateRecord(
                        candidate_id=mem_id,
                        candidate_type="semantic_memory",
                        category=str(row["category"]),
                        statement=str(row["statement"]),
                        scope=str(row["scope"]),
                        project_id=row["project_id"],
                        valid_from=str(row["valid_from"]),
                        validity_status=str(row["validity_status"]),
                        authority_class=str(row["authority_class"]),
                        proof_count=proof_count,
                        needs_privacy_redaction=0,
                        expression_policy=str(row["expression_policy"]),
                        provenance_refs=tuple(prov),
                    )
                )

        # 2. episodes
        if self._has_table("episodes"):
            cur = self._conn.execute(
                """
                SELECT episode_id, scope, project_id, started_at, closed_at,
                       title_hint, summary, status
                FROM episodes
                """
            )
            for row in cur.fetchall():
                ep_id = str(row["episode_id"])
                statement = str(row["summary"] or row["title_hint"])

                prov = []
                if self._has_table("episode_event_links"):
                    e_cur = self._conn.execute(
                        "SELECT event_id FROM episode_event_links WHERE episode_id = ?",
                        (ep_id,),
                    )
                    for erow in e_cur.fetchall():
                        prov.append(
                            ProvenanceRef(kind="event", id=str(erow["event_id"]), role="contextual")
                        )

                if self._has_table("episode_slice_links"):
                    s_cur = self._conn.execute(
                        "SELECT slice_id FROM episode_slice_links WHERE episode_id = ?",
                        (ep_id,),
                    )
                    for srow in s_cur.fetchall():
                        prov.append(
                            ProvenanceRef(kind="slice", id=str(srow["slice_id"]), role="supporting")
                        )

                candidates.append(
                    CanonicalCandidateRecord(
                        candidate_id=ep_id,
                        candidate_type="episode",
                        category="episode",
                        statement=statement,
                        scope=str(row["scope"]),
                        project_id=row["project_id"],
                        valid_from=str(row["started_at"]),
                        validity_status="active",
                        authority_class="system_observed",
                        proof_count=1,
                        needs_privacy_redaction=0,
                        expression_policy="normal",
                        provenance_refs=tuple(prov),
                    )
                )

        # 3. confirmed_insights
        if self._has_table("confirmed_insights"):
            cur = self._conn.execute(
                """
                SELECT insight_id, source_hypothesis_id, statement, valid_from,
                       status, superseded_by
                FROM confirmed_insights
                """
            )
            for row in cur.fetchall():
                ins_id = str(row["insight_id"])
                prov = [
                    ProvenanceRef(
                        kind="insight", id=str(row["source_hypothesis_id"]), role="supporting"
                    )
                ]
                candidates.append(
                    CanonicalCandidateRecord(
                        candidate_id=ins_id,
                        candidate_type="confirmed_insight",
                        category="confirmed_insight",
                        statement=str(row["statement"]),
                        scope="global",
                        project_id=None,
                        valid_from=str(row["valid_from"]),
                        validity_status=str(row["status"]),
                        authority_class="user_confirmed",
                        proof_count=2,
                        needs_privacy_redaction=0,
                        expression_policy="normal",
                        provenance_refs=tuple(prov),
                    )
                )

        # 4. chapter_metadata
        if self._has_table("chapter_metadata"):
            cur = self._conn.execute(
                """
                SELECT chapter_id, title, time_span_start, needs_privacy_redaction
                FROM chapter_metadata
                """
            )
            for row in cur.fetchall():
                chap_id = str(row["chapter_id"])
                prov = []
                if self._has_table("chapter_slice_links"):
                    s_cur = self._conn.execute(
                        "SELECT slice_id FROM chapter_slice_links WHERE chapter_id = ?",
                        (chap_id,),
                    )
                    for srow in s_cur.fetchall():
                        prov.append(
                            ProvenanceRef(kind="slice", id=str(srow["slice_id"]), role="supporting")
                        )
                if self._has_table("chapter_episode_links"):
                    e_cur = self._conn.execute(
                        "SELECT episode_id FROM chapter_episode_links WHERE chapter_id = ?",
                        (chap_id,),
                    )
                    for erow in e_cur.fetchall():
                        prov.append(
                            ProvenanceRef(
                                kind="episode", id=str(erow["episode_id"]), role="contextual"
                            )
                        )
                if self._has_table("chapter_insight_links"):
                    i_cur = self._conn.execute(
                        "SELECT insight_id FROM chapter_insight_links WHERE chapter_id = ?",
                        (chap_id,),
                    )
                    for irow in i_cur.fetchall():
                        prov.append(
                            ProvenanceRef(
                                kind="insight", id=str(irow["insight_id"]), role="supporting"
                            )
                        )
                needs_redaction = int(row["needs_privacy_redaction"])
                policy = "normal" if needs_redaction == 0 else "do_not_mention"
                candidates.append(
                    CanonicalCandidateRecord(
                        candidate_id=chap_id,
                        candidate_type="chapter_metadata",
                        category="narrative",
                        statement=str(row["title"]),
                        scope="global",
                        project_id=None,
                        valid_from=str(row["time_span_start"]),
                        validity_status="active",
                        authority_class="user_confirmed",
                        proof_count=1,
                        needs_privacy_redaction=needs_redaction,
                        expression_policy=policy,
                        provenance_refs=tuple(prov),
                    )
                )

        # 5. raw_slices
        if self._has_table("raw_slices"):
            cur = self._conn.execute(
                """
                SELECT slice_id, occurred_at, content, scope, project_id
                FROM raw_slices
                """
            )
            for row in cur.fetchall():
                sl_id = str(row["slice_id"])
                prov = [ProvenanceRef(kind="slice", id=sl_id, role="supporting")]
                candidates.append(
                    CanonicalCandidateRecord(
                        candidate_id=sl_id,
                        candidate_type="raw_slice",
                        category="raw_evidence",
                        statement=str(row["content"]),
                        scope=str(row["scope"]),
                        project_id=row["project_id"],
                        valid_from=str(row["occurred_at"]),
                        validity_status="active",
                        authority_class="user_asserted",
                        proof_count=1,
                        needs_privacy_redaction=0,
                        expression_policy="normal",
                        provenance_refs=tuple(prov),
                    )
                )

        return candidates


class StaticCandidateRepository:
    """In-memory candidate repository for benchmark datasets and testing."""

    def __init__(self, candidates: Sequence[CanonicalCandidateRecord]) -> None:
        self._candidates = list(candidates)

    def load_all_canonical_candidates(self) -> list[CanonicalCandidateRecord]:
        return list(self._candidates)
