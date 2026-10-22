# Fishing Simulator 12v19 — Refined Persistent Sea Foam

## Improved
- Reworked foam drawing into an aqua halo, translucent transition layer, and irregular bright core for more depth against the sea.
- Added stable seed-based detail: broken foam seams, irregular edges, micro-froth flecks, bubbles, and ragged whitecap lips. Details do not randomly flicker from frame to frame.
- Older patches contract as they dissipate; spray remains thin and transient.
- Passed the existing weather wind-strength and direction values into the sea-foam simulation to vary drift between light wind and storms.
- Capped emissions after long frames without keeping a backlog of whole spawn events.

## Preserved
- The 240-patch default cap, persistent water/world coordinates, `WaveField`, water-overlay render path, ship physics, steering, weather behaviour, rescue systems, crew AI, fishing logic, auction logic, and HUD.
- `run_fishing_sim.py` and `DO_NOT_REMOVE_THIS_IN_THE_ZIP.md`.

## Verification
- 87 automated tests passed.
- `py_compile` passed for the main game, sea-foam system, and launcher.
- Pygame was unavailable in the build environment, so live graphical validation remains outstanding. Test stopped/cruising and turning conditions in calm and storm weather on Windows.
