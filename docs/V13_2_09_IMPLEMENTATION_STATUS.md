# v13.2.09 Implementation Status

**Baseline:** v13.2.08
**Roadmap slices:** M6 social-policy foundation; M7 weather performance; M11 continued Phase A balancing

## Delivered

- `RelationshipDynamics` is integrated into `Game` and advances on coarse traffic ticks rather than every rendered frame.
- Trust decay returns both positive and negative trust toward neutral. Independent relationships decay at 0.01 per in-game day; corporate catcher, corporate longliner and mothership relationships decay at 0.02 per in-game day. A recent contact protects the time before that contact from decay.
- Gossip personalities among independent longliners/gillnetters can relay a small fraction (20%) of a detected trust change to up to two nearby independent contacts inside 30 NM. Each potential relay has a 45% deterministic chance, selected with a stable per-event seed. The change is one-hop only, uses the spatial index, and updates rival status.
- Social last-seen trust, sim-time baseline and counters are added to the career save. Snapshot-time processing flushes pending external trust changes before saving. Validation rejects mismatched traffic trust/baseline pairs. Older payloads without the optional section initialize a baseline without replaying existing contacts.
- Weather grid now stores a cached row-major seven-field tuple for each cell and maintains it during grid ticks, local observation and restore. The update kernel uses flat neighbor indices and inline bilinear interpolation/noise to reduce allocations and dictionary lookups.
- A seeded 50-simulation-second weather snapshot matches v13.2.08 exactly, providing a regression guard against unintended numeric behavior changes.
- All Markdown files remain directly under `/docs`.

## Performance

100 measured weather ticks after five warm-up ticks on the current build host:

- Grid: 23 x 18 = 414 cells, 20 NM cells
- Tick mean: 1.9268 ms (target <= 2.0 ms mean: met on this host)
- Tick median: 1.8815 ms
- Tick p95: 2.1475 ms (above 2.0 ms)
- 72-hour forecast: 0.7425 s
- Snapshot: 51,191 bytes (measured at benchmark end; byte size depends on values/float formatting)

Compared with v13.2.08 recorded mean tick 2.891 ms and forecast 1.0103 s, this is approximately a 33% lower mean tick and 27% lower forecast duration. Benchmarks are local and not hardware-independent.

## Validation

- New relationship + weather regression modules: 31 tests passed.
- Broader release regression results are in `TEST_RESULTS_V13_2_09.txt`.
- Python compilation passed.
- Archive integrity, Markdown placement and link audit are recorded in the release test report.
- Pygame is unavailable here; no graphical/live playtest was performed.

## Still outstanding

- Pygame-enabled save/load round-trip and visual UX verification.
- Longer Phase A playtest to tune rumor range/probability/trust decay and ambient radio cadence.
- Full Phase B fleet/map expansion.
- Full social reputation propagation, more radio templates, and integration of regional weather into additional market/tow effects.
