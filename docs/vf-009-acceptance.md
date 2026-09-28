# VF-009 acceptance record

Repository: isolated `vf-003-voice-playground` working copy based on `dcc59c9`.
The separate task is defined in `tasks/VF-009.md`. Operator-console code and
local synthetic checks are complete. The original product checkout remains
unchanged; no commit, hosted CI, deployment, or owner manual acceptance occurred.

## Criteria

| Criterion | Evidence | Status |
| --- | --- | --- |
| One card per session ID, many sessions per agent | PostgreSQL test starts two authorized users on one agent and confirms distinct rows/access | Synthetic passed; live two-browser test pending |
| Server-owned statuses and updates | API returns canonical status; board polls every two seconds and offers no status mutation; real ended/error rows displayed | Implemented; live transition watching pending |
| Separate conversation/events/logs/metrics | Successful live session showed caller/agent conversation, lifecycle events, provider usage and 1178 ms latency; failed session showed diagnostics; owner's interrupted session showed partial output and an interruption event | Live browser smoke passed |
| History filters and pagination | SQL ownership filter and `(created_at,id)` cursor; ID/agent/status/channel/date filters | Synthetic passed |
| Retention | PostgreSQL test confirms terminal session and cascaded diagnostics disappear | Synthetic passed; elapsed live retention pending |
| Authorization | Admin/all, operator/own, viewer/none checks in API tests; saved view needs CSRF/Origin | Synthetic passed; manual URL changes pending |
| Saved presentation | API isolation test and Chromium reload test | Passed |
| Two independent branded installations | Validated environment defaults and separate local databases documented | Manual two-install check pending |
| No mock integration claims | Navigation contains only implemented modules; Numbers says VF-005 is pending | Browser inspection passed |

## Checks and limitations

The final combined checks are the same as in `docs/vf-003-acceptance.md`:
21 unit, 17 disposable PostgreSQL integration, 3 disposable Chromium browser
tests, Compose startup, Ruff/format/Mypy, web lint/typecheck/build all passed.
Browser checks and web build predate the Gemini backend-only option; the
unchanged UI still uses the versioned agent JSON contract.
See the final Python reports in this checkout's `artifacts/vf003-accepted-*.json`
and earlier `vf009-*.json` reports in the parent `voice-fleet-dev/artifacts`.
The final web build
warned about a large JS chunk. The integration suite had one dependency
deprecation warning. A synthetic live audio call and real provider-error path
were tested. Worker capacity, two independent installs, and hosted CI were not.

On 2026-09-26, an isolated Compose installation accepted a local admin login
and returned HTTP 200 from console config, overview, saved view, sessions,
and logs endpoints. This confirms the migrated API is reachable with real
authentication. After a real LiveKit/Deepgram session failed on Gemini 2.5,
a headless browser found its canonical `error` status in History, opened the
session detail, saw the caller transcript and lifecycle events, and followed
the provider diagnostic in Logs. After the owner approved Gemini 3.5, a
successful live session appeared as one `ended` card on the board with its
caller/agent transcript and 1178 ms server-side latency in Metrics. The owner
subsequently confirmed hearing a response and seeing both transcript sides.
Two-browser board acceptance remains open.

A later local browser check signed in with the disposable admin, found the
Ukrainian test agent on Live board, and opened both retained sessions in
History. It verified the successful transcript and latency plus the failed
session's events and Logs. The earlier ended card was no longer on Live board
because that query includes terminal sessions for only five minutes; History
still contained it. The reusable local smoke script now checks the correct
surface after that window.
The same browser check opened an owner session with a real interruption event
and confirmed that its delivered agent turn was labeled
`Interrupted; partial output` in Conversation.

## Manual acceptance

1. Complete the VF-003 live setup in `docs/vf-003-acceptance.md`. In a
   disposable stack, create an admin and two operators, publish and activate
   one agent, and sign in through two separate browsers. Start one session per
   operator; confirm two cards with different session IDs under the same
   agent, independent conversations, and pinned versions.
2. Watch cards move from pending to active, then to ended/error after a normal
   end, interruption, disconnection, and provider failure. Open each card and
   compare Conversation, Events, Logs, and Metrics with the actual event flow.
   Verify interim and interrupted labels do not imply delivered full speech.
3. In History, filter by session ID, agent, status, browser channel, and date;
   page forward and find the ended session. In Logs, filter by severity,
   component, and session ID. Inspect an error link to its matching detail.
4. As operator A, change the URL to operator B's session and log; expect 404.
   As a viewer and anonymous browser, expect denied console reads and no room
   token. Save a board view as A, reload, then verify B's view and canonical
   server status did not change.
5. Start a second *independent disposable* installation with a different
   `CONSOLE_BRAND_NAME`, `CONSOLE_ACCENT_COLOR`, and group order. Compare the
   UI and verify the databases and secrets are separate. No number inventory
   or routing should appear. Stop both stacks without deleting non-disposable
   data.

API, authorization, retention, saved-view, and migration contracts:
`docs/operator-console.md` and `docs/migrations.md`. Human acceptance: pending.
