# StreamCrew

StreamCrew is an AI stage crew for Twitch streamers. The current foundation
includes an EventSub client, rule engine, guarded Helix action layer, and a
synthetic chat highlight detector.

## Setup

Requires Python 3.11 or newer.

```bash
cd streamcrew
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env
```

Fill in the Twitch values in `.env`. Keep that file private; it is ignored by
Git. `DRY_RUN` defaults to `true` so future actions are safe by default.

Run the tests with:

```bash
python -m pytest
```

## Current scope

The service configuration reads Twitch credentials and the EventSub WebSocket
URL. `SQLiteEventStore` records EventSub notifications and deduplicates them by
message ID. Rules can run in dry-run, approval, or auto mode. `DRY_RUN=true`
blocks every Helix action even when a rule requests auto mode.

## Local EventSub WebSocket mock

The Twitch CLI version installed for this project documents these mock server
flags: `--ip`, `--port`, `--require-subscription`, `--debug`, and `--ssl`.
Start the local mock server with:

```bash
twitch event websocket start-server --ip 127.0.0.1 --port 8080
```

Set `EVENTSUB_WS_URL` to the WebSocket URL printed by the mock server (for the
command above, `ws://127.0.0.1:8080/ws`), then run `crew listen` in another
terminal. The CLI lists `--transport websocket` and `--session` for forwarding
a generated mock event to a WebSocket session. For example, after obtaining a
session ID from the mock welcome message:

```bash
twitch event trigger stream.online --transport websocket --session SESSION_ID
```

The mock server's `--require-subscription` flag enables its 10-second
subscription requirement; use it when testing the subscription manager.

### Phase 2 duplicate check

With the local mock server running and `EVENTSUB_WS_URL` set to its printed
WebSocket URL, run:

```bash
.venv/bin/python scripts/replay_duplicate.py
```

The script receives one notification from one `twitch event trigger` run, then
passes that exact saved raw frame twice through the EventSub notification
handler. The Phase 2 mock check stored exactly one row. The test suite repeats
the same-frame check and also passes.

As a control, two separate `twitch event trigger stream.online --transport
websocket --session SESSION_ID` runs produced two rows with two different
`metadata.message_id` values. Those are distinct notifications, so storing two
rows is correct. Twitch's redelivery case repeats one notification with the
same message ID; that is the case deduplication suppresses.

## Phase 5 actions

`src/streamcrew/actions.py` is the single path for chat messages, announcements,
shoutouts, markers, bans, and message deletion. The requests follow Twitch's
current Helix reference, and tests use a mocked HTTP transport. Dry-run tests
verify that every action makes zero HTTP calls. No live action was sent; live
action testing is a manual step.

Ban and message deletion require `approve` mode and a specific target. Message
deletion requires a message ID so it cannot accidentally clear the whole chat.
Shoutout rate limits are reported without retrying.

## Phase 6 highlight detector

The detector tracks a rolling 10-second message count and compares it with an
exponentially weighted baseline. It requires at least eight messages and a
three-spread spike, then enforces a 60-second marker gap. Markers go through
the same `execute_action` guard, so the saved replay stays in dry-run:

```bash
.venv/bin/python scripts/replay_chat_trace.py
```

The synthetic fixture fires once at `2026-01-01T00:01:41.700000+00:00`; the
quiet and cooldown traces are covered by tests.

## Phase 7 approval queue

`crew approvals list` displays pending actions. `crew approve <id>` records the
decision and sends the action through the guarded action layer; `crew reject
<id>` records a rejection without sending anything. Ban and delete actions
remain locked until the pending item is approved. The current token needs
`moderator:manage:banned_users` and `moderator:manage:chat_messages` before
those moderation actions can be used.

## Phase 8 local API and CLI

The local API binds only to `127.0.0.1:8765`. Run it with:

```bash
.venv/bin/crew serve
```

`LOCAL_API_TOKEN` is generated into the ignored `.env` file during setup and is
required in the `X-Local-Token` header for approval decisions. Event and
approval reads stay local. Useful CLI commands include:

```bash
.venv/bin/crew events --limit 50
.venv/bin/crew test fixtures/raid_event.json
.venv/bin/crew approvals list
```

The fixture command forces dry-run mode so it cannot send a Helix action.

## Phase 9 OBS overlay

Open `http://127.0.0.1:8765/overlay` while `crew serve` is running and add it
as an OBS Browser Source at 1280x720. The self-contained page polls recent
events and pending approvals every two seconds, and displays successful marker
records from the local event feed. The page uses no external scripts or fonts
and does not contain the local API token.
