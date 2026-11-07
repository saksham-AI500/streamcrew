# 08 Implementation Roadmap

Work one step at a time. Each step has a **done-when** check. Do not start a step until the one it depends on is done. No dates here: if time is short, use the cut line in section 3.

## 1. Dependency map
```
R1 live pipe ----> R3 spam detector --> R4 incident to approval --> R5 approve path --> R6 simulate
      |                                                                     |
R2 Switch smoke test ------------------------------------> R7 room + Workflow A <---+
                                                            R8 Workflow B (ship step)
R9 raid rule live (needs R1) ----------------------------------------------+
                                                            R10 harden, record, submit
```

## 2. Steps
| Step | What | Depends on | Size | Done when |
|---|---|---|---|---|
| R0 | Freeze base: branch named, tests green, token valid (`check_setup.py`), `.env` untracked | none | S | `pytest` passes. `git ls-files` shows no `.env` |
| R1 | **Live pipe proof.** Run `crew listen` on the real channel. Store one real chat message | R0 | S | A new `channel.chat.message` row exists with its `message_id` |
| R2 | **Switch smoke test.** Install Switch Console and Docker, sign in one agent, run `crew events --limit 3` from the room | R0 | M | The agent's answer appears in the room. If not, try another agent |
| R3 | **Spam detector** `spam.py`: pure function, config params, tests with fixtures | R0 | M | Burst fixture fires once. Quiet fixture never fires. Cooldown enforced |
| R4 | **Incident to approval:** engine writes one grouped pending item (cap 25), no Twitch call | R3 | M | `crew approvals list` shows the item with account count |
| R5 | **Approve path:** paced execution, per-target results, idempotent, status check in a transaction. Test only on throwaway accounts you own | R4 | M | One owned alt account is timed out once. Second approve is refused |
| R6 | **`crew simulate spam`** and `fixtures/spam_burst.json` | R4 | S | One command creates the pending item from the fixture |
| R7 | **Room and Workflow A:** create `stream-ops`, roles, room instructions, agent briefs. Rehearse `what's pending?` then `approve <id>` | R2, R5, R6 | M | The run completes in under 3 minutes with no manual terminal work |
| R8 | **Workflow B:** `rules/draft` and `rules/active`, `crew rules ship`, decide how rules load, agent briefs | R2 | M | One sentence becomes a validated, tested, shipped rule |
| R9 | **Raid rule live:** shoutout, announcement, marker on a real or simulated raid | R1 | S | Actions logged, cooldown blocks a repeat |
| R10 | **Harden and submit:** redaction in `crew events`, retention, fixtures replay, README, backups, fallback video, room screenshots, submission | R7 (R8, R9 if done) | M | Demo recorded. Submission confirmation saved. No secret in git |

## 3. Cut line (short on time)
**Must:** R0, R1, R2, R3, R4, R5, R6, R7, then R10.
**Add next:** R8, then R9.
**Drop first:** dashboard, recap, highlight live test, incidents table, retention job.
Never cut: the fallback video, the README, the secret check, and the human approval rule.

## 4. Task card template (use for every agent task)
```
Task: <one sentence>
Roadmap step: <R#>
Files likely touched: <list, max 2 without approval>
Reason first: <goal and smallest change>
Tests: <which tests to add or run>
Done when: <check from the table>
Out of scope: <what not to touch>
Stop after: report PASS or FAIL, files changed, test counts
```

## 5. Do not build
Hosted service, multi-channel support, an LLM call in the engine, slow mode, polls, predictions, channel points, a frontend framework, user accounts, or any new dependency without asking.

## 6. Milestones
| Milestone | Steps | Meaning |
|---|---|---|
| M1 Engine proven live | R1 | Real events reach the database |
| M2 Agent link proven | R2 | An agent runs `crew` from the room |
| M3 Incident path | R3 to R6 | Simulated burst becomes one approval, approved safely |
| M4 Demo ready | R7 | Workflow A runs in the room |
| M5 Wow moment | R8 | Plain-English rule shipped |
| M6 Submitted | R10 | Video, repo, description sent |
