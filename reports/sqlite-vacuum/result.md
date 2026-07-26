# SQLite space reclamation for a long-running embedded orchestrator

## Scope, workload, and how to read this report

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
