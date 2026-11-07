# 02 Product Requirements (PRD)

## 1. Problems and solutions
| # | Problem | Solution | Priority |
|---|---|---|---|
| P1 | Spam or hate raid: same text from many new accounts | Spam detector creates one grouped approval item | Must |
| P2 | Moderator overload | One decision per burst, capped, paced, logged | Must |
| P3 | Raid welcome missed | Rule on `channel.raid`: shoutout, announcement, marker, cooldown | Must |
| P4 | Streamers cannot code bots | Plain-English rule drafted by an agent, validated, tested, shipped on "ship it" | Must |
| P5 | Highlights lost | Chat-rate detector adds a stream marker | Should |
| P6 | Post-stream chores | Recap from the event log | Could |

Design rule: the **runtime is deterministic** (detectors, rules). AI agents only converse and propose. They never act alone.

## 2. Personas
- **Streamer (owner).** Owns the channel and the token. Final say.
- **Moderator.** Approves or rejects incidents.
- **Editor.** Reads the recap. Optional.
- **crew-producer (agent).** Drafts rules, summarises. Cannot approve.
- **crew-mod (agent).** Reports the queue and runs approve or reject **only** after a human's explicit word.

## 3. User stories and acceptance criteria
**US-1 Detect a spam burst**
Given at least 5 distinct accounts post the same normalised text within 10 seconds (defaults, tunable), when the detector runs, then exactly one pending approval is created listing at most 25 accounts, and no Twitch call is made.

**US-2 Approve from the room**
Given a pending item #7, when a human replies `approve 7` in the room, then `crew-mod` runs `crew approve 7`, each account is actioned at most once, the row becomes `done` (or `failed` with a reason), and the result is posted in the room.

**US-3 Reject**
Given a pending item, when a human replies `reject 7`, then the row becomes `rejected` and no Twitch call is made.

**US-4 Plain-English rule**
Given the sentence "when a raid brings 20+ viewers, shout them out and drop a marker", when the streamer asks `@crew-producer`, then the agent writes a draft rule, `crew validate` passes, `crew test` prints a dry-run result, the diff is posted, and the rule is **not active** until a human replies "ship it".

**US-5 Raid welcome**
Given a `channel.raid` event with at least the configured viewer count, when the rule runs in `auto` mode, then a shoutout, an announcement, and a marker are produced, and a second raid inside the cooldown does nothing.

**US-6 Highlight marker**
Given a chat-rate spike above the floor, when it fires, then one marker is created and no second marker appears for 60 seconds.

**US-7 Visibility**
Given the overlay is open, when events arrive or approvals are pending, then both appear within 2 seconds. If the API is down, the overlay says so and keeps retrying.

**US-8 Safety**
Given `DRY_RUN=true`, when any action is requested, then no Twitch write call is made and a "would do" line is logged.

## 4. Workflows
**A. Spam incident (core demo)**
1. Chat spikes. The spam detector creates a pending approval.
2. Human: `@crew-mod what's pending?`
3. `crew-mod` lists ID, account count, sample text (redacted), and the proposed action.
4. Human: `approve 7`.
5. `crew-mod` runs `crew approve 7` and posts the result.
6. Room history shows the incident and the decision.

**B. Plain-English rule (wow moment)**
1. Streamer states the rule to `@crew-producer`.
2. Agent drafts it, runs `crew validate` and `crew test`, posts diff and dry-run result.
3. Human: `ship it`. Agent runs `crew rules ship <name>`.

**C. Recap (optional)**
After `stream.offline`, `@crew-producer` summarises markers and top moments from `crew events`.

## 5. Scope limits
- One channel, one machine, one operator group.
- No slow mode or shield mode (scope `moderator:manage:chat_settings` not granted).
- Affiliate or Partner features (polls, predictions, channel points, ad controls) are not relied on.
- The demo may use a **simulated** burst. The detector and queue are the real code path, and the demo must say so.

## 6. Success metrics
- Incident to decision in under 30 seconds in the demo.
- 0 unapproved risky actions.
- 100% of mutating CLI commands logged.
- Full test suite green. No secret in git.

## 7. Risks and assumptions
| Risk | Mitigation |
|---|---|
| Switch install is heavy on 12 GB RAM | Smoke test early. Close other apps. |
| An agent does not connect | Test each agent. Fall back to another from the list. |
| No real hate raid at demo time | `crew simulate spam`, said clearly |
| Agents see chat text (sent to an AI provider) | Redact chat text in `crew events` by default |
| Switch rules forbid reused code | Read the rules. Declare Layer 1 as pre-existing. |

## 8. Open questions
1. Switch judging criteria and cut-off time.
2. Does the engine re-read rule files on every event, or only at start? (Decides how "ship it" takes effect.)
3. Is an Antigravity-to-Switch connection supported? Test before relying on it.
