# VF-003 session contract (implementation in progress)

The API accepts a browser voice session only for a signed-in admin or operator
with a valid Origin and CSRF token. `POST /api/agents/{agent_id}/sessions`
selects the current binding for `ENVIRONMENT`, stores its published version ID,
creates a unique LiveKit room, explicitly dispatches the `voice-fleet-playground`
worker, and returns a five-minute LiveKit join token. The token is limited to
one room, microphone publication, and audio subscription. It grants neither room
administration nor data publication. One unexpired pending/active session per
user is allowed. A viewer receives HTTP 403; an unbound agent receives HTTP 409.
Missing LiveKit settings returns HTTP 503 before a session row is created.
Room/dispatch failure returns HTTP 503, records an error row and event, and
does not return a token.

`GET /api/sessions` lists recent sessions. `GET /api/sessions/{id}` shows state,
pinned version, deadline, errors, and metrics. `GET /api/sessions/{id}/events`
shows ordered transcript and lifecycle events. Admins can read all sessions;
operators can read only their own; viewers cannot read session history.
`POST /api/sessions/{id}/end` requires Origin and CSRF, closes the room, and
records an `ended` event. Logout closes all of the user's pending/active rooms
before revoking the login cookie; a room-close failure returns 503 and retains
the authenticated session for retry. The browser disconnects its microphone
and remote audio when the session ends.

The server closes rooms at the earlier of the published agent's
`session_limit_seconds` and `PLAYGROUND_MAX_SECONDS` (default 600), polling
every five seconds. A worker that has not marked the session active within 60
seconds causes a `worker_timeout` error and room closure. Room deletion is
idempotent if LiveKit has already removed the room. The limit is enforced while
the API is running and can retry after a temporary LiveKit outage.

`LIVEKIT_URL` is the URL reachable by the API and worker, and
`LIVEKIT_BROWSER_URL` is the WebSocket URL reachable by the browser. These can
be different for local Compose, but both must use `ws://` or `wss://`.
Production requires `wss://` for the browser URL. The API key and secret are
server-side only. Set these variables in ignored `.env` or a secret store;
do not put them in agent JSON. Whether LiveKit is Cloud or self-hosted remains
an owner decision in `docs/decisions.md`.

The registered worker name is `voice-fleet-playground`. It accepts only a
dispatch whose `session_id` identifies a pending database row in the assigned
room, then loads that row's immutable published snapshot. The provisional
direct-provider preset is Deepgram Nova-3 STT, OpenAI GPT-4o mini LLM, and
Cartesia Sonic 3 TTS with the published `voice` and `locale` settings. A
published agent can instead select Google Gemini 3.5 Flash-Lite as its LLM by
setting both `voice.llm_provider="google"` and
`voice.llm_model="gemini-3.5-flash-lite"` before publication. Existing
published 2.5 Flash-Lite snapshots remain valid for Google projects with
access to that model. The worker
requires `DEEPGRAM_API_KEY` and `CARTESIA_API_KEY`, plus the **selected** LLM
key: `OPENAI_API_KEY` or `GOOGLE_API_KEY`. Optional provider references must
match these exact env names. Gemini uses Google's direct API, so LiveKit
Inference charges do not apply. Google's free tier has project quotas and
lists free-tier content as used to improve its products; use only synthetic
test speech until the owner accepts that data treatment or selects a paid tier.
The owner approved a bounded synthetic Ukrainian live test using LiveKit
Cloud, Deepgram, Gemini, and Cartesia. A first session reached Deepgram STT
but Gemini 2.5 Flash-Lite returned 404 for a new user; the room was cleaned.
Gemini 3.5 Flash-Lite was added as a replacement option. The owner approved it, and a
second synthetic browser session completed on Gemini 3.5 with final caller
and agent transcripts, Cartesia audio delivered to the browser, and normal
room cleanup. Manual hearing and interruption acceptance remain open.

Worker events use `kind=connected`, `transcript`, `metric`, `interruption`,
`disconnected`, `error`, or `ended`, ordered by `created_at,id` within a session.
Transcript rows carry `speaker=caller|agent`, text, and `details.final`; agent
rows also carry `details.interrupted`. Interim STT text is sampled at most once
per second and may be superseded by final text. Agent text comes from the
LiveKit conversation item after playback processing; interrupted output is
labeled and must not be treated as a complete utterance. The worker records
per-turn `e2e_latency_ms` when the SDK supplies speech-end timing. If it does
not, the worker records `stt_final_to_audio_start_ms`, measured from final STT
transcript arrival to the worker's reported audio start. These are distinct
server-side measurements; neither measures browser speaker latency. The last
value appears in the session metrics object. It also records bounded provider usage counters from
the SDK's session usage events when supplied. These are units, not monetary
charges. Provider errors have stable codes without raw
exception text. Product events are stored in PostgreSQL; full technical logs
remain in worker/API stdout. No audio recording is enabled (`record=False`).

Terminal sessions and cascaded events are deleted on the API's hourly retention
sweep when `ended_at + pinned retention_days` has passed. The default is 30 days;
zero days means the next sweep. The sweep requires a running API. No external
log-sink deletion contract exists yet. The owner confirmed an audible response
and both transcript sides. Manual interruption and disconnection checks remain
open for full live voice acceptance.
Worker termination sets `room_cleanup_pending` until LiveKit room deletion
succeeds. The API sweep retries terminal rows with this marker every five
seconds; retention does not purge them until cleanup succeeds.

## VF-005 bounded outbound test slice

`POST /api/agents/{agent_id}/outbound-test` requires an admin login, Origin,
and CSRF token. It accepts no destination body. The server dials only
`OUTBOUND_TEST_DESTINATION` (`+380` E.164) through the stored LiveKit trunk
`OUTBOUND_SIP_TRUNK_ID`; both must be configured before the endpoint is ready.
Only one phone test may be pending/active in the installation. The call uses a
new `channel=phone` session with the active published version pinned at creation.
Its deadline is the minimum of the published limit, `PLAYGROUND_MAX_SECONDS`,
and `OUTBOUND_TEST_MAX_SECONDS` (default 180). The LiveKit SIP participant also
receives that maximum duration. The callee must answer before the API returns
201. SIP failure returns 503 and records a sanitized error and cleanup marker.
No ordinary page load or automated test calls the real carrier.

The session stores only `destination_last4` and a separate `provider_call_id`;
the read API exposes `destination_masked` and never returns the full phone
number. The worker marks the phone session active when the SIP participant
joins, greets the callee, and ends when that participant disconnects. The
existing transcript, metrics, diagnostics, retention, and session authorization
apply. Provider selection for +380 inbound calls, carrier delivery, and
arbitrary outbound destinations remain pending in VF-005.

## VF-005 inbound route contract

`GET /api/phone-numbers`, `POST /api/phone-numbers`, and
`PUT /api/phone-numbers/{id}/route` require an admin account. Mutations also
require Origin and CSRF. POST accepts an owned E.164 number, a lowercase
provider label, and an agent ID with an active deployment binding. It creates
a number-scoped LiveKit inbound trunk and individual-room dispatch rule, then
stores their IDs. The trunk restricts SIP traffic to the carrier CIDR list in
`INBOUND_SIP_ALLOWED_ADDRESSES`; creation fails without that list. The API
does not buy numbers or configure the carrier. A row means the LiveKit route
exists, not that the carrier is delivering calls. The list returns a masked
number, route agent, revision, and explicit unverified carrier status; it does
not expose the full number or SIP resource IDs. Route changes require
`expected_revision` to avoid stale updates and affect only future calls.
Provider credentials and carrier origination settings remain outside exports.

The LiveKit individual dispatch room name begins `vf-in-{number_id}-` and
worker metadata contains that number ID. The worker resolves the current
binding once, creates a new server session ID, and pins that published version.
The SIP participant must match the stored trunk ID, dispatch rule ID, and
called number before the session becomes active or the agent greets. The
provider call ID and masked caller suffix are stored separately. Each call on
one number gets its own session and appears on the same board/history. Admins
can inspect inbound sessions; operators' existing own-session scope excludes
them because there is no operator who started the call. No live listen-in is
included. One number does not imply a one-call limit; provider and worker
capacity still control actual concurrency. Production rollout requires a real
carrier delivery test and a verified allowlist.

Admins can `POST /api/phone-numbers/{id}/deactivate` with
`{"expected_revision": N}`. The server rejects it while that number has a
pending or active call. It first commits `deprovisioning`, so the worker rejects
new dispatches, then deletes the LiveKit rule and trunk. A 503 leaves the route
blocked in `deprovisioning`; retry the same endpoint with the latest revision.
Already deleted LiveKit resources are accepted on retry. Success marks the
number `retired` while preserving its session history and E.164 inventory row.
The list exposes the canonical status and reports `livekit_configured=true`
only for an active route. Carrier delivery remains unverified even after
reactivation.

Admins can `POST /api/phone-numbers/{id}/reactivate` with the current revision
after retirement. This provisions a new LiveKit trunk and dispatch rule for
the same owned number and current carrier CIDR allowlist. It requires the
selected agent to have an active binding. Both mutations require Origin, CSRF,
admin role, and an optimistic revision. Route changes are blocked during
deprovisioning. Neither operation configures the carrier or proves a real call.
