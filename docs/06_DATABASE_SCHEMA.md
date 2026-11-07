# 06 Database Schema (SQLite)

File path is `data/events.sqlite3` (hardcoded in `cli.py` and `api.py`; `DB_PATH` is not loaded). The file is git-ignored. **Verify every table below against `storage.py` before changing anything.** Names marked (verify) are best knowledge, not read from code.

## 1. Tables
### `events` (BUILT)
| Column | Type | Notes |
|---|---|---|
| `message_id` | TEXT PRIMARY KEY | Twitch `metadata.message_id`. Dedupe key |
| `message_type` | TEXT | notification, keepalive, and so on |
| `subscription_type` | TEXT | for example `channel.chat.message` |
| `received_at` | TEXT | UTC ISO 8601 |
| `payload_json` | TEXT | Raw notification. May contain abusive or personal text |

### `approvals` (BUILT)
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | The number humans type: `approve 7` |
| `rule_id` | TEXT | Rule or detector that created it, for example `spam-detector` |
| `action_json` | TEXT | The action or grouped action (shape below) |
| `status` | TEXT | `pending`, `approved`, `rejected`, `done`, `failed` |
| `created_at` | TEXT | UTC ISO 8601 |
| `decided_at` | TEXT NULL | Set on approve or reject |
| `decided_by` | TEXT NULL | `cli`, or the human's name passed in |

### `rule_cooldowns` (BUILT)
| Column | Type | Notes |
|---|---|---|
| `rule_id` | TEXT PRIMARY KEY | |
| `last_run_at` | TEXT | UTC ISO 8601 |

### `incidents` (TO BUILD, optional)
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | |
| `kind` | TEXT | `spam_burst`, `raid`, `highlight` |
| `detected_at` | TEXT | |
| `window_start`, `window_end` | TEXT | |
| `summary_json` | TEXT | Counts, normalised text hash, redacted sample |
| `approval_id` | INTEGER NULL | FK to `approvals.id` |

If time is short, skip `incidents` and put the summary inside `action_json`.

## 2. JSON shapes
**Grouped timeout (BUILT)**
```json
{
  "action": "ban_user",
  "duration": 600,
  "duration_seconds": 600,
  "reason": "spam burst",
  "targets": [{"user_id": "123", "login": "example_user"}],
  "results": [{"user_id": "123", "ok": true, "error": null}],
  "summary": {"accounts": 14, "messages": 31, "remaining_accounts": 0, "window_seconds": 10, "sample": "[redacted 40 chars]"}
}
```
`results` is empty while pending and filled during execution. Maximum 25 targets (`GROUP_CAP`).

## 3. Relationships
```
events          (stand-alone log, no foreign keys)
incidents 1---0..1 approvals     (optional)
approvals ---> action_json.targets[]   (logical, not enforced)
rule_cooldowns  (one row per rule)
```

## 4. Indexes and constraints
- `events`: PRIMARY KEY on `message_id`. (Secondary indexes on `received_at` and `subscription_type` not yet created).
- `approvals`: PRIMARY KEY on `id`. A CHECK constraint on `status` values.
- Status changes happen inside one transaction that first checks the current status is `pending`. This stops double approval.

## 5. Data access rules
| Actor | Reads | Writes |
|---|---|---|
| Listener | n/a | `events` |
| Engine and detectors | `events` | `approvals`, `rule_cooldowns`, `incidents` |
| `crew approve` and `crew reject` | `approvals` | `approvals` (status, decided fields, results) |
| Local API | `events`, `approvals` | `approvals` via the same code as the CLI |
| Agents | Only through `crew` commands | Only through `crew` commands |

SQLite does not currently use WAL mode or a busy timeout; connection uses default journal mode with thread RLock serialization.

## 6. Retention and privacy
- Chat payloads can contain slurs and personal details. Purge `payload_json` of chat events older than `RETENTION_DAYS` (default 14), or replace it with a hash plus a short sample.
- Never store tokens or the client secret in the database.
- Back up the database after each live run to a dated copy outside the repo.
