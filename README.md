# StreamCrew — Stream Incident Room on Switch

**One-line pitch:** When a stream is hit by a spam raid or a big raid arrives, a small crew (streamer, moderator, and AI agents) handles it together in a Switch room, and no risky action runs without a human "approve".

> **The engine runs without Switch. The team workflow, roles, and approval gate do not.**

![Switch #stream-ops Incident Room](design/screenshots/switch_stream_ops.jpg)

---

## How Switch Is Used

StreamCrew separates deterministic Twitch automation from collaborative incident response:

```text
[Twitch EventSub / Simulator]
        │
        ▼
[Local Engine & SQLite Queue] ──(2s poll)──► [OBS Browser Overlay (1280x720)]
        ▲
        │ (crew CLI only — never holds Twitch tokens)
        ▼
[Switch Room: #stream-ops]
  ├── Streamer (Human)       ── watches overlay, requests rule drafts
  ├── Moderator (Human)      ── reviews pending table, types "approve 1 --by Sam"
  ├── @crew-mod (Agent)      ── inspects queue, redacts spam, refuses unapproved bans
  └── @crew-producer (Agent) ── drafts JSON rules from plain English, validates & tests
```

1. **A Team, Not One Person:** Both the streamer and the moderator work in `#stream-ops` alongside `@crew-mod` and `@crew-producer`.
2. **The Room Is the Approval Gate:** The moderator has no terminal. Decisions happen by typing in the Switch room, and both the room history and SQLite (`decided_by`) form the audit log.
3. **Role Boundaries:** `@crew-mod` refuses to execute bans or timeouts without a human's explicit approval of a specific incident ID.
4. **Zero Token Exposure to Agents:** Switch agents never receive or read the Twitch OAuth token. They only run `crew` CLI commands against the local engine.

---

## Quick Start (No Twitch Account Needed)

Requires Python 3.11+. You can clone and run the full incident simulation and overlay immediately without Twitch credentials (`DRY_RUN=true` is on by default and falls back to `.env.example` placeholders automatically):

```bash
git clone https://github.com/saksham-AI500/streamcrew.git
cd streamcrew
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
cp .env.example .env

# 1. Trigger a simulated 6-bot spam raid through the real detector
crew simulate spam

# 2. Inspect the grouped pending approval (redacted sample & target count)
crew approvals list

# 3. Approve with target-count guard and human audit trail
crew approve 1 --count 6 --by Sam

# 4. Launch the local API and OBS overlay at http://127.0.0.1:8765/overlay
crew serve
```

Run the test suite (108 tests, mocked transport, zero network calls):

```bash
pytest -q
```

---

## 3-Minute Demo Storyboard

Screen layout: Switch `#stream-ops` room on the left, OBS preview with `/overlay` on the right. Terminal stays off screen.

| Time | On Screen | Narration |
|---|---|---|
| **0:00–0:20** | Chat flooding, one moderator | *"A bot raid posts the same text faster than anyone can ban one account at a time."* |
| **0:20–0:50** | `#stream-ops`: 2 humans, 2 agents, roles | *"Switch is where my team and my agents work together. Agents never see my Twitch token."* |
| **0:50–1:50** | **Workflow A:** Simulated burst fires, overlay turns red. Mod asks `@crew-mod what's pending?`, then types `@crew-mod approve 1 --count 6 --by Sam`. Overlay turns green. | *"One incident, one decision, logged in the room and database."* |
| **1:50–2:20** | **Safety Moment:** Someone types *"just ban everyone"*. `@crew-mod` refuses and requires an approval ID. | *"No human word, no action."* |
| **2:20–2:45** | **Workflow B:** `@crew-producer` drafts a raid rule (*"20+ viewers, shoutout and marker"*), runs `crew validate` and `crew test`, and ships on human word. | *"A streamer writes a rule in a sentence. Nothing goes live until a person says so."* |
| **2:45–3:00** | README and repository | *"Clone it, run the simulation, no Twitch account needed."* |

---

## Architecture & Safety Model

- **Architecture:** `eventsub.py` listens to Twitch WebSockets and deduplicates messages in SQLite (`storage.py`). `spam.py` runs a pure sliding-window detector that groups multi-account bursts (capped at 25 targets) into a single approval row. `approvals.py` locks target lists once displayed (`locked: True`), verifies `--count`, records `--by <moderator>`, and paces Helix requests (`actions.py`).
- **Safety Model:**
  - `DRY_RUN=true` by default: logs planned actions without calling Twitch Helix.
  - `ban_user` and `delete_message` are hard-coded to `approve` mode only; the engine refuses to run them in `auto` mode.
  - Chat samples in `crew events` and `crew approvals list` automatically redact URLs and emails (`redact.py`).
  - The OBS overlay (`overlay.html`) polls summary endpoints every 2 seconds using `textContent` only (no `innerHTML`, no external assets, no tokens).

## Honest Current Limits

- **Simulated Burst:** The spam burst in the demo is replayed via `crew simulate spam` (`fixtures/spam_burst.json`) through the real detector and approval queue. Never approve the simulated fixture with `DRY_RUN=false`; for a live timeout test on your own alt account, use `crew simulate test-alt --user-id <id> --login <login>`.
- **Supported Event Types:** Chat messages, raids (`channel.raid`), follows, and stream online/offline. `channel.subscribe` and `channel.cheer` are not subscribed (require Twitch Affiliate/Partner status).
- **Rule Conditions:** Rules support event type matching, minimum viewer count (`min_viewers` for raids), and cooldowns. There is no slow-mode/shield-mode toggle or substring text-matching condition in the JSON rule engine.
- **Highlight Markers:** Tested against synthetic chat velocity traces (`scripts/replay_chat_trace.py`); live stream calibration is next.

---

## Reference Details

### Live EventSub listener

Run the persistent listener with:

```bash
.venv/bin/crew listen
```

It creates the configured WebSocket subscriptions, stores each fresh
notification once by Twitch message ID, then passes newly stored notifications
to the shared rule engine. Chat messages also feed the rolling highlight
detector. `DRY_RUN=true` is the default; in that mode, Twitch actions are
reported as plans and no Helix action request is sent. Keep it enabled while
trying rules against a live stream.

The listener logs event types and operational status without logging Twitch
tokens or chat message bodies. Stored event payloads remain in the local SQLite
database under `data/`, which is ignored by Git.

Restart `crew listen` after changing the Python source so the running process
loads the new code. An already-running listener keeps the code it started with.
If Twitch closes the session with authentication code 4004, the listener logs a
clear error and stops instead of reconnecting in a loop; refresh the token and
restart it.

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

Set `LOCAL_API_TOKEN` to a random value in the ignored `.env` file. It is
required in the `X-Local-Token` header for full event and approval reads and
approval decisions. The OBS overlay uses summary-only endpoints and never
receives chat bodies or approval action parameters. Useful CLI commands include:

```bash
.venv/bin/crew events --limit 50
.venv/bin/crew events --limit 5 --metadata-only
.venv/bin/crew test fixtures/raid_event.json
.venv/bin/crew approvals list
```

Use `--metadata-only` when checking whether an event arrived; it omits decoded
payloads, including chat bodies. The fixture command forces dry-run mode so it
cannot send a Helix action.
See [the demo and submission checklist](docs/HACKATHON_DEMO.md) for the
reproducible Layer 1 demo and current verification limits.

## Phase 9 OBS overlay

Open `http://127.0.0.1:8765/overlay` while `crew serve` is running and add it
as an OBS Browser Source at 1280x720. The self-contained page polls recent
events and pending approvals every two seconds, and displays successful marker
records from the local event feed. The page uses no external scripts or fonts
and does not contain the local API token.

`GET /health` reports whether the local API and SQLite connection are usable.
If the overlay says `Local crew unavailable`, check that `crew serve` is
running and that `/health` responds. On a failed refresh the page clears stale
rows and shows the unavailable state in every panel instead of presenting old
data as current. Empty event, marker, or approval sections mean the API is
healthy but no matching rows exist yet; storage failures return HTTP 503
instead of a server error.
