# VF-005 progress — 2026-09-27

Working copy: `artifacts/vf003-work` on `vf-003-voice-playground`. All earlier
VF-003 and VF-009 edits remain uncommitted and preserved. The original `voice`
checkout was not changed. This record covers only the bounded outbound test
slice of VF-005; it is not full telephony acceptance.

## Implemented

- A real LiveKit `CreateSIPParticipant` path uses a stored outbound SIP trunk,
  waits for answer, and limits ringing and call duration. The endpoint accepts
  only the single +380 destination from ignored environment configuration.
- Admin, Origin, and CSRF checks guard the call command. A database advisory
  lock permits at most one pending/active phone test in an installation.
- The phone call gets its own session ID, pinned published agent version,
  `channel=phone`, masked destination suffix, and separate SIP call ID. The
  existing console board/history and session detail use the same record.
- The worker recognizes the SIP participant, greets after connection, records
  both transcript sides, events, usage/latency, and finishes on hangup. SIP
  setup failure records a sanitized error and requests room cleanup.
- Migration `0005_outbound_test` adds the two optional phone metadata columns
  and constrains channel values. API readiness expects the new head. Docs and
  `.env.example` include the configuration and manual setup contract.

## Automated evidence

| Check | Result | Evidence |
| --- | --- | --- |
| Python unit tests | 23 passed | `artifacts/vf005-unit2-20260927.json` |
| Disposable PostgreSQL integration | 19 passed before the final quick-hangup handling edit; final rerun did not complete | `artifacts/vf005-integration-20260927-4.json`, `artifacts/vf005-integration-20260927-6.json` |
| Ruff lint and format | passed | `artifacts/vf005-ruff2-20260927.json`, `artifacts/vf005-format2-20260927.json` |
| Mypy | passed | `artifacts/vf005-mypy2-20260927.json` |
| Web lint and TypeScript | passed; rerun after masked-number UI change passed directly | `artifacts/vf005-lint2-20260927.json`, `artifacts/vf005-types2-20260927.json` |
| Vite build | passed with Windows sandbox elevation; final UI change also built directly | `artifacts/vf005-build3-20260927.json` |
| Chromium UI | 3 passed, including disabled phone button without configuration | `artifacts/vf005-e2e-20260927.json` |
| `git diff --check` | passed | local invocation |

Earlier attempts were not passes: the first integration invocation could not
write an isolated Compose `.env` inside the sandbox; a second build used code
while readiness revision was still being updated and reported an unhealthy API.
The stable rerun passed. The first Vite build failed with Windows `spawn EPERM`;
the authorized rerun passed. A later final integration attempt was interrupted
under Windows memory pressure. The next attempt failed when Docker reported a
read-only filesystem while removing the disposable Compose network/volume;
Docker inspection also stalled. The final quick-hangup edit therefore lacks a
completed PostgreSQL rerun. Static checks and the web build passed after that
edit. No billed Twilio or LiveKit SIP call was made.

## Acceptance still required

- The owner chose a paid Twilio test with a foreign voice number on 2026-09-28,
  relaxing the earlier $5 cap. They need to complete their account upgrade,
  configure Twilio termination credentials, permitted Caller ID and Ukraine
  dialing, then create the matching LiveKit stored outbound trunk. The owner's
  own +380 destination and LiveKit trunk ID belong in ignored `.env`.
- Make one bounded real call to the owner's phone. Confirm audible greeting,
  two-sided transcript, interruption, hangup, metrics, masked destination, SIP
  call ID, and clean room termination. Decline a second call and verify the
  error path. These are untested against Twilio and cannot be accepted from
  synthetic checks alone.
- Select a +380 inbound carrier and verify actual SIP delivery, concurrent-call
  capacity, and a live inbound call before VF-005 can be marked complete.
  Provider choice is deferred by the owner; no number has been bought or
  marked carrier-verified.

## Inbound implementation update, 2026-09-28

- Migration 0006 adds number inventory and session direction while preserving
  existing browser and outbound sessions. API readiness now expects 0006.
- Admin-only number list/create/route endpoints create a real number-scoped
  LiveKit inbound trunk and individual dispatch rule when a DID and carrier
  origination CIDRs are supplied. The route remains explicitly unverified
  until a real call. No carrier account is needed to run regular tests.
- The worker resolves the number's current active agent on dispatch, pins its
  published version per call, verifies the SIP participant's trunk/rule/called
  number attributes, and writes caller/agent transcript, events, metrics, and
  cleanup through the existing session contract. Multiple calls on one number
  become different session IDs. Admins can inspect inbound sessions; operators
  remain limited to sessions they started.
- No real inbound call or provider interoperability test has run. Docker-based
  PostgreSQL integration remains pending while Docker Desktop is unavailable.
- At that point number removal/reprovisioning was not exposed; the route
  lifecycle update below adds it. Carrier and worker concurrent-call capacity
  remain unverified, so production limits remain an acceptance item.

The inbound synthetic unit checks covered LiveKit request scope, the carrier
allowlist guard, and SIP participant validation; 27 unit tests passed. Ruff,
mypy, web lint, TypeScript typecheck,
and the production web build passed. The integration suite ran without
`TEST_DATABASE_URL`: 3 database-free checks passed and 17 database checks
skipped. A sandboxed Docker check was denied access to the Windows named pipe;
the authorized check then stalled and was cancelled. Migration 0006 and the
new HTTP/worker integration test therefore still need a disposable PostgreSQL
run before live acceptance.

## Route lifecycle update, 2026-09-28

- Migration 0007 adds `active`, `deprovisioning`, and `retired` route states.
  Deactivation is admin-only and waits for pending/active calls to finish.
  Worker dispatch checks the state. LiveKit cleanup can be retried after a
  partial failure; reactivation provisions new trunk/rule IDs for the same
  inventory record.
- The console exposes Deactivate, Retry cleanup, and Reactivate actions and
  displays the server route state. Session history remains tied to the number.
- Synthetic test coverage includes active-call protection, failed cleanup,
  blocked dispatch, retry, reactivation, and distinct new session IDs. It
  still needs execution against a disposable PostgreSQL database. No real
  carrier call has been made.

Manual acceptance after a carrier and owned number are available: create the
route with verified carrier CIDRs; receive a call and confirm audio/transcripts;
finish the call; deactivate the route and confirm the LiveKit resources are
gone and a new call does not reach the agent; reactivate and repeat a real
inbound call. Verify an operator cannot invoke the admin endpoints. Keep a
carrier-side route disabled during cleanup if its provider retries failed SIP
delivery.
