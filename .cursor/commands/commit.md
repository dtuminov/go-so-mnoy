This command is used to commit changes made in the project.

## Process

1. Review `git status` and `git diff` (staged and unstaged as appropriate).
2. Ensure **`STRUCTURE.md`** reflects any new, removed, or moved significant paths; update it in the same session if needed.
3. Propose one or more **atomic** commits: grouped by logical change, not one giant commit unless the change is truly single-purpose.
4. Present the plan to the user (files per commit + exact messages) and proceed only after confirmation if the user expects approval.

## Commit message format

Use **Conventional Commits** (English, imperative mood):

```
type: short description

Optional body.
```

**Types:** `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, etc.

### Optional task prefix

If the **current branch name** contains a ticket id (e.g. `TD-420-feature-foo`, `GS-12-bot-handlers`), you may prefix the subject:

```
TD-420 feat: add event list keyboard layout
```

If there is **no** ticket id in the branch and none was given, **do not invent one** — a plain Conventional Commit subject is valid.

## Rules

- **Never** add Claude / AI attribution lines or `Co-Authored-By`.
- Message should describe **only what is being committed**.
- Subject line stays concise; use body for context, breaking changes, or follow-up notes.
