# Live voice setup and cost (checked 2026-09-26)

This guide uses the currently implemented **provisional** direct-provider
preset: Deepgram Nova-3 STT, OpenAI GPT-4o mini LLM, Cartesia Sonic 3 TTS,
English, and LiveKit Cloud for media. Google Gemini 3.5 Flash-Lite is also
implemented for a direct-provider LLM; 2.5 Flash-Lite is retained for older
projects with access. The Voice Fleet API and worker run locally in Compose.
The owner approved bounded synthetic Ukrainian testing. Google rejected 2.5
Flash-Lite for a new user, then two 3.5 Flash-Lite browser sessions completed
with two-sided transcripts and a remote audio signal. Production provider,
spending, and hosting choices remain open.

## Accounts and keys

1. Create a [LiveKit Cloud](https://livekit.com/pricing) Build project. Copy its
   `wss://` Project URL, API key, and API secret from project settings. A
   project consists of that URL/key/secret trio; see [LiveKit project
   documentation](https://docs.livekit.io/reference/developer-tools/livekit-cli/projects/).
   For this setup, use the same URL for `LIVEKIT_URL` (API and worker) and
   `LIVEKIT_BROWSER_URL` (browser). Keep the secret on the server only.
2. Create a Deepgram project key in the [Deepgram
   Console](https://developers.deepgram.com/docs/create-additional-api-keys).
3. Create a separate OpenAI API project and project API key on the [API
   Platform](https://developers.openai.com/api/docs/guides/production-best-practices).
   ChatGPT subscriptions are separate from API billing. If billing asks for a
   prepaid credit purchase, review the amount shown in the API billing page
   and disable automatic recharge unless desired. In Project Settings > Limits,
   configure a monthly **hard** spend limit and alert for the test. A soft
   budget alert does not stop requests; hard-limit enforcement can slightly
   exceed its amount while usage propagates. See [OpenAI Docs spend
   limits](https://developers.openai.com/api/docs/guides/spend-limits).
4. Create a Cartesia account and API key in its dashboard. The [official
   Cartesia Python SDK](https://github.com/cartesia-ai/cartesia-python) reads
   `CARTESIA_API_KEY`. Check the current [Cartesia
   plan](https://www.cartesia.ai/pricing) and credit usage before paid testing.
   This worker uses direct Cartesia TTS, not Cartesia Managed Agents.
5. To use a free LLM instead of OpenAI for synthetic test speech, create a
   [Gemini API key in Google AI Studio](https://ai.google.dev/gemini-api/docs/get-started).
   Choose a project on Google's Free tier and check its live quotas in AI
   Studio. The worker calls Google's API directly through the [LiveKit Gemini
   plugin](https://docs.livekit.io/agents/models/llm/gemini/), not LiveKit
   Inference. Google's [pricing page](https://ai.google.dev/gemini-api/docs/pricing)
   lists Gemini 3.5 Flash-Lite input/output as free on that tier and says
   free-tier data is used to improve its products. Use only synthetic speech
   until this data treatment is approved for client conversations.

Never paste keys into chat, agent JSON, a committed file, or a screenshot.
Use only the ignored `.env` in this isolated checkout or a secret manager.

## Local configuration (PowerShell)

Open PowerShell with Docker Engine running:

```powershell
Set-Location 'C:\Users\Maks\Desktop\prada\voice-fleet-dev\artifacts\vf003-work'
if (-not (Test-Path -LiteralPath '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
notepad .env
```

Fill these values; the password shown below is only a placeholder. Use a unique
password of at least 12 characters. An alphanumeric password avoids URL
encoding; otherwise URL-encode it in `DATABASE_URL`.

```dotenv
POSTGRES_PASSWORD=<unique_password>
DATABASE_URL=postgresql+psycopg://voice_fleet:<same_password>@db:5432/voice_fleet
APP_ORIGIN=http://localhost:8080
LIVEKIT_URL=wss://<your-project>.livekit.cloud
LIVEKIT_BROWSER_URL=wss://<your-project>.livekit.cloud
LIVEKIT_API_KEY=<project-key>
LIVEKIT_API_SECRET=<project-secret>
DEEPGRAM_API_KEY=<deepgram-key>
OPENAI_API_KEY=<openai-project-key>
GOOGLE_API_KEY=<google-ai-studio-key>
CARTESIA_API_KEY=<cartesia-key>
PLAYGROUND_MAX_SECONDS=180
```

The 180-second duration is a cautious first-test setting. It limits one
session's time, **not money**. Do not change `ENVIRONMENT=local` or
`SESSION_SECURE_COOKIE=false` for localhost testing.
Fill only the selected LLM key: `OPENAI_API_KEY` for the default agent, or
`GOOGLE_API_KEY` for an agent selecting Gemini. Deepgram and Cartesia keys are
still required for live audio in both cases.

```powershell
docker.exe compose build
docker.exe compose up -d
docker.exe compose ps
docker.exe compose logs --tail 100 worker
docker.exe compose run --rm api python -m voice_fleet_api.admin create-user --role admin
```

Create an administrator at the interactive prompt, open
`http://localhost:8080`, sign in, create an agent, publish its draft, and
activate the published version **locally**. Start a browser session, allow
microphone access, and speak. The default agent locale is `en-US` and default
voice/model IDs are in `docs/configuration.md`; use English for the initial
test. To select Gemini in the agent draft, set these JSON fields, then publish
and activate that version:

```json
{
  "schema_version": 1,
  "instructions": "Help the caller briefly in English.",
  "locale": "en-US",
  "voice": {
    "llm_provider": "google",
    "llm_model": "gemini-3.5-flash-lite"
  }
}
```

Check two-sided transcript, audible reply, events, logs, and metrics.
`/health/ready` proves database/migration readiness, not worker availability;
check `worker` logs and an actual call. Stop with `docker.exe compose down`
to retain database data; `down -v` removes the database volume and is not a
routine stop command. The original `voice` checkout does not contain these
changes.

## Cost for this specific setup

Pricing and offers below were checked on 2026-09-26 in USD. Verify each
provider's dashboard before purchase. Usage and taxes can change.

| Component | Current public price or allowance | Applied to this checkout |
| --- | --- | --- |
| [LiveKit Cloud Build](https://livekit.com/pricing) | $0/month; 5,000 WebRTC participant minutes and 50 GB downstream transfer included | Browser/media transport. The worker runs in local Compose, so Cloud-hosted agent-session charges do not describe this deployment. |
| [Deepgram Nova-3 streaming](https://deepgram.com/pricing) | $0.0048 per audio minute (current monolingual promotional rate); new accounts list $200 free credit | STT processes microphone audio, including silence while connected. Five minutes ≈ $0.024 before credits. |
| [OpenAI GPT-4o mini](https://developers.openai.com/api/docs/models/gpt-4o-mini) | $0.15 per 1M input tokens; $0.60 per 1M output tokens | Example 10k input + 2k output tokens ≈ $0.0027. Actual context and turns vary. |
| [Google Gemini 3.5 Flash-Lite](https://ai.google.dev/gemini-api/docs/pricing) | Input/output are free on the Gemini API Free tier, subject to project quotas; paid standard is $0.30 input and $2.50 output per 1M tokens | Alternative **LLM only**; Google lists free-tier data as used to improve its products. |
| [Cartesia Free/Pro](https://www.cartesia.ai/pricing) | Free: 20k credits/month, advertised as ~27 minutes of Sonic 3.6 TTS; Pro: $5/month for 100k credits, ~133 minutes of Sonic 3.6 | This checkout uses **Sonic 3**, so check its actual credit consumption in Cartesia usage. Only generated agent speech consumes TTS credits. Managed Agent $0.06/min does not apply. |
| Local host | Existing machine and electricity | No additional VM subscription for local testing. A production self-hosted LiveKit server would require separate hosting. |

For one **illustrative** five-minute conversation with five minutes of STT,
two minutes of generated agent speech, 10k LLM input tokens and 2k output
tokens: Deepgram is ~$0.024 and OpenAI is ~$0.0027 before credits. Cartesia's
actual Sonic 3 credits must be read from its dashboard; if they match the
advertised Sonic 3.6 Pro average, two TTS minutes correspond to about $0.075
of that $5 monthly package. Thus the example's resource value is roughly
**$0.10**, but an individual test may have **$0 incremental bill** when free
allowances cover usage; OpenAI may still require a prepaid credit purchase.
Any prepaid balance is credit, not the estimated cost of a conversation.
With Gemini 3.5 Flash-Lite on Google's Free tier, the example LLM cost is $0
within that project's quota. Deepgram, Cartesia, and LiveKit remain separate
services; their own included allowances may cover a small synthetic test.

LiveKit Cloud's [free Build allowance is a hard
cap](https://docs.livekit.io/deploy/admin/quotas-and-limits/). Direct provider
accounts bill under their own plans. A $10 OpenAI hard limit applies only to
OpenAI, not to Deepgram, Cartesia, or LiveKit. Monitor each account separately.
For production self-hosting, [LiveKit's VM
guide](https://docs.livekit.io/transport/self-hosting/vm/) requires a domain,
TLS and suitable network ports; VM/bandwidth pricing depends on the host.

## VF-005 outbound phone test (not yet live-accepted)

The owner considered a paid Twilio test with a foreign voice-capable Caller ID
number on 2026-09-28, then postponed the carrier decision. Their
account asks for a $20 upgrade and blocks trial SIP trunk creation. This $20
is initial account funding, not the price of one call. The code accepts any
LiveKit stored outbound SIP trunk ID, but no provider has completed a real
phone call yet. Twilio may request government ID during account upgrade; check
the actual account flow. Disable automatic recharge unless wanted. A foreign
test number does not provide inbound service on +380.
Twilio advertises 75 free Voice call minutes for new accounts and grants a new
Voice allowance after upgrade, but its current SIP limits page says Elastic
SIP Trunking is available only after upgrade. The public free-unit page does
not establish that SIP termination to Ukraine consumes that Voice allowance.
Budget the SIP test at the published Ukraine route price rather than assuming
the 75 Voice minutes make it free.
The **Try out Voice** button can call the owner's verified phone during trial,
but Twilio's trial TwiML restrictions block both `<Dial><Sip>` and `<Stream>`.
Those are the routes that would bridge a Programmable Voice trial call to
LiveKit. The sample call confirms Twilio can ring the phone; it is not a
Voice Fleet AI conversation.

Zadarma remains a candidate for the later +380 inbound number. It publishes a $5 minimum
top-up and +38091 at $3/month. Its AI integration guides show an alternative
to its static-IP SIP trunk: outgoing calls through `pbx.zadarma.com` using PBX
extension credentials, and incoming calls forwarded to an external SIP URI.
This is a candidate for LiveKit, not completed interoperability evidence.

### Zadarma candidate for later +380 inbound service (account registered, no purchase yet)

The owner registered a Zadarma account. Before spending, confirm a +38091
voice number is available in that account, the actual first-month checkout
total does not exceed $5. Zadarma's +38091 order page requests an ID/passport,
identity verification, and a current Ukrainian address; its displayed currency
and tax treatment vary by page/account, so the checkout total is authoritative.
SMS reception adds a three-month prepayment and is not needed for voice tests.
Do not share the account password, PBX extension password, API key, or full
phone number in chat.

1. In Zadarma, confirm the contact phone and inspect **Numbers → Ukraine →
   +38091**. Create a PBX extension under **My PBX → Extensions**, and retain
   its extension login and password privately. Do not create an IP-authorized
   Zadarma SIP trunk for this route. [Zadarma's Vapi AI
   instructions](https://zadarma.com/en/support/instructions/vapiai/) and
   [Retell AI instructions](https://zadarma.com/ua/support/instructions/retellai/)
   use `pbx.zadarma.com` with those PBX credentials for outgoing AI calls.
2. Once the number and spending limit are confirmed, create a LiveKit stored
   **outbound** trunk with address `pbx.zadarma.com`, `numbers` containing the
   purchased Zadarma Caller ID in E.164, and `authUsername`/`authPassword`
   matching the PBX extension. Copy LiveKit's `ST...` trunk ID into the ignored
   `.env` as `OUTBOUND_SIP_TRUNK_ID`. See the [LiveKit outbound trunk
   guide](https://docs.livekit.io/telephony/making-calls/outbound-trunk/).
3. Incoming +380 calls need a separate LiveKit **inbound** trunk, a per-call
   dispatch rule, and Voice Fleet number routing. The application can create
   those resources for an owned number after the carrier's documented SIP
   origination CIDRs are configured. Only then point the number's external SIP
   URI at the LiveKit SIP endpoint. Carrier delivery remains unverified. See the
   [LiveKit inbound guide](https://docs.livekit.io/telephony/accepting-calls/inbound-trunk/)
   and [Zadarma external SIP routing](https://zadarma.com/en/support/faq/virtual-numbers/connect-number-to-server/).

### Optional Twilio outbound test setup (deferred)

The original setup plan used Twilio for a first **outbound** AI call to the
owner's own +380 phone. This does not supply a +380 number for inbound calls.
Confirm current number availability and Ukraine termination rates on the
[Twilio pricing page](https://www.twilio.com/en-us/sip-trunking/pricing/ua)
before funding the test. Twilio, LiveKit telephony, STT, LLM, and TTS may each
charge separately.

1. In Twilio, enable [Voice geographic permission for
   Ukraine](https://help.twilio.com/articles/223179948-Does-Twilio-Support-Dialing-International-Phone-Numbers-)
   and create an [Elastic SIP trunk with a credential
   list](https://docs.livekit.io/telephony/start/providers/twilio/). Use a
   voice-capable Twilio number from an available country as Caller ID, or
   confirm with Twilio that a different verified number is accepted on this
   trunk. Do not use the destination itself as the initial Caller ID.
2. In LiveKit Cloud, create a **stored outbound SIP trunk** using the Twilio
   termination URI, matching credential username/password, and the authorized
   Caller ID number. Copy its LiveKit trunk ID (`ST...`). Follow the
   [LiveKit outbound-trunk guide](https://docs.livekit.io/telephony/making-calls/outbound-trunk/).
   Keep trunk credentials in LiveKit, not in Voice Fleet source files.
3. In the ignored `.env` of `artifacts/vf003-work`, set:

   ```dotenv
   OUTBOUND_SIP_TRUNK_ID=ST...
   OUTBOUND_TEST_DESTINATION=+380XXXXXXXXX
   OUTBOUND_TEST_MAX_SECONDS=180
   ```

   Run `docker.exe compose build` then `docker.exe compose up -d` in the
   isolated working copy so revision `0007_phone_route_lifecycle` is applied.
   This destination is the **only** number the test endpoint can dial. The full number is not
   stored in session rows; the UI shows only its last four digits.
4. Sign in as admin, publish and activate a voice agent, go to **Agents**, choose
   it, and click **Call test phone**. This click can start a billed call. Answer
   your phone, speak, hang up, then inspect the session card, transcript,
   events, metrics, and cleanup state. A trial Twilio account may require your
   destination to be verified first; check its current trial limitations.

Do not put the destination number or any Twilio credential in chat. The code
path is not evidence of a connected telephone call; the first live call and a
declined-call failure check remain manual acceptance steps.

# Deferred inbound setup

You can leave inbound telephony unconfigured while using the browser voice
playground and operator console. When you own a voice number, obtain the
carrier's documented SIP origination IP addresses or CIDR ranges and its
origination URI settings. Put the comma-separated ranges in ignored `.env` as
`INBOUND_SIP_ALLOWED_ADDRESSES`, then restart the API. In Numbers, add the
owned E.164 number, carrier label, and an agent with an active published
binding. The API then creates a LiveKit inbound trunk and dispatch rule. Set
the carrier's inbound SIP destination to the LiveKit project's SIP URI using
the carrier's own control panel. Do not enter API secrets or a carrier password
in the number form. The UI reports carrier delivery as unverified until a
real inbound call succeeds; a configured route alone proves no connectivity.

For manual acceptance, call the purchased number from another phone. Confirm
the correct agent speaks, both transcript sides appear under one inbound
session ID, caller digits are masked, hangup closes the room, and a second
simultaneous call produces a different session ID. Repeat after changing the
route: the existing call must retain its pinned version, while the new call
uses the new active agent. Check the carrier's actual charges and concurrency
limits before this test. No phone call is started by automated checks.
