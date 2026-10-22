# Changelog — v13.2.12

## M13 release-hardening slice

- Added `tools/release_gate_v13_2_12.py`, a dependency-free release audit for package version, source compilation, required release docs, Markdown placement, conflict markers, local Markdown links, and optional ZIP integrity/version checks.
- Added `tools/run_regression_shards_v13_2_12.py`, which executes tests in bounded fresh-process shards, records per-shard timing, and continues after a slow/timed-out shard instead of hiding later results.
- Added `tools/benchmark_v13_2_12_long_campaign.py` for fixed-seed Phase A/B subsystem stress runs. It records world generation, traffic update, radio candidate query, weather tick and snapshot serialization time/size across multiple in-game days. It explicitly does not claim to be a rendered-frame benchmark.
- Added a release hardening regression module for version/docs/release gate and one-day benchmark contracts.
- Added a Pygame visual QA checklist and updated milestone status. Visual checks are explicitly pending because Pygame is unavailable in this build environment.
- Preserved all prior game features and retained the rule that every Markdown file must live directly under `/docs`.

## Validation boundary

The release gate and dependency-free regression checks can be run here. No live graphical or interactive save/load test is reported as passed without Pygame. The actual rescue intercept/raft-pickup gameplay, fine-resolution Phase B weather decision, and old-save fixture remain open roadmap work.
