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
