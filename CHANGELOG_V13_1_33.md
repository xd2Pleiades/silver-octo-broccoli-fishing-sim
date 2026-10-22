# Fishing Simulator v13.1.33 — Coast Guard Hull and Harbour Approach

## What changed

- **PLACE HOLDER SHIP:** the Coast Guard launch is now drawn as a physical hull in the gameplay water view. It reuses the player ship's hull outline as the placeholder reference and has a navy hull, pale deck, Coast Guard orange safety stripe, bridge/windows, and wake.
- The launch begins at the harbour and moves continuously toward an intercept position near the player. It no longer gets created in front of the disabled vessel when the tow ETA expires.
- The launch reaches the intercept point, broadcasts a handover/line-passing exchange, turns over a short alongside phase, and only then begins towing home.
- A visible physical towline is drawn from the fishing vessel's bow to the Coast Guard launch's stern. It becomes dashed in high sea state, matching the chart towline.
- Chart position remains based on the launch's reported plot, so the map does not reveal its exact live position.
- Direct callers to `tow_in()` cannot bypass the launch's visible approach by instantly creating a tug beside the player.
- F4/G conversations, regular check-ins, the earlier v13.1.31 tow-retry changes, and the v13.1.32 Coast Guard crew/callsign remain intact.

## Verification

- Added targeted regression checks for the placeholder ship draw path, towline draw path, harbour-origin approach/intercept, delayed handover, and prohibition on starting a tow while the escort is still en route.
- Headless source/state tests and Python compilation are run for this release.
- A live visual playtest requires Pygame, which is not installed in the build environment.
