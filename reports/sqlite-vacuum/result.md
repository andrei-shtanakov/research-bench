# SQLite space reclamation for a long-running embedded orchestrator

## Scope, workload, and how to read this report

**The workload.** A single long-running orchestrator process embeds one SQLite database: exactly one writer, frequent small transactions, and a file that lives for months without being recreated. Disk footprint matters, but availability matters more — a maintenance pause is a worse outcome than an oversized file. Three space-reclamation strategies are compared against those properties: manual `VACUUM` (including `VACUUM INTO`), the `auto_vacuum` modes, and doing nothing while the freelist absorbs churn.

**WAL is given context.** The database runs in WAL journaling mode, where readers do not block the writer and the writer does not block readers, and one writer is allowed at a time {wal}. Whether to run WAL is settled and is not reopened here; each strategy is examined only for how it interacts with WAL — whether its page churn flows through the write-ahead log and what that does to WAL size and checkpointing, and whether it carries a WAL-specific restriction.

**Evidence and inference.** Claims about SQLite behavior carry an `[Sn]` marker resolving to the Sources list; anything that is my own judgment is introduced with "I infer" or an equivalent explicit flag and carries no citation on the inferential step. Only two other flags appear, with the same meaning: "this is my inference, not a documented claim", and "the documentation does not state X; my judgment is …". Where the documentation is silent, the silence is stated rather than covered by a nearby citation.

## Strategy 1 — Manual VACUUM (and VACUUM INTO)

### VACUUM INTO

## Strategy 2 — auto_vacuum (FULL and INCREMENTAL)

### auto_vacuum=FULL

### auto_vacuum=INCREMENTAL and PRAGMA incremental_vacuum

## Strategy 3 — Do nothing (freelist reuse)

Doing nothing is a choice with a mechanism, a cost, and a failure mode: SQLite's own free-page bookkeeping absorbs the churn.

**File & freelist.** Unused pages — pages that arise, for example, when information is deleted — are stored on the freelist and reused when additional pages are required {fileformat2}. That reuse is why a `DELETE` does not force the next insert to extend the file. It is also why the file does not get smaller: absent `auto_vacuum=FULL`, deleted data leaves behind "free" database pages so the file can be larger than strictly necessary, and `VACUUM` is what reclaims that space and reduces the file's size {lang_vacuum}. This strategy runs neither, so the file never shrinks on its own. The reserve is directly observable — `PRAGMA freelist_count` returns the number of unused pages in the database file, against `page_count` × `page_size` for the total {pragma}.

**Availability.** Zero, and that is the whole case for the baseline: no maintenance operation, therefore no maintenance lock, no window to schedule, nothing that can be interrupted part-way. The only locking is what each ordinary transaction already takes, and under WAL readers do not block the writer and the writer does not block readers, with one writer at a time {wal}.

**WAL.** Nothing reaches the write-ahead log except the transactions the application would have run anyway; reusing a freelist page happens inside an ordinary commit, not in a separate pass. WAL size therefore stays governed by ordinary commit size, and SQLite checkpoints automatically whenever a COMMIT takes the WAL to 1000 pages or more {wal}. No page addresses freelist reuse and WAL growth together; I infer the checkpoint cadence is simply unchanged by this choice.

**Fragmentation.** Here the baseline pays. Frequent inserts, updates, and deletes can leave the file fragmented, with data for a single table or index scattered around it, and `VACUUM` is what makes each table and index largely contiguous again {lang_vacuum}. Declining that repair lets fragmentation accumulate for the life of the file, since freed pages return to new rows wherever they happen to sit. The documentation does not state the read cost of a given degree of fragmentation; my judgment is that this is gradual degradation rather than a cliff.

**Operational cost & trigger.** Nothing triggers it, because there is no operation: no additional I/O, no duration to bound, no schedule. Temp disk is not applicable — nothing is rebuilt, so no temporary copy is created. The cost is instead a standing property of the file: freed pages are held for reuse rather than returned to the filesystem {fileformat2}, so the file ratchets to peak historical usage and stays there. That is the failure mode — a file permanently sized to the largest working set the orchestrator ever held, plus accumulated fragmentation, visible in `freelist_count` but unrecoverable without one of the other two strategies.

The usual argument for the baseline deserves stating as inference, not fact: if deletes and inserts roughly balance, pages are recycled about as fast as they are freed and the file plateaus rather than growing without bound. Given this workload I infer that plateau is the likely outcome, but it is not a documented guarantee — no cited page bounds file size — and it fails exactly when churn stops being symmetric, as after a retention change or one bulk delete that strands pages later inserts never reclaim.

## Comparative synthesis

## Recommendation for this workload

### What to monitor and when to act

### When to reconsider

## Sources
