# Persistence and reusable configuration work batch

Status: planning complete; no new implementation worker has started and no task
has been queued. The home installation has not been modified.

## Sequence and visible outcomes

| Wave | Task | Owner-visible result | Ownership |
| --- | --- | --- | --- |
| 1, parallel | VF-014-INSTALLATION-IDENTITY | Home versus temporary preview is obvious; two local logins do not overwrite each other | Settings/auth/login shell and disposable identity wiring |
| 1, parallel | VF-015-DURABLE-HISTORY | Completed tests remain findable and refresh; restart/recreation preserves exact account/session/event records | Console/history and startup durability checks |
| 2 | VF-016-BASE-RESET | Explicitly restore a saved draft to a named/versioned base without touching accounts, history or active versions | Agent draft/preset API and editor |
| 3 | VF-017-CLIENT-PACKAGE | Move a secret-free agent configuration between two independent installations, customize and reset one independently | Bounded package API/editor and two-stack runner |

VF016 requires accepted, integrated VF014 and VF015. VF017 requires accepted,
integrated VF016. These dependencies are intentional: a green planned task is
not a completed prerequisite. VF012/VF013 are separate pending fixes and must not
be silently merged or presented as these new features.

## Worker handoff

The full English specifications are `tasks/VF-014.md` through `tasks/VF-017.md`.
Machine-readable specifications are in `.fleet/tasks/`; the nonexecuting dispatch
manifest is `tasks/persistence-dispatch.json`. Metadata validation passed;
application checks and new behavioral criteria are unexecuted.

Before enqueueing, commit the reviewed planning files in this isolated planning
branch and pin that actual commit as the queue source. Create one new branch and
worktree per ready task. Do not point workers at this shared planning checkout,
an active author checkout, or the live home deployment. When later dependencies
are integrated, create a new explicit implementation base including their exact
accepted commits and update/revalidate the later task metadata before enqueueing.
The recorded 639c72a revision is the planning source, not permission to execute
blocked tasks against old code.

Use Antigravity `gemini-3.8-flash-medium` for bounded implementation and
`claude-sonnet-5-5-medium` for independent final source review through the included
quota. Both model IDs were listed by the installed CLI on 2026-10-22. Recheck the
selected model and its matching included-quota group immediately before every
run. Do not use paid credits, API keys, automatic provider fallback or unverified
quota. Cost is unknown unless measured; included quota is not an unlimited API.

Start at most two implementation workers on this Windows development machine.
If Docker resource pressure appears, serialize heavy two-stack/browser checks.
Subagents may handle bounded analysis/tests/review; one writer per worktree,
with separate worktrees for independent edits. Keep contexts scoped to the task
and reuse exact evidence rather than repeatedly sending full repository dumps.
The Ubuntu laptop continues hosting the application and runs no development job
in this batch.

Every result must include a commit, actual behavioral checks tied to that commit,
independent findings and concrete owner acceptance steps. A passing old suite is
insufficient. No auto-accept, merge, deployment, home SSH, account recreation,
database wipe, provider call, or copying real `.env` is included. Existing shared
files require integration review after the parallel branches finish.

## Configuration boundary

Core product code is reusable. A client configuration customizes supported agent
fields without forking the core. Versioned base reset replaces an agent draft
only. Removing a local package file never resets a database or the running agent.
Publish/activate and rollback remain explicit, separate operations. Global
installation branding, business integrations and evaluation runners remain
separate future slices; this batch must not claim they are already implemented.
