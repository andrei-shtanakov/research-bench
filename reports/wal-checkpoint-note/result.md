# WAL checkpointing — operational note for an embedded orchestrator

<!-- line budget: title 1 -->

## Scope, provenance, and how to read this

**The workload.** One long-lived orchestrator process embeds a single SQLite database in WAL mode: one writer committing small job-state transactions, many pollers each holding a short read transaction, and a database file that lives for months. Every mode and hazard below is judged against that deployment — what it costs this writer, these readers, and this file — not in the abstract.

**Provenance.** The operator's designated primary source for this note is the internal documentation mirror at `http://127.0.0.1:8931/wal.html` [S1]; at authoring time the host refused connection on port 8931 and the mirror could not be retrieved. Nothing below is drawn from its contents. Every checkpoint claim therefore carries [S1] as the operator's source of record and, alongside it, the public SQLite page that claim was actually verified against [S2]–[S4].

**Evidence and inference.** Claims about SQLite behavior carry an `[Sn]` marker resolving to the Sources list; anything that is my own judgment is introduced with "I infer" or carries the prefix `inferred:` — which also marks every figure below that no source states — and no citation ever sits on the inferential step.

## What a checkpoint does

**Page transfer.** A checkpoint takes the committed content accumulated in the `-wal` file and transfers it back into the main database file, resuming from where the previous checkpoint stopped rather than starting over [S1][S2].

**Reset and reuse.** A checkpoint does not normally shrink the log [S1][S2]. Once its whole contents have been transferred and synced and no reader is still using it, the next writer rewinds the log and begins overwriting it from the beginning — its space is reused rather than grown, which is the mechanism that keeps the file from growing without bound [S1][S2]. This runs on its own by default: a COMMIT that takes the log to 1000 pages or more triggers a checkpoint, and `PRAGMA wal_autocheckpoint` is where that threshold is raised, lowered, or turned off [S1][S2][S4].

**Why this deployment cares.** A reader looks in the log first for every page it needs, falling back to the main file only if no copy is there, so maximizing read performance means keeping the log small and checkpointing often, while amortizing checkpoint cost over more writes means letting it grow [S1][S2]. I infer that a fleet of pollers reading continuously against a single small-transaction writer puts this orchestrator on the read side of that tradeoff, making log size the thing to hold down.

## The four modes

**Invocation and the shared cost.** All four are reached the same way, through `PRAGMA wal_checkpoint(<mode>)` or `sqlite3_wal_checkpoint_v2()` [S1][S3][S4]. `FULL`, `RESTART`, and `TRUNCATE` block new writers while they are pending but leave readers unimpeded [S1][S3]. In the table, `inferred:` marks my own judgment rather than a cited claim.

| Mode | Waits on | Guarantees on completion | Effect on the `-wal` file | Consequence here |
|---|---|---|---|---|
| `PASSIVE` | Nothing; it neither blocks nor is blocked by readers or the writer [S1][S3] | Only that every frame it could transfer without waiting was transferred [S1][S3] | May stop short of the end, leaving the log unreset and free to keep growing [S1][S3] | The automatic 1000-page checkpoint runs in this mode [S1][S3][S4]; inferred: the default path is therefore the one that can quietly accomplish nothing under load |
| `FULL` | The writer to finish and every reader to be on the most recent snapshot [S1][S3] | Every frame present in the log at that point transferred, and the database file synced [S1][S3] | Contents fully transferred, but whether the next writer may rewind it still depends on the readers [S1][S3] | inferred: with this writer's small job-state commits the wait for it is short, but the mode buys no reduction in file size |
| `RESTART` | Everything `FULL` waits for, then for readers to be done with the log entirely [S1][S3] | `FULL`'s guarantee, plus that the next writer restarts the log from its beginning [S1][S3] | Rewound and overwritten from the start; the file stays at its current size [S1][S3] | Requires the reader set to go empty [S1][S3]; inferred: a continuously overlapping poller fleet is exactly what prevents that |
| `TRUNCATE` | Everything `RESTART` waits for [S1][S3] | `RESTART`'s guarantee, plus the log truncated to zero bytes on success [S1][S3] | The only mode that returns log space to the filesystem [S1][S3] | inferred: the mode to schedule deliberately in a quiet window — needing the same empty reader set as `RESTART`, it is also the likeliest to wait |

## Checkpoint starvation

**The end mark.** A read transaction begins by remembering the location of the last valid commit record then in the log and holding it as its end mark; that mark is what fixes the reader's snapshot, so it goes on seeing the database as it stood at that single point in time no matter what commits afterwards [S1][S2].

**Why a checkpoint stops.** Transferring past a live end mark and letting the log be reset would pull content out from under a reader still resolving pages through it, so the checkpointer must stop when it reaches a page in the log past the end mark of any current reader, and can run to completion and reset the log only when no other connection is still using it [S1][S2].

**The trap.** Those two rules compose badly under overlap: if read transactions overlap so that at least one is open at every instant, some end mark is always live, the checkpointer can never advance past the oldest of them, no checkpoint ever completes, and the log is therefore never reset [S1][S2]. I infer that nothing surfaces as an error while this happens — each call returns having moved as far as the oldest live mark allowed — so the only symptom is a `-wal` file that never shrinks.

**What it costs here.** The log then grows without bound, and read performance deteriorates as it does, because every reader must check the log for the content it needs and that check takes time proportional to the log's size [S1][S2]. This deployment generates the overlap by construction: I infer that a fleet of pollers on independent timers, each holding a short read transaction, is precisely the arrangement that keeps one mark live at every instant — short reads do not help if they are never all short at once — which makes starvation the steady state here rather than an edge case, and makes the degradation self-reinforcing as slower reads hold their marks longer.

## What this means for the orchestrator

**Bound the reads; make the idle gaps line up.** `RESTART` and `TRUNCATE` cannot complete until every reader is done with the log [S1][S3]. I infer no choice of mode rescues a reader set that is never empty, so the gap has to be manufactured: cap how long a poller may hold a read transaction — `inferred:` a few hundred milliseconds, enforced in the poll loop rather than trusted to query speed — and drive the pollers from one shared tick instead of independent timers, so their reads land together and the interval between ticks is genuinely reader-free (`inferred:` a 5-second period).

**Watch the `-wal` file.** A checkpoint that runs to completion lets the log be rewound and its space reused; one that never completes leaves it growing [S1][S2]. I infer that makes `-wal` size the health signal to watch — without instrumenting SQLite it is the one externally visible readout of whether checkpoints are actually landing, and it costs a `stat` to sample. `inferred:` alarm on a `-wal` file above 64 MB, and on any 24-hour window in which it never falls back toward zero.

**Schedule `TRUNCATE`; do not leave reclamation to the default.** The automatic checkpoint runs in `PASSIVE` and runs inside whichever COMMIT crosses the threshold, and `PRAGMA wal_checkpoint` reports back whether it was blocked and how many pages it moved [S1][S3][S4]. I infer that is what makes the default unpredictable — an ordinary job-state commit silently pays for the transfer, in the one mode that may reset nothing — and that a checkpoint whose returned row nobody reads is indistinguishable from one that did nothing. `inferred:` call `PRAGMA wal_checkpoint(TRUNCATE)` from the orchestrator itself on a nightly cadence, inside a quiet window of a minute or two with the pollers paused, and log the row it returns.

## Sources

- [S1] http://127.0.0.1:8931/wal.html — the operator's designated primary source of record for this note; unreachable at authoring time (connection refused on port 8931), so no claim above is drawn from it.
- [S2] https://sqlite.org/wal.html
- [S3] https://sqlite.org/c3ref/wal_checkpoint_v2.html
- [S4] https://sqlite.org/pragma.html
