# VF-003 acceptance record

Repository: isolated `vf-003-voice-playground` working copy based on `dcc59c9`.
The original `voice` checkout was not modified. Code, local synthetic checks,
and a live synthetic browser audio smoke test passed. The owner confirmed
hearing a response and seeing both transcript sides in the browser.
Interruption, network-loss, and duration-limit acceptance remain open.
Provider keys are present only in the ignored local environment.

The Google option now accepts Gemini 3.5 Flash-Lite for new projects and keeps
2.5 Flash-Lite valid for published snapshots with access. Existing OpenAI
snapshots remain compatible. OpenAI has not been called live.

On 2026-09-26, the owner supplied local provider credentials. An isolated
Compose installation applied revision `0004_operator_console`, passed
`/health/ready`, and registered the worker with LiveKit Cloud in Germany 2.
This live startup exposed a callback serialization defect: the job function
was defined in `__main__`, which child processes could not import. The job
function now lives in the importable `voice_fleet_worker.worker` module, with a
pickle regression check. After the fix, worker child processes initialized
and LiveKit reported `registered worker`.

A bounded synthetic Ukrainian browser session then connected to LiveKit and
Deepgram produced a final caller transcript (`Привіт!`). Google rejected
`gemini-2.5-flash-lite` for the new API project with HTTP 404 and recommended
`gemini-3.5-flash-lite`. The server recorded `provider_unavailable`, ended the
session, and cleared `room_cleanup_pending`. No agent audio or agent transcript
was produced. This exercised safe provider-error reporting and room cleanup.

The owner approved the 3.5 replacement. Two subsequent bounded sessions used
headless Chromium with a synthetic 48 kHz Ukrainian microphone fixture,
LiveKit Cloud Germany 2, Deepgram Nova-3, Gemini 3.5 Flash-Lite, and Cartesia
Sonic 3 through LiveKit Agents 1.8.3. Each recorded final caller and agent
transcripts. The agent replied, “Привіт! Двадцять три. Чим ще можу допомогти?”
The browser received nonzero remote audio (maximum measured RMS 0.148 in the
second call). The second call recorded server-side speech-end to audio-start
latency of **1178 ms**. Usage was 114 Gemini input and 25 output tokens, 71
Cartesia characters / 5.15 seconds of speech, and 14.8 seconds of Deepgram
audio. This is one observation, not a latency benchmark or a currency bill.
Both sessions ended normally with `room_cleanup_pending=false`. Headless audio
signal proved delivery to the browser media track. In a subsequent manual
check, the owner replied "Є" to the request to confirm audible response and
both transcript sides. The browser, session ID, perceived latency, and audio
quality for that manual check were not recorded.

Two additional browser sessions appeared during the owner's check. Both ended
without an error and with `room_cleanup_pending=false`, and both stored caller
and agent transcript rows. Session
`6553121e-601f-4f4a-8cb7-89980ada1177` also stored a worker interruption
event and an agent transcript row with `details.interrupted=true`. A later
headless console check opened that session in History and found the
`Interrupted; partial output` label and the interruption event. This confirms
the recorded path and UI label; the owner has not described whether playback
stopped promptly when speaking over the agent.

Recreating the API container exposed a stale Nginx upstream address (HTTP
502). The web proxy now resolves the Compose API service through Docker DNS
for each request. After rebuilding the web image, recreating only the API and
requesting `/health/ready` through the unchanged web container returned HTTP
200. An interrupted Docker image export was recovered without deleting data.

## Criteria

| Criterion | Evidence | Status |
| --- | --- | --- |
| Audible two-way browser conversation | Two Gemini 3.5 sessions produced caller and agent transcripts and nonzero browser audio; owner confirmed hearing a response and seeing both transcript sides | Automated and owner listening checks passed; quality details unrecorded |
| Pinned version during publication | PostgreSQL HTTP and worker lifecycle tests load the session's immutable version | Synthetic test passed; live switch pending |
| Both transcript sides and interruption | Owner sessions stored both transcript sides; one stored an interruption event and partial agent row, rendered correctly in History | Recorded path and UI passed; perceived interruption behavior unconfirmed |
| Events, metrics and usage | Live call recorded lifecycle, 1178 ms server-side latency and provider usage | Passed for one call; broader latency baseline pending |
| Failure and resource cleanup | Google 404 produced server error status and room cleanup; API room-start, expiry, sign-out, worker exit, and retry paths covered synthetically | Google error path passed; network loss pending |
| Authorization and duration | Scoped room token, role and ownership checks, CSRF/Origin, one active session per user, server duration sweep | Synthetic checks passed; live duration pending |

## Local checks

All commands ran in the isolated checkout. The final Python check results are
in this checkout's `artifacts/vf003-accepted-*.json`; earlier browser, web,
and Compose checks are in the parent `voice-fleet-dev/artifacts/vf009-*.json`.

| Check | Final result |
| --- | --- |
| Ruff check and scoped format check (`apps tests scripts`) | Exit 0, 0 |
| Mypy API, worker, tests | Exit 0 |
| Unit tests | Exit 0; 21 passed after worker callback, latency, and Gemini 3.5 option checks |
| Disposable PostgreSQL integration | Exit 0; 17 passed after Gemini 3.5 option and environment-independent duration fixture, four dependency deprecation warnings |
| Web lint, typecheck and production build | Exit 0, 0, 0; Vite warns about a 764 kB JS chunk |
| Disposable Chromium browser suite | Exit 0; 3 passed (UI/navigation, not real speech) |
| Disposable Compose startup/restart | Exit 0 after Gemini dependency update; migration, auth, explicit unconfigured worker, persistence passed; API recreation returned HTTP 200 through the repaired proxy |
| Credentialed worker registration | Isolated Compose worker registered with LiveKit Cloud after the importable callback fix |
| Live audible/provider/network/latency check | Synthetic microphone, both transcripts, remote audio signal, usage, latency, normal end and provider-error cleanup passed; owner confirmed audible response; live interruption record/UI passed; network loss and perceived interruption response untested |
| Hosted CI | Unexecuted on this uncommitted branch |

The initial sandboxed integration run could not create its temporary Compose
environment; the authorized rerun passed. A sandboxed Vite build hit Windows
spawn permissions; the authorized build passed. A later build was interrupted
by Windows process termination; its immediate retry passed. An earlier
repository-wide Ruff format walk hit an inaccessible disposable artifact;
the scoped source check passed. These are recorded in the dated JSON reports.

## Manual acceptance with live credentials

1. For this isolated local stack, open `http://localhost:8080` and sign in
   with the disposable admin stored in ignored `.env.smoke`. On Live board,
   select “Український тест — Gemini”, start a session, allow microphone access,
   say “Привіт, скажи число двадцять три”, and listen for a Ukrainian response.
   End the session within 180 seconds. Check both transcript sides, the board
   card, History, Events, Logs, and Metrics. The owner confirmed hearing a
   response and seeing both transcript sides; record quality and session ID
   if repeating this check. Use synthetic speech only on Google's Free tier.
2. Check the provider dashboards for actual charges or free-tier usage. The
   180-second API duration limit is not a monetary limit. Keep client data out
   of the test until the production provider, data-treatment, budget and
   hosting choices are approved.
3. Record the owner's observed audio quality, latency, browser, microphone,
   speaker, network, and model IDs. The automated 1178 ms result is server-side
   and does not include speaker playback delay.
4. Publish and activate a new version during the conversation. Confirm the
   existing session keeps its pinned version and a new session uses the new
   version. Interrupt speech and confirm a
   partial agent turn is labeled interrupted.
5. Disconnect network, make one provider unavailable, sign out during speech,
   and wait past the duration cap. For each case inspect final status, safe
   error code, room deletion/retry, and microphone/audio cleanup. Test an
   anonymous browser and viewer for denied token and history access.

Contracts and migration behavior: `docs/sessions.md`, `docs/configuration.md`,
and `docs/migrations.md`. Audio recording remains disabled. Owner listening
passed; full manual acceptance remains pending.
