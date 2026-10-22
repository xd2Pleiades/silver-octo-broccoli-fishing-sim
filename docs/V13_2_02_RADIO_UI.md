# v13.2.02 — Selectable Fleet Radio UI

**Status:** Implemented in source; headless regression tested; graphical playtest still required.
**Depends on:** v13.2.01 traffic world and `ShipRadioService`; existing radio operator, Radio Log, and Notebook systems.

## Player experience

- Click the new **RADIO** HUD button immediately left of **ANCHOR**, or press **Ctrl+F11**.
- The radio opens as a wheelhouse-style modal. The left rail lists nearby scheduled ships, their approximate distance, current activity, and whether each vessel is within its own configured radio range.
- Select a ship, then choose **Hail**, **Position**, **Weather**, **Activity**, **Grounds**, **Crew**, or **Identify**.
- Conversations are staged. The transmit appears first; use **NEXT LINE**, Enter, or Space to reveal each reply in sequence. When the exchange is exhausted, **NEXT SHIP** advances to another contact. `Tab` and the arrow keys also change selection.
- Each ship has a separate bounded local transcript history. Switching to another ship does not erase the first conversation; returning to the contact restores its visible history.
- Radio attempts require a working watch at the physical set. Out-of-range calls, occupied frequencies, weak reception, and silence are described in the panel rather than silently converting into successful contact.

## Input reference

| Input | Action |
|---|---|
| Click **RADIO** / `Ctrl+F11` | Open or close fleet radio panel |
| Click a vessel row | Select a contact |
| Click a topic | Transmit that question/call |
| **NEXT LINE**, Enter, Space | Reveal the next staged line |
| **NEXT SHIP**, Tab, Down | Select next contact |
| Up | Select previous contact |
| Mouse wheel | Scroll vessel list |
| `1`–`7` | Hail, position, weather, activity, grounds, crew, identify |
| Escape, Backspace, right-click | Close radio panel |

`F11` remains fullscreen and is not rebound. Radio UI input is modal, so it does not issue deck orders or alter helm/duty assignments by accident. Held gameplay keys are suppressed while the panel is open.

## Information and simulation rules

- The contact list is built from the spatial index within 55 nm; each row is independently marked in/out of that vessel's radio range.
- The panel displays the selected ship's activity and callsign from the currently sampled world state. It does not expose that ship's exact position as a chart report.
- Position questions create/refresh a separate approximate reported fix. The chart still consumes last-reported position rather than live position.
- Corporate ships decline fishing-ground questions; cooperative/gossip peers provide cautious reports; low-trust competitive peers can be misleading. Weather and safety remain broadly shareable.
- Reply chances depend on range, clarity, and sea state. A valid unanswered call produces a static/no-reply line; it doesn't lock the UI.
- The UI logs each revealed TX/RX turn to the existing Ship's Notebook Radio Log. Conversation history is bounded to 100 lines per contact in the open UI session.

## Scope boundary

This is a selectable interaction UI over the v13.2.01 coarse/warm/active traffic foundation. It is **not yet** the complete v13.2 radio dispatcher: ambient overheard corporate traffic, cross-session save migration for contact/trust state, full priority preemption, incoming AI MAYDAY assistance, and unified tow-escort identity remain later milestones.
