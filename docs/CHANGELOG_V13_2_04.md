# Changelog — v13.2.04

Date: 2026-10-22

## Tow/rescue identity unification (M8 slice)

- Added a stable namespaced `vessel_id` to the active `TowEscort` launch (`coast_guard_launch:<callsign>`).
- Registered the active Coast Guard launch as a runtime `AIShip` in the shared `TrafficWorld`, exposing it to the spatial index, known-contact list, radio-range queries, and chart-contact renderer.
- The traffic world protects runtime escort position from scheduled-ship interpolation and keeps active rescue contacts promoted even when that exceeds the normal nearest-first LOD cap.
- Chart marker and radio UI selection now resolve to the same contact ID. The specialized `PLACE HOLDER SHIP` renderer remains the one visible sea-view hull; the generic traffic renderer skips it to avoid a duplicate ship.
- Radio topic replies from the Coast Guard are routed to the same `TowEscort` captain/crew, and broadcast transcript metadata includes the stable vessel ID.
- Critical-priority distress traffic closes an open modal radio panel and discards the unshown tail of a routine exchange; the broadcast director can also interrupt an active medium-priority tow conversation.
- Added versioned `TowEscort` JSON snapshot/restore APIs and persistence wrappers for en-route, alongside, under-tow, and arrived snapshots.
- Updated roadmap, controls, README and original plan implementation notes. All Markdown remains directly under `/docs`.

## Not yet included

- The snapshot API is not wired into the legacy career save/load migration. That remains M10.
- Complete MAYDAY sender/receiver orchestration, player rescue/ignore consequences, line-part/reconnection outcomes, and full-world rescue interactions remain M9.
- The regional weather grid still averages about 2.86 ms per fixed tick on the recorded build host, above its 2 ms target; continue profiling before Phase B expansion.

## Validation

- Python compileall: passed.
- Focused regression suite: 153 tests run, 138 passed and 15 skipped because they require Pygame runtime dependencies.
- ZIP integrity, Markdown placement, and local Markdown-link audit are checked for this release.
- No live graphical playtest was possible in the build environment because Pygame is unavailable.
