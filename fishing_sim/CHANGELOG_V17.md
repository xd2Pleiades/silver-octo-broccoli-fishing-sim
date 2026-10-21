# 12v17 — Visual Scale, Sea Foam, and Information HUD

## Changes
- Resized/redesigned the rescue boat as a long, wider person-sized dinghy with an inner deck, gunwales, thwarts, two represented rescuers, a passenger/casualty position, paddles, and life-vest accents. Rescue state/timing and gameplay collision geometry are unchanged.
- Made bucket-line pails visibly larger and more recognizable, with a wooden tapered body, strong rim/handle, and water surface; reusable bucket inventory and work logic are unchanged.
- Reworked sea rendering around the ship with bow-shoulder foam, side ribbons, stern wake streaks and bounded animated flecks. Foam density/length responds to speed and sea state; rough-water crest flecks remain visible at lower speed.
- Replaced the always-on detail panel with a two-line, critical-only HUD. It shows speed/heading and sea/weather by default; F7 switches to operations status and urgent alerts; F8 hides/restores the HUD.
- F1 now opens a unified information sheet with **Ship & Catch**, **Telemetry**, and **Crew** tabs. Existing Aboard/Shore/Hire management tabs remain nested under Crew; hiring, recall, keep-ashore, and wait-until-rested restrictions remain intact.
- The F1 sheet consumes clicks so they cannot issue world orders. It pauses ordinary simulation while open, while explicit shore-recovery waiting can continue advancing.
- Adjusted the fishing tension/gaff controls to fit between the HUD and minimap. On narrow windows, the minimap is briefly suppressed while an active fishing minigame needs that screen space.
- Preserved `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`.

## Verification
- 75 automated tests passed after the 12v17 refactor.
- Python syntax compilation passed.
- Graphical playtest was not possible because Pygame is not installed in the build environment. Check actual visual scale/foam and small-window layout manually.

## Known limitations
- Boat occupants are rendered as stylized Pygame shapes, not animated seated character rigs.
- Foam uses a fixed bounded count of animated shapes/ribbons rather than a persisted particle pool, to avoid unbounded memory growth.
- Small-screen fishing temporarily hides the minimap only while a tension or gaffing interaction is active.
