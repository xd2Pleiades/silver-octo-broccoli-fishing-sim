# Phase 6 gear mechanics — v13.1.20

This release implements the Roadmap V2 Phase 6 hauler/roller loop in the modular V13 codebase.

## Hauler load and drive

`Longline._line_load()` combines deployed hook load, current sea state/hull tilt, vessel speed during setting, and landed-candidate/fight tension during hauling. `calculate_hauler_slip()` uses line load, diesel output, the number of hands actually working the hauler, and friction-drum condition. Slip eases toward the requested state, reduces the available hauling pull, and degrades the drum while sustained above its slip threshold. Low slip allows gradual drum recovery.

## Stern roller

The roller state is `working`, `bypassed`, or `jammed`. A working roller reduces line wear but itself wears under load and sea conditions. Prolonged high load can jam a worn roller. Bypassing or a jam increases line chafe and snag frequency. Snags temporarily stop the set/haul operation; persistent wear under high load can part the line and expose unharnessed crew at the stern to whipping-line injuries.

## Player feedback and controls

`M` toggles roller bypass when the roller is operable. If it is jammed, a healthy crew member must first be on the main deck and within the stern service radius; then `M` clears the jam. The physical roller tint and status text communicate state, while the drum tint/percentage indicate slip. `Y` remains the harness trade-off for rail/hauler workers.

## Model boundaries

Wear, snag and slip coefficients are first-pass game tuning, not a marine engineering simulator. Pygame wasn't installed during this build, so desktop playtesting must verify how often the roller jams, how visible the tint is at different zoom values, and whether the slip/line-part rates feel fair.
