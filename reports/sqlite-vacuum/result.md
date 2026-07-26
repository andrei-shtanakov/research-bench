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

## Comparative synthesis

## Recommendation for this workload

### What to monitor and when to act

### When to reconsider

## Sources
