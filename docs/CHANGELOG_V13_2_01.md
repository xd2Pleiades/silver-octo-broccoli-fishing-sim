# Changelog — v13.2.01

## First roadmap implementation slice

- Added `fishing_sim/world/` with stable seeding, coordinate projection, sparse 20-NM spatial indexing, active/warm/coarse LOD, deterministic scheduled traffic, and versioned contact persistence helpers.
- Added `fishing_sim/systems/ship_radio.py` for radio-range gating, seeded response uncertainty, separated corporate refusal vs. competitive misdirection, official safety/weather replies, and multi-turn routine exchanges.
- Integrated a seeded 23-vessel Phase A pool into the live game loop. Traffic state is sampled on a fixed simulation-time tick; rendering does not independently advance vessels.
- Drew local active vessels as small ship silhouettes (limited by current weather visibility) and exposed known vessel plots on the chart from last-reported positions, with stale-contact markers. Chart rendering uses a sparse set of known contacts and safely handles unknown-age restored reports.
- Added `Ctrl+F11` to broadcast a routine fleet hail; retained plain `F11` for fullscreen. Radio must be staffed and not occupied. A silent nearer listener no longer blocks a farther listener from answering.
- Optimized chart contact rendering to iterate only the sparse known-contact collection.
- Preserved existing v13.1.34 crew, trip-order, rescue, navigation, and Coast Guard tow placeholder behavior.
- Included both the source `Plan 13.2.xx.md` and optimized implementation roadmap. Added a repeatable standard-library benchmark for generation, scheduled updates, and radio queries.

## Not claimed in this release

The full 461-vessel source fleet, Phase B map, weather grid, complete ambient-radio dispatcher, full MAYDAY/assist system, long-term trust decay/gossip, career-save integration/migration, and unified Coast Guard tow/AI identity remain future roadmap milestones. The existing game has not been visually launched because Pygame is unavailable in the build environment.
