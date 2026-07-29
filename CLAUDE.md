# CLAUDE.md

## Active work

- **Task list:** `./TODO.md` — читать в начале каждой сессии. Только пункты уровня
  команды; микрошаги реализации живут в `docs/plans/` и в описаниях PR (сканер планов
  Robin намеренно не читает `docs/plans/*.md`).
- **Что это за репо:** полигон research-домена над **неизменённым** Maestro/spec-runner.
  Два выхода: `bench-verify` (гейт верификации) и доказательная база для
  провайдер-интерфейсов Maestro. Контракт со Stage B — `README.md` → «Stage B contract».
- **Закрытия Stage B:** `docs/stage-b-closure-matrix.md` — 13 frictions Stage A с
  evidence и остаточными рисками. Читать перед тем, как заводить «новую» проблему:
  скорее всего она там уже названа и у неё есть владелец.
- **Входящие кросс-репные находки:** handoff-ноты в `../_cowork_output/` (dev-only).
  Актуальные: `2026-07-26-plan-fields-and-todo-coverage-handoff.md` (формат тегов планов, §3),
  `2026-07-26-robin-mirror-list-drift-handoff.md` (дрейф списка зеркал).
  Что из них взято в работу — в `./TODO.md`; нота не источник истины.

## `_cowork_output/` — только для разработки (dev-only)

`../_cowork_output/` — координационный workspace между сессиями на время разработки
(ADR-ы, статусы, черновики контрактов, форензика прогонов). У тех, кто клонирует этот
репо, её **нет**. Отсюда:

- Shipped/runtime-код НИКОГДА не читает и не резолвит пути под `_cowork_output/`.
  В частности `bench-verify` и всё под `src/` — только пути внутри репо.
- Кросс-репные контракты **вендорятся внутрь** пиненой копией
  (`contracts/maestro-verdict-v2/` + `VENDORED_FROM`), а не референсятся наружу.
- Ссылаться на `_cowork_output/` могут только документация и dev-тулинг в самом workspace.

Правило дублируется из корневого `../CLAUDE.md` — он требует его в CLAUDE.md каждого проекта.

## Проверки перед PR

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest tests/ -q -m "not slow"   # ровно то, что гоняет CI (.github/workflows/ci.yml)
uv run pyrefly check                    # CI это НЕ гоняет — гонять локально
```

На 2026-07-26: 91 тест зелёный, ruff чист, pyrefly — 0 errors (9 suppressed).
`-m "not slow"` исключает интеграционные тесты, поднимающие spec-runner; они требуют
живого окружения и в CI не идут.

## Грабли этого репо

- **Вердикты append-only, и это связывает руки при правках отчётов.** Вердикт
  привязан к артефакту через `identity.artifact_sha256`, а evidence-коммит — через
  `parent == identity.verified_source_commit` (+ `verified_source_tree`). Поэтому:
  **нельзя** править байты отчёта в том же PR, где лежит его вердикт, и **нельзя**
  ребейзить ветку доставки — и то и другое рвёт связь. Полировка едет следующим циклом
  авторинга; расхождение с базой лечится merge-ом `origin/master` **в** ветку.
  Прецедент: PR #11, два minor'а оставлены на записи сознательно.
- **Fail-closed везде.** Exit-контракт `0=PASS / 1=FAIL / 2=ERROR`, и `ERROR ≠ FAIL ≠ PASS`:
  ERROR означает «перепроверить», а не «переписать отчёт». Verdict-документ пишется по
  `--out` на **каждом** пути, включая необработанное исключение.
- **Пять echo-env переменных без дефолтов:** `MAESTRO_PROFILE_SHA256`,
  `MAESTRO_VERIFIED_SOURCE_COMMIT`, `MAESTRO_VERIFIED_SOURCE_TREE`,
  `MAESTRO_WORKSTREAM_ID`, `MAESTRO_REWORK_ATTEMPT`. Любая пустая или отсутствующая
  закорачивает весь пайплайн (ни один этап не запускается) и пишет ERROR-вердикт.
  Не подставлять дефолты — это и есть защита от вранья про провенанс.
- **Верификатор запускается под обеднённым env** (`inherit_env=False` у Maestro: только
  `PATH` + пять `MAESTRO_*`). Поэтому пиненый `claude` CLI, к которому шеллится критик,
  обязан аутентифицироваться через файловый конфиг (`~/.claude`), а не через переменные
  окружения. Однажды это уже стоило отладки (Maestro #108: `HOME`/`USER` не пробрасывались).
- **Этап code-review для этого домена выключен** (`run_review: false` в `project.yaml`).
  Причина не косметическая: в golden run 1 он принял отчёт за код и переписал 11 файлов
  бенча под предлогом «SSRF guard». Поймал это scope-гейт. Реальная защита сейчас —
  role-scoped write authority (`domain.workspace.roles`), а не выключенный этап.
- **Области записи автора и верификатора не пересекаются.** Автор — только `reports/**`,
  `verdicts/**` вне его досягаемости. В обоих успешных прогонах Stage A автор писал в
  `verdicts/` — именно это и породило требование per-role write authority.
- **Не двигать базовую ветку посреди живого прогона.** Иначе scope-гейт получает
  несколько merge-баз и рапортует фантомный escape (run 3: 7 путей), а локальный и
  GitHub-ные merge-коммиты расходятся при идентичных деревьях — `ff-reconcile` не проходит.
  Лечение: `reset --hard origin/master`, когда деревья совпадают. Это friction 9 матрицы.
- **`ops/project-run*.yaml` — конфиги конкретных прогонов, не шаблоны.** `project.yaml` в
  корне — действующий; файлы в `ops/` соответствуют golden runs и трогать их задним числом
  не надо: на них ссылается форензика.

## Repo scope & boundaries

- **Этот репо:** `research-bench` — git-корень `all_ai_orchestrators/research-bench/`,
  remote `git@github.com:andrei-shtanakov/research-bench.git`.
- **Соседи (READ-ONLY reference):** `../arbiter/`, `../atp-platform/`, `../deployer/`,
  `../discovery/`, `../dispatcher/`, `../github-checker/`, `../libretto/`, `../maestro/`,
  `../proctor/`, `../prograph/`, `../prograph-vault/`, `../robin-runtime/`,
  `../spec-runner/`, `../spec-runner-vscode/`, `../steward/` — их код не редактировать.
  Каноническое имя Maestro — **`maestro`** (рейнейм 2026-07-16, remote уже
  `andrei-shtanakov/maestro.git`); локальный каталог на диске пока `Maestro` и резолвится
  только благодаря case-insensitive APFS.
- Нужна правка у соседа → **стоп**: запиши handoff в `../prograph-vault/authored/notes/`
  (кросс-проектное) или `../_cowork_output/` (черновик), не трогай его файлы.
  Открытые зависимости от соседей перечислены в `./TODO.md` → «Зависимости и расхождения».
- Кросс-репные контракты — **вендорить пиненой копией внутрь**, не ссылаться наружу.
- Полное правило (SSOT): `../prograph-vault/authored/rules/repo-boundaries.md`.

## Git workflow (у репо есть remote)

- Ветка `<type>/<slug>` → push → `gh pr create`. **Прямые коммиты в `master` запрещены**,
  как и локальный мерж ветки в `master` в обход PR.
- После открытия PR — прочитать ревью **GitHub Copilot**: валидные замечания исправлять
  новыми коммитами в ту же ветку; невалидные — ответить с обоснованием, не применять молча.
  Замечание к отчёту, у которого уже есть вердикт, — особый случай: см. «Грабли»,
  правка в том же PR ломает привязку, диспозиция пишется в тред.
- **Мерж делает человек.** После мержа — `git pull --ff-only` в `master` + удаление
  влитых веток (локальных и на origin).
- Полное правило (SSOT): `../prograph-vault/authored/rules/git-workflow.md`.

## Стиль кода

Наследуется из личного `~/.claude/CLAUDE.md` (uv, а не pip; типы обязательны; строка
88 символов; ruff format + ruff check; docstring'и у публичных API). Специфика репо —
только та, что выше.

## Входящие запросы (inbox)

В начале работы проверь входящие: `gh issue list --label inbox --state open`.
Issue с лейблом `inbox` — запрос от соседнего репо, ещё **не** пункт плана.
Принять = завести пункт в `TODO.md` с указанным `slug:`; принял под другим
именем — поправь `slug:` в теле issue.
Отказать = `gh issue close --reason "not planned"`.
Нужна работа в соседнем репо — не редактируй его: заведи там issue
(`slug:` + `from:` + проза). Правило: ADR-ECO-006.
