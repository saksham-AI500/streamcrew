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
- 2026-10-27 — Access token renewed via refresh.
- 2026-10-27 — Phase A1 real-Twitch retry: all four POSTs returned HTTP 202
  with status `enabled` within 1.19 seconds of `session_welcome`. Immediate
  subscription-list readback showed `stream.online`, `stream.offline`, and
  `channel.follow` as enabled, but did not show `channel.raid`. The socket
  ended with `EventSub keepalive timed out` before the requested 60-second
  observation; no notification was logged. All four test subscription IDs
  were deleted individually after confirmation, and each was confirmed absent
  from the list. No channel content was changed. Gate: FAIL.
- 2026-10-27 — Live verification findings (cause unresolved; no code fix or
  test added yet):
  - Symptom: `channel.raid` POST succeeded with HTTP 202 and `enabled`, but the
    immediate GET readback did not find it for the new session. Cause: not yet
    determined; possible list propagation delay or verification matching
    discrepancy. Fix: pending investigation. Test added: none; no production
    code defect is confirmed.
  - Symptom: the 60-second WebSocket observation exited with
    `EventSub keepalive timed out` before 60 seconds. Cause: no application
    message arrived within the welcome's advertised keepalive timeout; whether
    Twitch closed the socket or a keepalive was missed is undetermined. Fix:
    pending investigation. Test added: none.
- 2026-10-27 — Project completion audit: `main` is checked out; the
  `frontend-overlay` branch points to the same commit and contains no unique
  changes. The existing live listener (PID 58652) was still running. The
  database contains historical mock events and no chat messages at audit time.
  `.env`, `.venv/`, databases, and logs are ignored; `.env` is not staged or
  tracked, and configured secret/token values matched neither current candidate
  files nor Git history.
- 2026-10-27 — Layer 1 integration fix: `crew listen` previously stored
  notifications without evaluating rules or passing chat messages to the
  highlight detector. Added a notification callback invoked only after a fresh
  event is saved, wired the existing engine and detector into the listener,
  and added regression tests. Dry-run remains guarded by `DRY_RUN=true`.
  Reduced dry-run log details so rendered chat text and user IDs are not logged.
  The EventSub timeout tests use virtual time for the five-second grace period;
  a local WebSocket test confirms automatic Pong handling. Full suite: 71 passed,
  1 Starlette/httpx deprecation warning. Full `/events` and `/approvals` reads
  now require `LOCAL_API_TOKEN`; the overlay uses summary-only routes that omit
  chat payloads and action parameters, and `/health` checks storage readiness.
  Action validation follows current Twitch field limits, rejects unknown action
  fields, and a chat API `is_sent: false` response is treated as failure.
- Bug record — Live events were saved but never reached the configured rule
  engine or highlight detector. Cause: `crew listen` connected storage and
  subscriptions only. Fix: added a callback after successful deduplicated
  storage and wired the CLI to the existing processor. Test added:
  `test_notification_callback_runs_only_after_first_store` and
  `test_saved_raid_notification_runs_matching_rule_in_dry_run`.
- Bug record — Dry-run rule logs could include rendered chat text or user IDs.
  Cause: the engine logged the full rendered action dictionary. Fix: logs now
  identify only the planned action. Test added:
  `test_dry_run_log_does_not_include_rendered_chat_content`.
- Bug record — Unauthenticated local API reads returned full event payloads and
  approval action parameters to the OBS page. Cause: the overlay called the
  same full-data routes used by local clients. Fix: full reads now require the
  local API token; overlay routes expose type/time and approval metadata only.
  Test added: `test_events_and_pending_approvals_are_readable` verifies both
  authentication and summary redaction.
- Bug record — Twitch's chat API can return HTTP 200 with `is_sent: false`,
  which the action layer previously called sent. Cause: success was based only
  on the HTTP status. Fix: the response body is checked and a non-sent result
  raises `ActionError`. Test added:
  `test_chat_api_accepted_but_not_sent_is_reported_as_failure`.
- 2026-10-27 — Hackathon rules checked: Codex x TwitchCon requires the project
  to be newly built during its Oct 23–Nov 2 submission period, with repository,
  Codex session ID, feature description, and a public YouTube demo under three
  minutes. The existing project commits are dated Oct 26. Flip the Switch runs
  Nov 4–7 and requires Switch to be central to a real team-chat workflow.
  Switch uses an agent protocol (SSE down, HTTP up). Docker/Switch Console and
  Switch bridge/agent credentials are not present in this workspace, so a live
  Switch room test remains blocked on setup. No actual submission was made.
- 2026-10-27 — OpenCode takeover audit (no Twitch call, no listener restart):
  `main` at `3d9ccc3` with the existing dirty Layer 1 worktree preserved.
  Baseline: 71 tests passed, 1 Starlette/httpx warning; `pip check`,
  `compileall`, `crew --help`, and `git diff --check` passed. Read-only SQLite
  audit: 13 events (`stream.online` 7, `stream.offline` 2, `channel.raid` 2,
  `channel.follow` 2), no chat event, no approvals, no cooldowns. A temporary
  `crew serve` process returned `/health` 200, `/overlay/events` 200 with
  summaries, `/overlay/approvals` 200 with an empty list, and `/overlay` 200;
  unauthenticated `/events` and `/approvals` returned 401. Headless Chrome
  rendered “Connected to local crew” with the stored event rows and the empty
  marker/approval messages. The screenshot’s “Local crew unavailable” state was
  because `crew serve` was not running, not an API defect.
- 2026-10-27 — Listener process note: PID 58652 is still running `crew listen`
  and had an established TLS connection when checked, but it started at 09:59,
  before `event_processor.py`/`cli.py` (10:53) and `eventsub.py` (11:01) were
  changed. It therefore is not proof that the current processing and keepalive
  code is active. It was not stopped or restarted. The A2 real-chat gate is
  still waiting for the human `chat sent` signal; no chat row exists.
- Bug record — When SQLite became unavailable, `/health` returned 503 but
  `/events`, `/approvals`, `/overlay/events`, and `/overlay/approvals` raised an
  unhandled `sqlite3.ProgrammingError` (HTTP 500), and approval decisions did
  the same. Cause: only `/health` caught storage errors. Fix: all storage reads
  and approval decisions now return HTTP 503 “Storage unavailable”. Tests
  added: `test_storage_failure_returns_service_unavailable_not_server_error`
  and `test_empty_database_returns_empty_overlay_summaries`.
- Bug record — `scripts/check_setup.py` printed the first four characters of
  the client ID, access token, and client secret. Cause: its “masked” helper
  included a value prefix. Fix: the helper now prints only `set` or `missing`.
  Test added: `test_setup_report_never_prints_credential_values`.
- 2026-10-27 — Added an end-to-end local regression test that passes a fresh
  raid notification through `EventSubClient.handle_message` into
  `EventProcessor`, verifies the rule cooldown was written, and verifies a
  duplicate frame does not run twice:
  `test_fresh_eventsub_notification_reaches_processor_through_client`.
  Full suite after these changes: 75 passed, 1 Starlette/httpx warning.
- 2026-10-27 — Cooldown bug fixed: an auto-mode rule stored its cooldown
  before calling the action layer, so a failed Twitch action suppressed retries
  until the cooldown expired. Cooldowns are now recorded only after a dry-run
  plan, a queued approval, or a successful auto action. Tests added:
  `test_failed_auto_action_does_not_consume_the_rule_cooldown` and
  `test_successful_auto_action_records_the_rule_cooldown`.
- 2026-10-27 — EventSub authentication close fixed: a WebSocket close with code
  4004 returned to the run loop, which immediately reconnected with no delay.
  The listener now logs a clear authentication error, stops reconnecting, and
  asks for the token to be refreshed before restart. Test added:
  `test_authentication_close_4004_stops_without_reconnecting`. The close-code
  check also avoids the deprecated `ConnectionClosed.code` accessor.
- 2026-10-27 — Overlay truthfulness improved: on an API/fetch failure the page
  previously left stale event/approval rows visible while only changing the
  header text. It now clears all three panels, shows `Local crew unavailable.`
  in each, and displays loading states before the first response. Verified with
  headless Chrome against both a healthy API (10 event rows, connected state)
  and a static server whose API requests fail (no stale rows, unavailable
  state). Static-state assertion added:
  `test_overlay_page_has_loading_and_unavailable_states`.
- 2026-10-27 — Added configuration tests for missing required values, invalid
  `DRY_RUN`, and the safe dry-run default, plus a CLI test confirming
  `crew listen` prints a configuration error reason while still withholding
  other exception text.
- 2026-10-27 — Added `crew events --metadata-only`, which prints event IDs and
  subscription metadata without decoded payloads or chat bodies. This makes
  the pending live-chat check privacy-safe. Test added:
  `test_cli_events_metadata_only_omits_message_body`. Full suite after all
  changes: 84 passed, 1 Starlette/httpx warning.

- 2026-10-27 — With explicit authorization, stopped the old listener (PID
  58652) with SIGINT and started the current code as PID 74598. It connected to
  EventSub and created enabled subscriptions for `stream.online`,
  `stream.offline`, `channel.chat.message`, `channel.raid`, `channel.follow`,
  and `channel.chat.notification` (all HTTP 202, cost 0). Metadata-only event
  inspection still shows no `channel.chat.message` row. The live chat check
  remains pending a human-confirmed message; no payload was read or recorded.

- 2026-11-05 — Step 0 doc reconciliation: database path hardcoded to data/events.sqlite3 (DB_PATH unused), table named rule_cooldowns (no WAL mode), rules load at startup only, and /events and /approvals require X-Local-Token.

- 2026-11-05 — Step 1 (R3) PASS: added pure spam detector in src/streamcrew/spam.py, SRS config defaults in src/streamcrew/config.py, burst/quiet fixtures, and 12 unit/fixture/performance tests in tests/test_spam.py.
- 2026-11-05 — Steps 2–4 (R4, R6, R5) + R8/R10/Overlay PASS: wired grouped spam approval (cap 25) in event_processor.py, crew simulate spam, paced per-target execution and transactional claim in approvals.py/storage.py, crew rules ship, redact.py, and polished 1280x720 overlay UI (102 passed).

- 2026-11-06 — Switch Hackathon rules & cut-off verified: Flip the Switch Hackathon (WeMakeDevs x DevTools Academy, powered by Switch AI). Submission deadline is November 7, 2026 at 11:59 PM IST. Judging criteria: (1) Use of Switch, (2) Technical execution, (3) Creativity & impact, (4) Presentation & demo video. Pre-event engine code is permitted because the challenge is connecting the agent workflow to chat via Switch.
- 2026-11-06 — Resolved critical audit issues:
  1. Approval locking & count verification: pending approvals lock when listed/viewed (`locked: True`) to prevent silent target expansion during continuing raids; `crew approve <id> --count <N>` rejects execution if target count changed.
  2. Safe alt-account testing: added `crew simulate test-alt --user-id <id> --login <login>` to prevent accidental moderation of fixture account IDs when testing with `DRY_RUN=false`.
  3. Switch agent interaction model: Switch agents are reactive (trigger on `@mention`). Demo Workflow A starts with human asking `@crew-mod what's pending?`.
  4. Details verified & reconciled: `crew approvals approve <id>` added as CLI alias for `crew approve <id>`; 1,000-message benchmark verified at 10.78 ms (< 100 ms budget); 0.5s pacing verified by sleep tests (yields 120 req/min within Twitch Helix limits); `crew simulate` writes to real database (`data/events.sqlite3`); dynamic rule reloading added to `EventProcessor` via `rules_loader` so `crew rules ship` rules take effect without restarting `crew listen`. Total tests: 107 passed, 0 failed.
- 2026-11-07 — R2, R7 & R10 PASS: Switch Console + Docker Mattermost + `@crew-mod` proven live in `#stream-ops` (Workflow A table & approval verified); added `--by <name>` audit trail to `crew approve`/`reject`, `.env.example` zero-config fallback when `.env` is absent, and updated `README.md` with Switch architecture and honest limits (108 passed, 0 failed).
