# v13.2.12 Implementation Status — M13 Release Hardening

## Delivered

- **Release gate:** `tools/release_gate_v13_2_12.py` checks that the package version is correct, the required release artifacts exist, every Markdown file is directly under `docs/`, local Markdown links resolve, no merge-conflict markers remain, Python source compiles, and the optional archive has valid CRCs and the correct version.
- **Sharded regression runner:** `tools/run_regression_shards_v13_2_12.py` runs tests in bounded child processes. It records the module list, time per shard, skips, failures, and timeouts; one slow shard no longer prevents later shards from executing.
- **Long-campaign subsystem benchmark:** `tools/benchmark_v13_2_12_long_campaign.py` runs a fixed-seed multi-day traffic/weather/radio-query loop and measures daily snapshot serialization and size. The output expressly excludes Pygame rendering and is not presented as a full-game FPS result.
- **Release contracts:** tests validate the release gate's version and documentation audits and exercise the one-day benchmark path.
- **Visual QA checklist:** `VISUAL_QA_CHECKLIST_V13_2_12.md` records the checks to run when Pygame is available.
- All Markdown files are stored directly under `/docs`.

## Not complete

- Pygame is not installed in the build environment. No graphical review of chart marker readability, route editing, radio panel behavior, water effects, or live save/load has been performed here.
- Full Phase B physical simulation (global current, global bathymetry and land collision/avoidance) remains open.
- The Phase B 20-NM weather field remains profiling-only; 80-NM coarse Phase B remains the default.
- M9 physical rescue vessel dispatch/interception, raft survival/pickup and full rescue outcome remain open.
- No authentic pre-v13.2.07 career-save file was supplied, so a real legacy save migration fixture is not fabricated.
- Full discovery previously exceeded the execution limit. The new sharded runner is the intended measurement path; its current run status is recorded in `TEST_RESULTS_V13_2_12.txt`.

## Controls / scripts

- Run the dependency-free release gate: `python tools/release_gate_v13_2_12.py --root .`
- Validate a packaged archive: `python tools/release_gate_v13_2_12.py --root . --archive fishing_sim_v13.2.12.zip`
- Run focused test shards: `python tools/run_regression_shards_v13_2_12.py --scope focused --timeout 30 --log docs/TEST_RESULTS_V13_2_12.txt`
- Run the full suite sharded (timeouts are reported honestly): `python tools/run_regression_shards_v13_2_12.py --scope full --timeout 30 --log docs/TEST_LOG_V13_2_12.txt`
- Benchmark one week: `python tools/benchmark_v13_2_12_long_campaign.py --days 7 --phase A --output docs/PERFORMANCE_V13_2_12.txt`
