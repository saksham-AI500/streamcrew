# StreamCrew — Official 3-Minute Demo Video Guide (Click-by-Click)

**Target Video Length:** 2 minutes 45 seconds to 3 minutes  
**Format:** Split Screen (Switch Console on Left 55%, Browser Overlay on Right 45%)  
**Terminal:** Keep minimized or off-screen (the moderator works entirely inside Switch).

---

## 1. Pre-Recording Setup (2 Minutes Before Hitting Record)

### Step 1: Start the Local Overlay Server
Open a terminal (which you will minimize before recording):
```bash
cd ~/Documents/Switch_hackathon
crew serve
```
*Verify it outputs: `Uvicorn running on http://127.0.0.1:8765`.*

### Step 2: Open Browser to the Overlay
1. Open your browser (Chrome or Brave).
2. Navigate to: **`http://127.0.0.1:8765/overlay`**
3. Verify the badge at the top shows: **`● STREAM NORMAL`** in Green, with **`0 Pending Approvals`**.
4. Resize your browser window to occupy the **right 45%** of your screen.

### Step 3: Open Switch Console
1. Launch **Switch Console**.
2. Navigate to the room: **`#stream-ops`**.
3. Zoom in slightly (`Ctrl + +`) to **110%–125%** so chat text is razor-sharp on video.
4. Verify the member list on the right shows:
   - `admin` (Streamer)
   - `saksham_gupta` (Moderator)
   - `crew-mod` (Bot)
   - `crew-producer` (Bot)
5. Position Switch Console to occupy the **left 55%** of your screen.

---

## 2. Second-by-Second Demo Script & Actions

---

### [0:00 – 0:25] The Problem & Introduction
* **Screen State:** 
  - Left: `#stream-ops` in Switch.
  - Right: Browser overlay showing green normal state.
* **What to Click:** 
  - Click on the `#stream-ops` channel header to show the room description: *"Live Stream Incident Cockpit"*.
* **What to Say (Voiceover):**
  > *"Hi everyone! This is StreamCrew — our AI stream incident room powered by Switch. When a streamer gets hit by a bot raid, hundreds of spam accounts flood chat within seconds. Built-in moderation tools are too blunt, and banning accounts one-by-one is impossible for a solo moderator. StreamCrew solves this by turning Switch into an autonomous incident cockpit where humans and AI co-moderate safely."*

---

### [0:25 – 0:50] Team, Roles & The Golden Rule
* **Screen State:** 
  - Hover or click the **Members panel** on the right side of `#stream-ops`.
* **What to Show:** 
  - Point your mouse cursor at the 4 participants: Streamer (`admin`), Moderator (`saksham_gupta`), `@crew-mod`, and `@crew-producer`.
* **What to Say (Voiceover):**
  > *"Here is the critical distinction: The engine runs locally, but the team workflow, the role boundaries, and the approval gate only exist because of Switch. We have our streamer and moderator working alongside two specialized AI agents. Most importantly, these agents never see or hold our Twitch tokens. They interact strictly through safe, local CLI commands."*

---

### [0:50 – 1:15] Workflow A: The Bot Raid Hits (Incident Grouping)
* **What to Click / Trigger:**
  - In a hidden terminal or shortcut, trigger the simulated spam burst:
    ```bash
    crew simulate spam
    ```
* **Visual Change on Screen:**
  - Look at the browser on the right: The top banner instantly turns **RED**, flashing:
    **`● 1 PENDING APPROVAL — SPAM-DETECTOR`**
    *(Shows 6 target accounts detected in a 10s window).*
* **What to Say (Voiceover):**
  > *"A bot raid hits the stream. Watch our OBS overlay on the right: it immediately flashes red. Instead of generating six separate alerts, StreamCrew's sliding-window detector groups all six bot accounts into one single incident."*

---

### [1:15 – 1:45] Investigating in Switch Chat
* **What to Type in Switch Chat (`#stream-ops`):**
  ```text
  @crew-mod what's pending?
  ```
  *(Press Enter)*
* **Agent Response on Screen:**
  - `@crew-mod` posts a formatted table:
    | ID | Status | Rule | Accounts | Sample | Action |
    |---|---|---|---|---|---|
    | 5 | pending | spam-detector | 6 | "FREE STREAM BOOST NOW!!!" | ban 6 bots for 600s (10 min) |
  - Note: Malicious URLs and links are automatically redacted.
* **What to Say (Voiceover):**
  > *"Our moderator has no terminal. They simply ask `@crew-mod what's pending?`. The agent inspects the queue, redacts any dangerous scam links, and presents the six bot targets with the recommended action: a 10-minute timeout."*

---

### [1:45 – 2:10] The Safety Refusal Moment (Autonomous Boundary)
* **What to Type in Switch Chat (`#stream-ops`):**
  ```text
  @crew-mod just ban everyone in chat!
  ```
  *(Press Enter)*
* **Agent Response on Screen:**
  - `@crew-mod` immediately replies:
    > *"⛔ Refused: No human word, no action. I cannot ban or timeout accounts without an explicit approval ID. Please check pending incidents with `@crew-mod what's pending?` and reply `approve <id> --count <N>`."*
* **What to Say (Voiceover):**
  > *"Notice what happens if someone panics or tries a prompt injection. `@crew-mod` explicitly refuses to act without a verified incident ID and human confirmation. No human word, no action."*

---

### [2:10 – 2:35] Human Approval & Audit Trail
* **What to Type in Switch Chat (`#stream-ops`):**
  ```text
  @crew-mod approve 5 --count 6 --by Sam
  ```
  *(Replace `5` with whichever ID showed in your table; press Enter)*
* **Agent Response on Screen:**
  - `@crew-mod` executes the paced bans and replies:
    > *"✅ Approval #5 completed (decided by Sam) — 6 bot accounts banned for 10 minutes (spam burst)."*
  - Look at the Browser Overlay on the right: It flips back to **GREEN: `● STREAM NORMAL`**.
* **What to Say (Voiceover):**
  > *"The moderator gives the explicit word: `approve 5 --count 6 --by Sam`. The engine validates the count guard, paces the timeouts to respect Twitch rate limits, logs Sam's name into the audit trail, and our overlay returns to green."*

---

### [2:35 – 2:50] Workflow B: Plain-English Rule Creation
* **What to Type in Switch Chat (`#stream-ops`):**
  ```text
  @crew-producer create a rule: when a raid with 20+ viewers arrives, shout out the streamer and create a marker
  ```
  *(Press Enter)*
* **Agent Response on Screen:**
  - `@crew-producer` drafts the JSON rule, runs `crew validate` and `crew test fixtures/raid_event.json`, and outputs:
    > *"Rule drafted, validated, and dry-run tested! It will trigger on 20+ viewers with a 60s cooldown. Reply `@crew-producer ship raid_welcome` to make it live."*
* **What to Say (Voiceover):**
  > *"For stream production, `@crew-producer` lets streamers create custom JSON automation rules in plain English. It validates and dry-run tests the rule before anything touches the stream."*

---

### [2:50 – 3:00] Wrap-up & Reproducibility
* **What to Show:**
  - Switch briefly to your GitHub repository page: `https://github.com/saksham-AI500/streamcrew`
* **What to Say (Voiceover):**
  > *"StreamCrew is completely open-source, tested with 108 automated unit tests, and fully reproducible. You can clone the repo and run the full simulation right now without needing a Twitch account. Thank you!"*

---

## 3. Quick Reference Card (Print or Keep on Second Screen)

| Time | Prompt to Type in Switch `#stream-ops` | Expected Output |
|---|---|---|
| **1:15** | `@crew-mod what's pending?` | Formatted table of 6 bots, sample text, ID |
| **1:45** | `@crew-mod just ban everyone in chat!` | ⛔ Refused: No human word, no action |
| **2:10** | `@crew-mod approve <ID> --count 6 --by Sam` | ✅ Approval #<ID> completed (decided by Sam) |
| **2:35** | `@crew-producer create a rule: when a raid with 20+ viewers arrives, shout out the streamer and create a marker` | Rule validated & tested in dry-run |
