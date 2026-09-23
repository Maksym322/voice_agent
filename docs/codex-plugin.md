# voice-fleet-dev plan

A separate development tool, not a Voice Fleet runtime dependency.
The plugin has not been created or installed yet.
Write all prompts, skill instructions, and templates in English.

Structure: .codex-plugin/plugin.json, skills/, templates/, scripts/.
Skills: plan-task, implement-task, review-task, prepare-release.
Product documentation stays in the product repository; skills reference it.

- plan-task: read requirements, identify dependencies, and create a small
  task with behavioral acceptance criteria and manual verification steps.
- implement-task: inspect the code, implement, verify, and report.
- review-task: inspect the diff and acceptance criteria; report reproducible
  defects. Do not modify code during the initial review.
- prepare-release: check tests, migrations, compatibility, self-hosting,
  and release notes. Publishing remains a separate action.

Templates: task, review-report, acceptance-report, release-checklist.
Scripts must execute real checks; skill prose alone does not enforce them.
Do not add MCP servers or hooks without a concrete need.

Plugin acceptance: validate structure, run a sample task, review a known
defect, and verify that a failed check is reported accurately.
Verify updates in a new Codex session.

Reference: https://developers.openai.com/plugins/concepts/plugins
