# .claude/ — кратко

Материалы для **Claude Code** и смежных агентных сценариев рядом с репозиторием `go-so-mnoy`.

## Что здесь есть

| Путь | Назначение |
|------|------------|
| `SUMMARY.md` | Этот файл |
| `skills/composition-patterns/` | Паттерны композиции React (из референс-проекта `trading-diary`) |
| `skills/web-design-guidelines/` | Чеклист UI по Web Interface Guidelines (Vercel), правила подгружаются по URL из `SKILL.md` |

Корневой **`CLAUDE.md`** — контекст агента **по этому репозиторию**: продукт, стек, команды, правила. Карта каталогов — **`STRUCTURE.md`** (там же шаги первого запуска).

## Что сознательно не копировали из `trading-diary`

Там большой набор slash-команд (планы, Jira, worktrees, `thoughts/`). Имеет смысл **докидывать по одному** из их `.claude/commands/`, если понадобится процесс, а не тащить всё.

| Идея | Где у них |
|------|-----------|
| Планы фич в Claude Code | `.claude/commands/create_plan_generic.md` и соседние |
| Знания / HumanLayer | их `.claude/` + каталог `thoughts/` |
| Веб-админка | `skills/frontend-conventions` |
| React / Nest | `skills/react-best-practices`, `skills/nestjs-*` |
| CI в PR | `.github/workflows/` (если есть) |

## Cursor

Slash-команды для редактора: **`.cursor/commands/`** (`validate`, `commit`). Правила: **`.cursor/rules/agentic-development-workflow.mdc`**.
