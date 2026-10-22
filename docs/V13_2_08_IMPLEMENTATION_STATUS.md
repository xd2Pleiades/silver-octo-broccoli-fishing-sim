# v13.2.08 Implementation Status — M11 Phase A Content and Balance

**Release:** Fishing Simulator v13.2.08
**Scope:** Next roadmap slice after v13.2.07; regional fleet and ship-radio balance

## Delivered

- Phase A fleet expanded to 40 deterministic scheduled vessels: 14 independent longliners, 8 independent gillnetters, 8 corporate catchers, 3 corporate longliners, 2 motherships, 2 Coast Guard vessels, and 3 Soviet trawlers. The full source-plan fleet of roughly 461 is not enabled.
- Ambient ship-to-ship radio conversations are generated on fixed simulation slots, not every frame. Content includes peer exchange/solo chatter, corporate coordination, routine traffic, weather/safety broadcasts, distant traffic and dockside market gossip.
- Ambient events are gated by radio staffing, channel occupancy, clarity, day/night, season and sea state. Busy/unmanned slots are consumed rather than queued, avoiding a backlog after a long conversation.
- Ambient source cooldowns, cadence and counters have versioned snapshot/restore and are included in career save/load.
- Direct selected-ship queries now have a per-vessel/per-topic cooldown of 45 in-game minutes (18.75 simulation seconds under the 600-simulation-second game day). A throttled attempt does not advance contact_attempts or consume the deterministic response stream; other topics remain available.
- Direct reply odds respond to archetype and time of day, with a modest peak-season bonus for corporate catcher/mothership traffic.
- First successful contact can add a Notebook hint about observable conventions without exposing hidden personality/trust or the truth of a report.
- Treaty-edge ambient traffic is only eligible when a Soviet vessel is close to the 45°N boundary and another ship is within mutual radio range. This branch is expected to remain dormant within current Phase A route bounds.
- Direct radio cooldown timestamps are saved in the career payload. The optional section is backward-compatible with existing v13.2.07 save envelopes, which do not contain `ship_radio_service`.
- All Markdown files are stored directly under `/docs`. Local Markdown links audited clean.

## Validation

- Focused regression suite: 164 tests run; 149 passed; 15 skipped; zero failures.
- `python -m compileall -q fishing_sim`: passed.
- ZIP archive integrity: checked during release packaging.
- Pygame visual playtest: not performed because Pygame is not installed in this environment.

## Performance notes

Traffic benchmark on the local build host for 40 Phase A vessels: 0.0935 ms mean scheduled update, 42.68 microseconds mean radio-candidate query, and 0.920 ms generation.

Weather-grid benchmark: 414 cells; tick mean 2.891 ms, median 2.8122 ms, p95 3.2291 ms; 72-hour forecast 1.0103 seconds; snapshot JSON 52,948 bytes. The roadmap's 2.0 ms mean tick budget is **not met**. Profile allocations and memory passes before expanding to Phase B.

## Still outstanding

- Full template coverage and balance/playtest for ambient traffic.
- Relationship trust decay, gossip propagation and wider social consequences.
- Full ~461-vessel roster and Phase B high-seas bounds.
- Weather tick optimization to the <=2 ms target and full simulation/Pygame profiling.
- A Pygame-enabled career save/load round trip, particularly during active distress, hauling and broadcast dialogue.
