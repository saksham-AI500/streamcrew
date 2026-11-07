# 04 UI/UX Specification

There are three surfaces. The **Switch room is the primary UI**. Everything else is supporting.

| Surface | Purpose | Status |
|---|---|---|
| Switch room (`stream-ops`) | Where humans and agents work the incident | TO BUILD |
| OBS overlay `/overlay` | What viewers and the streamer see on stream | BUILT (fixtures only) |
| Dashboard `/dashboard` | Optional control room. **Paused.** Do not build until Switch workflows work | OUT OF SCOPE for now |

No Figma file exists. Reference screenshots go in `design/screenshots/`.

## 1. Switch room: conversation design
Principles: short messages, IDs always visible, one clear next action, never act without a human word.

**Pending list (reply from `crew-mod`)**
```
Pending (1)
#7  spam burst  14 accounts  same text x31 in 10 s
Proposed: timeout 10 min for 14 accounts (needs your approval)
Reply: approve 7  |  reject 7  |  details 7
```
**After approve**
```
#7 done. 14 timed out, 0 failed. Logged at 14:22 by Sam.
```
**Partial failure**
```
#7 done with errors. 12 timed out, 2 failed (already banned). Details: details 7
```
**Rule draft (reply from `crew-producer`)**
```
Draft rule "raid-welcome" (not active)
When: channel.raid, viewers >= 20
Do: shoutout, marker
Mode: auto   Cooldown: 120 s
Validate: OK   Dry-run on fixture: OK
Say "ship it" to activate, or tell me what to change.
```
**Refusal pattern**
```
I can't do that without your approval. Reply "approve 7" to run it.
```
Room instructions (read by every agent): stream context, the approval rule, "dry-run is on", "never print chat text in full", "only run `crew` commands".

## 2. Overlay (OBS Browser Source, 1280x720)
- Transparent page background. Semi-transparent dark panels (`rgba(18,24,38,0.85)`, 1 px border).
- No scrolling. Must fit exactly 1280x720.
- Top-left: wordmark and a connection pill (text label plus colour: "Live" / "API offline").
- Left panel: last 10 events, newest first. Each row: type (monospace), time `HH:MM:SS`, short detail, ellipsis if long.
- Right panel: pending approvals count and the first 3 items (ID, action, status).
- Bottom-right: last successful update time.
- Poll `/events?limit=10` and `/approvals?status=pending` every 2 s. 1.5 s timeout. Skip a poll if the last one is still running.
- API unreachable: show "API offline, retrying" in the danger colour. Never blank the screen.
- Never show chat text in full on stream. Show the type and a redacted sample.

## 3. Design system
| Token | Value |
|---|---|
| Background | `#0b0f17` |
| Surface | `#121826` |
| Raised surface | `#171f30` |
| Border | `#1f2a3d` (1 px) |
| Text | `#e6edf7` |
| Muted text | `#8b97ab` |
| Accent | `#2dd4bf` |
| Success | `#34d399` |
| Warning (approve mode) | `#fbbf24` |
| Danger | `#f87171` |
| Dry-run grey | `#64748b` |

- Spacing on a 4 px scale. Card radius 12 px. Soft shadow only.
- Fonts: system stack only (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`). Monospace for IDs, times, logs.
- Sizes: overlay body 22 px or larger. Headings 28 px or larger.
- Components: status pill, chip, event row, approval card, toast, skeleton loader, empty state with a one-line hint.

## 4. Motion
- 150 to 200 ms transitions only. No looping animation except one gentle pulse on a pending-approval pill.
- Respect `prefers-reduced-motion`.

## 5. Accessibility
- Never convey status by colour alone. Always add a text label.
- Real `<button>` elements. Visible focus ring (2 px accent). Text contrast at least WCAG AA.
- Modals trap focus and close on Escape.

## 6. Hard constraints for any static page
- Plain HTML, CSS, and vanilla JS. No framework, no build step.
- No external resources: no CDN, no web fonts, no remote images, no `https://` URLs.
- Render API data with `textContent` only. Never `innerHTML` with API data.
- No `localStorage`, `sessionStorage`, cookies, or service workers.
- Never embed the local API token. A token field, if added, holds the value in memory only.
- A `?demo=1` mode may show sample data with a visible "DEMO DATA" banner. It is off by default.
