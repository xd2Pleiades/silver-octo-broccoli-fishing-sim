# V13V1-13 — One-button manual line setting

## Gameplay

- Press **P** to start one manual longline set while **L** auto-fishing remains disabled.
- The vessel begins a slow straight setting run; available deckhands self-assign to the stern roller and move into position. The existing line state machine continues through the one set, soak, and following haul, then stops rather than starting another cycle.
- The captain's chosen bait and line depth are preserved. A committed chart route is cancelled for the uninterrupted setting run and that cancellation is recorded in the crew log.
- The command is refused when auto-fishing is enabled, a line operation is already active, the vessel is too near the harbour, or docking/rescue has priority.

## Controls

- **P** — Manual set: pay out one line while the vessel proceeds on the setting run.
- **L** — Auto-fishing: keep the existing autonomous fishing cycle enabled/disabled.
- **J** — End soaking early and begin hauling, when the line is soaking.

## Verification

- Python compilation passed.
- **259 automated tests passed, 0 failed**.
- Pygame is unavailable in this build environment. Verify in a graphical run that deckhands walk to the stern roller, the ship gets underway during payout, and the one-shot set/soak/haul cycle ends with auto-fishing still off.
