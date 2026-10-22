# V13V1-08 — Timed Broadcast Conversations

## Summary

This release prioritizes the supplied **Broadcast Conversations — Catalogue** over the previously scheduled position-fixing milestone. Navigation fixes are deferred to `v13v1-09` so the game can build out attributed, timed, priority-aware conversations first.

## Implemented

- Added a `BroadcastDirector` for attributed multi-turn conversations with channel, source, priority, and per-turn delay.
- Added priority-based interruptions and a priority-sorted pending queue. Critical Mayday traffic, man-overboard rescue, high-priority weather warnings, and serious engine alerts can cut through routine chatter.
- Extended radio/ambient traffic with ship-to-ship position, catch, and weather exchanges; market/weather/navigation/fleet/news-style broadcasts; CQ-style traffic; race/trade exchanges; harbour arrival/gossip; and rare Mayday/Pan-pan conversation scripts.
- Added sparse deck/intercom/crew exchanges around hauling, engine work, weather, and harbour state.
- Routed delivered turns through existing crew speech and radio-log paths so conversation lines are recorded individually with in-game timestamps.
- Preserved the existing F2 weather request, F3 market request, and F4 tow request mechanics. Dialogues complement those actions; they do not replace them.
- Limited routine traffic while another interaction is busy or radio is unstaffed. Harbour gossip is capped per docking visit. Mayday and Pan-pan rolls are once per session at 5% and 10%, respectively.
- Preserved the user-supplied `docs/Broadcast Conversations - Catalogue.md` as the design reference.

## Deliberately deferred

- Player-selected replies to distress calls are not included; the supplied catalogue marks branching replies as a future phase.
- A guaranteed time-signal broadcast exactly every game hour, a fully simulated fleet of other vessels, and all listed event scripts are not claimed as complete. Several content types are represented in the sparse ambient pool, and further triggers can be added incrementally.
- Navigation position fixes from the previous roadmap are rescheduled as `v13v1-09`.

## Verification

- **194 automated tests passed** (`python -m unittest discover -s fishing_sim/tests -v`).
- Python compilation passed (`python -m compileall -q fishing_sim run_fishing_sim.py`).
- Final ZIP integrity, the launcher and preservation marker, and inclusion of the supplied catalogue/roadmap/changelog were verified. The suite was rerun from a fresh extraction of the archive: 194 tests passed.
- No live Pygame graphical playtest was possible because Pygame is unavailable in the build environment. Test speech-bubble legibility, conversation dwell time, radio priority behavior, and ambience frequency in a Windows playthrough.
