# Fishing Simulator 13.1.23 — lower-deck layout, rescue, and ocean navigation refit

## Ship interior

- Reordered the lower-deck spaces from stern to bow as **aft stores → engine room → ice hold → crew cabin → forepeak**.
- Put the engine access hatch directly over the aft engine bay, kept the two fish-hold hatches amidships, and retained one continuous centreline passage through the spaces.
- Kept all six bunks in paired side rows with clear aisle approaches.
- Reworked the engine inspection gauges into a compact horizontal bank on the opposite side of the passage from the machinery casing. This keeps the walkway visually open and avoids stacking gauges across it.

## Rescue behavior

- If a storm makes the rescue boat unavailable, the captain begins a come-about immediately while the ship's headway bleeds away, then approaches slowly to present the starboard side to the swimmer. It no longer simply waits at high speed with the bow facing away.
- Reduced rescue-boat assembly, launch, pickup, and return delays and raised boat speed, while retaining a sea-state penalty.

## Ocean-space navigation

- Right-click visible water for a **quick steer-to** order; it creates a temporary bearing mark, not a committed route.
- Hold **Shift** and right-drag **A → B** to commit a persistent plotted leg. Shift-drag an existing waypoint to reposition it; right-click a waypoint to delete it; `Esc` clears an active course.
- Ocean plotting is restricted to the working-deck view in daylight and reasonably clear weather. The click target is limited to nearby visible water (about 0.4 nautical mile maximum); use the chart for night, fog, heavy rain, or longer distances.
- The chart and ocean view share the same route-waypoint model. Route geometry, bearing, distance, ETA, cross-track error, a live preview, a predicted turn arc, and an overshoot hint are displayed where relevant. Near-edge targets can extend the leg past the viewport without allowing unlimited range.
- A plotted line is a **desired track**, not a rail. Track correction follows the crew's estimated position; wind/current drift, finite rudder rate, speed-dependent steering, propeller reversal delay, momentum, and astern prop walk keep actual motion imperfect.
- Engine orders are shown as stop/slow/half/full ahead or astern/reversing rather than a throttle percentage. A plotted leg finishes at slow ahead and holds the heading for further orders. Plot and steer-to orders are recorded in the Ship's Notebook; without a competent person at the helm, the order waits rather than executing itself.

## Validation

- Added deterministic unit tests for leg geometry, bearing/ETA, cross-track error, visibility gates, turn/rudder helpers, ocean plot input, rescue pacing, and lower-deck layout.
- See `docs/V13_1_23_NAVIGATION_REFIT.md` for controls and implementation details.
- A graphical playtest is still recommended. Pygame is not installed in the build environment, so this release could not be visually launched here.
