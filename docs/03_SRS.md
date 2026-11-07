# 03 Software Requirements Specification (SRS)

Priority: **M** must, **S** should, **C** could. Status: BUILT, LIVE-UNPROVEN, TO BUILD.
All numeric defaults are design parameters. Put them in `config.py` or the rule file, not in code.

## 1. Functional requirements

### Ingestion
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-01 | Connect to the EventSub WebSocket (`EVENTSUB_WS_URL`, default Twitch URL) with a user token | M | BUILT |
| FR-02 | Create subscriptions within 10 s of `session_welcome` | M | BUILT |
| FR-03 | Handle keepalive (timeout + 5 s grace), `session_reconnect`, close code 4004, and resubscribe after any non-reconnect drop. Backoff max 60 s | M | BUILT |
| FR-04 | Deduplicate by `metadata.message_id` | M | BUILT |
| FR-05 | Ignore notifications older than 10 minutes | M | BUILT |
| FR-06 | Persist each accepted notification to SQLite | M | BUILT |
| FR-07 | Subscribe to: `stream.online`, `stream.offline`, `channel.chat.message`, `channel.raid` (to_broadcaster), `channel.follow` v2, `channel.chat.notification` | M | BUILT (chat types real, others mock plus create-only on real) |
| FR-08 | Keep total subscription cost at or below 10. Reuse on HTTP 409 | M | BUILT |

### Rules
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-10 | Rule JSON: `id`, `event`, `conditions`, `actions[]`, `cooldown_seconds`, `mode` | M | BUILT |
| FR-11 | Modes: `dry_run` (default), `approve`, `auto` | M | BUILT |
| FR-12 | Conditions: equality, `gte`, `lte` on payload fields | M | BUILT |
| FR-13 | Template variables `{{field}}` filled from the payload | M | BUILT |
| FR-14 | Per-rule cooldown | M | BUILT |
| FR-15 | Action allow-list: `send_chat_message`, `send_announcement`, `send_shoutout`, `create_marker`, `ban_user`, `delete_message` | M | BUILT |
| FR-16 | Reject invalid rules with a clear error naming the field | M | BUILT |
| FR-17 | Rule lifecycle: `rules/draft/` then `rules/active/` via `crew rules ship <name>`, which validates first. Current code loads rules from `rules/*.json` once at startup | M | TO BUILD (draft/active split and reload) |

### Actions
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-20 | All actions pass through one `execute_action(action, mode, settings)` | M | BUILT |
| FR-21 | Refuse if `DRY_RUN` is true, mode is `dry_run`, or the action is not allow-listed. Log "would do X" | M | BUILT |
| FR-22 | On HTTP 429 log the retry time and do not retry | M | BUILT |
| FR-23 | `ban_user` and `delete_message` run only from an approved item | M | BUILT |
| FR-24 | Marker on an offline channel logs the 4xx and continues | S | BUILT |

### Detectors
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-30 | Highlight detector: 10 s rolling window, EWMA mean and spread, fire when count >= 8 and z >= 3, 60 s gap | S | BUILT |
| FR-31 | **Spam detector:** normalise text (lowercase, trim, collapse spaces, strip URLs and repeated punctuation). Fire when >= `SPAM_MIN_ACCOUNTS` (default 5) distinct accounts post the same normalised text within `SPAM_WINDOW_SECONDS` (default 10) | M | BUILT |
| FR-32 | Spam detector is a pure function over a list of recent messages plus a clock. No network, no database | M | BUILT |
| FR-33 | One incident per burst. A burst re-fires only after `SPAM_COOLDOWN_SECONDS` (default 60) | M | BUILT |
| FR-34 | Detectors call actions only through `execute_action` or the approval queue | M | BUILT |

### Approvals
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-40 | Table with statuses `pending`, `approved`, `rejected`, `done`, `failed` | M | BUILT |
| FR-41 | Approve and reject record `decided_at` and `decided_by`, and are logged | M | BUILT |
| FR-42 | **Grouped item:** one approval can hold up to `GROUP_CAP` (default 25) targets | M | BUILT |
| FR-43 | Approved group executes sequentially with pacing (`ACTION_PACING_SECONDS`, default 0.5). Partial failure is recorded per target. Item ends `done` or `failed` | M | BUILT |
| FR-44 | Idempotent: approving or rejecting a non-pending item is refused with a clear message. A target is never actioned twice | M | BUILT |
| FR-45 | Timeout duration for spam items: `SPAM_TIMEOUT_SECONDS` (default 600) | M | BUILT |

### Interfaces
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-50 | CLI commands listed in `07_API_SPECIFICATION.md` | M | BUILT |
| FR-51 | `crew events` redacts chat text by default (truncate to 40 chars, no emails or URLs). `--full` prints raw text and is for humans only | S | BUILT |
| FR-52 | Local API on `127.0.0.1:8765`. Sensitive routes (`/events`, `/approvals`, mutations) require `X-Local-Token`; `/health` and `/overlay/*` are unauthenticated | M | BUILT |
| FR-53 | Overlay at `/overlay`, 1280x720, polls every 2 s | M | BUILT |
| FR-54 | `crew simulate spam` feeds a fixture burst through the real detector and queue, with no Twitch call | M | BUILT |

### Switch integration
| ID | Requirement | P | Status |
|---|---|---|---|
| FR-60 | Agents run only `crew` commands. They never read `.env` or call Twitch | M | Policy |
| FR-61 | Room instructions state the approval rule and that dry-run is on | M | TO BUILD |
| FR-62 | Roles: `producer` and `moderator` mapped to `crew-producer` and `crew-mod` | M | TO BUILD |
| FR-63 | `crew-mod` runs approve or reject only after an explicit human reply naming the ID | M | TO BUILD |

## 2. Non-functional requirements
| ID | Area | Requirement |
|---|---|---|
| NFR-01 | Performance | Detector handles 1,000 messages in under 100 ms. Listener stores bursts of at least 50 messages per second without loss |
| NFR-02 | Reliability | Auto-reconnect with backoff. No duplicate rows. Survives a dropped socket during a burst |
| NFR-03 | Security | Secrets only in `.env`. Logs mask to 4 characters. API bound to 127.0.0.1. Mutations need the local token. No `innerHTML` with API data |
| NFR-04 | Privacy | Chat text can hold abuse and personal data. Redact in agent-facing output. Retention: purge chat payloads older than `RETENTION_DAYS` (default 14) |
| NFR-05 | Portability | Ubuntu, Python 3.11+, 12 GB RAM. No GPU |
| NFR-06 | Cost | Runtime needs no paid service and no LLM key |
| NFR-07 | Observability | Rotating log file at `data/`. Levels from `LOG_LEVEL`. One line per decision |
| NFR-08 | Testability | No network in tests. Fixtures for every detector and rule |
| NFR-09 | Maintainability | Small modules. Pure functions for detectors. Each doc updated with the code it describes |

## 3. Roles and permissions
| Role | Can | Cannot |
|---|---|---|
| Streamer | Everything, including re-authorising the token and turning dry-run off | n/a |
| Moderator | List, approve, reject | Edit rules, change config |
| Editor | Read recap | Approve |
| `crew-producer` | Read redacted events, draft rules, run validate and test, ship on a human's "ship it" | Approve, read `.env`, call Twitch |
| `crew-mod` | List the queue, approve or reject on a human's explicit word | Draft or ship rules, read `.env` |
| Engine | Hold the token, call Twitch, write the database | Act on risky items without approval |

## 4. Errors and edge cases
| Case | Expected behaviour |
|---|---|
| Access token expires (401) | Refresh once with the refresh token. If that fails, stop and tell the human to re-authorise |
| Socket drops | Reconnect, resubscribe, log the gap. Missed events are not replayed |
| Duplicate notification | Skipped, logged at debug |
| Subscription exists (409) | Reuse it |
| Shoutout rate limit (429) | Log retry time. Do not retry |
| Marker while offline | Log the 4xx. Continue |
| Target is a moderator, the streamer, or already banned | Twitch rejects. Record `failed` for that target and continue |
| Message already deleted | Record `failed` for that target and continue |
| Approve unknown or already decided ID | Refuse with a clear message. Exit code non-zero |
| Two approvers at once | Second one is refused (status check inside one transaction) |
| Database busy | Short retry, then a clear error |
| Invalid rule | Rejected with the field name. Nothing activates |
| Empty or very long chat text | Normalise safely. Cap stored sample length |
| Clock skew | Use the event's own timestamps for windows |
| Burst larger than `GROUP_CAP` | First 25 accounts in the item. Count of the rest shown. A second item may follow after the cooldown |

## 5. Constraints and assumptions
- Slow mode, shield mode and chat settings need `moderator:manage:chat_settings`, which is **not granted**. Out of scope unless the human re-authorises.
- Access tokens are short-lived. The refresh token is long-lived but revocable.
- Real hate raids cannot be summoned for the demo. Use simulation and say so.
