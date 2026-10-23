"""CLI and Developer tool for validating Pet Manifest directories (Phase 2.5 WP-1).

Usage:
    python -m src.core.behavior.validate_pet <pet_dir>
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.core.behavior.manifest import load_pet_manifest, validate_pet_manifest
from src.core.behavior.semantics import (
    OPTIONAL_BEHAVIOR_CATEGORIES,
    REQUIRED_BEHAVIOR_CATEGORIES,
)


def format_pet_diagnostic_report(pet_dir: Path) -> tuple[bool, str]:
    """Inspect and format human-readable validation report for a pet directory."""
    if not pet_dir.is_dir():
        return False, f"Directory not found: {pet_dir}"

    pet_json = pet_dir / "pet.json"
    if not pet_json.is_file():
        return False, f"pet.json not found in: {pet_dir}"

    try:
        manifest = load_pet_manifest(pet_dir)
    except Exception as exc:
        return False, f"Manifest load failure in '{pet_dir}': {exc}"

    result = validate_pet_manifest(manifest, pet_dir)

    lines: list[str] = [
        f"Pet: {manifest.id} ({manifest.name}) [schema_v{manifest.schema_version}]",
        "",
        "Required Capabilities:",
    ]

    for req_cat in sorted(REQUIRED_BEHAVIOR_CATEGORIES):
        acts = manifest.get_activities_for_category(req_cat)
        if acts:
            lines.append(f"  PASS {req_cat.value.upper()} ({len(acts)} activities)")
        else:
            lines.append(f"  MISS {req_cat.value.upper()} (0 activities)")

    lines.append("")
    lines.append("Optional Capabilities:")

    for opt_cat in sorted(OPTIONAL_BEHAVIOR_CATEGORIES):
        acts = manifest.get_activities_for_category(opt_cat)
        if acts:
            lines.append(f"  PASS {opt_cat.value.upper()} ({len(acts)} activities)")
        else:
            lines.append(f"  MISS {opt_cat.value.upper()}")

    lines.append("")
    if result.valid:
        lines.append("Manifest valid.")
    else:
        lines.append("Manifest INVALID:")
        for err in result.errors:
            lines.append(f"  - {err}")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warn in result.warnings:
            lines.append(f"  - {warn}")

    return result.valid, "\n".join(lines)


def main() -> int:
    """CLI entrypoint."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.core.behavior.validate_pet <pet_dir>")
        return 1

    pet_dir = Path(sys.argv[1])
    is_valid, report = format_pet_diagnostic_report(pet_dir)
    print(report)
    return 0 if is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
