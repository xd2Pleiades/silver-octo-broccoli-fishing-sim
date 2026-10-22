# Fishing Simulator — V13V1-05

## Ship's Notebook, Radio Conversations, Seasonal Calendar, and Storm Market

**Built on:** `v13v1-04`  
**Status:** implemented; automated verification passed; graphical playtest still required.

### Added

- **Ship's Notebook (`F9`)** using the same sepia/chart-paper visual language as the navigation chart. It has four sections: Crew Log, Radio Log, Calendar, and Forecast. Use the visible `< PREV` / `NEXT >` controls, left/right arrows, mouse, or section tabs to navigate pages.
- **Crew log:** timestamped entries for crew dialogue, work and incident reports, orders, movement/station assignments, and weather/market events. Each entry includes simulated date and time, speaker, and a compact event kind. Histories are capped to 600 entries per log so long careers do not grow memory without limit.
- **Radio conversation transcripts:** the vessel's call, coast-station acknowledgement, individual report lines, and vessel read-back are rendered one turn at a time. Every visible turn is recorded to the Radio Log with date/time and sender. New calls queue behind the current exchange instead of replacing the radio bubble mid-conversation.
- **Calendar:** new campaigns begin on **1 April 1962**. The on-screen date and notebook share the existing simulation clock; a game day lasts the existing 600 simulated seconds.
- **Three-day radio weather outlook:** the F2 weather call now reports daily forecasts for the next three days. Forecasts include broad conditions, temperature range, wind, rain probability, sea-state estimate, and lead-time confidence. A given date produces a stable forecast so the radio and notebook remain consistent.
- **Seasonal coastal climate:** the current setting uses Hakodate / North Pacific as its climate analogue. Monthly normal temperatures and precipitation help shape weather and forecasts; the local weather-front transition model is nudged toward the date's outlook. This is deterministic simulated climatology, not a live forecast or a reconstruction of the actual weather in April 1962.
- **Storm-driven fish-market scarcity premium:** entering the storm regime raises the existing market index. The temporary premium is bounded, affects actual auction pricing through the same effective market index, and decays over roughly a few in-game days. Repeated storms cannot increase the premium indefinitely; fish quality grading remains a separate system.

### Implementation notes

- Added `fishing_sim/systems/almanac.py` for campaign dates, regional monthly climate baselines, stable daily forecast generation, and seasonal notes.
- Added `fishing_sim/systems/market_weather.py` for bounded storm-price surge and decay.
- The date strip is also visible in the HUD. The minimap stays removed and the hook-depth profile remains 20 px lower (`y=82`) from `v13v1-04`.
- The original V13 source plan (`docs/v13 Plans.md`) and previous changelogs are preserved in the project archive.

### Verification

- **148 automated tests passed** from the project root.
- Python compilation passed with `python -m compileall -q fishing_sim run_fishing_sim.py`.
- Fresh-extraction ZIP integrity and required launcher/preservation files are checked as a release gate.
- **Not verified:** live Pygame rendering and interactive playtest. Pygame is unavailable in this environment, so the notebook's visual readability, radio pacing, and actual perceived storm-price tuning still need a Windows playtest.

### Climate reference

The seasonal temperature baseline uses the Japan Meteorological Agency's climatological normals (1991–2020) and monthly Hakodate normals as a regional analogue:

- <https://www.data.jma.go.jp/stats/en/normal/normal.html>
- <https://ds.data.jma.go.jp/gmd/tcc/tcc/products/climate/climatview/graph_mkhtml_nrm.php?e=6&k=0&m=2&n=47430&r=1&s=3&y=2025>
