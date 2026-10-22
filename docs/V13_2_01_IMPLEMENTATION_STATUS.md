# v13.2.01 Implementation Status

**Release type:** first world/traffic/radio foundation slice built on v13.1.34.
**Source design:** [`Plan 13.2.xx.md`](Plan%2013.2.xx.md) and [`Roadmap_V13_2_Optimized.md`](Roadmap_V13_2_Optimized.md).

## Implemented

- Stable, process-independent seed and vessel ID utilities. Chunk seed is compatible with the supplied `<qqq` CRC32 contract.
- Equirectangular local projections (Hakodate Phase A and 160°E/45°N high-seas reference), date-line wrapping, distance and bearing helpers.
- Deterministic, schedule-driven 23-vessel regional Phase A pool across independent longliners/gillnetters, corporate catchers/longliners, mothership, Coast Guard and Soviet traffic. Names and schedules are stable for the same world seed.
- Separate physical and reported positions. Sightings and answered radio hails update the plot; charts show the last report and mark it stale rather than revealing current physical truth.
- Sparse 20-NM spatial index, deterministic query order, 12-NM active ring, 40-NM warm ring, nearest-first cap of 30 active ships.
- Low-frequency traffic updates every 3 simulation seconds; fast-forward samples schedules directly instead of replaying every missed tick.
- Phase A active vessel silhouettes in the sea view, limited by the current weather visibility, and known-contact markers on the chart. Current Coast Guard patrol traffic is an AI contact; the existing rescue/tow escort remains its own existing gameplay service until the roadmap's identity-unification milestone.
- `Ctrl+F11` routine ship-to-ship hail. Plain `F11` remains fullscreen. The call checks eligible listeners in range; one silent listener does not prevent a later listener from answering. The existing broadcast/Notebook path owns reply timing/display/logging.
- Initial intent policy separates independent peer exchange, competitive grounds misdirection, corporate refusal, official safety, weather warning, and hostile/Soviet replies. Radio replies update contact count, trust, and reported positions.
- Versioned JSON contact snapshots for identity, trust, contact counts, reported plot, mayday flags and activity overrides.

## Explicitly deferred

- Full source fleet of 461 vessels and Phase B 160°E–175°W high-seas contents. The Phase A runtime pool is deliberately 23 ships until density/frame-time profiling exists.
- Complete `weather_grid.py`, forecast snapshot/advection, and weather-cell influence on every vessel. The first radio slice uses the existing local game weather.
- Background ambient chatter/overheard corporate control traffic without player input; a complete intent eligibility/weighted-selection system; radio watch clock and full priority interruption/MAYDAY dispatcher.
- Social-trust decay, gossip propagation, save migration into the existing career-save system, and the full persistent contacted-vessel list across game saves. The new persistence module is a tested helper, not yet wired into a unified game save file.
- AI navigation collision avoidance, full Phase A map expansion, treaty-line events, AI vessel distress/rescue, and unifying the existing tow escort identity with a world traffic vessel.

## Controls

- `Ctrl+F11`: transmit a routine fleet hail; the radio station must be staffed and free. A call can receive silence.
- `F11`: fullscreen.
- `C`: chart; only known/reporting contacts are marked, with staleness indicated.

## Verification

The release's dependency-free foundation tests cover stable cross-process generation, coordinate conversion and date-line handling, seasonal activity, fleet totals, fast-forward behavior, spatial index/LOD caps, sparse chart contacts, radio-range gating, silent-listener fall-through, contact snapshot round-trip and radio intent policy. Source-contract regression suites cover prior crew, trip, tow-launch and tow-persistence behavior. The standard-library micro-benchmark measured about 0.0493 ms per scheduled update of 23 vessels, 22.78 µs per radio-candidate query and 0.504 ms mean fleet generation on the build host (`tools/benchmark_v13_2_01_world.py`); these figures do not extrapolate to the full 461-vessel population.

Pygame is not installed in the build environment, so compilation and headless/source-level regressions were run, but no live graphical playtest was possible. Full-fleet performance and game-save migration remain unverified.
