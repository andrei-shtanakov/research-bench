# Self-verdict: v2 update (independent-benchmark)

Date: 2026-07-25
Artifact: reports/sqlite-wal/result.md

Change: additive only — new `### Independent measurements` subsection at the end
of "What WAL changes vs. the rollback journal", one corroborating sentence in
Recommendation, `[S6]` appended to Sources. All prior prose, [S1]–[S5]
citations, and inference labels preserved verbatim.

Criteria check (all four simultaneously):

- source-coverage: PASS — every new material claim carries [S6] (benchmark
  figures) or [S1] (documentation claim being corroborated).
- synthesis: PASS — benchmark figures stated as cited evidence; the
  generalization to the orchestrator workload is explicitly labeled
  ("that extrapolation is my inference, not a measured result"); existing
  inference labels untouched.
- structure: PASS — all five topics (WAL vs. rollback journal, concurrency,
  crash-safety, checkpointing, recommendation) present; top-level section
  order unchanged.
- independent-benchmark: PASS — [S6] https://blog.pecar.me/django-sqlite-benchmark
  (Anže Pečar, 2024-02-06, Locust, 100 concurrent clients, mixed read/write
  Django workload) is not hosted on sqlite.org; concrete numbers stated:
  ~611 req/s (DELETE) → ~781 req/s (WAL), ~28% throughput gain, with the
  error-rate caveat (3.5% vs 3.3%) reported faithfully.

Scope check: `git status --porcelain` showed only `reports/sqlite-wal/result.md`
modified before this note; src/**, tests/**, pyproject.toml, bench.config.yaml,
prompts/**, briefs/**, spec/plugins/** untouched. `uv run pytest` (57 passed)
and `uv run ruff check .` clean.
