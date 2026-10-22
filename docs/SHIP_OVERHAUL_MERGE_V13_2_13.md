# Ship overhaul integration — v13.2.13 working merge

## Lineage

This working build uses `v13.2.13` as its systems base and integrates the ship redesign from `v13.2.02_ship_redesign`. It is a compatibility merge, not a claim that the older prototype branch contains the current rescue/radio/career systems. The package and career-envelope version markers remain `13.2.13`; this is not a formal version bump.

## Integrated ship changes

- Increased the player hull from `1100 × 280` to `1650 × 420` deck units so aisles, ladder wells and bunks are proportioned for the crew.
- Replaced the single lower-deck centre passage with aft stores, engine room, ice hold, crew cabin and forepeak compartments. Solid athwartships bulkheads separate the engine room from the ice hold and the ice hold from the crew cabin; watertight door gaps connect the aft stores and forepeak to their neighboring spaces.
- Added independent engine, hold and crew-companionway access. The new crew stair is aft of the wheelhouse and routes directly into the cabin.
- Moved the engine to port with a walkable ladder-side aisle; added the auxiliary generator, switchboard gauges, two insulated ice pens, aft stores racks, six full-size bunks and unique berth approach points.
- Restored the detailed hull/deck artwork, freeing ports, timber rail cap and plank joints, hatch and ladder wells, cutting table/drain, hose reel, lifeboat/davits, hauler base, wheelhouse steps and screen-space-stacked lower-deck labels.
- Restored the engineer's short-range on-watch hysteresis and the blanket drawn over a sleeping bunk occupant.

## Preserved from the newer systems base

The merge keeps the current `Game`/`World` implementations and their rescue mission manager, career save/load, selectable ship radio, Phase A/B traffic and weather, sea-foam/hull-wave interaction, compartment flooding and bilge systems. Current water effects and flooding visuals remain in `Ship.update_water()` / `Ship.draw_water()`; the older branch's geometry and art were merged around them rather than replacing the newer systems wholesale.

## Post-merge startup crash fix — 2026-10-22

The first merged package crashed during `Ship()` initialization in `_build_art()` with `TypeError: Ship._inset_poly() takes 2 positional arguments but 3 were given`. Three geometry helper functions (`_inset_poly`, `_clip_x`, and `_spans`) were defined without `self` but were not decorated as static methods. Calling them through `self` passed an unintended instance argument.

The hotfix adds `@staticmethod` to all three helpers and adds a source-contract regression test to check those decorators.

## Validation and remaining check

- After the hotfix, the bounded ship/layout/pathfinding/release/rescue regression selection passed **45 tests**, with **1 Pygame-dependent test skipped** and **3 subtests passed**.
- `game.py` Python compilation passed.
- The dependency-free documentation/release checks passed when run without pytest's cache provider. A pytest-created `.pytest_cache/README.md` briefly tripped the doc-placement audit in an earlier run; it was a generated test artifact and was removed before the clean rerun.
- A real graphical startup/playtest could not be run in this environment because Pygame is not installed. Please install the project's dependencies and launch `run_fishing_sim.py` to verify runtime behavior on the target machine.

The v13.1.21 and v13.1.23 roadmap descriptions of a continuous centre passage are historical design notes; the merged working build uses the compartmentalized plan above.
