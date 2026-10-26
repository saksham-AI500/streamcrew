# StreamCrew notes

## Decisions for Step 1

- Use Python 3.11+, `httpx`, `websockets`, `python-dotenv`, and the standard
  library `sqlite3`; no Twitch wrapper library.
- Require `TWITCH_CLIENT_ID`, `TWITCH_USER_ACCESS_TOKEN`, and
  `TWITCH_BROADCASTER_ID`. `DRY_RUN` defaults to `true` and accepts common
  boolean spellings.
- Keep SQLite records unique by EventSub `message_id`, using a primary key and
  `INSERT OR IGNORE` so duplicate deliveries do not create duplicate rows.
- Never log or print credentials. `.env` is excluded from Git.
- Twitch docs checked on 2026-10-26: EventSub uses
  `wss://eventsub.wss.twitch.tv/ws`; subscriptions must be created within the
  welcome timeout; WebSocket subscriptions use user access tokens; reconnect
  handoff waits for the new welcome before closing the old connection; drops
  require resubscription; duplicate IDs identify retransmissions; the stale
  timestamp and connection/subscription limits in the project brief match.
- The Python `websockets` library automatically responds to received Ping
  frames with Pong by default. Its own periodic Ping keepalive is enabled by
  default too; this will be considered when implementing the Twitch client.

## Open questions

- Which EventSub event types and corresponding Twitch scopes should the first
  live client subscribe to? Decide before implementing subscriptions.
- Confirm the desired location/name for the runtime SQLite database when the
  service entry point is added.

## Scope boundary

Only the configuration and SQLite event store are included in Step 1. The
EventSub client, automations, highlight detector, approval queue, OBS overlay,
and CLI are intentionally deferred.

## Setup phases

- 2026-10-26 — Phase 0 check: project folder and base files are present, but
  `src/streamcrew/twitch_auth.py` and `scripts/check_setup.py` are missing.
  Per the setup gate, no files were recreated and later phases were not started.
- 2026-10-26 — Created `src/streamcrew/twitch_auth.py` and
  `scripts/check_setup.py` as requested, then re-ran Phase 0. All required
  Phase 0 files are now present. Syntax passed using `python3`; no Twitch API
  calls were made. Phase 1 was not started.
- 2026-10-26 — Phase 1 passed: created `.venv` with Python 3.14.4, installed
  the project runtime and dev dependencies, confirmed `httpx`, `websockets`,
  `dotenv`, and `pytest` import successfully, and confirmed `.venv/` is in
  `.gitignore`.
- 2026-10-26 — Phase 2 passed: client ID and Client Secret are present, and
  the secret does not start with either known old prefix. User and refresh
  tokens are empty. `.env` is ignored and `.env.example` contains credential
  placeholders. No Twitch API calls were made.
- 2026-10-26 — Phase 3 token check failed: `TWITCH_USER_ACCESS_TOKEN` and
  `TWITCH_REFRESH_TOKEN` were empty in the project `.env` when checked. Phase 4
  and later phases were not started; no Twitch API calls were made.
- 2026-10-26 — Phase 3 re-check passed: both user and refresh tokens are now
  present in `.env`. Values were not recorded here.
- 2026-10-26 — Phase 4 passed: the read-only Helix users request returned the
  broadcaster identity and it was saved in `.env`. No credential values were
  recorded here.
- 2026-10-26 — Phase 5 passed: `scripts/check_setup.py` validated the token,
  confirmed the client and broadcaster identities match, and returned all
  requested scopes. No requested scopes are missing. Broadcaster login:
  `saksham034`.
- 2026-10-26 — Phase A passed: `.venv` exists, the `httpx`, `websockets`,
  `dotenv`, and `pytest` imports succeeded, and `.venv/` is listed in
  `.gitignore`.
- 2026-10-26 — Phase 1 PASS: created `src/streamcrew/token_refresh.py` and
  `tests/test_token_refresh.py`; updated config loading and project dependencies.
  Dependencies import, all four tests pass, `.env` and `.venv/` are ignored,
  and none of the full configured secret/token values match this file. Open
  question: Git metadata is absent in this workspace, so tracked-file status
  cannot currently be inspected.
- 2026-10-26 — Phase 2 gate revised and passed. The initial control compared
  two distinct mock triggers, which correctly have different message IDs and
  should create two rows. Added `scripts/replay_duplicate.py` to capture one
  local mock notification and replay its exact raw frame through the handler;
  it stores one row. Two separate triggers store two rows with different IDs,
  and all eight tests pass. No secrets or token values are recorded here.
- 2026-10-26 — Phase 3 gate revised and PASS. Official Twitch documentation
  confirms both chat subscription types are version 1, use broadcaster and
  user IDs in their conditions, and require `user:read:chat`; the implementation
  matches. Added request-body tests for all six types. All 13 tests pass. The
  local mock still rejects both chat types with HTTP 400, while the other four
  types create subscriptions and deliver events. A real Twitch check enabled
  both chat test subscriptions, observed the channel for 60 seconds (no chat
  notifications arrived), deleted both test subscriptions, and confirmed both
  absent from the subscription list. No secrets or token values recorded.
- 2026-10-26 — Phase 3 real-Twitch gap closed for the other four types:
  stream.online v1, stream.offline v1, channel.raid v1, and channel.follow v2
  were enabled on a real WebSocket session, observed for about 60 seconds with
  no notifications received, then all four test subscriptions were deleted
  and confirmed absent. No secrets or token values recorded.
- 2026-10-26 — Phase 4 PASS: added rule validation, event matching and templates,
  persisted cooldown and approval storage, `crew validate`, and `crew rules list`.
  The saved raid fixture runs in dry-run and logs its planned shoutout; all 22
  tests pass. Open question: auto-mode execution depends on the Phase 5 action
  layer, which is not implemented yet.
- 2026-10-26 — Phase 3 recheck passed: both user and refresh tokens are now
  present in the project `.env`. Values intentionally omitted.
- 2026-10-26 — Phase 5 PASS: added `src/streamcrew/actions.py` as the single
  guarded Helix action path and `tests/test_actions.py` for mocked contracts
  and dry-run zero-request checks. Current Twitch reference uses query
  parameters for announcement and shoutout IDs; requests follow that format.
  All 38 tests passed at the Phase 5 gate. No live action was sent. Manual live
  action testing remains for the user.
- 2026-10-26 — Phase 6 PASS: added `src/streamcrew/highlights.py`,
  `tests/test_highlights.py`, `fixtures/chat_trace.json`, and
  `scripts/replay_chat_trace.py`. The synthetic trace fired one marker request
  through the dry-run guard; quiet activity did not fire, and the 60-second
  gap suppressed a second spike. All 42 tests pass. Open question: the real
  recorded-chat check remains a manual step; no live marker was created.
- 2026-10-26 — Phase 7 implementation completed, but the phase gate is FAIL.
  Added `src/streamcrew/approvals.py`, approval decision methods in
  `src/streamcrew/storage.py`, CLI commands in `src/streamcrew/cli.py`, and
  tests in `tests/test_approvals.py` plus an approved-action guard test. All 48
  tests pass. The previously recorded granted scope set does not include
  `moderator:manage:banned_users` or `moderator:manage:chat_messages`, which
  Phase 7 requires. No new Twitch call was made. Open item: the user must
  reauthorize with those two scopes before Phase 7 can pass.
- 2026-10-26 — Phase 7 scopes re-authorized: the read-only token validation
  confirmed the current scopes are `bits:read`, `channel:bot`,
  `channel:manage:broadcast`, `channel:read:ads`,
  `channel:read:subscriptions`, `moderator:manage:announcements`,
  `moderator:manage:banned_users`, `moderator:manage:chat_messages`,
  `moderator:manage:shoutouts`, `moderator:read:followers`, `user:bot`,
  `user:read:chat`, and `user:write:chat`. The two Phase 7 moderation scopes
  are present. `scripts/check_setup.py` confirmed valid token and matching
  client and broadcaster identity; all 48 tests pass. No credentials recorded.
- 2026-10-26 — Phase 7 PASS after re-authorization: all approval tests pass,
  the `crew approvals list`, `crew approve`, and `crew reject` command parsers
  are available, and the validated token includes both moderation scopes.
  Approval, rejection, and action execution tests use mocks; no live channel
  action was sent.
- 2026-10-26 — Phase 8 PASS: added `src/streamcrew/api.py`, local event listing
  in `src/streamcrew/storage.py`, `LOCAL_API_TOKEN` config support, and CLI
  commands for events, fixture testing, and serving. Added `tests/test_api.py`,
  updated `.env.example` and README, and generated the local API token directly
  into ignored `.env` without displaying it. The API bound to
  `127.0.0.1:8765`; `GET /events` returned HTTP 200. CLI fixture, rules,
  events, approvals, and help checks passed. All 54 tests pass. A connection
  lock was added after API tests exposed SQLite thread affinity. No Twitch
  action was sent. Open questions: none for Phase 8.
- 2026-10-26 — Phase 9 PASS: added `src/streamcrew/static/overlay.html` and
  `fixtures/marker_created.json`; updated marker logging in
  `src/streamcrew/actions.py`, `src/streamcrew/engine.py`,
  `src/streamcrew/highlights.py`, and `src/streamcrew/approvals.py`; added
  overlay/API coverage in `tests/test_api.py`, `tests/test_engine.py`,
  `tests/test_highlights.py`, and `tests/test_approvals.py`; included the page
  as package data in `pyproject.toml`. The page polls local events and pending
  approvals every two seconds and displays successful marker records. It loaded
  in a browser and visibly showed the saved raid and marker fixtures;
  `GET /overlay` returned HTTP 200. The preview used a temporary SQLite
  database, removed afterward. All 57 tests pass. No token is present in the
  page, and no Twitch action was sent. Open questions: none for Phase 9.
- 2026-10-26 — Repository upload complete: https://github.com/saksham-AI500/streamcrew
  Commit: `48dbb87`. Pushed to GitHub, secrets excluded.
