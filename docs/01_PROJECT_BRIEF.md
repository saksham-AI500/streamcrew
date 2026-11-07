# 01 Project Brief

## Name
**StreamCrew**. Hackathon concept: **Stream Incident Room**.

## Event
Flip the Switch Hackathon (WeMakeDevs x DevTools Academy). Online, 4 to 7 Nov 2026. Solo or team of up to 4. The brief: take an AI agent you already use, connect it to a chat app with Switch, and build a workflow where it gets real work done with teammates.
The Codex x TwitchCon submission was dropped. Layer 1 code is reused.
**Open item:** the Switch rules page has not been read. Check the judging criteria, the exact cut-off time, and whether work started before 4 Nov counts. Record the answers in `NOTES.md`.

## One-line pitch
When a stream is hit by a spam raid or a big raid arrives, a small crew (streamer, moderator, AI agents) handles it together in a Switch room, and no risky action runs without a human "approve".

## Problem
Streamers get spam and hate raids. Bots post the same text faster than a moderator can ban account by account. Built-in Twitch tools are blunt. Most streamers cannot write automations. Good raids and highlights are missed because the streamer is busy.

## Users
| User | Need |
|---|---|
| Streamer | Safe automation without coding. Stay in control. |
| Moderator | One decision per incident instead of one per account. |
| Editor (optional) | Recap and highlight timestamps after the stream. |
| AI agents | Read the log, propose rules, run `crew` commands on a human's word. |

## Core features (priority order)
1. Spam burst detector that creates one grouped approval item. **TO BUILD**
2. Approval queue with approve and reject, logged. **BUILT**, grouping **TO BUILD**
3. Plain-English rule creation: agent drafts, `crew validate`, `crew test`, human says "ship it". CLI **BUILT**, ship step **TO BUILD**
4. Raid welcome: shoutout, announcement, marker, with cooldown. **BUILT (mock-tested), LIVE-UNPROVEN**
5. Highlight marker from chat-rate spikes. **BUILT (synthetic-tested), LIVE-UNPROVEN**
6. Overlay showing events and pending approvals. **BUILT (fixtures only)**
7. Simulation command that replays a fixture burst through the real detector. **TO BUILD**

## How Switch is used
Room `stream-ops`. Roles: `producer` (agent `crew-producer`) and `moderator` (agent `crew-mod`). The agents run the `crew` CLI in this repo. They never hold the Twitch token.

## Scope
**In:** local engine, CLI, local API, overlay, Switch room workflows A and B, demo, README.
**Out:** hosted service, multi-channel support, any LLM call inside the engine, slow mode or shield mode (scope not granted), polls, predictions, channel points, ads, mobile app, user accounts.

## Success criteria
- Workflow A runs end to end in the Switch room in under 3 minutes: incident, `@crew-mod what's pending?`, `approve <id>`, result posted.
- Zero risky actions run without a human approval.
- Workflow B produces a validated and tested rule from one sentence.
- `pytest` passes. No secret in git or in `NOTES.md`.
- A recorded fallback video exists.

## Current state
| Area | Status |
|---|---|
| Token, scopes, refresh helper | BUILT |
| EventSub client (dedupe, reconnect, 5 s keepalive grace) | BUILT, mock plus short live probe |
| Six subscription types | Chat types proven on real Twitch. Others created OK on real Twitch, no live events seen |
| Rule engine, modes, cooldowns | BUILT |
| Actions (six) | BUILT, mocked, no live action run |
| Highlight detector | BUILT, synthetic traces |
| Approval queue and CLI | BUILT |
| Local API and overlay | BUILT, fixtures only |
| Spam detector, grouped approval, simulate, ship step | TO BUILD |
| Switch install and agent link | NOT STARTED |

## Constraints
- Free tools only where possible. No paid LLM key in the engine.
- Token scopes granted: `user:read:chat`, `user:write:chat`, `user:bot`, `channel:bot`, `moderator:read:followers`, `channel:read:subscriptions`, `channel:manage:broadcast`, `moderator:manage:announcements`, `moderator:manage:shoutouts`, `moderator:manage:banned_users`, `moderator:manage:chat_messages`, `bits:read`, `channel:read:ads`. Anything else needs re-authorization by the human.
- Laptop: Ubuntu, 12 GB RAM. Switch runs a Mattermost server in Docker, so keep other processes light.
- Agents available: Codex, OpenCode, Antigravity. Each must be tested in Switch Console before it is relied on.
