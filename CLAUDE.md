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
- **Входящая кросс-репная находка:** handoff-нота в `../_cowork_output/` (dev-only):
  `2026-07-26-robin-mirror-list-drift-handoff.md` (дрейф списка зеркал).
  Что из них взято в работу — в `./TODO.md`; нота не источник истины.

## `../_cowork_output/` — dev-only

Координационный dev-scratch воркспейса; у пользователей и клонов проекта его НЕТ.
Shipped/runtime-код никогда не читает и не резолвит пути под ним; кросс-репные
контракты вендорятся пиненой копией внутрь, не ссылкой наружу. Ссылаться на него
могут только dev-тулинг самого воркспейса и документация. Канонические факты живут
в репо-владельце (пример: SSOT agents-catalog — `atp-platform/method/agents-catalog.toml`,
ADR-ECO-003). Полное правило (SSOT): `../prograph-vault/authored/rules/cowork-output.md`.
В частности `bench-verify` и всё под `src/` — только пути внутри репо; живой пример
вендоринга здесь — `contracts/maestro-verdict-v2/` + `VENDORED_FROM`.

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

- **Этот репо:** `research-bench` — git-корень `all_ai_orchestrators/research-bench/`, remote `git@github.com:andrei-shtanakov/research-bench.git`.
- **Соседи (READ-ONLY reference):** все остальные подпроекты воркспейса — их код не
  редактировать. Состав флота — `ai-orchestrators-workspace/workspace-manifest.toml`
  (SSOT); рукописные списки соседей в CLAUDE.md не ведём — они дрейфуют.
- **Канон имени репо = имя каталога после обычного `git clone`** (`maestro`, `libretto`).
- Нужна правка у соседа → **стоп**: запиши handoff в `../prograph-vault/authored/notes/`
  (кросс-проектное) или `../_cowork_output/` (черновик), не трогай его файлы.
- Кросс-репные контракты — **вендорить пиненой копией внутрь**, не ссылаться наружу.
- Полное правило (SSOT): `../prograph-vault/authored/rules/repo-boundaries.md`.

## Git workflow (у репо есть remote)

- Ветка `<type>/<slug>` → push → `gh pr create`. **Прямые коммиты в `master`
  запрещены**, как и локальный мерж ветки в `master` в обход PR.
- После открытия PR — прочитать ревью **GitHub Copilot**: валидные замечания исправлять
  новыми коммитами в ту же ветку; невалидные — ответить с обоснованием, **не применять
  вслепую**; итерировать, пока не останется открытых замечаний. Ревью не всегда
  запрашивается само — если его нет, запросить явно:
  `gh api -X POST repos/<owner>/<repo>/pulls/<n>/requested_reviewers -f 'reviewers[]=copilot-pull-request-reviewer[bot]'`.
- **Не мержить.** Мерж делает пользователь.
- После мержа пользователем: `git switch master && git pull --ff-only`, затем удалить
  влитую ветку в **обеих половинах**: локально `git branch -d` (после squash-мержа `-d`
  откажется — сверить, что `git diff master <ветка>` пуст, и удалить `-D`) и на origin
  `git push origin --delete <ветка>`, если GitHub не удалил сам; затем `git fetch --prune`.
- Никогда не делать force-push в общие ветки; не трогать другие репо (см. scope выше).
- Замечание к отчёту, у которого уже есть вердикт, — особый случай: см. «Грабли»,
  правка в том же PR ломает привязку, диспозиция пишется в тред.
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
(`slug:` + `from:` + проза). Правило: ADR-ECO-006 — канон в `ecosystem-kb`
(каталог `prograph-vault/` в корне воркспейса),
`authored/decisions/2026-07-28-adr-eco-006-cross-repo-issue-inbox.md`.

Исходящее ожидание — вторая половина того же ритуала: «ждём соседа» существует
**только** как чекбокс `TODO.md` с `@blocked_by:todo://<repo>/<id>` (переходно —
`<repo>#<номер>`); память сессий, заметки и handoff-доки — лишь зеркало. Находка
PF-BLOCKER-STALE по этому репо = «ожидание доставлено — действуй или переставь тег».
Правило (SSOT): `../prograph-vault/authored/rules/cross-repo-waits.md`.
