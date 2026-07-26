# Brief: SQLite space reclamation for a long-running embedded orchestrator

Produce `reports/sqlite-vacuum/result.md` — a research report on space
reclamation strategies for a SQLite database embedded in a long-running
orchestrator process (single writer, frequent small transactions, DB file
lives for months, disk footprint matters but availability matters more).

Compare the three strategies:

1. Manual `VACUUM` (full rebuild), including `VACUUM INTO`.
2. `auto_vacuum` modes (`FULL`, `INCREMENTAL` + `incremental_vacuum`).
3. Doing nothing (freelist reuse) as the baseline.

For each strategy cover: what it actually does to the file and the freelist;
locking/availability impact while it runs; interaction with WAL mode;
fragmentation and page-layout effects; operational cost (I/O, duration,
temp disk) and when it triggers.

Every material claim must cite a primary source (sqlite.org documentation)
with a stable `[Sn]` marker and a Sources section at the end. Separate
evidence from inference: judgment calls are allowed but must be flagged as
inference, not attributed to the documentation.

Finish with a recommendation section for the stated workload: which strategy
(or combination, e.g. periodic `VACUUM INTO` during quiet windows vs
`auto_vacuum=INCREMENTAL`) the orchestrator should adopt, under which
conditions to reconsider, and what to monitor (freelist_count, file size vs
page_count).

Suggested working order (you may organize the work as you see fit): collect
and verify sources first, then per-strategy analysis, then the comparative
synthesis and recommendation.
