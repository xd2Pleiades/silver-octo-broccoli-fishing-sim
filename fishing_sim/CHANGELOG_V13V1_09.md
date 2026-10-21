# Fishing Simulator — V13V1-09 Position Fixes

## Summary

Implements the next V13 roadmap milestone after the broadcast-conversation release. All position-fix interactions occur while the navigation chart is open, keeping chart tools isolated from helm and crew commands.

## Implemented

- Added four chart-keyed actions: **1 Landmark**, **2 Sextant**, **3 RDF**, and **4 Echo Sounder**. The chart-side POSITION FIXES panel summarizes current availability and the footer lists each control.
- Landmark bearing selects the nearest named landmark currently within weather-limited visibility and requires a sailor aboard on the main deck. Positional uncertainty grows with landmark distance and sea state and shrinks with observer skill.
- Sextant observations require the dawn/noon/dusk windows, cloud no greater than 0.70, an on-deck observer, and skill of at least 0.40. Better skill yields a tighter fix.
- RDF requires a working, staffed radio set; the assigned operator must be at the set, skill must be at least 0.40, and the ship must be within 3,200 chart units of the coastal station. The uncertainty is elongated along the bearing line.
- Echo-sounder checks compare the current sounder reading with a stable charted-depth field that preserves the plan's ±7% old-survey noise. The comparison tolerance is 4 m. A mismatch is recorded and displayed but applies no position correction; only a valid match is allowed to reset belief.
- Approximate fixes change only `believed_pos`, fix metadata, bias state, and displayed uncertainty. `ship_pos` remains physical truth and the hidden true error vector is never printed or drawn.
- Added per-method cooldowns (landmark 15 s, sextant 45 s, RDF 30 s, sounder 15 s) to make repeated readings less exploitable. Unavailable conditions do not consume a cooldown.
- Every completed fix and echo-sounder mismatch is recorded in the Ship's Notebook crew log; outcome text remains visible in the chart status line.

## Controls

Open the chart with **C**, then press **1** for a landmark bearing, **2** for a sextant fix, **3** for RDF, or **4** for the echo sounder. Press **C** to close the chart. **Esc** clears the staged course; route editing controls remain otherwise unchanged.

## Deliberately not claimed

- No live radio direction-finding service or real meteorological signal is added; RDF is an in-game navigation mechanic using existing radio staffing.
- Approximate fixes are noisy measurements, not perfect teleportation to true coordinates.
- A sounder mismatch is diagnostic only: it does not infer a correction vector or zero navigation doubt.
- No live Pygame graphical playtest was possible in this environment.

## Verification

- **212 automated tests passed** with `python -m unittest discover -s fishing_sim/tests -v`.
- Python compilation passed with `python -m compileall -q fishing_sim run_fishing_sim.py`.
- 18 new focused tests cover conditions, measurement quality, RDF uncertainty shape, survey noise, mismatch behavior, key integration, fix logging, and preservation of physical ship truth.
- A fresh-extraction ZIP validation is performed as part of release packaging.
