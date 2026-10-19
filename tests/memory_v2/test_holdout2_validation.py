"""Independent Holdout 2 Validation Suite for WP-7 Retrieval V2.1.

This test suite validates the frozen retrieval configuration against a brand-new,
independent, previously unseen set of 12 test cases (Holdout 2), satisfying the
Case A protocol requirement after extensive inspection of the original Holdout set.

Requirements:
- 100% Query Pass Rate (12/12)
- Zero Forbidden Retrieval violations
- Zero Cross-Project Contamination
- Zero Privacy Leakage
- Zero Supersession Failures
- Strict confidence threshold 0.16
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory.v2.retrieval.config import RetrievalConfig
from src.memory.v2.retrieval.models import RetrievalQueryContext
from src.memory.v2.retrieval.pipeline import TechnicalRetrievalPipeline
from src.memory.v2.retrieval.repository import StaticCandidateRepository
from tests.memory_v2.retrieval_fixtures import (
    FROZEN_BENCHMARK_NOW,
    build_frozen_canonical_corpus,
)

HOLDOUT2_CASES_JSON_PATH = Path(__file__).parent / "holdout2_benchmark_cases.json"


@pytest.fixture
def holdout2_pipeline() -> TechnicalRetrievalPipeline:
    """Fixture providing a TechnicalRetrievalPipeline with confidence_threshold=0.16."""
    corpus = build_frozen_canonical_corpus(FROZEN_BENCHMARK_NOW)
    repo = StaticCandidateRepository(corpus)
    cfg = RetrievalConfig(confidence_threshold=0.16)
    return TechnicalRetrievalPipeline(repo, config=cfg)


def test_holdout2_dataset_integrity() -> None:
    """Validate Holdout 2 dataset integrity and case counts."""
    assert HOLDOUT2_CASES_JSON_PATH.exists(), f"Missing {HOLDOUT2_CASES_JSON_PATH}"
    with open(HOLDOUT2_CASES_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["holdout2_set"]
    assert len(cases) == 12, f"Expected 12 Holdout 2 cases, got {len(cases)}"
    no_mem_count = sum(1 for c in cases if c.get("no_memory_expected"))
    must_count = sum(len(c.get("must_retrieve", [])) for c in cases)
    assert no_mem_count == 6
    assert must_count == 6


def test_holdout2_independent_generalization(
    holdout2_pipeline: TechnicalRetrievalPipeline,
) -> None:
    """Validate 100% generalization of the frozen errata pipeline on unseen Holdout 2."""
    with open(HOLDOUT2_CASES_JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)

    cases = data["holdout2_set"]
    passed_queries = 0
    must_hits = 0
    must_expected = 0
    total_retrieved = 0
    relevant_retrieved = 0
    no_mem_correct = 0
    no_mem_expected = 0
    forbidden_hits = 0
    cross_proj_violations = 0
    supersession_violations = 0
    privacy_violations = 0

    for case in cases:
        q = str(case["query"])
        proj = case["current_project"]
        proj_str = str(proj) if proj is not None else None
        sanctuary = bool(case.get("sanctuary_active", False))
        raw_must = case.get("must_retrieve")
        must_set = set(raw_must) if isinstance(raw_must, list) else set()
        raw_acc = case.get("acceptable_retrieve")
        acc_set = set(raw_acc) if isinstance(raw_acc, list) else set()
        raw_forbidden = case.get("must_not_retrieve")
        forbidden_set = set(raw_forbidden) if isinstance(raw_forbidden, list) else set()
        no_mem = bool(case["no_memory_expected"])

        if no_mem:
            no_mem_expected += 1
        if must_set:
            must_expected += len(must_set)

        ctx = RetrievalQueryContext(
            query_text=q,
            current_project_id=proj_str,
            sanctuary_active=sanctuary,
            now=FROZEN_BENCHMARK_NOW,
        )
        res = holdout2_pipeline.retrieve(ctx)
        recalled_ids = [c.candidate_id for c in res.candidates]
        recalled_set = set(recalled_ids)
        total_retrieved += len(recalled_ids)

        for rid in recalled_ids:
            if rid in must_set or rid in acc_set:
                relevant_retrieved += 1
            if rid in forbidden_set:
                forbidden_hits += 1

        for c in res.candidates:
            if c.scope == "project" and c.project_id != proj_str:
                cross_proj_violations += 1
            if case["historical_or_current"] == "current" and c.validity_status == "superseded":
                supersession_violations += 1
            if c.candidate_id == "chap_01_privacy_pending":
                privacy_violations += 1

        # Check pass
        case_passed = True
        if no_mem:
            if len(recalled_ids) == 0:
                no_mem_correct += 1
            else:
                case_passed = False
        else:
            if must_set:
                hits = must_set.intersection(recalled_set)
                must_hits += len(hits)
                if not hits:
                    case_passed = False
            else:
                if not acc_set.intersection(recalled_set):
                    case_passed = False

        if forbidden_set.intersection(recalled_set):
            case_passed = False

        if case_passed:
            passed_queries += 1

    # Exact Assertion Matrix on Holdout 2
    assert passed_queries == 12, f"Holdout 2 passed {passed_queries}/12 != 12"
    assert must_hits == must_expected == 6
    assert no_mem_correct == no_mem_expected == 6
    assert forbidden_hits == 0, f"Forbidden hits: {forbidden_hits}"
    assert cross_proj_violations == 0, f"Cross-project violations: {cross_proj_violations}"
    assert supersession_violations == 0, f"Supersession violations: {supersession_violations}"
    assert privacy_violations == 0, f"Privacy violations: {privacy_violations}"
