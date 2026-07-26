# SQLite space reclamation for a long-running embedded orchestrator

## Scope, workload, and how to read this report

**The workload.** A single long-running orchestrator process embeds one SQLite database: exactly one writer, frequent small transactions, and a file that lives for months without being recreated. Disk footprint matters, but availability matters more — a maintenance pause is a worse outcome than an oversized file. Three space-reclamation strategies are compared against those properties: manual `VACUUM` (including `VACUUM INTO`), the `auto_vacuum` modes, and doing nothing while the freelist absorbs churn.

**WAL is given context.** The database runs in WAL journaling mode, where readers do not block the writer and the writer does not block readers, and one writer is allowed at a time {wal}. Whether to run WAL is settled and is not reopened here; each strategy is examined only for how it interacts with WAL — whether its page churn flows through the write-ahead log and what that does to WAL size and checkpointing, and whether it carries a WAL-specific restriction.

**Evidence and inference.** Claims about SQLite behavior carry an `[Sn]` marker resolving to the Sources list; anything that is my own judgment is introduced with "I infer" or an equivalent explicit flag and carries no citation on the inferential step. Only two other flags appear, with the same meaning: "this is my inference, not a documented claim", and "the documentation does not state X; my judgment is …". Where the documentation is silent, the silence is stated rather than covered by a nearby citation.

## Strategy 1 — Manual VACUUM (and VACUUM INTO)

**File & freelist.** `VACUUM` "rebuilds the database file, repacking it into a minimal amount of disk space" {lang_vacuum}: it copies the contents into a temporary file no larger than the original, which exists only for the duration of the command {tempfiles}, then overwrites the original with it {lang_vacuum}. Repacking reclaims the free pages a large delete leaves behind — the reason a file "might be larger than strictly necessary" — and reduces the file's size {lang_vacuum}. The freelist does not survive: what `freelist_count` reported beforehand returns to the filesystem rather than staying in reserve for later inserts.

**Availability.** It is a write operation that fails rather than waits — if the connection running it has an open transaction, and unfinalized statements typically hold one open, or if another connection holds a lock that prevents writes {lang_vacuum}. WAL permits one writer at a time {wal}, so the rebuild owns the orchestrator's write slot throughout; readers carry on, since readers do not block writers and a writer does not block readers {wal}. No page states a duration; I infer the pause scales with the live content copied, roughly with database size — the largest availability event of any strategy here.

**WAL.** The churn flows through the log: when overwriting the original, a rollback journal or WAL file is used just as it would be for any other database transaction {lang_vacuum}. A checkpoint cannot reset the WAL in the middle of a write transaction, so a large change to a large database can leave a large WAL file, checkpointed only once the transaction completes {wal}, and a transaction's WAL is proportional in size to the transaction itself {wal}; WAL "does not work well for very large transactions" {wal}. Applying that to a whole-file rewrite is my inference, not a documented claim: expect a WAL transiently approaching database size, on top of the rebuild's disk requirement. WAL also restricts the rebuild — in WAL mode only the `auto_vacuum` property can be changed by VACUUMing {lang_vacuum}, and page size cannot be changed after entering WAL mode, even by `VACUUM` {wal}.

**Fragmentation.** Frequent inserts, updates, and deletes scatter a single table's or index's data around the file; `VACUUM` makes each table and index largely contiguous again and in some cases also reduces the number of partially filled pages {lang_vacuum}. No other strategy here does that, and for a file that has churned for months my judgment is that this repacking, not the bytes handed back, is the durable benefit.

**Operational cost & trigger.** "[A]s much as twice the size of the original database file is required in free disk space" {lang_vacuum} — not necessarily on the database's own volume, since the VFS picks the temporary file's directory, searching on unix `PRAGMA temp_store_directory`, `SQLITE_TMPDIR`, `TMPDIR`, `/var/tmp`, `/usr/tmp`, `/tmp`, then the working directory {tempfiles}. Nothing triggers a `VACUUM`; it runs only when the application issues the statement, auto-vacuum being the documented alternative that reclaims space without rebuilding the entire database {lang_vacuum}. The I/O is a full read of live content plus two writes of it, and no page gives durations: my judgment is that a run is scheduled maintenance sized from the file, not a routine statement.

Two side effects matter over months. `VACUUM` may change the ROWIDs of entries in tables that lack an explicit `INTEGER PRIMARY KEY` {lang_vacuum}. And since `page_size` and `auto_vacuum` must normally be configured before the file is created, VACUUMing is how they are changed afterwards {lang_vacuum} — making Strategy 1 the migration path into Strategy 2 as well as a competitor to it.

### VACUUM INTO

Same operation, different destination — and the difference falls almost entirely on availability.

**File & freelist.** With an `INTO` clause the original database file is unchanged and a new database is created in a file named by the argument, holding the same logical content, fully vacuumed {lang_vacuum}; that file must not previously exist, or else must be an empty file, or the command fails with an error {lang_vacuum}. It works the same way as `VACUUM` except that the named file takes the place of the temporary database and the copy-back over the original is omitted {lang_vacuum}. The live file therefore keeps its size and its freelist {lang_vacuum}: nothing is reclaimed in place, a compacted copy simply appears beside it. Adopting that copy — stop the writer, replace the file, reopen — is an application-level step no cited page describes; that it is required at all, and that the reclamation lands only when it happens, is my inference, not a documented claim.

**Availability.** Here the variant diverges sharply from the in-place rebuild, and only half the divergence is documented. Documented: "VACUUM (but not VACUUM INTO) is a write operation", and it is the write operation that fails when another connection holds a lock preventing writes {lang_vacuum}; under WAL readers do not block the writer and the writer does not block readers {wal}. From those I infer that the orchestrator's readers and its single writer both keep running for the whole copy, where an in-place `VACUUM` would own the write slot for that entire span. The documentation does not state what adopting the result costs; my judgment is that the availability event moves to the swap, sized by a process restart rather than by the database.

**WAL.** The output goes to the named file and the copy-back is omitted {lang_vacuum}, so the rebuilt pages never enter the live database's write-ahead log — none of the WAL growth an in-place rewrite provokes. No cited page pairs `VACUUM INTO` with checkpointing; the documentation does state that a long-running read transaction can prevent a checkpointer from making progress {wal}, and the copy is transactional, its output a consistent snapshot of the original {lang_vacuum}, so my judgment is that the live WAL can grow for the duration of the copy even though the copy writes nothing into it. The WAL-mode restrictions attach to the rebuild that changes the live file, not to this variant: no page states one for `VACUUM INTO`.

**Fragmentation.** The output database is fully vacuumed {lang_vacuum}, so the defragmentation gain is the one in-place `VACUUM` delivers — but it lands only at the swap. Until then the original is unchanged {lang_vacuum}; my judgment is that the live file stays exactly as fragmented as it was.

**Operational cost & trigger.** The disk requirement is one compacted copy rather than the ~2× transient an in-place rebuild needs {lang_vacuum}, and since the `INTO` argument can be an arbitrary SQL expression evaluating to a string {lang_vacuum}, that copy can be aimed at another filesystem — my inference: this is the escape when the database has outgrown free space on its own volume. Interrupted by an unplanned shutdown or power loss, the generated output database might be incomplete and corrupt {lang_vacuum}; since the original is unchanged {lang_vacuum}, I infer the exposure is a wasted run rather than a damaged source. Like `VACUUM`, nothing triggers it: it runs when the application issues the statement {lang_vacuum}.

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
