-- Co-evolving Companion (Coeva) Long-Term Memory V2.1 Schema Definition
-- Formal implementation of docs/memory-v2/cross-session-long-term-memory-v2.1-data-model.md
-- Canonical Memory Entity Count: Exactly 20 tables
-- Technical Operational / Migration Metadata: Exactly 4 tables (isolated from memory entities)

PRAGMA foreign_keys = ON;

-- ============================================================================
-- 1. Core Evidence & Experience Container Entities (5 Tables)
-- ============================================================================

-- Entity 1: raw_slices (Canonical User Raw Input Evidence, Immutable Content)
CREATE TABLE IF NOT EXISTS raw_slices (
    slice_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    content TEXT NOT NULL,
    actor TEXT NOT NULL DEFAULT 'user',
    source TEXT NOT NULL DEFAULT 'manual_feed',
    scope TEXT NOT NULL DEFAULT 'unresolved',
    project_id TEXT,
    ingestion_dedup_key TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (actor IN ('user')),
    CHECK (source IN ('manual_feed', 'bubble_reply')),
    CHECK (scope IN ('global', 'project', 'unresolved')),
    CHECK (
        (scope = 'unresolved' AND project_id IS NULL) OR
        (scope = 'global' AND project_id = 'global') OR
        (scope = 'project' AND project_id IS NOT NULL AND length(project_id) > 0)
    )
);
CREATE INDEX IF NOT EXISTS idx_raw_slices_occurred ON raw_slices(occurred_at);
CREATE INDEX IF NOT EXISTS idx_raw_slices_scope ON raw_slices(scope, project_id, occurred_at);

-- Entity 2: event_skeletons (External Agent Behavior Telemetry Skeleton)
CREATE TABLE IF NOT EXISTS event_skeletons (
    event_id TEXT PRIMARY KEY,
    occurred_at TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    tool_name TEXT NOT NULL DEFAULT '',
    error_category TEXT NOT NULL DEFAULT '',
    retention_class TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (retention_class IN ('transient', 'durable'))
);
CREATE INDEX IF NOT EXISTS idx_event_skeletons_occurred ON event_skeletons(occurred_at);
CREATE INDEX IF NOT EXISTS idx_event_skeletons_session ON event_skeletons(session_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_event_skeletons_retention ON event_skeletons(retention_class, occurred_at);

-- Entity 3: episodes (Experience Grouping Container, Derived Non-Evidence)
CREATE TABLE IF NOT EXISTS episodes (
    episode_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    project_id TEXT,
    started_at TEXT NOT NULL,
    closed_at TEXT,
    title_hint TEXT NOT NULL,
    summary TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (scope IN ('global', 'project', 'unresolved')),
    CHECK (status IN ('open', 'closed', 'archived'))
);
CREATE INDEX IF NOT EXISTS idx_episodes_scope ON episodes(scope, project_id, started_at);
CREATE INDEX IF NOT EXISTS idx_episodes_status ON episodes(status);

-- Entity 4: episode_slice_links (Typed Relation: Episode <-> Raw Slice)
CREATE TABLE IF NOT EXISTS episode_slice_links (
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    slice_id TEXT NOT NULL REFERENCES raw_slices(slice_id) ON DELETE RESTRICT,
    curation_source TEXT NOT NULL DEFAULT 'system',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (episode_id, slice_id),
    CHECK (curation_source IN ('system', 'user'))
);
CREATE INDEX IF NOT EXISTS idx_ep_slice_links_slice ON episode_slice_links(slice_id);

-- Entity 5: episode_event_links (Typed Relation: Episode <-> Event Skeleton)
CREATE TABLE IF NOT EXISTS episode_event_links (
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES event_skeletons(event_id) ON DELETE RESTRICT,
    curation_source TEXT NOT NULL DEFAULT 'system',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (episode_id, event_id),
    CHECK (curation_source IN ('system', 'user'))
);
CREATE INDEX IF NOT EXISTS idx_ep_event_links_event ON episode_event_links(event_id);

-- ============================================================================
-- 2. Derived Facts & Understanding Belief Entities (7 Tables)
-- ============================================================================

-- Entity 6: semantic_memories (Atomic Semantic Facts, Preferences, Rules)
CREATE TABLE IF NOT EXISTS semantic_memories (
    memory_id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    statement TEXT NOT NULL,
    authority_class TEXT NOT NULL,
    scope TEXT NOT NULL,
    project_id TEXT,
    source_slice_id TEXT REFERENCES raw_slices(slice_id) ON DELETE RESTRICT,
    source_event_id TEXT REFERENCES event_skeletons(event_id) ON DELETE RESTRICT,
    source_episode_id TEXT REFERENCES episodes(episode_id) ON DELETE RESTRICT,
    valid_from TEXT NOT NULL,
    invalidated_at TEXT,
    superseded_by TEXT REFERENCES semantic_memories(memory_id) ON DELETE SET NULL,
    validity_status TEXT NOT NULL,
    expression_policy TEXT NOT NULL DEFAULT 'normal',
    created_at TEXT NOT NULL,
    CHECK (category IN ('preference', 'fact', 'relationship_rule', 'goal')),
    CHECK (authority_class IN ('user_asserted', 'system_observed', 'user_confirmed')),
    CHECK (scope IN ('global', 'project', 'unresolved')),
    CHECK (validity_status IN ('active', 'superseded', 'invalidated', 'ambiguous')),
    CHECK (expression_policy IN ('normal', 'muted', 'do_not_mention')),
    CHECK (source_slice_id IS NOT NULL OR source_event_id IS NOT NULL OR source_episode_id IS NOT NULL)
);
CREATE INDEX IF NOT EXISTS idx_sem_mem_scope ON semantic_memories(scope, project_id, validity_status, valid_from);
CREATE INDEX IF NOT EXISTS idx_sem_mem_slice ON semantic_memories(source_slice_id);
CREATE INDEX IF NOT EXISTS idx_sem_mem_event ON semantic_memories(source_event_id);
CREATE INDEX IF NOT EXISTS idx_sem_mem_episode ON semantic_memories(source_episode_id);
CREATE INDEX IF NOT EXISTS idx_sem_mem_superseded ON semantic_memories(superseded_by);

-- Entity 7: evidence_reinforcements (Independent Evidence Ledger)
CREATE TABLE IF NOT EXISTS evidence_reinforcements (
    reinforcement_id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES semantic_memories(memory_id) ON DELETE CASCADE,
    slice_id TEXT REFERENCES raw_slices(slice_id) ON DELETE RESTRICT,
    event_id TEXT REFERENCES event_skeletons(event_id) ON DELETE RESTRICT,
    independence_fingerprint TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(memory_id, independence_fingerprint)
);
CREATE INDEX IF NOT EXISTS idx_ev_reinf_mem ON evidence_reinforcements(memory_id);
CREATE INDEX IF NOT EXISTS idx_ev_reinf_slice ON evidence_reinforcements(slice_id);
CREATE INDEX IF NOT EXISTS idx_ev_reinf_event ON evidence_reinforcements(event_id);

-- Entity 8: observations (Aggregated Objective Beliefs)
CREATE TABLE IF NOT EXISTS observations (
    observation_id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    project_id TEXT,
    statement TEXT NOT NULL,
    proof_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    CHECK (scope IN ('global', 'project', 'unresolved')),
    CHECK (status IN ('active', 'retracted'))
);
CREATE INDEX IF NOT EXISTS idx_obs_scope ON observations(scope, project_id, status);

-- Entity 9: observation_slice_links (Typed Relation: Observation <-> Raw Slice)
CREATE TABLE IF NOT EXISTS observation_slice_links (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    slice_id TEXT NOT NULL REFERENCES raw_slices(slice_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'supporting',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (observation_id, slice_id),
    CHECK (role IN ('supporting', 'counter'))
);
CREATE INDEX IF NOT EXISTS idx_obs_slice_links_slice ON observation_slice_links(slice_id);

-- Entity 10: observation_event_links (Typed Relation: Observation <-> Event Skeleton, Retention Pinning)
CREATE TABLE IF NOT EXISTS observation_event_links (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    event_id TEXT NOT NULL REFERENCES event_skeletons(event_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'supporting',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (observation_id, event_id),
    CHECK (role IN ('supporting', 'counter'))
);
CREATE INDEX IF NOT EXISTS idx_obs_event_links_event ON observation_event_links(event_id);

-- Entity 11: observation_memory_links (Typed Relation: Observation <-> Semantic Memory)
CREATE TABLE IF NOT EXISTS observation_memory_links (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    memory_id TEXT NOT NULL REFERENCES semantic_memories(memory_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'supporting',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (observation_id, memory_id),
    CHECK (role IN ('supporting', 'counter'))
);
CREATE INDEX IF NOT EXISTS idx_obs_mem_links_mem ON observation_memory_links(memory_id);

-- Entity 12: observation_episode_links (Typed Relation: Observation <-> Episode Contextual Scope)
CREATE TABLE IF NOT EXISTS observation_episode_links (
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'contextual_scope',
    linked_at TEXT NOT NULL,
    PRIMARY KEY (observation_id, episode_id),
    CHECK (role IN ('contextual_scope'))
);
CREATE INDEX IF NOT EXISTS idx_obs_ep_links_ep ON observation_episode_links(episode_id);

-- ============================================================================
-- 3. Hypotheses & Human Calibration Consensus Entities (4 Tables)
-- ============================================================================

-- Entity 13: hypotheses (Candidate Development Hypotheses)
CREATE TABLE IF NOT EXISTS hypotheses (
    hypothesis_id TEXT PRIMARY KEY,
    statement TEXT NOT NULL,
    lenses TEXT NOT NULL,
    confidence_class TEXT NOT NULL,
    status TEXT NOT NULL,
    last_calibrated_at TEXT,
    created_at TEXT NOT NULL,
    CHECK (confidence_class IN ('tentative', 'grounded')),
    CHECK (status IN ('candidate', 'rejected', 'revalidation_required', 'retracted'))
);
CREATE INDEX IF NOT EXISTS idx_hyp_status ON hypotheses(status);

-- Entity 14: hypothesis_observation_links (Typed Relation: Hypothesis <-> Observation)
CREATE TABLE IF NOT EXISTS hypothesis_observation_links (
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE CASCADE,
    observation_id TEXT NOT NULL REFERENCES observations(observation_id) ON DELETE RESTRICT,
    role TEXT NOT NULL DEFAULT 'supporting',
    is_primary INTEGER NOT NULL DEFAULT 0,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (hypothesis_id, observation_id),
    CHECK (role IN ('supporting', 'counter', 'contextual')),
    CHECK (is_primary IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_hyp_obs_links_obs ON hypothesis_observation_links(observation_id);

-- Entity 15: calibration_events (Immutable Human Calibration Action Log)
CREATE TABLE IF NOT EXISTS calibration_events (
    calibration_id TEXT PRIMARY KEY,
    hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE RESTRICT,
    user_action TEXT NOT NULL,
    user_note TEXT,
    calibrated_at TEXT NOT NULL,
    CHECK (user_action IN ('yes', 'partly', 'no'))
);
CREATE INDEX IF NOT EXISTS idx_calib_events_hyp ON calibration_events(hypothesis_id, calibrated_at);

-- Entity 16: confirmed_insights (Confirmed Self Model Consensus Entity)
CREATE TABLE IF NOT EXISTS confirmed_insights (
    insight_id TEXT PRIMARY KEY,
    source_hypothesis_id TEXT NOT NULL REFERENCES hypotheses(hypothesis_id) ON DELETE RESTRICT,
    source_calibration_id TEXT NOT NULL REFERENCES calibration_events(calibration_id) ON DELETE RESTRICT,
    statement TEXT NOT NULL,
    valid_from TEXT NOT NULL,
    invalidated_at TEXT,
    superseded_by TEXT REFERENCES confirmed_insights(insight_id) ON DELETE SET NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (status IN ('confirmed', 'superseded', 'revalidation_required', 'retracted'))
);
CREATE INDEX IF NOT EXISTS idx_conf_insights_status ON confirmed_insights(status, valid_from);
CREATE INDEX IF NOT EXISTS idx_conf_insights_hyp ON confirmed_insights(source_hypothesis_id);

-- ============================================================================
-- 4. Narrative Metadata & Cross-Domain Links (4 Tables)
-- ============================================================================

-- Entity 17: chapter_metadata (Growth Chapter Index & Privacy Redaction Tracker)
CREATE TABLE IF NOT EXISTS chapter_metadata (
    chapter_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    file_path TEXT UNIQUE NOT NULL,
    time_span_start TEXT NOT NULL,
    time_span_end TEXT NOT NULL,
    needs_privacy_redaction INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    CHECK (needs_privacy_redaction IN (0, 1))
);

-- Entity 18: chapter_slice_links (Typed Relation: Chapter <-> Raw Slice)
CREATE TABLE IF NOT EXISTS chapter_slice_links (
    chapter_id TEXT NOT NULL REFERENCES chapter_metadata(chapter_id) ON DELETE CASCADE,
    slice_id TEXT NOT NULL REFERENCES raw_slices(slice_id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (chapter_id, slice_id)
);
CREATE INDEX IF NOT EXISTS idx_chap_slice_links_slice ON chapter_slice_links(slice_id);

-- Entity 19: chapter_episode_links (Typed Relation: Chapter <-> Episode)
CREATE TABLE IF NOT EXISTS chapter_episode_links (
    chapter_id TEXT NOT NULL REFERENCES chapter_metadata(chapter_id) ON DELETE CASCADE,
    episode_id TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (chapter_id, episode_id)
);
CREATE INDEX IF NOT EXISTS idx_chap_ep_links_ep ON chapter_episode_links(episode_id);

-- Entity 20: chapter_insight_links (Typed Relation: Chapter <-> Confirmed Insight)
CREATE TABLE IF NOT EXISTS chapter_insight_links (
    chapter_id TEXT NOT NULL REFERENCES chapter_metadata(chapter_id) ON DELETE CASCADE,
    insight_id TEXT NOT NULL REFERENCES confirmed_insights(insight_id) ON DELETE RESTRICT,
    linked_at TEXT NOT NULL,
    PRIMARY KEY (chapter_id, insight_id)
);
CREATE INDEX IF NOT EXISTS idx_chap_ins_links_ins ON chapter_insight_links(insight_id);

-- ============================================================================
-- 5. Technical Operational & Migration Metadata Tables (Isolated from Memory Truth)
-- ============================================================================

-- Migration ledger tracking schema migrations
CREATE TABLE IF NOT EXISTS _schema_migrations (
    migration_id TEXT PRIMARY KEY,
    source_version INTEGER NOT NULL,
    target_version INTEGER NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    checksum TEXT,
    error_message TEXT
);

-- Technical audit metadata for legacy V1 hypotheses (non-canonical, not in retrieval)
CREATE TABLE IF NOT EXISTS legacy_hypothesis_audit (
    hypothesis_id TEXT PRIMARY KEY,
    original_statement TEXT NOT NULL,
    original_status TEXT NOT NULL,
    original_lenses TEXT NOT NULL,
    original_confidence TEXT,
    supporting_episodes_raw TEXT,
    migrated_at TEXT NOT NULL
);

-- Operational background job queue for near-real-time consolidation
CREATE TABLE IF NOT EXISTS consolidation_jobs (
    job_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Operational tracker for idle background backfill progress
CREATE TABLE IF NOT EXISTS backfill_progress (
    task_name TEXT PRIMARY KEY,
    last_processed_id TEXT,
    processed_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'idle',
    updated_at TEXT NOT NULL
);
