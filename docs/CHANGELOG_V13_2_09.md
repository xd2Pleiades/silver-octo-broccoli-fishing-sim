# Fishing Simulator v13.2.09 Changelog

## M6 — Social policy and relationship dynamics

- Added deterministic trust decay that moves stale positive/negative relationships toward neutral, at 0.01 trust/day for independents and 0.02/day for corporate contacts.
- Added bounded, one-hop fleet gossip. A nearby independent vessel with the `gossip` personality can relay a small fraction of an observed relationship change to up to two nearby independent contacts.
- Gossip uses the shared spatial index and per-event stable seeds; it does not consume global random state or chain through further gossip in the same update.
- Rival flags update when trust changes across the independent-vessel threshold.
- Relationship baseline, update time and counters are stored in the career-save payload. Load validation checks baseline/traffic trust consistency so an old event cannot replay as new gossip. Older saves without this optional section remain supported.

## M7 — Regional weather performance

- Replaced hot-loop tuple-key reads with a flat row-major cell index and precomputed neighbor indices.
- Cached numeric cell tuples between ticks; local observations and restore update the cache explicitly.
- Inlined the shared bilinear advection and deterministic noise kernels in the hot loop, retaining the original field equations and deterministic output.
- Recorded mean weather tick improved from 2.891 ms (v13.2.08 report) to 1.9268 ms on the current build host (median 1.8815 ms, p95 2.1475 ms). The 72-hour forecast improved from 1.0103 s to 0.7425 s in the latest recorded benchmark. These are local measurements.

## Compatibility and packaging

- Bumped package/save envelope game-version metadata to 13.2.09; career payload schema remains version 1 because the new relationship section is optional and backward-compatible.
- Updated release-version regression contracts.
- Kept all Markdown documentation directly under `/docs`.

## Not completed in this release

- Full Phase B high-seas population/map expansion.
- Broader multi-hop reputation simulation, dialogue catalogue expansion and social-balance playtesting.
- Pygame visual QA or live Game-object save/load round-trip; Pygame is unavailable in the build environment.
