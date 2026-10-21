# V13V1-11 — Auto-fishing hunts detected water; speech bubble cleanup

## Implemented

- **Auto-fishing now hunts detected hotspots.** With `L` enabled, a confident main-deck lookout contact can become the ship's next destination instead of always heading to the generic grounds.
- **Detection gates are explicit.** A school must be live, stronger than `0.40`, and detected with confidence greater than `0.70`. Selection favors the best confidence/strength combination rather than blindly using the first sailor in the list.
- **Dead reckoning still matters.** Auto-fishing plots the target using the current navigation position error. The ship follows the existing destination/autopilot path; it is not teleported to the true hotspot.
- **Fallback and stale-target handling.** With no suitable detection, the existing fishing-grounds destination remains in use. If a target expires or weakens while underway, auto-fishing reselects another credible contact or falls back to the general grounds. It will not start setting far away just because a destination was cleared mid-route.
- **Speech bubbles now prioritize dialogue.** Actual crew speech, commands, urgent spoken warnings, and named conversation turns remain visible. Action narration and operational/context notices—such as catch/stowing summaries, headcount totals, navigation status, machinery status, auction instructions, and route-state feedback—continue to be recorded in the Ship's Notebook crew log but no longer automatically appear as speech from the selected sailor. Radio traffic keeps its separate radio bubble.
- **Updated roadmap and tests.** Added headless coverage for hotspot selection thresholds, dead-reckoning offset, stale/weak-target handling, fallback behavior, and spoken-vs-context message routing.

## Verification

```powershell
python -m compileall -q fishing_sim run_fishing_sim.py
python -m unittest discover -s fishing_sim/tests -v
```

**239 automated tests pass** and Python compilation passes. Pygame is unavailable in the build environment, so the new route transitions, live bubble density, and click/steering behavior still require a graphical playtest.

## Next milestone

`v13v1-12` is the optional fishing-log gut book. Integration, balance, and release hardening remain `v13v1-13`.
