# v13.2.02 Implementation Status

**Release type:** selectable fleet radio UI built on v13.2.01 traffic foundation, preserving the v13.1.34 merged game and Coast Guard towing.
**Design sources:** [`Plan 13.2.xx.md`](Plan%2013.2.xx.md), [`Roadmap_V13_2_Optimized.md`](Roadmap_V13_2_Optimized.md), [`V13_2_02_RADIO_UI.md`](V13_2_02_RADIO_UI.md).

## Implemented

- Clickable **RADIO** HUD card directly next to **ANCHOR**, plus `Ctrl+F11` shortcut. Plain `F11` remains fullscreen.
- Modal wheelhouse-style radio UI with a distance-sorted nearby vessel list, vessel type/activity, signal range status, and per-vessel selection.
- Clickable topics: hail, position, weather, activity, fishing grounds, crew, and vessel identification; keyboard shortcuts `1`–`7` are available while the UI is open.
- Multi-turn response playback: transmit first, then reveal replies with **NEXT LINE**, Enter, or Space; **NEXT SHIP**, Tab, and the arrow keys allow moving between contacts.
- Per-vessel bounded transcript history during the current session; Radio Log entries are written as lines are revealed.
- Topic-specific radio content, out-of-range/silence outcomes, staffed-radio gating, and channel-busy feedback.
- Position answers return reported plot data and keep it separate from live physical state. Corporate vessels decline grounds questions; peer behavior varies by personality/trust.
- Modal input handling prevents UI clicks and held movement keys from leaking into deck/helm orders.
- Version `13.2.02`, release notes, updated controls, roadmap status, and dependency-free tests.

## Deferred

- Full 461-vessel Phase B fleet, warm/active collision avoidance, weather-grid persistence, background ambient/overheard traffic, complete priority interruption/MAYDAY dispatcher, incoming AI distress/rescue, persistent relationships integrated into career save/load, and unified Coast Guard/tow identity.
- Pygame live playtest; Pygame is unavailable in this build environment.

## Verification scope

The release includes focused tests for the selectable UI contract, topic-specific exchanges, position report separation, corporate refusal, out-of-range behavior, current version, prior traffic foundation, crew-trip and Coast Guard escort regressions. These can be run with:

```bash
python -m unittest fishing_sim.tests.test_v13_2_02_radio_ui fishing_sim.tests.test_v13_2_01_world_foundation fishing_sim.tests.test_v13_1_34_merge_contracts fishing_sim.tests.test_v13_1_33_tow_placeholder_ship fishing_sim.tests.test_v13_1_30_tow_persistence -v
```
