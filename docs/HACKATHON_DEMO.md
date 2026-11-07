# StreamCrew hackathon demo and release checklist

## Layer 1: Codex x TwitchCon

The submission period is Oct 23–Nov 2, 2026. The official rules require a
working Twitch-connected project, a repository URL, a description of the
features and Codex use, the Codex session ID, and a public YouTube demo video
under three minutes. See the [official rules](https://twitchcon-codex.devpost.com/rules).

### Reproducible local demo

1. Show the problem: a streamer is busy running the show while stream events
   and chat activity need attention.
2. Run `.venv/bin/crew test fixtures/raid_event.json`. State plainly that this
   is a **synthetic fixture**. Show the rule match and planned shoutout; it is
   dry-run output and does not send a Twitch action.
3. Run `.venv/bin/crew serve`, open `http://127.0.0.1:8765/overlay`, and show
   the local event timeline, marker summary, and pending approval summary.
4. Explain that full event and approval details require the local API token,
   and that the overlay receives summaries only.
5. If a real chat event has been verified by then, show its stored event type
   and ID without exposing message text. Otherwise, keep the demo explicitly
   labeled as local simulation and do not claim live chat verification.
6. Explain the human approval gate and show a mocked or dry-run decision path.
   Do not execute a real Twitch action in the demo without separate approval.

### Locally verified on 2026-10-27

- The test suite passes (84 passed, 1 Starlette/httpx warning).
- A temporary `crew serve` process returned 200 from `/health`,
  `/overlay/events`, `/overlay/approvals`, and `/overlay`; full-data routes
  returned 401 without the local token, and storage failures return 503.
- Headless Chrome rendered the overlay as connected, showed the stored event
  summaries, and showed the correct empty marker/approval messages. A failed
  API refresh was also rendered: stale rows were cleared and every panel showed
  the unavailable state.
- Cooldown, authentication-close, configuration, CLI diagnostics, and overlay
  state regressions are covered by automated tests.
- This does not verify a real Twitch chat event, a live channel action, a clean
  clone, or any Switch integration. The A2 live-chat check is still pending.

### Live chat verification procedure (listener restarted; chat pending)

This is the minimum real-Twitch check; it requires no channel write. It is
pending because the currently running listener predates the latest code.

1. **Done on 2026-10-27.** With explicit authorization the old listener was
   replaced by PID 74598 running the current code. It connected and created all
   six subscriptions, including `channel.chat.message`.
2. Have a human send one ordinary chat message from another account. Do not
   infer that it was sent until the human confirms it.
3. Inspect metadata only:
   `.venv/bin/crew events --limit 5 --metadata-only`. It prints `message_id`,
   `message_type`, `subscription_type`, and `received_at` but omits payloads and
   chat bodies.
4. Confirm no unexpected approval or external action was created. Record the
   result in `NOTES.md`; if no row appears, record the failure honestly.

### Submission checklist

- [ ] Verify a clean clone installs and starts on Ubuntu.
- [ ] Verify one real Twitch EventSub chat event is stored, if the streamer is
      available; identify the live run separately from historical fixtures.
- [ ] Record a video under three minutes showing the project running and how
      Codex was used. Upload it publicly to YouTube and avoid unlicensed music
      or other copyrighted material.
- [ ] Include the public GitHub repository URL and an accurate feature/limits
      description.
- [ ] Retrieve the Codex session ID for the thread where the project was built.
- [ ] Submit the entry on Devpost before Nov 2, 2026 at 2:00 PM Pacific Time
      (Nov 3 at 3:30 AM IST).

Do not claim the Switch integration is complete in this Layer 1 demo. The Flip
the Switch event runs Nov 4–7, and its official page says the Switch setup and
workflow must be built during that event. The implementation should start after
Nov 4 and be demonstrated separately. See the [official Flip the Switch
page](https://www.wemakedevs.org/hackathons/switch).

