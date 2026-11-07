# 07 API Specification

Four interfaces: the **CLI** (the agent boundary), the **local API**, the **Twitch APIs** the engine calls, and the **Switch** integration. Response shapes below are indicative. **Read `api.py` and `cli.py` for the real shapes** and update this file if they differ.

## 1. CLI (`crew`)
Exit codes: `0` success, `1` failure or refused, `2` invalid usage.
| Command | Purpose | Mutates | Agent may run |
|---|---|---|---|
| `crew listen` | Start the EventSub listener | database | No (human starts it) |
| `crew serve` | Start API and overlay | no | No |
| `crew events [--limit N] [--metadata-only] [--full]` | Recent events (redacted by default; `--metadata-only` omits payloads; `--full` prints raw) | no | Yes (never `--full`) |
| `crew rules list` | List rules and modes | no | Yes |
| `crew validate <file>` | Validate a rule file | no | Yes |
| `crew test <fixture>` | Run rules on a saved event. Dry-run output only | no | Yes |
| `crew approvals list [--status S]` | List approval items (with account count & redacted sample) | no | Yes |
| `crew approve <id>` | Approve and execute | **yes** | Only after a human reply naming the ID |
| `crew reject <id>` | Reject | **yes** | Only after a human reply naming the ID |
| `crew simulate spam` | Feed the spam fixture through detector and queue | database | Yes |
| `crew rules ship <name>` | Validate, then move `rules/draft/<name>.json` to `rules/active/` | **yes** | Only after a human says "ship it" |

All CLI commands above are BUILT (verify with `crew --help`).

## 2. Local API (FastAPI, `127.0.0.1:8765`)
| Method and path | Auth | Description |
|---|---|---|
| `GET /health` | none | API and SQLite responsiveness |
| `GET /events?limit=N` | `X-Local-Token` | Recent events with decoded payload |
| `GET /overlay/events?limit=N` | none | Event summaries only (no chat payload) |
| `GET /approvals?status=pending` | `X-Local-Token` | Approval items with action_json |
| `GET /overlay/approvals` | none | Pending approval summaries |
| `POST /approvals/{id}/approve` | `X-Local-Token` | Same logic as the CLI |
| `POST /approvals/{id}/reject` | `X-Local-Token` | Same logic as the CLI |
| `GET /overlay` | none | OBS overlay page |
| `GET /dashboard` | none | Only if built (paused) |

Indicative event: `{"events": [{"message_id": "...", "message_type": "notification", "subscription_type": "channel.raid", "received_at": "...Z", "payload": {...}}]}`
Indicative approval: `{"approvals": [{"id": 7, "rule_id": "spam-detector", "action_json": "{\"action\":\"ban_user\",...}", "status": "pending", "created_at": "...Z", "decided_at": null, "decided_by": null}]}`

Errors: `401` missing or wrong token, `404` unknown ID, `409` item not pending, `422` bad input. Error bodies carry a one-line message and never a secret.

## 3. Twitch EventSub (WebSocket)
URL `wss://eventsub.wss.twitch.tv/ws`. A user access token is required. Create subscriptions within 10 s of the welcome message.
| Type | Version | Condition | Scope |
|---|---|---|---|
| `stream.online` | 1 | `broadcaster_user_id` | none |
| `stream.offline` | 1 | `broadcaster_user_id` | none |
| `channel.chat.message` | 1 | `broadcaster_user_id`, `user_id` | `user:read:chat` |
| `channel.chat.notification` | 1 | `broadcaster_user_id`, `user_id` | `user:read:chat` |
| `channel.raid` | 1 | `to_broadcaster_user_id` | none |
| `channel.follow` | 2 | `broadcaster_user_id`, `moderator_user_id` | `moderator:read:followers` |
Limits per user token: 3 WebSocket connections, 300 subscriptions per connection, max total cost 10. Duplicates carry the same `message_id`. Ignore notifications older than 10 minutes.

## 4. Twitch Helix (actions)
Auth header `Authorization: Bearer <user token>` plus `Client-Id`. Confirm each endpoint and field on the Twitch reference page before editing the call.
| Action | Endpoint | Key fields | Scope | Mode |
|---|---|---|---|---|
| `send_chat_message` | `POST /helix/chat/messages` | `broadcaster_id`, `sender_id`, `message` | `user:write:chat` | auto or approve |
| `send_announcement` | `POST /helix/chat/announcements` | `broadcaster_id`, `moderator_id`, `message`, `color` | `moderator:manage:announcements` | auto or approve |
| `send_shoutout` | `POST /helix/chat/shoutouts` | `from_broadcaster_id`, `to_broadcaster_id`, `moderator_id` | `moderator:manage:shoutouts` | auto or approve |
| `create_marker` | `POST /helix/streams/markers` | `user_id`, `description` | `channel:manage:broadcast` | auto |
| `ban_user` (timeout with `duration`) | `POST /helix/moderation/bans` (verify) | `broadcaster_id`, `moderator_id`, body `user_id`, `duration`, `reason` | `moderator:manage:banned_users` | **approve only** |
| `delete_message` | `DELETE /helix/moderation/chat` (verify) | `broadcaster_id`, `moderator_id`, `message_id` | `moderator:manage:chat_messages` | **approve only** |
**Not available:** `Update Chat Settings` and shield mode need `moderator:manage:chat_settings`, which is not granted.
Token endpoints: `GET https://id.twitch.tv/oauth2/validate` (header `Authorization: OAuth <token>`), `POST https://id.twitch.tv/oauth2/token` (refresh).
Shoutouts have cooldowns. On 429 log the retry time and do not retry.

## 5. Switch integration
Switch needs **no API key and no client library**. The Switch Console desktop app runs a local room (Mattermost in Docker) and runs your signed-in agent apps (Codex, OpenCode, Antigravity).
- An agent answers only when addressed by exact `@name`. Default permission is owner-only. Add teammates in the agent's settings.
- Agents run in the repo directory and use only the `crew` commands in section 1.
- Switch Console must stay open while agents are needed.
- Agent provider sign-in is separate and may need a paid plan. Check each provider.

## 6. Rule file format
```json
{
  "id": "raid-welcome",
  "event": "channel.raid",
  "conditions": {"viewers": {"gte": 20}},
  "actions": [
    {"action": "send_shoutout", "target": "{{from_broadcaster_user_id}}"},
    {"action": "create_marker", "description": "Raid from {{from_broadcaster_user_name}}"}
  ],
  "cooldown_seconds": 120,
  "mode": "auto"
}
```
`mode` is `dry_run`, `approve`, or `auto`. A missing mode means `dry_run`. Check the exact event field names against the Twitch EventSub reference.
