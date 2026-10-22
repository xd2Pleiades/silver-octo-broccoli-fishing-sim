# v13.2.07 Implementation Status

**Milestone:** M10 — Versioned persistence and migration hardening (first integrated slice)
**Package version:** 13.2.07

## Delivered

- Global keybinds: `Ctrl+S` saves and `Ctrl+O` loads; the existing plain `O` speed-report action remains available.
- Save format: JSON (no pickle), format ID, schema version, game version, canonical SHA-256 payload checksum, 32 MiB size limit.
- Atomic same-directory temp write, fsync and replacement. Prior valid primary is preserved as `.bak`; corrupt primary can fall back to it.
- World/player navigation and time, hotspots/reports, hull state including flood compartments/hatches/slope, local/regional weather, sea-wave phase, deterministic traffic contacts and MAYDAY decision state. Traffic contact snapshots are correctly validated as mappings.
- Coast Guard escort and tow timers/target, crew and station ownership, longline hook/fight/gaff state, catch/inventory/table/deck items, radio UI histories, radio calls/pending calls, broadcast director active/pending turns and cursor/timers, radio instrument state and global random state.
- Bait stock/freshness/selection, hatch alternation, active man-overboard rescue boat and casualty references, lifeline holders, mid-ladder link/progress, muster targets/reports/unavailability, bucket-chain crew and slots, and live sighting timers. Object references are restored by sailor name or stable ship-link index.
- Preflight checks for required sections, weather and traffic snapshots, escort state, broadcast conversations, queue limits, finite values, unique roster names, rescue/muster/lifeline/ladder references, and random state. An unexpected restore exception attempts to roll back from a snapshot of the current voyage.
- Control reference, roadmap and source plan updated; all Markdown remains under `/docs`.

## Validation

The standalone save-envelope suite covers normal reads, checksum tampering, unknown schemas, invalid JSON, NaN rejection, atomic write and backup recovery. Static Game contracts cover global keys, full payload section presence, broadcast cursor/timers, validate-before-mutation, rollback, and final PRNG restore ordering. The current build's Game module cannot be imported/run in this environment because Pygame is not installed; therefore a genuine end-to-end runtime save/load is not claimed.

## Outstanding

1. Install Pygame in the target environment and test mid-haul save/load, mid-conversation save/load, mid-rescue-boat save/load, muster/bucket-chain restoration, storm/flooding restoration, mid-tow restore, and corrupt-main/backup load through the actual UI.
2. Add a genuine v13.1.34 save fixture only if an existing old-save artifact is supplied; that project version did not define a formal career-save format.
3. Measure long-campaign save size and serialization latency; archive/rotate old logs if growth exceeds target.
4. Increment save schema and add idempotent migration functions before changing a released save schema.
5. Test rollback against intentionally malformed but checksummed state sections in a Pygame-enabled environment.
