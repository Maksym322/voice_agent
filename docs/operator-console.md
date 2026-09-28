# Operator console contract (VF-009)

The console presents real browser voice sessions from VF-003. One card is one
immutable `voice_sessions.id`; multiple cards may share an agent. Its status is
the server's canonical `pending`, `active`, `error`, or `ended` value. The client
polls every two seconds and has no status mutation endpoint. Board results
include current sessions and sessions ended in the last five minutes; older
terminal sessions are in History. API dates are UTC and displayed in the
browser's local timezone.

## Access and queries

Existing roles continue: admins read all sessions, operators read only their
own, and viewers cannot read console sessions, events, diagnostics, metrics, or
room tokens. Every read is filtered in SQL before pagination.
`PUT /api/console/view` requires the existing login cookie, exact Origin, and
CSRF token. Server authentication still applies if a navigation item is hidden.

- `GET /api/console/config`: validated per-installation brand, accent color,
  visible real modules, and default board view. Secrets are never returned.
- `GET/PUT /api/console/view`: validated version 1 per-user board presentation.
  It contains card fields, a permutation of the four display groups, optional
  agent filter, and whether recently ended cards are visible. Saving it never
  changes a session or another user's view.
- `GET /api/console/overview`: role-scoped status counts, database readiness,
  and `worker=unverified`. Agent activation is not worker health or capacity.
- `GET /api/console/sessions`: `scope=board|history`, optional `session_id`,
  `agent_id`, `status`, `channel=browser|phone`, `from_at`, `to_at`, `limit` (1–100),
  and opaque `cursor`. Results sort by `(created_at DESC,id DESC)` with a
  `next_cursor`. History includes terminal sessions until retention deletion.
  Board includes recent terminal sessions for five minutes. Each row includes
  agent name, pinned version number, channel, and last event time.
- `GET /api/sessions/{id}` and `/events`: role-filtered details and ordered
  timestamped events. Transcript rows have `speaker`, `details.final`, and
  optional `details.interrupted`. Caller interim rows may be superseded by a
  final row. Metrics expose the server-side latency reported by LiveKit.
- `GET /api/console/logs`: role-scoped, cursor-paginated product diagnostics
  with optional `session_id`, `severity`, `component`, and `since` filters.
  The Logs page links a diagnostic to its session detail.

`session_events` are product lifecycle/conversation records, separate from
diagnostics and configuration audit records. `session_diagnostics` contains
only bounded, stable error codes and fixed sanitized messages from API/worker
failure paths. Full process logs remain structured stdout; the console does
not claim to search them without an external log sink. No audio is recorded.
Terminal sessions, transcripts, events, metrics and diagnostics are deleted
together by the hourly retention sweep after the pinned published
`retention_days` period. External log retention is deployment-specific.

## Configuration and rollout

Set `CONSOLE_BRAND_NAME`, `CONSOLE_ACCENT_COLOR` (six-digit hex),
`CONSOLE_DEFAULT_GROUPS` (each canonical status once), and
`CONSOLE_VISIBLE_MODULES` (comma-separated real module IDs, including
`overview`) in ignored `.env` or deployment environment. Independent
installations use separate databases and secrets. VF-005 adds admin number
inventory and LiveKit inbound routing; carrier delivery still needs a real
call. Business tools, reports, and listen-in remain unavailable. A bounded outbound phone test shows a masked
destination when configured. The browser one-active-session-per-user cap remains;
use two operators to test simultaneous cards for one agent.

Apply Alembic revision `0004_operator_console` through the normal migration
service before starting the API. It adds `channel=browser` to existing session
rows, an event `source`, sort indexes, `session_diagnostics`, and
`operator_views`. Downgrade removes diagnostics and saved views. The worker and
API now expect the later `0006_phone_numbers` head, which adds phone direction
and number routing after the bounded outbound metadata. Back up a real database before schema changes.
No migration duplicates transcript text into diagnostics.

Live acceptance still requires actual LiveKit hosting, provider credentials,
approved language/budget, two browser users, audible speech, interruption,
provider failure, network loss, and cleanup. Synthetic tests use controlled
room substitutes and do not prove audio or worker capacity.
