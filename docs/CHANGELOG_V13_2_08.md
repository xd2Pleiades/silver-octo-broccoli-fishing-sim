# Fishing Simulator v13.2.08 — Phase A content and radio balance

Date: 2026-10-22

## Added

- Expanded deterministic Phase A traffic from 23 to 40 vessels using explicit archetype counts.
- Added `AmbientShipRadioDirector` for occasional overheard peer, corporate, safety/weather, routine, distant traffic, and dockside gossip conversations.
- Added deterministic scheduled radio slots, global/per-source cooldowns, no-backlog handling for busy/unmanned radio, seasonal and daypart weighting, weather/signal weighting, and persistence snapshot support.
- Added direct ship-radio per-vessel/per-topic cooldowns: 45 in-game minutes (18.75 simulation seconds at 600 simulation seconds per game day). Different topics remain available.
- Added daypart/archetype reply adjustment and a modest in-season bonus for corporate/mothership traffic.
- Persisted direct radio topic cooldown state in career saves while allowing older saves to omit the new optional field.
- Enabled treaty-edge ambient radio only when a Soviet vessel is near 45°N and another vessel is in mutually compatible radio range.
- Added observable, non-spoiling Notebook hints after first successful radio contacts.

## Optimization and balance notes

- 40 scheduled vessels; no expansion to the full ~461 source-plan fleet yet.
- Ambient traffic updates on fixed simulation slots, never per render frame.
- Traffic benchmark (local build host): mean update 0.0935 ms, radio candidate query 42.68 µs, generation 0.920 ms.
- Weather grid benchmark: mean tick 2.891 ms, median 2.8122 ms, p95 3.2291 ms, 72-hour forecast 1.0103 seconds, snapshot JSON 52,948 bytes. The 2 ms tick target is not met.

## Validation

- Focused suite: 164 tests run, 149 passed, 15 skipped (Pygame runtime dependencies unavailable).
- `compileall` passed.
- No live Pygame graphical playtest was possible.
- All Markdown is directly under `/docs`; local Markdown link audit passed.

## Deferred

- Full ambient template catalog, relationship decay/gossip propagation, complete Phase A playtest/balance, Phase B map/fleet expansion, weather tick optimization, and full graphical regression.
