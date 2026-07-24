# Brief: SQLite WAL mode trade-offs for embedded orchestrators

Write a short research report (600-1200 words) on SQLite WAL journal mode:
what it changes vs rollback journal, concurrency and crash-safety
properties, checkpointing costs, and when an embedded orchestrator
(single-writer, many readers) should or should not use it.

Output: `reports/sqlite-wal/result.md`.
Every material claim must cite a source as `[Sn]`, with all sources listed
in a final `## Sources` section as `- [Sn] <url>`.
Acceptance criteria: `briefs/sqlite-wal/criteria.yaml` (read-only for you).
