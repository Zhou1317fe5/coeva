"""Multi-agent historical session harvester and CLI runner."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from src.connectors.history.base import BaseSessionParser, HarvestedSession
from src.connectors.history.codex_cli import CodexCliParser
from src.connectors.history.hermes_db import HermesDbParser
from src.connectors.history.pi_desktop import PiDesktopParser
from src.memory.store import ChronicleStore


class MultiAgentHistoryHarvester:
    """Discovers, parses, and ingests historical sessions from multi-agent runtimes."""

    def __init__(
        self,
        parsers: dict[str, BaseSessionParser] | None = None,
    ) -> None:
        self.parsers: dict[str, BaseSessionParser] = parsers or {
            "pi-desktop": PiDesktopParser(),
            "codex": CodexCliParser(),
            "hermes": HermesDbParser(),
        }

    def harvest_sessions(
        self,
        sources: list[str] | None = None,
        *,
        limit_per_source: int | None = None,
    ) -> dict[str, list[HarvestedSession]]:
        """Harvest sessions from selected or all registered agent sources."""
        active_sources = sources or list(self.parsers.keys())
        results: dict[str, list[HarvestedSession]] = {}

        for src in active_sources:
            parser = self.parsers.get(src)
            if not parser:
                continue

            results[src] = []
            if isinstance(parser, HermesDbParser):
                # HermesDbParser handles all sessions via SQLite query directly
                all_sessions = parser.parse_all_sessions()
                if limit_per_source is not None:
                    all_sessions = all_sessions[:limit_per_source]
                results[src].extend(all_sessions)
            else:
                targets = parser.discover_targets()
                if limit_per_source is not None:
                    targets = targets[:limit_per_source]
                for t in targets:
                    sess = parser.parse_session(t)
                    if sess:
                        results[src].append(sess)

        return results

    def dry_run(
        self,
        sources: list[str] | None = None,
        *,
        limit_per_source: int | None = None,
    ) -> dict[str, Any]:
        """Perform a read-only analysis of discoverable historical sessions."""
        harvested = self.harvest_sessions(sources=sources, limit_per_source=limit_per_source)
        summary: dict[str, Any] = {
            "sources": {},
            "total_sessions": 0,
            "total_events": 0,
            "earliest_timestamp": None,
            "latest_timestamp": None,
        }

        all_ts: list[str] = []

        for src, sessions in harvested.items():
            ev_count = sum(len(s.events) for s in sessions)
            src_ts = [s.started_at for s in sessions if s.started_at] + [
                s.ended_at for s in sessions if s.ended_at
            ]
            all_ts.extend(src_ts)

            summary["sources"][src] = {
                "sessions_count": len(sessions),
                "events_count": ev_count,
                "earliest": min(src_ts) if src_ts else None,
                "latest": max(src_ts) if src_ts else None,
            }
            summary["total_sessions"] += len(sessions)
            summary["total_events"] += ev_count

        if all_ts:
            summary["earliest_timestamp"] = min(all_ts)
            summary["latest_timestamp"] = max(all_ts)

        return summary

    def ingest_into_store(
        self,
        store: ChronicleStore,
        sources: list[str] | None = None,
        *,
        limit_per_source: int | None = None,
    ) -> dict[str, int]:
        """Parse sessions and idempotently record events into ChronicleStore."""
        harvested = self.harvest_sessions(sources=sources, limit_per_source=limit_per_source)
        ingested_counts: dict[str, int] = {}
        total_ingested = 0

        for src, sessions in harvested.items():
            count = 0
            for sess in sessions:
                for ev in sess.events:
                    store.record_event(ev)
                    count += 1
            ingested_counts[src] = count
            total_ingested += count

        ingested_counts["total"] = total_ingested
        return ingested_counts


def build_cli_parser() -> argparse.ArgumentParser:
    """Build command-line parser for the historical session harvester."""
    parser = argparse.ArgumentParser(
        description=(
            "Harvest historical sessions from Multi-Agent runtimes (PI-Desktop, Codex, Hermes)"
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Analyze and preview discoverable sessions without persisting to database",
    )
    parser.add_argument(
        "--sources",
        type=str,
        default="pi-desktop,codex,hermes",
        help="Comma-separated agent sources to harvest (default: pi-desktop,codex,hermes)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum sessions to harvest per source",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/companion_chronicle.db",
        help="Target SQLite DB path for ChronicleStore (default: data/companion_chronicle.db)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Perform actual harvest and ingestion for all discovered sessions",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the harvester."""
    cli_parser = build_cli_parser()
    args = cli_parser.parse_args(argv)

    harvester = MultiAgentHistoryHarvester()
    requested_sources = [s.strip() for s in args.sources.split(",") if s.strip()]

    if args.dry_run or not args.all:
        print("=== Multi-Agent History Harvester (Dry Run Preview) ===")
        summary = harvester.dry_run(sources=requested_sources, limit_per_source=args.limit)
        for src, info in summary["sources"].items():
            print(f"[{src}]")
            print(f"  Sessions : {info['sessions_count']}")
            print(f"  Events   : {info['events_count']}")
            print(f"  Span     : {info['earliest']} -> {info['latest']}")
        print("---------------------------------------------------------")
        print(f"Total Sessions: {summary['total_sessions']}")
        print(f"Total Events  : {summary['total_events']}")
        print(f"Overall Span  : {summary['earliest_timestamp']} -> {summary['latest_timestamp']}")
        if not args.all:
            print("\nNote: Run with '--all' to persist harvested events into ChronicleStore.")
        return 0

    # Actual ingestion mode
    db_path = Path(args.db_path)
    print(f"=== Harvesting into ChronicleStore ({db_path}) ===")
    store = ChronicleStore(db_path)
    try:
        counts = harvester.ingest_into_store(
            store, sources=requested_sources, limit_per_source=args.limit
        )
        print("Ingestion complete:")
        for src, count in counts.items():
            if src != "total":
                print(f"  {src:<12} : {count} events")
        print(f"Total Ingested : {counts.get('total', 0)} events")
        print(f"Chronicle Stats: {store.stats()}")
    finally:
        store.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
