# Fishing Simulator v13.1.32 — Coast Guard Tow Escort

## Added

- Separate `TowEscort` entity spawned when Coast Guard accepts a tow request. Each launch has a callsign, captain identity/personality, skill, independent four-person roster, fuel/patience state, location, and reported plot.
- Chart presence for the tug using the existing ship-marker language with Coast Guard orange colours, callsign label, report age, staleness marker (`?`), and towline connection.
- Regular radio check-ins every 30 in-game minutes, personality-based unscheduled transmissions, weather/line-strain warnings, and final arrival dialogue.
- Player radio topics: `F4` asks for the escort's position after the tow is accepted; `G` cycles ETA, weather, traffic, fishing, fuel, crew, captain name, fee, and whether they will stay.
- Tow-escort information in the chart side panel and persistent HUD strip, including stale report indication.
- Marker remains for 30 in-game minutes after arrival before the Coast Guard signs off and disappears.
- Headless regression tests for escort data, chart-report staleness, reported-position error, dashed towline geometry, and communication wiring.

## Changed

- High sea state (normalized `World.sea_state >= 0.72`) marks the towline at risk and changes it to dashed; tow speed is reduced while that risk remains active.
- Coast Guard reports require the player's radio station to be staffed and can be missed due to reception quality; missing check-ins ages the chart contact rather than updating it silently.
- Updated in-game and Markdown controls; updated app caption and session version to v13.1.32.

## Not yet implemented

- Physical line parting/reconnection, emergency departure when Coast Guard fuel is low, player correction of the captain's plot, full `ALONGSIDE` / raft recovery logic, persistent save/load for escort state, and an exterior second-ship model in the deck view. The tow vessel is shown on the navigation chart, using the same marker style recolored.
- Full PAN-PAN/MAYDAY conversation model in `TOW_REQUEST_AND_DISTRESS_RADIO.md` remains a broader proposed system.

## Verification

- `python -m compileall -q fishing_sim`: passed.
- Targeted regression run across tow/anchor/HUD/legacy radio tests plus v13.1.32 escort tests: **51 tests passed**.
- The complete test discovery run exceeded the 120-second command limit while running unrelated legacy tests; the process was terminated by the tool timeout, with no failure reported before timeout.
- No graphical Pygame playtest was performed in this environment.
