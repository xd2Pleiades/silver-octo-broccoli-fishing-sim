# Visual QA Checklist — v13.2.12

**Status:** Not executed in this environment; Pygame is not installed. This file is a checklist, not evidence of a passed visual test.

## Reference setup

- Install the project's declared requirements in a Pygame-capable environment.
- Use a fixed seed and fresh profile for the first run; repeat key cases after loading an existing career.
- Record display resolution, OS, Python version, Pygame version, simulation speed and current campaign phase.

## Phase A chart and world

- [ ] Open/close the chart using `C`; ensure the HUD and anchor controls remain clickable.
- [ ] Verify `A / REGIONAL` selection, known-contact labels, stale `?` labels, and click hitboxes.
- [ ] Stage, insert, move, delete, commit and cancel a route; verify waypoint conversion and helm behavior.
- [ ] Compare chart contact positions with the last received report; verify no hidden true position is shown.
- [ ] Observe the sea view under clear, rainy and foggy weather; visual range must respect visibility.

## Phase B chart and traffic

- [ ] Switch with `B / HIGH SEAS`; check projection, graticule, operating-box outline and approximate-chart label.
- [ ] Plot routes near both longitude bounds and across the date line; verify no abrupt coordinate jump.
- [ ] Select a reported contact and press `R`; verify only an in-range contact opens radio.
- [ ] Confirm Phase A/B changes do not duplicate the Coast Guard hull or move its shared identity.

## Radio and emergency priority

- [ ] Open radio using the RADIO button and `Ctrl+F11`; select ships and try all topics.
- [ ] Advance multi-turn dialogue with the button and Enter/Space; confirm transcript timestamps appear as lines are revealed.
- [ ] Confirm out-of-range and unmanned-radio states are legible and do not claim a reply.
- [ ] Trigger a MAYDAY during routine dialogue; the emergency interrupts, and the unheard remainder is not falsely logged as heard.
- [ ] Test ASSIST and IGNORE; each decision applies only once and survives save/load.

## Save/load and rescue

- [ ] Save/load while docked, underway, hauling, the radio panel is open, the Coast Guard is en route, and under tow.
- [ ] Save/load during hull flooding and while the man-overboard/rescue launch is active.
- [ ] Corrupt the main save and confirm recovery from the last-good backup; verify unknown schema versions fail safely.
- [ ] Compare known contacts, trust, reported positions, distress decisions, weather snapshots and tow identity before/after load.

## Performance and acceptance

- [ ] Capture p50/p95 update time, active entity count, weather tick and radio candidate query on reference hardware.
- [ ] Repeat a seven-day simulation and compare snapshot size and deterministic outputs.
- [ ] Ensure normal play stays interactive; no hitch when switching phases or opening chart/radio UI.
- [ ] Attach screenshots and raw metrics to the release issue before checking off any item above.


## M9 survivor transfer and raft beacon QA (merged with v13.2.15 input)

- [ ] Trigger an injury MAYDAY; recover once before the 360-s casualty timer expires and confirm duplicate completion cannot count the casualty twice.
- [ ] Trigger a taking-water MAYDAY; confirm one stable two-person raft is deployed without adding an AIShip or Coast Guard hull.
- [ ] Recover the raft within 2 NM; repeat assistance outside 2 NM and confirm the raft remains afloat rather than teleporting aboard.
- [ ] With the wireless staffed and a raft within 55 NM, confirm a beacon event and chart plot; unstaff the watch and confirm no new fix is received.
- [ ] Confirm the Phase A and Phase B charts draw an amber diamond/ring from the noisy report, not the raft's true physical position.
- [ ] Leave the raft out of radio range for 180 s; verify the last fix stays in place and gains the stale `?`; return in range for a new beacon and refreshed plot.
- [ ] Save/load with a live raft and again with a stale beacon; verify physical drift/survival, stable IDs, report time, sequence and error radius persist.
- [ ] Confirm campaign-phase switching is blocked while a casualty or raft remains active and becomes available after all survivors are recovered/lost.
- [ ] Run the same flows during a storm and compare raft survival drain and beacon/plot updates.

## Player-directed Coast Guard routing (v13.2.15)

- [ ] With wireless staffed, select a received MAYDAY contact and verify the radio UI enables **ROUTE CG TO MAYDAY** / `G` only when an eligible patrol is available.
- [ ] Dispatch the patrol and confirm its stable identity remains the same across sea view, chart, radio, and traffic contact list; no duplicate Coast Guard hull/marker appears.
- [ ] Verify the patrol follows the *reported* distress/raft coordinate, turns at a finite rate, and does not teleport to the target.
- [ ] Verify on-scene approach slows sufficiently to avoid orbiting past a distressed vessel; assistance completes only after physical proximity and timed work.
- [ ] Select a contact with a received liferaft beacon and verify **ROUTE CG TO RAFT** / `L` uses the reported fix, not the hidden physical raft position.
- [ ] Refresh a beacon while the patrol is on scene and verify it re-plots to the newer reported fix; verify an old plot is labelled stale.
- [ ] Save/load while en route and on scene; verify route state, responder identity/heading/overrides, and survivor registry remain consistent.
- [ ] Try routing while player rescue or autonomous response is active and verify duplicate dispatch is blocked with a clear radio status.

