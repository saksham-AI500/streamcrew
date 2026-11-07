# 05 Technical Architecture (TAD)

## 1. System diagram
```
Twitch --EventSub WebSocket--> listener --> SQLite (events)
                                              |
                                              v
                      detectors (spam, highlight) + rule engine
                         |                               |
            risky action? yes                  safe action, mode auto
                         v                               v
                approvals (pending)              actions --Helix REST--> Twitch
                         ^
                         | list / approve / reject
 Switch room <--> agents --run--> `crew` CLI --> SQLite + rules/ folder
                                       ^
                          local API (127.0.0.1:8765) --> overlay
```
Boundary rule: **the engine holds the token. Agents only run `crew` commands.**

## 2. Stack
Python 3.11+, `httpx` (Helix), `websockets` (EventSub), `python-dotenv`, FastAPI and uvicorn (local API), SQLite (`sqlite3`), pytest. Plain HTML, CSS, JS for the overlay. No frontend framework. Switch Console plus Docker (Mattermost) for the room.

## 3. Modules (`src/streamcrew/`)
| Module | Responsibility | Status |
|---|---|---|
| `config.py` | Load `.env`. Typed settings. Fail clearly on missing keys. Mask secrets | BUILT |
| `storage.py` | SQLite: events, approvals, rule_cooldowns. `save_event` returns False on duplicates | BUILT |
| `event_processor.py` | Connect EventSub notifications to RuleEngine and HighlightDetector | BUILT |
| `twitch_auth.py` | Validate token, check client and user IDs | BUILT |
| `token_refresh.py` | Refresh the user token and rewrite `.env` | BUILT |
| `eventsub.py` | WebSocket client: welcome, keepalive, reconnect, resubscribe, dedupe, persist | BUILT |
| `subscriptions.py` | Create and track subscriptions, enforce cost, reuse on 409 | BUILT |
| `rules.py` | Rule schema and validation | BUILT |
| `engine.py` | Match events to rules. Modes. Cooldowns. Template filling | BUILT |
| `actions.py` | `execute_action` and the six Helix calls | BUILT (mocked) |
| `highlights.py` | Chat-rate detector (pure math) | BUILT |
| `approvals.py` | Queue operations, approve and reject, execution | BUILT |
| `api.py` | FastAPI routes and overlay | BUILT |
| `cli.py` | `crew` entry point | BUILT |
| `spam.py` | Spam detector (pure function) | BUILT |
| `redact.py` | Redact chat text for agent-facing output | BUILT |
| `static/overlay.html` | OBS overlay | BUILT |

Verify the real file list with `ls src/streamcrew` before editing. Do not create a module if an equivalent exists.

## 4. Data flows
**Event path:** Twitch sends a frame, the client checks `message_id` and age, then stores the event, then calls detectors and the engine.

**Incident path (Workflow A):** `channel.chat.message` events feed a rolling window. `spam.py` returns an incident (account IDs, normalised text, counts, window). The engine writes **one** approval row with a grouped `action_json`. Nothing is sent to Twitch.

**Approval path:** a human replies `approve 7`. `crew-mod` runs `crew approve 7`. The approvals module checks the row is `pending`, then executes each target through `execute_action` with pacing, records per-target results, and sets `done` or `failed`.

**Rule authoring path (Workflow B):** `crew-producer` writes `rules/draft/<name>.json`. It runs `crew validate` and `crew test`. After a human says "ship it" it runs `crew rules ship <name>`, which validates again and moves the file to `rules/active/`.

**Simulation path:** `crew simulate spam` loads `fixtures/spam_burst.json` and feeds it through the same detector and queue code as live events. No network.

## 5. Key decisions
| # | Decision | Reason |
|---|---|---|
| D1 | Deterministic runtime. AI only at the edges | Stable, testable, safe to demo |
| D2 | EventSub over WebSocket, not webhooks | No public URL needed on a laptop |
| D3 | SQLite single file at data/events.sqlite3 (no WAL mode set). Thread RLock in storage.py | No server, simple backup |
| D4 | CLI is the agent boundary | The agent never sees the token |
| D5 | Risky actions approve-only | The human is always in the loop |
| D6 | Simulation uses the real code path | Honest, repeatable demo |
| D7 | Redact chat text for agents | Agent output goes to an AI provider |
| D8 | No frontend framework | Runs with `crew serve`, nothing to build |

## 6. Configuration (`.env`)
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`, `TWITCH_USER_ACCESS_TOKEN`, `TWITCH_REFRESH_TOKEN`, `TWITCH_BROADCASTER_ID`, `TWITCH_BROADCASTER_LOGIN`, `DRY_RUN`, `LOG_LEVEL`, `DB_PATH`, `LOCAL_API_TOKEN`, `EVENTSUB_WS_URL`.
Proposed additions (TO BUILD, with defaults): `SPAM_MIN_ACCOUNTS=5`, `SPAM_WINDOW_SECONDS=10`, `SPAM_COOLDOWN_SECONDS=60`, `SPAM_TIMEOUT_SECONDS=600`, `GROUP_CAP=25`, `ACTION_PACING_SECONDS=0.5`, `RETENTION_DAYS=14`. Keep every key in `.env.example` with a placeholder.

## 7. Folder structure
```
streamcrew/
  AGENTS.md
  docs/                      01 to 09 documents
  design/                    screenshots, references, diagrams
  src/streamcrew/            modules above, static/
  rules/                     draft/ and active/ (TO BUILD split)
  fixtures/                  sample events, chat traces, spam_burst.json (TO BUILD)
  scripts/                   check_setup.py, replay scripts
  tests/
  data/                      logs (git-ignored)
  NOTES.md  README.md  pyproject.toml  .env.example
```
There is no `frontend/` or `backend/` split. The overlay lives in `src/streamcrew/static/`.

## 8. Deployment
Local only, on the Ubuntu laptop.
| Process | Command | Notes |
|---|---|---|
| Listener | `crew listen` | Long-running |
| API and overlay | `crew serve` | Port 8765, localhost only |
| Switch Console | desktop app | Must stay open. Runs Mattermost in Docker |
| OBS | desktop app | Browser Source points at `/overlay` |
Memory is tight on 12 GB. Close browsers and other tools during the demo. Back up `data/events.sqlite3` and `data/` after each live run.

## 9. Security architecture
- Token and secret live only in `.env`, which is git-ignored.
- Agents run in the repo directory. Room instructions forbid reading `.env`. Keep the token out of any file an agent is told to read.
- API binds to 127.0.0.1. Mutating routes need `X-Local-Token`.
- Real-channel tests use accounts the owner controls.
- Revoke the app at Twitch connections settings and rotate the secret after the project.
