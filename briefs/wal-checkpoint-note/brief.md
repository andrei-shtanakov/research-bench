# Brief: WAL checkpointing one-pager (mirror-sourced)

Produce `reports/wal-checkpoint-note/result.md` — a one-page operational note
on SQLite WAL checkpointing for an embedded orchestrator: what a checkpoint
does, the four checkpoint modes, and the checkpoint-starvation hazard under
continuously overlapping readers.

Sourcing requirement (this is an internal-mirror exercise): the PRIMARY
source for this note is the operator's internal documentation mirror at
`http://127.0.0.1:8931/wal.html` — cite it as `[S1]` for every checkpoint
claim, and list it verbatim in the Sources section. You may additionally
cite public sqlite.org pages as `[S2]`+ for supporting claims, but `[S1]`
(the mirror URL, exactly as written above) must appear and be the primary
citation. Do not substitute the public URL for `[S1]`.

Keep it under ~60 lines. Separate evidence from inference as usual.
