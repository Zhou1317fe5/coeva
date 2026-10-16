"""AC-8: Phase 2A must ship no narrative generation.

The spec promises that 2A contains no LLM dependency and no chapter storage
(docs/specs/phase-2-chronicle-and-growth-chapters/SPEC.md, section 9, AC-8).
That promise is what keeps the whole Phase 2A boundary honest -- if an LLM SDK
or a chapters table appears without the Narrative Firewall and the deferred
work in section 8, the "2A ships no interpretation" claim is silently false.

These tests fail loudly when that happens, instead of letting the AC rot into
a line of prose nobody checks.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Packages that would mean narrative generation had been pulled in.
_LLM_SDK_MARKERS = (
    "openai",
    "anthropic",
    "litellm",
    "ollama",
    "transformers",
    "llama-cpp",
    "llama_cpp",
    "google-generativeai",
    "google-genai",
    "cohere",
    "mistralai",
    "dashscope",
    "zhipuai",
    "qianfan",
    "huggingface-hub",
)


def _declared_dependencies() -> list[str]:
    """Every dependency string declared in pyproject.toml."""
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    deps: list[str] = list(project.get("dependencies", []))
    for group in project.get("optional-dependencies", {}).values():
        deps.extend(group)
    return deps


def test_ac8_no_llm_sdk_is_declared() -> None:
    """AC-8: the dependency tree contains no LLM SDK."""
    declared = " ".join(_declared_dependencies()).lower()
    found = [marker for marker in _LLM_SDK_MARKERS if marker in declared]
    assert found == [], (
        f"AC-8 violated: LLM SDK(s) declared in pyproject.toml: {found}. "
        "Chapter generation is Phase 2D and needs the Narrative Firewall first "
        "(spec section 8)."
    )


def test_ac8_dependency_list_is_not_empty() -> None:
    """Guard the test above: an empty dependency list would make it vacuous."""
    deps = _declared_dependencies()
    assert len(deps) >= 5, f"dependency parsing looks broken, only got {deps}"
    assert any(d.startswith("PySide6") for d in deps), deps


def test_ac8_no_chapters_table_or_narrative_artifacts() -> None:
    """AC-8: the Chronicle schema has no chapter storage."""
    from src.memory.store import ChronicleStore

    store = ChronicleStore(Path(":memory:"))
    try:
        rows = store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        ).fetchall()
        names = {str(r["name"]).lower() for r in rows}
    finally:
        store.close()

    # The 2A schema is exactly these two tables plus the evidence view.
    assert names == {"slices", "events", "evidence"}, names

    narrative = {n for n in names if "chapter" in n or "insight" in n or "hypothesis" in n}
    assert narrative == set(), f"AC-8 violated: narrative storage present: {narrative}"


def test_ac8_no_llm_client_module_exists() -> None:
    """AC-8: no module in src/ performs LLM calls."""
    import src.core
    import src.memory

    for package in (src.core, src.memory):
        for module_path in Path(package.__file__).parent.glob("*.py"):
            source = module_path.read_text(encoding="utf-8").lower()
            for marker in ("import openai", "import anthropic", "from openai", "from anthropic"):
                assert marker not in source, f"{module_path.name} imports an LLM SDK"


def test_ac8_chronicle_store_has_no_generation_api() -> None:
    """AC-8: ChronicleStore exposes queries and decay, not narrative generation."""
    from src.memory.store import ChronicleStore

    public = {name for name in dir(ChronicleStore) if not name.startswith("_")}
    forbidden = {"generate_chapter", "generate", "summarize", "reflect", "write_chapter"}
    assert public & forbidden == set(), f"generation API appeared: {public & forbidden}"

    # Sanity: the 2A surface really is there.
    for expected in ("record_slice", "record_event", "list_evidence", "prune", "stats"):
        assert expected in public, f"missing expected 2A method: {expected}"
