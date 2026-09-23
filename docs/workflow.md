# Робота з AI

1. Відкрити цей каталог як проєкт Codex.
2. Обрати задачу з tasks/backlog.md.
3. Окрема Git-гілка -> реалізація -> тести.
4. Commit і push після підключення GitHub.
5. PR, CI, окреме review, виправлення, ручне приймання, merge.

Push сам по собі не означає деплой.
Усі промпти та інструкції для AI пишемо англійською.

## Початок роботи над плагіном

Read AGENTS.md, the project documentation, and tasks/backlog.md.
Start by preparing the voice-fleet-dev Codex plugin described in
docs/codex-plugin.md. First check that its plan matches the product
architecture. Keep all prompts, skill instructions, and task templates
in English. Do not start implementing the application as part of this task.

## Промпт реалізації

Read AGENTS.md and tasks/VF-XXX.md.
Implement the task within its defined scope, run relevant checks,
and update affected contracts and documentation.
Report actual results and provide manual acceptance instructions.
Do not claim that checks passed unless you ran them.

## Промпт review

Review the task diff against its base branch and acceptance criteria.
Look for behavioral, authorization, concurrency, and compatibility issues.
For each finding, provide the file, impact, and reproduction steps.
Separate verified defects from hypotheses. Do not modify code during
the initial review.

## Для нової сесії

Read AGENTS.md and tasks/backlog.md.
Inspect the actual Git state and relevant documents.
Resume the current task. Do not treat a backlog status as evidence
that tests have passed.
