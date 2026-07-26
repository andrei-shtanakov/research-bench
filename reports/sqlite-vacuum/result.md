# SQLite space reclamation for a long-running embedded orchestrator

## Scope, workload, and how to read this report

**The workload.** One long-running orchestrator process embeds a single SQLite database: one writer, frequent small transactions, a file living for months. Footprint matters; availability matters more — a pause is worse than an oversized file.

**WAL is given context.** The database runs in WAL journaling mode: readers do not block the writer, the writer does not block readers, one writer at a time [S4]. That is settled; each strategy is examined only for how its churn reaches the log and what restriction WAL adds.

**Evidence and inference.** Claims about SQLite behavior carry an `[Sn]` marker resolving to the Sources list; anything that is my own judgment is introduced with "I infer" or an equivalent explicit flag and carries no citation on the inferential step.

## Strategy 1 — Manual VACUUM (and VACUUM INTO)

**File & freelist.** `VACUUM` "rebuilds the database file, repacking it into a minimal amount of disk space" [S1] via a temporary file lasting only for the command [S5]; freed pages return to the filesystem, and the reserve `PRAGMA freelist_count` reported [S2] is gone [S1].

**Availability.** A write operation that fails rather than waits — on an open transaction, or a lock preventing writes [S1] — holding WAL's one write slot while readers continue [S4]. Duration is undocumented; I infer it scales with content copied.

**WAL.** The write-back passes through the log like any transaction, proportional in WAL size and un-resettable by a checkpoint mid-write-transaction [S1][S4]; I infer a rebuild leaves a WAL near database size and one deferred checkpoint. Restriction: under WAL, VACUUMing changes only `auto_vacuum`, never `page_size` [S1][S4].

**Fragmentation.** `VACUUM` makes each table and index largely contiguous again, undoing the scatter inserts, updates, and deletes leave, and sometimes reduces partially filled pages [S1] — alone here, the durable gain.

**Operational cost & trigger.** Nothing triggers it; it runs when the application issues the statement, needing "[a]s much as twice the size of the original database file … in free disk space" [S1], wherever the VFS puts it [S5].

### VACUUM INTO

Same rebuild, different destination: fragmentation and I/O volume unchanged; three dimensions differ.

**File & freelist.** The original is unchanged; a fully vacuumed copy appears in the named file, which must not already exist or must be empty [S1], so the live file keeps its size and freelist [S1]. That a swap must follow, where reclamation and defragmentation land, is my inference.

**Availability.** "VACUUM (but not VACUUM INTO) is a write operation" [S1], and readers and the writer do not block each other under WAL [S4], so I infer both run throughout the copy. The swap's cost is undocumented; I judge it a process restart.

**WAL & operational cost.** The churn never reaches the live log, the copy-back being omitted [S1]; but the copy is transactional and a long-running read transaction can block a checkpointer [S1][S4], so I infer the live WAL can still grow meanwhile. One compacted copy replaces the roughly-2× transient, and the `INTO` argument being any string-valued expression [S1], it can target another filesystem — the escape, I infer, when the database outgrows its volume. Interrupted, the output may be corrupt [S1].

## Strategy 2 — auto_vacuum (FULL and INCREMENTAL)

Both modes share one standing investment. Auto-vacuuming needs extra information letting each page be traced back to its referrer, so it must be on before any tables are created and cannot be enabled afterwards; an existing database moves off `none` only by running `VACUUM`, while switching between `full` and `incremental` is free at any time [S2] — and under WAL `auto_vacuum` is the one property `VACUUM` can change [S1]. That information lives in pointer-map pages, about one per 820 at the default page size [S2][S3] by arithmetic from the format rule, not a documented figure; I infer their upkeep on relocation is the cost, not that space.

### auto_vacuum=FULL

**File & freelist.** Freelist pages are moved to the end of the file and truncated away at every transaction commit [S2], so the freelist stays near empty and space returns without a rebuild [S1].

**Availability.** Nothing is scheduled, so no maintenance lock and no window — the work rides commits the writer was already making [S2]. No page prices it; I infer added latency there, many imperceptible pauses, not one long one.

**WAL.** No cited page pairs `auto_vacuum` with WAL. Documented: a COMMIT appends to the log, a checkpoint moves changes back [S4]. I infer truncation therefore cannot land at commit as the pragma's wording suggests but is checkpoint-paced, in small continuous volume; automatic checkpointing at 1000 WAL pages [S4] makes checkpoints frequent, not peaks large.

**Fragmentation.** Actively negative: auto-vacuum only truncates freelist pages, never defragments or repacks the way `VACUUM` does, and can worsen fragmentation because pages move [S2]; nor does it compact partially filled pages [S1]. I infer that is its liability.

**Operational cost & trigger.** The trigger is automatic and cannot be deferred: every commit that frees pages [S2]. Temp disk is not applicable, nothing being rebuilt [S1]. I infer cost tracks pages freed per transaction, so a bulk delete pays it all at once.

### auto_vacuum=INCREMENTAL and PRAGMA incremental_vacuum

Same pointer-map investment and fragmentation liability as `full` — pages move, nothing is repacked [S2][S1]; only the trigger, and so availability, differs.

**File & freelist.** Auto-vacuuming does not occur at each commit as with `auto_vacuum=full`; the `incremental_vacuum` pragma must be invoked [S2]. It removes up to N freelist pages and truncates the file by that amount, clears the whole freelist when N is omitted or below 1, and does nothing outside `auto_vacuum=incremental` or on an empty freelist [S2]. Between calls it accumulates.

**Availability & operational cost.** No cited page states the lock a call takes or its duration; documented is only WAL's one writer with readers neither blocking nor blocked [S4]. I infer a call holds the write slot while readers continue, at a cost proportional to the pages released — so N is the availability knob, the only tunable pause here. Nothing is reclaimed until invoked [S2], letting it be timed for a quiet moment; temp disk is N-A [S1].

**WAL.** No cited page pairs `incremental_vacuum` with WAL either. The moves and truncation reach the file through ordinary transactions transferred by a checkpoint, and WAL "does not work well for very large transactions" [S4]. I infer a large N behaves like the whole-database rewrite, checkpoint deferred, a small N stays commit-sized — a second reason to bound it.

## Strategy 3 — Do nothing (freelist reuse)

**File & freelist.** Unused pages, those arising when information is deleted, are stored on the freelist and reused when more are required [S3], so a `DELETE` does not force the next insert to extend the file — and absent `auto_vacuum=FULL` the file never shrinks [S1]. `PRAGMA freelist_count` makes the reserve visible [S2].

**Availability.** Zero, and that is the whole case for the baseline: no maintenance operation, so no lock, no window, nothing to interrupt part-way — only what each ordinary transaction takes, under WAL's one writer with neither side blocking the other [S4].

**WAL.** No churn of its own reaches the log, because there is no operation: a freelist page is reused when an insert needs it [S3], inside an ordinary commit. WAL size stays governed by commit size, with automatic checkpointing at 1000 WAL pages [S4]; no cited page pairs the two, and I infer the cadence unchanged.

**Fragmentation.** Here the baseline pays: frequent inserts, updates, and deletes can leave a table's or index's data scattered around the file, and `VACUUM` is what makes each contiguous again [S1]. Declining that repair lets fragmentation accumulate; no page prices it, and I infer gradual degradation, not a cliff.

**Operational cost & trigger.** Nothing triggers it: no additional I/O, no duration to bound, no schedule, no temp disk [S1]. Freed pages are held for reuse, not returned [S3], so the file ratchets to peak usage, visible in `freelist_count` [S2]. The usual defence is inference, not evidence: if deletes and inserts roughly balance the file plateaus, likely here — but no cited page bounds file size, and it fails when churn stops being symmetric.

## Comparative synthesis

The options separate on **where the cost lands**: inside every commit, inside a bounded call, or inside one pause sized by the database. `inferred:` marks my judgment.

| Strategy | Space actually reclaimed | Availability cost while running | WAL interaction | Standing steady-state overhead | Temp disk required |
|---|---|---|---|---|---|
| Do nothing (freelist reuse) | None; freed pages stay on the freelist [S3] | Zero; no lock beyond ordinary commits [S4] | None of its own [S3] | None; the file ratchets to peak usage [S3] | N-A; nothing is rebuilt [S1] |
| `auto_vacuum=FULL` | Continuous; truncated at every commit [S2] | No window; work rides the writer's commits [S2] | inferred: moves append to the log, truncation lands at a checkpoint | Pointer-map pages, per-commit relocation [S3][S2] | N-A; nothing is rebuilt [S1] |
| `auto_vacuum=INCREMENTAL` | Only on `PRAGMA incremental_vacuum(N)`, up to N pages [S2] | inferred: a call holds the write slot; N bounds the pause | inferred: large N one transaction, small N commit-sized | Same pointer-map pages, relocation deferred [S3][S2] | N-A; nothing is rebuilt [S1] |
| In-place `VACUUM` | Maximal; repacked into minimal disk space [S1] | Highest; fails on a blocking lock [S1], owns the write slot [S4] | Passes through the log [S1]; inferred: WAL near database size | None between runs [S1] | ~2× the database, wherever the VFS picks [S1][S5] |
| `VACUUM INTO` | None in the live file; a vacuumed copy beside it [S1] | Not a write operation [S1]; inferred: cost moves to the swap | Copy-back omitted [S1]; inferred: churn misses the live log | None between runs [S1] | One compacted copy, possibly another filesystem [S1] |

## Recommendation for this workload

**The recommendation is `auto_vacuum=INCREMENTAL`, set when the database file is created, with the freelist drained by a scheduled, bounded `PRAGMA incremental_vacuum(N)` — and `VACUUM INTO` followed by an explicit file swap held in reserve as occasional out-of-band compaction.**

**Availability over footprint.** A call removes up to N pages, truncating the file by that amount [S2], while in-place `VACUUM` fails on a lock preventing writes [S1] and holds WAL's one write slot [S4] for an unbounded span. I infer `incremental` alone has a pause set by a parameter, not by the database.

**Single writer, small transactions, months-long lifetime.** One writer knows when it is idle; small transactions leave gaps, not one busy period. `auto_vacuum=full` truncates at every commit with no way to defer, while switching modes is free and auto-vacuuming must be on before any tables exist [S2]. I infer `incremental` dominates `full` — identical work, but control over when it lands — and the choice is made once, at creation.

**What the choice costs.** Pointer-map pages [S3][S2], whose upkeep I infer outweighs the space. No defragmentation: the mode only truncates freelist pages, can worsen fragmentation because pages move [S2], and does not compact partially filled pages [S1] — which is why `VACUUM INTO` stays in the plan: a vacuumed copy, original unchanged [S1], at a swap I infer costs a restart. Being wrong costs the set-at-creation constraint [S2].

### What to monitor and when to act

Three signals track the freelist, one tracks whether each drain worked, one gates the fallback. No cited page states a threshold; `inferred:` marks mine.

| Signal | Healthy | What triggers action | Action |
|---|---|---|---|
| `PRAGMA freelist_count` [S2], read weekly for trend | inferred: a sawtooth returning near the same floor | inferred: the post-drain floor rising in three consecutive readings | inferred: shorten the interval or raise `N`, else `VACUUM INTO` plus swap |
| Free ratio `freelist_count / page_count` [S2] | inferred: below ~10% when a drain is due | inferred: above ~25% at two consecutive drains | inferred: drain early, omitting the argument, clearing the whole freelist [S2] |
| On-disk size against `page_count` × `page_size` [S2] | inferred: the two track, the gap being `freelist_count` × `page_size` [S2] | Unchanged after a drain, though the pragma truncates [S2] | inferred: the drain is ineffective; the pragma needs `auto_vacuum=incremental` [S2] |
| Per-run duration and pages released, `freelist_count` before minus after [S2] | inferred: each run releases near its `N` inside the window | Duration drifting upward at unchanged `N`; short releases are documented below `N` free pages [S2] | inferred: lower `N` until a run fits, and drain more often |
| Free space where the temporary file lands [S5] | Above twice the database size, the transient a rebuild needs [S1] | That headroom lost, or the search order resolving unexpectedly [S5] | In-place `VACUUM` unavailable; fall back to `VACUUM INTO` elsewhere [S1] |

**~10% and ~25%:** wide enough that ordinary churn wakes nobody, tight enough that slack stays a fraction of live content. **`N`:** it follows from the window, not the file — time one run at a small `N` (1,000 pages is about 4 MB at the default page size [S2]), then scale to fit. **Three readings:** two cannot tell a rising floor from a plateau.

### When to reconsider

Each condition is observable and names what it would favour. No cited page ranks strategies, so every mapping below is my inference, cited only on the mechanism it reasons from.

- **Free temp-file space falls below twice the database size** [S5] — as much as twice the original is required free [S1], ruling in-place `VACUUM` out. Favours `VACUUM INTO` elsewhere [S1], or bounded drains alone.
- **The quiet window disappears** — nothing is reclaimed under `incremental` until the pragma is invoked [S2]. Favours `auto_vacuum=full`: truncation every commit, one free switch away [S2].
- **One large deletion strands a working set the file will not re-use** — a step change in `freelist_count` that a cadence of at most `N` pages per call cannot absorb [S2]. Favours a one-time `VACUUM INTO` plus swap, repacking fragmentation the mode never touches [S1][S2].
- **The post-drain floor rises monotonically instead of plateauing** — three rising weekly readings of `freelist_count / page_count` [S2] mean pages are not re-used as fast as freed [S3]. Favours a shorter interval or larger `N`, then a scheduled `VACUUM INTO` plus swap.
- **The database leaves WAL, or the writer stops being the only one** — every availability comparison above rests on WAL's one writer with readers neither blocking nor blocked [S4]. Favours re-running the analysis; no rollback-journal or concurrent-writer case is examined.
- **The file stops being long-lived** — auto-vacuuming must be on before any tables exist and cannot be enabled later [S2], and its pointer-map pages cost for the file's whole life [S3] against a freelist reused anyway [S3]. Favours doing nothing.

## Sources

- [S1] https://sqlite.org/lang_vacuum.html
- [S2] https://sqlite.org/pragma.html
- [S3] https://sqlite.org/fileformat2.html
- [S4] https://sqlite.org/wal.html
- [S5] https://sqlite.org/tempfiles.html
