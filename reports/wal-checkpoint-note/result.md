# WAL checkpointing — operational note for an embedded orchestrator

<!-- line budget: title 1 -->

## Scope, provenance, and how to read this

**The workload.** One long-lived orchestrator process embeds a single SQLite database in WAL mode: one writer committing small job-state transactions, many pollers each holding a short read transaction, and a database file that lives for months. Every mode and hazard below is judged against that deployment — what it costs this writer, these readers, and this file — not in the abstract.

**Provenance.** The operator's designated primary source for this note is the internal documentation mirror at `http://127.0.0.1:8931/wal.html` [S1]; at authoring time the host refused connection on port 8931 and the mirror could not be retrieved. Nothing below is drawn from its contents. Every checkpoint claim therefore carries [S1] as the operator's source of record and, alongside it, the public SQLite page that claim was actually verified against [S2]–[S4].

**Evidence and inference.** Claims about SQLite behavior carry an `[Sn]` marker resolving to the Sources list; anything that is my own judgment is introduced with "I infer" or, inside a table cell, the prefix `inferred:` — and carries no citation on the inferential step.

## What a checkpoint does

**Page transfer.** A checkpoint takes the committed content accumulated in the `-wal` file and transfers it back into the main database file, resuming from where the previous checkpoint stopped rather than starting over [S1][S2].

**Reset and reuse.** A checkpoint does not normally shrink the log. Once its whole contents have been transferred and synced and no reader is still using it, the next writer rewinds the log and begins overwriting it from the beginning — its space is reused rather than grown, which is the mechanism that keeps the file from growing without bound [S1][S2]. This runs on its own by default: a COMMIT that takes the log to 1000 pages or more triggers a checkpoint, and `PRAGMA wal_autocheckpoint` is where that threshold is raised, lowered, or turned off [S1][S2][S4].

**Why this deployment cares.** A reader looks in the log first for every page it needs, falling back to the main file only if no copy is there, so maximizing read performance means keeping the log small and checkpointing often, while amortizing checkpoint cost over more writes means letting it grow [S1][S2]. I infer that a fleet of pollers reading continuously against a single small-transaction writer puts this orchestrator on the read side of that tradeoff, making log size the thing to hold down.

## The four modes

<!-- line budget: 9 — table, one row per mode -->

## Checkpoint starvation

<!-- line budget: 9 — mechanism, not just symptom -->

## What this means for the orchestrator

<!-- line budget: 9 — operational consequences, thresholds marked as inference -->

## Sources

<!-- line budget: 6 — four [Sn] URL entries -->
