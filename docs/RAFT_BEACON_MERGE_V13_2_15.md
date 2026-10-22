# v13.2.15 archive merge — M9 survivor and raft-beacon integration

## Merge policy

The supplied `fishing_sim_v13.2.15.zip` was used as the base. The previous `fishing_sim_v13.2.13_ship_overhaul_raft_beacon.zip` source was not copied wholesale because its `core/game.py` lacked later Chapter A conversation and Chapter B motion hooks present in the newer base. Only the missing survivor-registry module, integration points, tests, and current documentation updates were merged.

## Functionality brought forward

- Stable survivor ledger keyed to the original distress vessel ID; no duplicate fleet or Coast Guard hull is created for a raft.
- One time-limited casualty for an injury incident and one two-person drifting liferaft for a taking-water incident.
- Weather-sensitive drift/survival and an idempotent assistance completion keyed by rescue mission ID.
- Physical raft pickup only within 2 NM; a completed ship-assistance job beyond that range leaves the raft adrift.
- Staffed-wireless beacon reception within 55 NM, attempted at 90-s intervals, with deterministic 0.25–0.95 NM position error; chart plots turn stale after 180 s without refresh.
- Phase A and Phase B navigation charts display only the reported fix plus an uncertainty ring; the close-range sea view draws the physical raft separately.
- Optional validated career-save section stores survivor and beacon state and permits legacy saves without the new section.
- Phase switching is blocked while survivor targets remain active.

## Preserved from the newer base

- Ship compartment overhaul and the `_inset_poly` / related geometry helper static-method fix.
- Chapter A crew conversation director and scripts.
- Chapter B sailor-motion/bracing, smoothed roll-rate tracking, and associated tests.
- Existing AI rescue response, player physical rescue route, career save/load, radio UI, phase-specific traffic/weather, and the rest of the supplied project files.

## Integration note

Radio language refers to the "current chart reference" rather than always naming Hakodate as the origin; this avoids describing Phase B coordinates in the regional Phase A reference frame.

The input archive is named `v13.2.15.zip`, but `fishing_sim/__init__.py` and the career save-envelope builder still declare `13.2.13`. Those internal version declarations are retained rather than changed as part of a feature merge. A formal version bump should update code, save envelope, release gate, changelog, and tests together.

## Verification

- Survivor registry/beacon unit tests: **12 passed**.
- Focused project runner: **319/319 passed**, zero skips, across six shards.
- Cross-subsystem selection (Chapter A conversations, Chapter B motion, AI/player rescue, ship overhaul, career save/load and release-hardening): **163 tests run, 15 skipped because they require Pygame; no failures**.
- Dependency-free release gate: **PASS**; 118 Markdown files and 32 local links checked; Python compilation passed.
- Final ZIP validation: **PASS** (CRC/integrity clean, required source/docs/tests present, release gate passes against the actual archive).

Pygame-backed live visual QA is not available in this headless environment and must not be considered complete.
