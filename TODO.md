# TODO — research-bench (заведён 2026-07-26)

> Роль в экосистеме: полигон research-домена над **неизменённым** Maestro/spec-runner.
> Даёт два артефакта: `bench-verify` (гейт верификации: детерминированные проверки →
> link-resolve → LLM-критик, exit `0=PASS / 1=FAIL / 2=ERROR`, fail-closed) и
> доказательную базу для провайдер-интерфейсов Maestro (Stage A friction log → Stage B).
> Дизайн и статусы: `../_cowork_output/plans/2026-07-2{4,5}-*.md`,
> `../_cowork_output/status/` (dev-only, рантайм их никогда не читает).
> Контракт со Stage B: `README.md` → «Stage B contract»; закрытия: `docs/stage-b-closure-matrix.md`.
>
> Открытые пункты размечены инлайн-тегами `@owner:` / `@blocked_by:` / `@trigger:` по
> формату из `../_cowork_output/2026-07-26-plan-fields-and-todo-coverage-handoff.md` §3.
> Теги опциональны и исключены из ключа идентичности пункта в Robin (robin-runtime#27);
> отсутствие тега значит «неизвестно» — выдумывать значение не надо.
>
> Robin видит этот репо с 2026-07-26 (robin-runtime#29 добавил `research-bench` в
> `_ECOSYSTEM_REPOS` как «106 коммитов/30д, самый активный репо экосистемы»). До этого
> файла репо попадал в отчёт как пробел покрытия.

## Текущее состояние

- ✅ **Stage A vertical slice сдан** (PR #1–#6): research-домен прошёл end-to-end на
  неизменённых Maestro/spec-runner; 4 сценария отработаны, включая отвергнутую
  prompt-инъекцию. Выход — `docs/stage-a-friction-log.md`, 13 friction items с evidence.
- ✅ **Stage B bench-verify v2** (PR #7, `feat/stage-b-verdict-v2`): структурированный
  verdict-контракт вместо exit-кодов как единственного канала, критик v2, домен-профиль в
  `project.yaml`. Схема Maestro вендорена пином в `contracts/maestro-verdict-v2/`.
- ✅ **Golden runs 1, 3, 4** (PR #8–#11): run 1 — PASS end-to-end; run 3 — два
  инфраструктурных ERROR → re-verify → PASS с одним `run_id` на всю цепочку и
  `rework_attempt=0`; run 4 — терминальный NEEDS_REVIEW, FAIL остался только в ledger,
  worktree и PR не тронуты. Форензика: `../_cowork_output/golden-runs/run{1,3,4}/`.
- ✅ **Матрица закрытий Stage B** (PR #12): 11 из 13 frictions закрыты машинно-проверяемым
  evidence, плюс 5 новых frictions, найденных в операционной фазе (3 из них исправлены и
  подтверждены live-регрессией внутри той же фазы).
- 🚧 **Golden run 2 не выполнен** — на хосте оператора нет docker-рантайма, а именно он
  гейтит criteria-visibility (verifier-only рубрика). Механизм сдан, live-доказательства нет.
- ⚠️ **Агрегатного бюджета у link-resolve нет** — виден только per-request таймаут. См. чекбокс.

## Правила ведения

- После выполненной задачи — `[x]` и хеш коммита либо номер PR.
- **Вердикты append-only**: `verdicts/<topic>/<run_id>/attempt-NNN.{json,md,raw.txt}`
  не переписываются никогда. Отсюда практическое следствие ниже про правку отчётов.
- **Отчёт, у которого есть вердикт, в том же PR не правится.** Вердикт связан с артефактом
  через `artifact_sha256`, а evidence-коммит — через `parent == verified_source_commit`;
  любая правка байтов отчёта или rebase ветки доставки рвёт эту связь. Полировка едет
  следующим циклом авторинга — см. соответствующий чекбокс.
- Пункты уровня команды — сюда. Микрошаги реализации — в `docs/plans/` (Robin их
  намеренно не читает) и в описания PR.
- Инлайн-теги `@owner:` / `@blocked_by:` / `@trigger:` — формат из handoff §3, все опциональны.

---

## Активные задачи

### Гейт верификации (bench-verify)

- [ ] Агрегатный бюджет link-resolve: streaming GET + per-stage budget @owner:andrei @trigger:"этап link-resolve вышел за 5 мин на реальном прогоне ИЛИ отчёт с >20 ссылками"

  Friction 12 матрицы закрыт **частично**. Maestro-уровень сделан (`timeout_seconds`
  верификатора через execution layer, тест в `test_command_verifier`), а внутри
  `bench-verify` агрегатного потолка нет: run 3 показал per-request стоимость 10 с, но
  суммарную стоимость этапа ничто не ограничивает. Нужны потоковый GET (не читать тело
  целиком) и бюджет на этап, а не только на запрос.

- [ ] Golden run 2: доказать verifier-only рубрику живым прогоном @owner:andrei @blocked_by:operator-host#docker-runtime @trigger:"на хосте оператора появился рабочий docker"

  Friction 7 — единственный из 13, где механизм сдан, а live-доказательства нет.
  Проверяется: location-based `verifier_only` + capability-gate, и что детерминированный
  addendum отдаёт автору **только** `severity` + `author_feedback`, никогда
  `criterion_id`/`evidence`/хеши. Тесты на исключения есть; не хватает прогона.

- [ ] Добавить `pyrefly check` в CI @owner:andrei

  Pyrefly настроен (`[tool.pyrefly]` в `pyproject.toml`, в dev-зависимостях) и на
  2026-07-26 чист — 0 errors, 9 suppressed. Но `.github/workflows/ci.yml` гоняет только
  `ruff format --check` → `ruff check` → `pytest -m "not slow"`, поэтому типы держатся
  на дисциплине запуска локально. Прецедент цены такого пробела рядом:
  `spec-runner-vscode` три dependency-PR подряд отчитался `CLEAN`, ни разу не запустив
  компилятор (их PR #14).

### Отчёты и авторинг

- [ ] Полировка двух synthesis-minor в `reports/wal-checkpoint-note/result.md` @owner:andrei @trigger:"следующий цикл авторинга по этому отчёту"

  Оба minor'а зафиксированы навсегда в `verdicts/wal-checkpoint-note/a5373eff-.../attempt-003.json`
  (`findings[0..1]`, оба `criterion_id: synthesis`): компаундный вывод в абзаце «Those two
  rules compose badly» подан как sourced, и второй вывод в абзаце «This deployment generates
  the overlap» не помечен как inference отдельно. PASS рубрично корректен — minor'ы не
  блокируют. В PR #11 не правились сознательно: правка байтов десинхронизировала бы
  `artifact_sha256`. Copilot независимо нашёл ровно те же два абзаца.

- [ ] Решить судьбу ветки `research/injection-note-report` @owner:andrei

  Остаток golden run 4 (терминальный NEEDS_REVIEW): `reports/injection-note/result.md`,
  +16 строк, в worktree `/tmp/maestro-ws/research-bench/injection-note-report`, никогда не
  пушилась. После чистки веток 2026-07-26 её база — **осиротевший** коммит `b7c1897`
  (бывший локальный merge-коммит master, из `origin/master` недостижим). Варианты:
  доводить отчёт до вердикта, либо снять ветку и worktree и оставить run 4 только в
  форензике. Пока ветка жива, `b7c1897` не соберётся GC.

### Доказательная база Stage B

- [ ] Внести в матрицу закрытий сходимость Copilot ↔ машинный критик @owner:andrei

  Трижды подряд (PR #9, #10, #11) внешний ревьюер независимо от машинного критика указал
  на те же самые места артефакта. В `docs/stage-b-closure-matrix.md` этого нет: слово
  Copilot встречается там один раз и по другому поводу (friction 10, glob-vs-glob).
  Место — раздел «New frictions discovered during the Stage B operational phase» или
  отдельная строка в «Verdict». Это независимая калибровка критика, и сейчас она
  держится только в тредах смерженных PR.

- [ ] Вклад в правило реконсиляции баз (friction 9, Stage C) @owner:andrei @blocked_by:maestro#base-pin-at-branch-creation

  Матрица зафиксировала наблюдение: если база двигается посреди прогона, локальный и
  GitHub-ные merge-коммиты расходятся при идентичных деревьях, и `ff-reconcile` не
  проходит. 2026-07-26 это воспроизвелось второй раз при чистке веток (см. чекбокс про
  `injection-note-report`). От research-bench нужен воспроизводимый рецепт, от Maestro —
  пин базы диффа на момент создания ветки.

---

## Зависимости и расхождения у соседей

Правки — за владельцами своих репо (полирепо, см. `CLAUDE.md` → «Repo scope & boundaries»).
Здесь только то, что упирается в research-bench.

- **spec-runner** — молчаливый retry внутри spec-runner не всплывает наружу (residual
  friction 5 матрицы, «small QoL PR»). Бюджет spec-gen сам по себе закрыт.
- **maestro** — запущенный оркестратор никогда не перезапрашивает workstream, упавший в
  FAILED **внутри** прогона: правило retry работает только на startup-реконсиляции. В run 3
  это дало 30 минут простоя в FAILED при уже поднятой инфраструктуре. Сегодня лечится
  рестартом или ручным re-queue оператора; в Stage C — in-loop retry tick.
- **maestro** — движение базовой ветки посреди живого прогона даёт scope-гейту несколько
  merge-баз и ложный escape (в run 3 — 7 фантомных путей). Принято как ops-правило
  «не мутировать базу во время прогона»; кандидат в Stage C — пин базы диффа.
- **robin-runtime** — непрорезолвившееся имя зеркала теряется молча (`config.py`,
  фильтр `.is_dir()`), поэтому переименование репо остаётся невидимой потерей, а механизм
  отчёта о пробелах покрытия поймать её не может по построению. Корневая причина названа
  в robin-runtime#29 и ведётся в его собственном `TODO.md` — здесь только как контекст
  того, почему этот файл появился так поздно.

## История

- 2026-07-26 — заведён этот файл; Stage B закрыт матрицей (PR #12), golden run 3 сдан (PR #11).
- 2026-07-25 — Stage A завершён, friction log передан во вход Stage B.
