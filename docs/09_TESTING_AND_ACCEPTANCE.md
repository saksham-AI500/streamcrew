# 09 Testing and Acceptance

## 1. Principles
- Tests never call Twitch. Mock `httpx` and `websockets`. Use `fixtures/` and a fake clock.
- Run the changed module's tests first, then the full suite at the end of a task.
- A bug gets a failing test first.
- Live checks are manual and run only on accounts the owner controls.

## 2. Unit tests
| Module | Must cover |
|---|---|
| `config.py` | Missing required key raises a clear error. Secrets masked |
| `storage.py` | Duplicate `message_id` returns False. Status transition only from `pending` |
| `token_refresh.py` | 200 rewrites `.env` (temp copy). 400 or 401 raises the re-authorise error |
| `eventsub.py` | Welcome, keepalive at 0.9 x timeout stays alive, silent socket reconnects after timeout + 5 s, ping answered, old message ignored, reconnect URL used |
| `subscriptions.py` | Request bodies for all six types. Cost cap. 409 reuse |
| `rules.py` and `engine.py` | Valid rule passes. Unknown action rejected. Cooldown blocks a repeat. `dry_run` changes nothing. `approve` writes a pending row. Missing mode means `dry_run` |
| `actions.py` | Each action sends the right request (mock). Dry-run makes zero HTTP calls. 429 does not retry |
| `highlights.py` | Spike fires once. Quiet trace never fires. 60 s gap |
| `spam.py` | See section 5 |
| `approvals.py` | Pending stays pending. Reject never calls Helix. Approve calls Helix once per target. Second approve refused. Partial failure recorded |
| `redact.py` | Chat text truncated. URLs and emails removed |

## 3. Integration tests
1. Fake websocket frame, then stored row, then engine, then dry-run log.
2. Burst fixture, then spam detector, then one pending approval, then approve (mocked Helix), then `done`.
3. `crew validate`, `crew test`, `crew rules ship` on a sample rule.
4. API: `/events` returns 200. Approve without token returns 401. Approve a non-pending item returns 409.

## 4. End-to-end checks (manual)
| # | Check | Pass |
|---|---|---|
| E1 | `crew listen` on the real channel, a friend types in chat | A `channel.chat.message` row appears |
| E2 | `crew simulate spam` | One pending item, no Twitch call |
| E3 | Agent in the room runs `crew approvals list` | Item shown, text redacted |
| E4 | Human replies `approve <id>` | Alt account timed out once. Result posted. Row `done` |
| E5 | Agent drafts a rule from one sentence | Validate OK, test OK, not active |
| E6 | Human says "ship it" | Rule in `rules/active/`, listed by `crew rules list` |
| E7 | Raid event (real or simulated) | Shoutout, announcement, marker logged. Second raid inside cooldown does nothing |
| E8 | Stop the API | Overlay shows "API offline", recovers when restarted |
| E9 | 20 minutes of `crew listen` during a live stream | No crash, no duplicate rows |

## 5. Spam detector cases
| Case | Expected |
|---|---|
| 5 accounts, same text, within 10 s | Fires once |
| 4 accounts | Does not fire |
| 1 account repeating 30 times | Does not fire as a burst (single-account rule is separate) |
| Same text, spread over 60 s | Does not fire |
| Text differs only by case, spacing, or trailing punctuation | Counts as the same |
| Burst of 40 accounts | One item with 25 targets plus the remaining count |
| Fires, then same burst continues | No second item until the cooldown ends |
| Empty or one-character messages | Ignored |

## 6. Performance
- Detector over 1,000 messages in under 100 ms.
- Listener stores 50 messages per second without loss (fixture replay).
- Overlay updates within 2 s of a new event.

## 7. Security checks (run before every commit that will be pushed)
- `git ls-files | grep -E '^\.env$|\.db$|\.log$'` prints nothing.
- Search tracked files and `NOTES.md` for the full values of the client secret, user token, refresh token, and local API token. Report only yes or no.
- `grep -rnE 'innerHTML|localStorage|sessionStorage|document.cookie|https?://' src/streamcrew/static/` shows no unsafe use and no external URL.
- Logs and test output show secrets masked to 4 characters.
- API refuses mutations without `X-Local-Token`.

## 8. Feature acceptance criteria
The acceptance criteria in `02_PRD.md` (US-1 to US-8) are the pass criteria for each feature.

## 9. Definition of Done
A task is done when:
1. The code does what the roadmap step says and the step's done-when check passes.
2. New behaviour has tests. The full suite passes.
3. The security checks pass.
4. The matching doc is updated in the same change.
5. `NOTES.md` has one line on the result. No secrets.
6. For anything that changes a channel: the human saw the plan and said "yes" first.

## 10. Demo acceptance (3 minutes)
| Time | Show | Pass |
|---|---|---|
| 0:00 to 0:20 | The problem: spam burst, one moderator | Clear in one sentence |
| 0:20 to 1:30 | Workflow A in the room: pending, approve, result | No manual terminal work |
| 1:30 to 2:20 | Workflow B: one sentence becomes a shipped rule | Validate and test shown |
| 2:20 to 2:45 | Safety: dry-run, approve-only, logs | Stated and visible |
| 2:45 to 3:00 | What is next | One sentence |
The demo must state that the burst is simulated if it is, and that the detector and queue are the real code.
